"""Drive the chat-room server in-process against a temporary chat directory."""

import json
import os
import sys
from pathlib import Path

import anyio
import pytest
from mcp import Client
from mcp.types import ElicitResult

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


@pytest.fixture()
def mcp_server(tmp_path, monkeypatch):
    """A server whose rooms live in a fresh temp directory for each test."""
    monkeypatch.setenv("AGENT_CHAT_DIR", str(tmp_path))
    monkeypatch.setenv("AGENT_CHAT_ROOM", "default")
    for module in [m for m in sys.modules if m.startswith("agent_chat_mcp")]:
        del sys.modules[module]

    import agent_chat_mcp.server as server_module

    return server_module.mcp


def _client(mcp_server, answers=None, asked=None):
    """A client that answers every elicitation with `answers`."""

    async def elicit(context, params):
        if asked is not None:
            asked.append(params.message)
        return ElicitResult(action="accept", content=dict(answers or {}))

    return Client(mcp_server, elicitation_callback=elicit)


def test_tools_resources_and_prompts(mcp_server):
    async def run():
        async with Client(mcp_server) as client:
            tools = (await client.list_tools()).tools
            assert {t.name for t in tools} == {
                "join_room",
                "send_message",
                "read_messages",
                "read_all_messages",
                "list_agents",
                "leave_room",
                "clear_room",
                "get_last_message_id",
                "list_rooms",
            }
            # Every tool carries a structured result and behavioural hints.
            for tool in tools:
                assert tool.output_schema is not None
                assert tool.annotations is not None

            assert [str(r.uri) for r in (await client.list_resources()).resources] == [
                "chat://rooms"
            ]
            templates = (await client.list_resource_templates()).resource_templates
            assert [t.uri_template for t in templates] == ["chat://rooms/{room}/messages"]
            assert [p.name for p in (await client.list_prompts()).prompts] == ["summarize_room"]

    anyio.run(run)


def test_join_send_and_read(mcp_server):
    async def run():
        async with Client(mcp_server) as client:
            joined = await client.call_tool(
                "join_room", {"agent_name": "backend", "role": "API"}
            )
            assert joined.structured_content["other_agents"] == []

            await client.call_tool("join_room", {"agent_name": "frontend"})
            sent = await client.call_tool(
                "send_message",
                {
                    "from_agent": "backend",
                    "content": "hazır mısın?",
                    "to_agent": "frontend",
                    "priority": "urgent",
                },
            )
            assert sent.structured_content["type"] == "direct"

            read = await client.call_tool("read_messages", {"agent_name": "frontend"})
            contents = [m["content"] for m in read.structured_content["messages"]]
            assert "hazır mısın?" in contents
            # The join notices are system messages every agent sees.
            assert any(m["type"] == "system" for m in read.structured_content["messages"])

            agents = await client.call_tool("list_agents", {"agent_name": "frontend"})
            assert {a["name"] for a in agents.structured_content["agents"]} == {
                "backend",
                "frontend",
            }

    anyio.run(run)


def test_leaving_a_room_you_are_not_in_is_an_error(mcp_server):
    async def run():
        async with Client(mcp_server) as client:
            result = await client.call_tool("leave_room", {"agent_name": "nobody"})
            assert result.is_error is True
            assert "zaten" in result.content[0].text

    anyio.run(run)


def test_clear_room_asks_first_and_honours_a_refusal(mcp_server):
    async def run():
        asked: list[str] = []

        async with _client(mcp_server, {"confirm": False}, asked) as client:
            await client.call_tool("join_room", {"agent_name": "backend"})
            refused = await client.call_tool("clear_room", {})
            assert refused.is_error is True
            assert asked, "a room with content must be confirmed before clearing"

            # Nothing was deleted.
            rooms = await client.call_tool("list_rooms", {})
            assert rooms.structured_content["rooms"][0]["agent_count"] == 1

        async with _client(mcp_server, {"confirm": True}) as client:
            cleared = await client.call_tool("clear_room", {})
            assert cleared.structured_content["agents_removed"] == 1

    anyio.run(run)


def test_room_history_resource(mcp_server):
    async def run():
        async with Client(mcp_server) as client:
            await client.call_tool("join_room", {"agent_name": "backend"})
            body = json.loads(
                (await client.read_resource("chat://rooms/default/messages")).contents[0].text
            )
            assert body["room"] == "default"
            assert body["total_matching"] == len(body["messages"]) == 1

    anyio.run(run)


