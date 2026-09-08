#!/usr/bin/env python3
"""
Agent Chat Room MCP Server
Allows multiple Claude Code agents to communicate with each other.
"""

import fcntl
import json
import logging
import os
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal

from mcp.server import MCPServer
from mcp.server.mcpserver import Context, Elicit, Resolve
from mcp.server.mcpserver.exceptions import ResourceError, ToolError
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from . import __version__

logger = logging.getLogger(__name__)

# Chat data directory - shared between all instances
CHAT_DIR = Path(os.environ.get("AGENT_CHAT_DIR", "/tmp/agent-chat-room"))
DEFAULT_ROOM = os.environ.get("AGENT_CHAT_ROOM", "default")

# An agent that hasn't been seen for this long is dropped from the roster.
STALE_AFTER_SECONDS = 300


# ---------------------------------------------------------------------------
# Wire models
# ---------------------------------------------------------------------------

Priority = Literal["urgent", "normal", "low"]
MessageKind = Literal["direct", "broadcast", "system"]


class Message(BaseModel):
    """One message in a room."""

    id: int = Field(description="Message ID, unique and increasing within the room.")
    from_agent: str = Field(description="Sender agent name, or SYSTEM for join/leave notices.")
    to_agent: str = Field(description="Recipient agent name, or 'all' for a broadcast.")
    content: str
    timestamp: str = Field(description="ISO-8601 timestamp of when the message was sent.")
    type: MessageKind
    expects_reply: bool = Field(
        default=False,
        description="False for acknowledgements, so the recipient knows not to answer.",
    )
    priority: Priority = "normal"


class AgentInfo(BaseModel):
    """One agent currently in a room."""

    name: str
    role: str = ""
    joined_at: str = Field(description="ISO-8601 timestamp of when the agent joined.")
    last_seen: float = Field(description="Unix timestamp of the agent's last activity.")


class RoomInfo(BaseModel):
    """One chat room."""

    name: str
    agent_count: int
    message_count: int
    is_default: bool


class JoinResult(BaseModel):
    agent_name: str
    room: str
    other_agents: list[str] = Field(description="Agents already in the room.")


class SendResult(BaseModel):
    message_id: int
    room: str
    to_agent: str
    type: MessageKind


class MessageBatch(BaseModel):
    room: str
    total_matching: int = Field(description="How many messages matched before `limit` was applied.")
    messages: list[Message] = Field(description="The most recent matching messages, oldest first.")


class AgentList(BaseModel):
    room: str
    agents: list[AgentInfo]


class LeaveResult(BaseModel):
    agent_name: str
    room: str


class ClearResult(BaseModel):
    room: str
    messages_deleted: int
    agents_removed: int


class RoomList(BaseModel):
    default_room: str
    rooms: list[RoomInfo]


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------


class ChatStore:
    """The on-disk chat rooms: one directory per room, two JSON files inside."""

    def __init__(self, chat_dir: Path, default_room: str) -> None:
        self.chat_dir = chat_dir
        self.default_room = default_room
        self.chat_dir.mkdir(parents=True, exist_ok=True)

    def room_name(self, room: str) -> str:
        return room or self.default_room

    def room_dir(self, room: str) -> Path:
        room_dir = self.chat_dir / self.room_name(room)
        room_dir.mkdir(parents=True, exist_ok=True)
        return room_dir

    @staticmethod
    def _read_json(filepath: Path, default: dict | list) -> dict | list:
        """Thread-safe JSON file reading."""
        if not filepath.exists():
            return default
        try:
            with open(filepath) as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_SH)
                content = f.read()
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                return json.loads(content) if content else default
        except (json.JSONDecodeError, OSError):
            logger.warning("Bozuk veya okunamayan dosya, varsayılana dönülüyor: %s", filepath)
            return default

    @staticmethod
    def _write_json(filepath: Path, data: dict | list) -> None:
        """Thread-safe JSON file writing."""
        with open(filepath, "w") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            json.dump(data, f, indent=2, ensure_ascii=False)
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    def agents(self, room: str) -> dict[str, dict]:
        raw = self._read_json(self.room_dir(room) / "agents.json", {})
        return raw if isinstance(raw, dict) else {}

    def save_agents(self, agents: dict[str, dict], room: str) -> None:
        self._write_json(self.room_dir(room) / "agents.json", agents)

    def messages(self, room: str) -> list[dict]:
        raw = self._read_json(self.room_dir(room) / "messages.json", [])
        return raw if isinstance(raw, list) else []

    def save_messages(self, messages: list[dict], room: str) -> None:
        self._write_json(self.room_dir(room) / "messages.json", messages)

    def touch(self, agent_name: str, room: str) -> None:
        """Record that an agent is still alive, if it is in the room."""
        if not agent_name:
            return
        agents = self.agents(room)
        if agent_name in agents:
            agents[agent_name]["last_seen"] = time.time()
            self.save_agents(agents, room)

    def append_message(self, room: str, **fields) -> dict:
        messages = self.messages(room)
        message = {"id": len(messages) + 1, "timestamp": datetime.now().isoformat(), **fields}
        messages.append(message)
        self.save_messages(messages, room)
        return message

    def live_agents(self, room: str) -> dict[str, dict]:
        """Agents seen recently enough to count as present, persisting the cleanup."""
        agents = self.agents(room)
        now = time.time()
        live = {
            name: info
            for name, info in agents.items()
            if now - info.get("last_seen", 0) < STALE_AFTER_SECONDS
        }
        if len(live) != len(agents):
            self.save_agents(live, room)
        return live

    def rooms(self) -> list[RoomInfo]:
        if not self.chat_dir.exists():
            return []
        return [
            RoomInfo(
                name=item.name,
                agent_count=len(self.live_agents(item.name)),
                message_count=len(self.messages(item.name)),
                is_default=item.name == self.default_room,
            )
            for item in sorted(self.chat_dir.iterdir())
            if item.is_dir()
        ]


