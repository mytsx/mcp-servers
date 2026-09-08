"""Drive the reviews server in-process against a stub GitHub API.

Gemini Code Assist itself is not reachable from a test, so the fixture serves
the shapes its bot leaves behind on a PR.
"""

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import anyio
import pytest
from mcp import Client

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

BOT = "gemini-code-assist[bot]"

RESPONSES = {
    "/user": {"login": "mytsx"},
    "/repos/mytsx/demo/pulls": [{"number": 42}],
    "/repos/mytsx/demo/pulls/42/reviews": [
        {
            "user": {"login": BOT},
            "submitted_at": "2026-01-02T10:00:00Z",
            "state": "CHANGES_REQUESTED",
            "body": "eski inceleme",
            "html_url": "u1",
        },
        {
            "user": {"login": BOT},
            "submitted_at": "2026-03-02T10:00:00Z",
            "state": "COMMENTED",
            "body": "yeni inceleme",
            "html_url": "u2",
        },
        {
            "user": {"login": "human"},
            "submitted_at": "2026-03-03T10:00:00Z",
            "state": "APPROVED",
            "body": "lgtm",
            "html_url": "u3",
        },
    ],
    "/repos/mytsx/demo/pulls/42/comments": [
        {
            "user": {"login": BOT},
            "created_at": "2026-03-02T11:00:00Z",
            "path": "a.py",
            "line": 12,
            "body": "burada bug var",
            "html_url": "u4",
        }
    ],
    "/repos/mytsx/demo/issues/42/comments": [
        {
            "user": {"login": "mytsx"},
            "created_at": "2026-03-01T09:00:00Z",
            "body": "/gemini review",
            "html_url": "u5",
        },
        {
            "user": {"login": BOT},
            "created_at": "2026-03-02T12:00:00Z",
            "body": "ozet",
            "html_url": "u6",
        },
    ],
}


class _StubGitHub(BaseHTTPRequestHandler):
    """Answers the handful of endpoints the server calls, with paging."""

    def do_GET(self):  # noqa: N802
        path, _, query = self.path.partition("?")

        # /user needs credentials, as it does on real GitHub. Everything else
        # here stands in for a public repository and answers either way.
        if path == "/user" and not self.headers.get("Authorization"):
            self.send_response(401)
            self.send_header("content-length", "0")
            self.end_headers()
            return

        page = 1
        for part in query.split("&"):
            if part.startswith("page="):
                page = int(part[len("page=") :])

        body = RESPONSES.get(path, [])
        if isinstance(body, list) and page > 1:
            body = []  # only one page of each collection

        encoded = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, *args):
        pass


@pytest.fixture()
def server_module(monkeypatch):
    api = HTTPServer(("127.0.0.1", 0), _StubGitHub)
    threading.Thread(target=api.serve_forever, daemon=True).start()

    monkeypatch.setenv("GITHUB_TOKEN", "fake-token")
    for module in [m for m in sys.modules if m.startswith("gemini_reviews_mcp")]:
        del sys.modules[module]

    import gemini_reviews_mcp.server as module

    monkeypatch.setattr(module, "GITHUB_API", f"http://127.0.0.1:{api.server_port}")
    monkeypatch.setattr(module, "_resolve_github_token", lambda: "fake-token")
    try:
        yield module
    finally:
        api.shutdown()


def test_only_comments_after_the_last_review_request(server_module):
    async def run():
        async with Client(server_module.mcp) as client:
            result = await client.call_tool("get_gemini_reviews", {"repo": "demo"})
            content = result.structured_content

            # The owner and PR number are filled in from the API.
            assert content["repo"] == "mytsx/demo"
            assert content["pr"] == 42
            assert content["after_date"] == "2026-03-01T09:00:00Z"

            # The January review predates the cutoff; the human review is not Gemini's.
            bodies = [c["body"] for c in content["comments"]]
            assert bodies == ["yeni inceleme", "burada bug var", "ozet"]
            assert content["counts"] == {
                "reviews": 1,
                "line_comments": 1,
                "issue_comments": 1,
            }

    anyio.run(run)