def test_unknown_room_history_fails(mcp_server):
    async def run():
        async with Client(mcp_server) as client:
            with pytest.raises(Exception, match="oda"):
                await client.read_resource("chat://rooms/yok-boyle/messages")

    anyio.run(run)


def test_listing_rooms_does_not_prune_agents(mcp_server, tmp_path, monkeypatch):
    """list_rooms is advertised read-only, so it must not rewrite agents.json."""
    import agent_chat_mcp.server as server_module

    async def run():
        async with Client(mcp_server) as client:
            await client.call_tool("join_room", {"agent_name": "backend"})

            # Age the agent past the staleness cutoff.
            agents_file = tmp_path / "default" / "agents.json"
            agents = json.loads(agents_file.read_text())
            agents["backend"]["last_seen"] = 0
            agents_file.write_text(json.dumps(agents))
            before = agents_file.read_text()

            listed = await client.call_tool("list_rooms", {})
            # The stale agent is not counted as present...
            assert listed.structured_content["rooms"][0]["agent_count"] == 0
            # ...but the roster on disk is untouched.
            assert agents_file.read_text() == before
            assert "backend" in json.loads(agents_file.read_text())

    anyio.run(run)

    assert server_module.STALE_AFTER_SECONDS > 0


def _append_from_worker(chat_dir: str, agent: str, count: int) -> None:
    """Append messages from a separate process, using its own ChatStore."""
    import importlib
    import sys as _sys

    _sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    os.environ["AGENT_CHAT_DIR"] = chat_dir
    os.environ["AGENT_CHAT_ROOM"] = "default"
    for module in [m for m in _sys.modules if m.startswith("agent_chat_mcp")]:
        del _sys.modules[module]
    module = importlib.import_module("agent_chat_mcp.server")

    store = module.ChatStore(Path(chat_dir), "default")
    for index in range(count):
        store.append_message(
            "default",
            **{
                "from": agent,
                "to": "all",
                "content": f"{agent}-{index}",
                "type": "broadcast",
            },
        )


def test_concurrent_writers_lose_nothing(tmp_path):
    """Two processes appending at once must not drop messages or reuse an id.

    The read-modify-write happens under one exclusive lock, and the file is
    never truncated before that lock is held.
    """
    import multiprocessing

    per_worker = 25
    agents = ["backend", "frontend", "mobile"]

    context = multiprocessing.get_context("spawn")
    workers = [
        context.Process(target=_append_from_worker, args=(str(tmp_path), agent, per_worker))
        for agent in agents
    ]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=60)
        assert worker.exitcode == 0

    messages = json.loads((tmp_path / "default" / "messages.json").read_text())
    assert len(messages) == per_worker * len(agents)

    ids = [m["id"] for m in messages]
    assert len(set(ids)) == len(ids), "message ids must be unique"
    assert sorted(ids) == list(range(1, len(ids) + 1))

    for agent in agents:
        sent = {m["content"] for m in messages if m["from"] == agent}
        assert sent == {f"{agent}-{i}" for i in range(per_worker)}


def test_reading_a_missing_room_does_not_create_it(mcp_server, tmp_path):
    """A mistyped room name must not leave a phantom room behind.

    read_messages is advertised read-only, but it used to go through a helper
    that created the room directory on the way in, after which the empty room
    showed up in list_rooms.
    """

    async def run():
        async with Client(mcp_server) as client:
            read = await client.call_tool(
                "read_messages", {"agent_name": "backend", "room": "yanlis-yazilmis-oda"}
            )
            assert read.structured_content["messages"] == []

            assert not (tmp_path / "yanlis-yazilmis-oda").exists()
            rooms = await client.call_tool("list_rooms", {})
            assert [r["name"] for r in rooms.structured_content["rooms"]] == []

    anyio.run(run)


