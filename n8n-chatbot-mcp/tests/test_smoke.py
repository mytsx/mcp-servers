"""Drive the server in-process against a stub n8n Chat Trigger webhook."""

import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import anyio
import pytest
from mcp import Client

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

CHAT_HTML = b"""<html>x i18n: { en: {"subtitle":"Muhasebe asistani","title":"Mali Bot"} }
'X-Instance-Id': 'abc123',
initialMessages: ["Merhaba!"]</html>"""


class _StubHandler(BaseHTTPRequestHandler):
    """Serves the chat UI page on GET and echoes the question on POST."""

    def _respond(self, body: bytes, content_type: str) -> None:
        self.send_response(200)
        self.send_header("content-type", content_type)
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802 - name fixed by BaseHTTPRequestHandler
        self._respond(CHAT_HTML, "text/html")

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("content-length", 0))
        request = json.loads(self.rfile.read(length))
        self._respond(
            json.dumps({"output": f"cevap: {request['chatInput']}"}).encode(),
            "application/json",
        )

    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def chatbot_url():
    server = HTTPServer(("127.0.0.1", 0), _StubHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/webhook/test/chat"
    finally:
        server.shutdown()


@pytest.fixture(scope="module")
def mcp_server(chatbot_url):
    os.environ["N8N_CHATBOT_URL"] = chatbot_url
    from n8n_chatbot_mcp.server import mcp

    return mcp


def test_tool_schema_and_discovery(mcp_server):
    async def run():
        async with Client(mcp_server) as client:
            tools = (await client.list_tools()).tools
            assert [t.name for t in tools] == ["ask_chatbot"]

            tool = tools[0]
            assert set(tool.input_schema["properties"]) == {"question", "session_id"}
            assert tool.input_schema["required"] == ["question"]
            # Structured output comes from the ChatReply return annotation.
            assert set(tool.output_schema["properties"]) == {"answer", "session_id"}
            assert tool.annotations.read_only_hint is False

            # The name and greeting are discovered from the chat UI page.
            assert "Mali Bot" in (tool.description or "")
            assert "Merhaba!" in (tool.description or "")

    anyio.run(run)


def test_answer_and_session_continuity(mcp_server):
    async def run():
        async with Client(mcp_server) as client:
            first = await client.call_tool("ask_chatbot", {"question": "KDV oranı?"})
            assert first.is_error is False
            assert first.structured_content["answer"] == "cevap: KDV oranı?"

            session_id = first.structured_content["session_id"]
            second = await client.call_tool(
                "ask_chatbot", {"question": "devam", "session_id": session_id}
            )
            assert second.structured_content["session_id"] == session_id

    anyio.run(run)


def test_config_resource(mcp_server, chatbot_url):
    async def run():
        async with Client(mcp_server) as client:
            resources = (await client.list_resources()).resources
            assert [str(r.uri) for r in resources] == ["n8n://config"]

            body = json.loads((await client.read_resource("n8n://config")).contents[0].text)
            assert body["url"] == chatbot_url
            assert body["name"] == "Mali Bot"
            assert body["request_headers"] == ["X-Instance-Id"]

    anyio.run(run)


def test_unreachable_chatbot_is_a_tool_error():
    os.environ["N8N_CHATBOT_URL"] = "http://127.0.0.1:9/webhook/dead/chat"
    for module in [m for m in sys.modules if m.startswith("n8n_chatbot_mcp")]:
        del sys.modules[module]
    from n8n_chatbot_mcp.server import mcp

    async def run():
        async with Client(mcp) as client:
            result = await client.call_tool("ask_chatbot", {"question": "merhaba"})
            # A failure must be an error, not text that reads like an answer.
            assert result.is_error is True
            assert "bağlanılamadı" in result.content[0].text

    anyio.run(run)