def test_whole_history_when_the_cutoff_is_off(server_module):
    async def run():
        async with Client(server_module.mcp) as client:
            result = await client.call_tool(
                "get_gemini_reviews", {"repo": "demo", "after_last_review": False}
            )
            assert result.structured_content["counts"]["reviews"] == 2
            assert result.structured_content["after_date"] is None

    anyio.run(run)


def test_a_token_is_required_only_for_what_needs_one(server_module):
    """No token is fine for a fully specified public target.

    The README documents that, and the review resource already worked without
    one; only the defaults that go through /user need credentials.
    """

    async def run():
        async with Client(server_module.mcp) as client:
            # No token means no token: the header the client was built with has
            # to go too, or /user still answers.
            server_module._app.gh.token = ""
            server_module._app.gh.client.headers.pop("Authorization", None)

            # An owner-less repo has to ask /user who the owner is.
            missing_owner = await client.call_tool("get_gemini_reviews", {"repo": "demo"})
            assert missing_owner.is_error is True
            assert "Tam yolu ver" in missing_owner.content[0].text

            # So does working out whose "/gemini review" comment marks the cutoff.
            missing_user = await client.call_tool(
                "get_gemini_reviews", {"repo": "mytsx/demo", "pr": 42}
            )
            assert missing_user.is_error is True
            assert "after_last_review=false" in missing_user.content[0].text

            # Fully specified, no cutoff: nothing needs authentication.
            explicit = await client.call_tool(
                "get_gemini_reviews",
                {"repo": "mytsx/demo", "pr": 42, "after_last_review": False},
            )
            assert explicit.is_error is False
            assert explicit.structured_content["counts"]["reviews"] == 2

    anyio.run(run)


def test_resource_and_prompt(server_module):
    async def run():
        async with Client(server_module.mcp) as client:
            templates = (await client.list_resource_templates()).resource_templates
            assert [t.uri_template for t in templates] == ["review://{owner}/{repo}/{pr}"]

            body = json.loads(
                (await client.read_resource("review://mytsx/demo/42")).contents[0].text
            )
            assert len(body["comments"]) == 4  # the full history, no cutoff

            assert [p.name for p in (await client.list_prompts()).prompts] == ["address_review"]

    anyio.run(run)


def test_a_failed_request_fails_the_call(server_module, monkeypatch):
    """A partial history must not come back as a complete one.

    When a page of reviews fails, the tool has to fail too rather than report
    the comments it did manage to read: a missing finding reads exactly like
    no finding.
    """
    original_get = server_module.httpx2.AsyncClient.get

    async def broken_reviews(self, url, **kwargs):
        if "/reviews" in str(url):
            request = server_module.httpx2.Request("GET", str(url))
            return server_module.httpx2.Response(500, request=request, json={})
        return await original_get(self, url, **kwargs)

    monkeypatch.setattr(server_module.httpx2.AsyncClient, "get", broken_reviews)

    async def run():
        async with Client(server_module.mcp) as client:
            result = await client.call_tool(
                "get_gemini_reviews", {"repo": "demo", "after_last_review": False}
            )
            assert result.is_error is True
            assert "HTTP 500" in result.content[0].text

    anyio.run(run)


def test_a_403_names_the_likely_cause(server_module, monkeypatch):
    original_get = server_module.httpx2.AsyncClient.get

    async def forbidden(self, url, **kwargs):
        if "/reviews" in str(url):
            request = server_module.httpx2.Request("GET", str(url))
            return server_module.httpx2.Response(403, request=request, json={})
        return await original_get(self, url, **kwargs)

    monkeypatch.setattr(server_module.httpx2.AsyncClient, "get", forbidden)

    async def run():
        async with Client(server_module.mcp) as client:
            result = await client.call_tool(
                "get_gemini_reviews", {"repo": "demo", "after_last_review": False}
            )
            assert result.is_error is True
            assert "rate limit" in result.content[0].text

    anyio.run(run)