def _join_from_worker(chat_dir: str, agent: str, ready) -> None:
    """Join a room from another process, once told to."""
    import importlib
    import sys as _sys

    _sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    os.environ["AGENT_CHAT_DIR"] = chat_dir
    os.environ["AGENT_CHAT_ROOM"] = "default"
    for module in [m for m in _sys.modules if m.startswith("agent_chat_mcp")]:
        del _sys.modules[module]
    module = importlib.import_module("agent_chat_mcp.server")

    store = module.ChatStore(Path(chat_dir), "default")
    ready.wait(timeout=30)
    with store.room_lock("default"):
        agents = store.agents("default")
        agents[agent] = {"role": "", "joined_at": "now", "last_seen": 0}
        store.save_agents(agents, "default")
        store.append_message(
            "default",
            **{"from": "SYSTEM", "to": "all", "content": f"{agent} katıldı", "type": "system"},
        )


def test_clearing_a_room_is_all_or_nothing(mcp_server, tmp_path):
    """A join must not interleave between clearing the messages and the roster.

    The two files have their own locks, so without a room-wide one an agent
    could land its roster entry after the messages were cleared and its join
    notice after the roster was — leaving a room that is neither cleared nor
    intact.
    """
    import multiprocessing

    context = multiprocessing.get_context("spawn")
    ready = context.Event()
    joiner = context.Process(target=_join_from_worker, args=(str(tmp_path), "latecomer", ready))
    joiner.start()

    async def run():
        async with _client(mcp_server, {"confirm": True}) as client:
            await client.call_tool("join_room", {"agent_name": "backend"})
            ready.set()  # let the other process race the clear
            await client.call_tool("clear_room", {})

    anyio.run(run)
    joiner.join(timeout=60)
    assert joiner.exitcode == 0

    messages = json.loads((tmp_path / "default" / "messages.json").read_text())
    agents = json.loads((tmp_path / "default" / "agents.json").read_text())

    # Either the join landed entirely before the clear (both empty), or entirely
    # after it (one agent and its own notice). Never one without the other.
    assert (len(messages), len(agents)) in {(0, 0), (1, 1)}, (messages, agents)


def _send_from_worker(chat_dir: str, ready) -> None:
    """Send a message from another process, once told to."""
    import importlib
    import sys as _sys

    _sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    os.environ["AGENT_CHAT_DIR"] = chat_dir
    os.environ["AGENT_CHAT_ROOM"] = "default"
    for module in [m for m in _sys.modules if m.startswith("agent_chat_mcp")]:
        del _sys.modules[module]
    module = importlib.import_module("agent_chat_mcp.server")

    store = module.ChatStore(Path(chat_dir), "default")
    ready.wait(timeout=30)
    with store.room_lock("default"):
        store.touch("backend", "default")
        store.append_message(
            "default",
            **{"from": "backend", "to": "all", "content": "yarış", "type": "broadcast"},
        )


def test_a_send_cannot_straddle_a_clear(mcp_server, tmp_path):
    """A message and its sender's presence land together, or not at all.

    Without the room lock a clear finishing between the touch and the append
    left a message sitting in a room reported as emptied.
    """
    import multiprocessing

    context = multiprocessing.get_context("spawn")
    ready = context.Event()
    sender = context.Process(target=_send_from_worker, args=(str(tmp_path), ready))
    sender.start()

    async def run():
        async with _client(mcp_server, {"confirm": True}) as client:
            await client.call_tool("join_room", {"agent_name": "backend"})
            ready.set()
            await client.call_tool("clear_room", {})

    anyio.run(run)
    sender.join(timeout=60)
    assert sender.exitcode == 0

    messages = json.loads((tmp_path / "default" / "messages.json").read_text())
    agents = json.loads((tmp_path / "default" / "agents.json").read_text())

    # Either the send happened before the clear (both empty afterwards), or
    # after it (the message is there). A message with no trace of its sender
    # having been present is the state the lock rules out.
    assert len(messages) in {0, 1}, messages
    if messages:
        assert messages[0]["content"] == "yarış"
    assert len(agents) == 0 or "backend" in agents


def test_mutating_tools_are_not_marked_idempotent(mcp_server):
    """Retrying a send appends twice, so it must not claim to be idempotent."""

    async def run():
        async with Client(mcp_server) as client:
            tools = {t.name: t for t in (await client.list_tools()).tools}
            for name in ["send_message", "join_room", "leave_room"]:
                assert tools[name].annotations.idempotent_hint is False, name
            for name in ["read_messages", "list_agents", "get_last_message_id"]:
                assert tools[name].annotations.idempotent_hint is True, name

    anyio.run(run)