def _to_message(raw: dict) -> Message:
    """Adapt a stored record to the wire model (stored keys are `from`/`to`)."""
    return Message(
        id=raw["id"],
        from_agent=raw["from"],
        to_agent=raw["to"],
        content=raw["content"],
        timestamp=raw["timestamp"],
        type=raw.get("type", "direct"),
        expects_reply=raw.get("expects_reply", False),
        priority=raw.get("priority", "normal"),
    )


# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------


@dataclass
class AppContext:
    store: ChatStore


# One store for the process. The lifespan hands it to tools; the resources reach
# it directly, because a resource with no URI template gets no Context.
_store = ChatStore(CHAT_DIR, DEFAULT_ROOM)


@asynccontextmanager
async def app_lifespan(server: MCPServer) -> AsyncIterator[AppContext]:
    yield AppContext(store=_store)


mcp = MCPServer("agent-chat", version=__version__, lifespan=app_lifespan)

RoomArg = Annotated[
    str,
    Field(description="Room name. Empty means the default room (AGENT_CHAT_ROOM, or 'default')."),
]

# Presence-tracking tools update the caller's `last_seen`, so they are not
# read-only in the strict sense the annotation means — hence read_only_hint=False
# on tools that only look like readers.
_PRESENCE_TOOL = ToolAnnotations(
    read_only_hint=False,
    destructive_hint=False,
    idempotent_hint=True,
    open_world_hint=False,
)
_READ_ONLY_TOOL = ToolAnnotations(read_only_hint=True, open_world_hint=False)


@mcp.tool(title="Odaya katıl", annotations=_PRESENCE_TOOL)
def join_room(
    agent_name: Annotated[
        str, Field(description="Unique name for this agent, e.g. 'backend', 'frontend'.")
    ],
    ctx: Context[AppContext],
    role: Annotated[
        str, Field(description="Optional role description, e.g. 'Backend API Developer'.")
    ] = "",
    room: RoomArg = "",
) -> JoinResult:
    """Join the chat room with a unique name."""
    store = ctx.request_context.lifespan_context.store
    agents = store.live_agents(room)

    agents[agent_name] = {
        "role": role,
        "joined_at": datetime.now().isoformat(),
        "last_seen": time.time(),
    }
    store.save_agents(agents, room)

    store.append_message(
        room,
        **{
            "from": "SYSTEM",
            "to": "all",
            "content": f"🟢 {agent_name} odaya katıldı" + (f" (Rol: {role})" if role else ""),
            "type": "system",
        },
    )

    return JoinResult(
        agent_name=agent_name,
        room=store.room_name(room),
        other_agents=[name for name in agents if name != agent_name],
    )


