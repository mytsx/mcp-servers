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