@mcp.tool(title="Mesaj gönder", annotations=_PRESENCE_TOOL)
def send_message(
    from_agent: Annotated[str, Field(description="Your agent name.")],
    content: Annotated[str, Field(description="Message content.")],
    ctx: Context[AppContext],
    to_agent: Annotated[
        str, Field(description="Target agent name, or 'all' to broadcast.")
    ] = "all",
    expects_reply: Annotated[
        bool,
        Field(
            description="Set False for acknowledgements and thanks, so the recipient does not "
            "answer and the agents do not loop forever."
        ),
    ] = True,
    priority: Priority = "normal",
    room: RoomArg = "",
) -> SendResult:
    """Send a message to other agents."""
    store = ctx.request_context.lifespan_context.store
    store.touch(from_agent, room)

    kind: MessageKind = "broadcast" if to_agent == "all" else "direct"
    message = store.append_message(
        room,
        **{
            "from": from_agent,
            "to": to_agent,
            "content": content,
            "type": kind,
            "expects_reply": expects_reply,
            "priority": priority,
        },
    )

    return SendResult(
        message_id=message["id"], room=store.room_name(room), to_agent=to_agent, type=kind
    )


@mcp.tool(title="Mesajları oku", annotations=_PRESENCE_TOOL)
def read_messages(
    agent_name: Annotated[
        str, Field(description="Your agent name, used to pick out messages meant for you.")
    ],
    ctx: Context[AppContext],
    since_id: Annotated[
        int, Field(ge=0, description="Only return messages after this ID. 0 means all.")
    ] = 0,
    unread_only: Annotated[
        bool, Field(description="Skip your own messages.")
    ] = True,
    limit: Annotated[
        int, Field(ge=0, description="Maximum messages to return. 0 means unlimited.")
    ] = 10,
    room: RoomArg = "",
) -> MessageBatch:
    """Read the messages addressed to you, newest last."""
    store = ctx.request_context.lifespan_context.store
    store.touch(agent_name, room)

    matching = [
        raw
        for raw in store.messages(room)
        if raw["id"] > since_id
        and not (unread_only and raw["from"] == agent_name)
        and (raw["to"] in ("all", agent_name) or raw.get("type") == "system")
    ]

    return _batch(store.room_name(room), matching, limit)


@mcp.tool(title="Tüm mesajları oku", annotations=_READ_ONLY_TOOL)
def read_all_messages(
    ctx: Context[AppContext],
    since_id: Annotated[
        int, Field(ge=0, description="Only return messages after this ID. 0 means all.")
    ] = 0,
    limit: Annotated[
        int, Field(ge=0, description="Maximum messages to return. 0 means unlimited.")
    ] = 15,
    room: RoomArg = "",
) -> MessageBatch:
    """Read every message in the room, regardless of recipient (manager/admin view)."""
    store = ctx.request_context.lifespan_context.store
    matching = [raw for raw in store.messages(room) if raw["id"] > since_id]
    return _batch(store.room_name(room), matching, limit)


def _batch(room: str, matching: list[dict], limit: int) -> MessageBatch:
    """Apply `limit` to the tail of the matches and adapt them to the wire model."""
    selected = matching[-limit:] if limit > 0 else matching
    return MessageBatch(
        room=room,
        total_matching=len(matching),
        messages=[_to_message(raw) for raw in selected],
    )


@mcp.tool(title="Agent'ları listele", annotations=_PRESENCE_TOOL)
def list_agents(
    ctx: Context[AppContext],
    agent_name: Annotated[
        str, Field(description="Your agent name, if you want your presence refreshed too.")
    ] = "",
    room: RoomArg = "",
) -> AgentList:
    """List the agents currently in the chat room."""
    store = ctx.request_context.lifespan_context.store
    store.touch(agent_name, room)
    agents = store.live_agents(room)

    return AgentList(
        room=store.room_name(room),
        agents=[
            AgentInfo(
                name=name,
                role=info.get("role", ""),
                joined_at=info.get("joined_at", ""),
                last_seen=info.get("last_seen", 0.0),
            )
            for name, info in agents.items()
        ],
    )


@mcp.tool(title="Odadan ayrıl", annotations=_PRESENCE_TOOL)
def leave_room(
    agent_name: Annotated[str, Field(description="Your agent name.")],
    ctx: Context[AppContext],
    room: RoomArg = "",
) -> LeaveResult:
    """Leave the chat room."""
    store = ctx.request_context.lifespan_context.store
    agents = store.agents(room)

    if agent_name not in agents:
        raise ToolError(f"'{agent_name}' zaten '{store.room_name(room)}' odasında değil.")

    del agents[agent_name]
    store.save_agents(agents, room)
    store.append_message(
        room,
        **{
            "from": "SYSTEM",
            "to": "all",
            "content": f"🔴 {agent_name} odadan ayrıldı",
            "type": "system",
        },
    )

    return LeaveResult(agent_name=agent_name, room=store.room_name(room))


class ClearConfirmation(BaseModel):
    """The user's answer to the clear-room question."""

    confirm: bool = Field(description="Delete every message and agent record in this room?")


async def confirm_clear(
    ctx: Context[AppContext],
    room: str = "",
) -> ClearConfirmation | Elicit[ClearConfirmation]:
    """Ask before wiping a room that still has anything in it."""
    store = ctx.request_context.lifespan_context.store
    message_count = len(store.messages(room))
    agent_count = len(store.agents(room))

    if message_count == 0 and agent_count == 0:
        return ClearConfirmation(confirm=True)  # nothing to lose, nothing to ask

    return Elicit(
        f"'{store.room_name(room)}' odasındaki {message_count} mesaj ve {agent_count} agent "
        "kaydı kalıcı olarak silinecek. Onaylıyor musun?",
        ClearConfirmation,
    )


@mcp.tool(
    title="Odayı temizle",
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=True,
        idempotent_hint=True,
        open_world_hint=False,
    ),
)
def clear_room(
    ctx: Context[AppContext],
    confirmation: Annotated[ClearConfirmation, Resolve(confirm_clear)],
    room: RoomArg = "",
) -> ClearResult:
    """Delete every message and agent record in the room. Asks the user first."""
    store = ctx.request_context.lifespan_context.store

    if not confirmation.confirm:
        raise ToolError("Temizleme iptal edildi; oda olduğu gibi bırakıldı.")

    message_count = len(store.messages(room))
    agent_count = len(store.agents(room))
    store.save_messages([], room)
    store.save_agents({}, room)

    logger.info("'%s' odası temizlendi", store.room_name(room))
    return ClearResult(
        room=store.room_name(room),
        messages_deleted=message_count,
        agents_removed=agent_count,
    )


@mcp.tool(title="Son mesaj ID'si", annotations=_PRESENCE_TOOL)
def get_last_message_id(
    ctx: Context[AppContext],
    agent_name: Annotated[
        str, Field(description="Your agent name, if you want your presence refreshed too.")
    ] = "",
    room: RoomArg = "",
) -> int:
    """Get the ID of the last message, for polling with read_messages(since_id=...)."""
    store = ctx.request_context.lifespan_context.store
    store.touch(agent_name, room)
    messages = store.messages(room)
    return messages[-1]["id"] if messages else 0


@mcp.tool(title="Odaları listele", annotations=_READ_ONLY_TOOL)
def list_rooms(ctx: Context[AppContext]) -> RoomList:
    """List all available chat rooms."""
    store = ctx.request_context.lifespan_context.store
    return RoomList(default_room=store.default_room, rooms=store.rooms())


# ---------------------------------------------------------------------------
# Resources & prompts
# ---------------------------------------------------------------------------


@mcp.resource(
    "chat://rooms",
    name="Sohbet odaları",
    description="Tüm odalar; her biri için agent ve mesaj sayısı.",
    mime_type="application/json",
)
def rooms_resource() -> str:
    return RoomList(default_room=_store.default_room, rooms=_store.rooms()).model_dump_json(indent=2)


@mcp.resource(
    "chat://rooms/{room}/messages",
    name="Oda geçmişi",
    description="Bir odadaki bütün mesajlar, eskiden yeniye.",
    mime_type="application/json",
)
def room_messages_resource(room: str) -> str:
    if not (_store.chat_dir / _store.room_name(room)).exists():
        raise ResourceError(f"'{room}' diye bir oda yok.")
    messages = [_to_message(raw) for raw in _store.messages(room)]
    return MessageBatch(
        room=_store.room_name(room), total_matching=len(messages), messages=messages
    ).model_dump_json(indent=2)


@mcp.prompt(title="Oda özeti")
def summarize_room(room: str = "") -> str:
    """Summarize what the agents in a room have been discussing."""
    label = room or DEFAULT_ROOM
    return (
        f"'{label}' odasının mesaj geçmişini `chat://rooms/{label}/messages` kaynağından oku ve özetle:\n"
        "- Odadaki agent'lar ve rolleri\n"
        "- Konuşulan ana konular, zaman sırasına göre\n"
        "- Verilen kararlar\n"
        "- Cevaplanmamış sorular (expects_reply=true olup yanıtsız kalanlar)\n"
        "- Sıradaki adımlar"
    )


if __name__ == "__main__":
    mcp.run()
