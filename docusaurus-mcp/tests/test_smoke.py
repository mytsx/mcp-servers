"""Drive the docs server in-process against a stub Docusaurus site."""

import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import anyio
import pytest
from mcp import Client

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

PAGES = {
    "/docs/kurulum/baslangic": ("Baslangic", "Kuruluma giris", "Sunucuyu kurmak icin uvx kullan."),
    "/docs/kurulum/gelismis": ("Gelismis Kurulum", "Docker ile", "Docker compose ile calistirilir."),
    "/docs/api/tools": ("Tool Referansi", "Tum toollar", "search_docs ve fetch_doc mevcuttur."),
}


class _StubSite(BaseHTTPRequestHandler):
    """A minimal statically rendered Docusaurus site."""

    port = 0

    def _respond(self, body: str, content_type: str = "text/html") -> None:
        encoded = body.encode()
        self.send_response(200)
        self.send_header("content-type", content_type)
        self.send_header("content-length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self):  # noqa: N802
        if self.path == "/sitemap.xml":
            locs = "".join(
                f"<url><loc>http://127.0.0.1:{self.server.server_port}{p}</loc></url>"
                for p in PAGES
            )
            return self._respond(
                '<?xml version="1.0"?>'
                f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{locs}</urlset>',
                "application/xml",
            )
        if self.path in PAGES:
            title, description, body = PAGES[self.path]
            return self._respond(
                f"<html><head><title>{title} | Test Docs</title>"
                f'<meta name="description" content="{description}"></head>'
                f'<body><article class="markdown"><h1>{title}</h1><p>{body}</p></article></body></html>'
            )
        return self._respond(
            "<html><head><title>Test Docs</title></head><body><main><h1>Ana</h1></main></body></html>"
        )

    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def mcp_server():
    site = HTTPServer(("127.0.0.1", 0), _StubSite)
    threading.Thread(target=site.serve_forever, daemon=True).start()
    os.environ["DOCUSAURUS_URL"] = f"http://127.0.0.1:{site.server_port}"
    for module in [m for m in sys.modules if m.startswith("docusaurus_mcp")]:
        del sys.modules[module]

    from docusaurus_mcp.server import mcp

    try:
        yield mcp
    finally:
        site.shutdown()


def test_structure_and_categories(mcp_server):
    async def run():
        async with Client(mcp_server) as client:
            structure = (await client.call_tool("get_doc_structure", {})).structured_content
            assert structure["site_title"] == "Test Docs"
            assert structure["doc_count"] == 3
            assert {c["name"] for c in structure["categories"]} == {"api", "kurulum"}

            listing = (await client.call_tool("list_docs", {"category": "kurulum"})).structured_content
            titles = {d["title"] for d in listing["categories"][0]["docs"]}
            assert titles == {"Baslangic", "Gelismis Kurulum"}

    anyio.run(run)


def test_search_and_fetch(mcp_server):
    async def run():
        async with Client(mcp_server) as client:
            hits = (await client.call_tool("search_docs", {"query": "docker"})).structured_content
            assert [h["doc"]["title"] for h in hits["hits"]] == ["Gelismis Kurulum"]

            doc = (await client.call_tool("fetch_doc", {"doc_ref": "tools"})).structured_content
            assert doc["title"] == "Tool Referansi"
            assert "fetch" in doc["content"]

    anyio.run(run)


def test_bad_input_is_a_tool_error(mcp_server):
    async def run():
        async with Client(mcp_server) as client:
            missing = await client.call_tool("list_docs", {"category": "yok-boyle"})
            assert missing.is_error is True
            assert "kategorisi yok" in missing.content[0].text

            # The limit is bounded by the schema, so this never reaches the handler.
            over_limit = await client.call_tool("search_docs", {"query": "x", "limit": 999})
            assert over_limit.is_error is True

    anyio.run(run)


def test_resource_and_prompt(mcp_server):
    async def run():
        async with Client(mcp_server) as client:
            page = (await client.read_resource("docs://tools")).contents[0].text
            assert page.startswith("# Tool Referansi")
            assert [p.name for p in (await client.list_prompts()).prompts] == ["explain_topic"]

    anyio.run(run)


def test_refresh_index_reports_progress(mcp_server):
    seen: list[tuple[float, float | None, str | None]] = []

    async def on_progress(progress, total, message):
        seen.append((progress, total, message))

    async def run():
        async with Client(mcp_server) as client:
            result = await client.call_tool("refresh_index", {}, progress_callback=on_progress)
            assert result.structured_content["doc_count"] == 3
            assert result.structured_content["spa_mode"] is False
            # One event per page crawled, plus the sitemap step.
            assert len(seen) >= 4

    anyio.run(run)


def test_a_failed_refresh_keeps_the_working_index(mcp_server, monkeypatch):
    """An empty crawl must not be installed over a good index.

    build_index treats a failed sitemap as best-effort, so a transient failure
    would otherwise replace a working index with an empty one and report
    success with doc_count=0.
    """
    import docusaurus_mcp.server as module

    async def empty_crawl(client, progress=module._noop_progress):
        return module.DocIndex(site_title="Test Docs")

    async def run():
        async with Client(mcp_server) as client:
            before = (await client.call_tool("get_doc_structure", {})).structured_content
            assert before["doc_count"] == 3

            monkeypatch.setattr(module, "build_index", empty_crawl)
            failed = await client.call_tool("refresh_index", {})
            assert failed.is_error is True
            assert "korundu" in failed.content[0].text

            monkeypatch.undo()
            after = (await client.call_tool("get_doc_structure", {})).structured_content
            assert after["doc_count"] == 3

    anyio.run(run)


def test_pages_that_fail_are_left_out_of_the_index(mcp_server):
    """A site that is up but serving errors must not replace a good index.

    The sitemap still lists every page, and `get()` does not raise on a 404, so
    without dropping the failures the refresh would install an index full of
    error pages and report success.
    """
    import docusaurus_mcp.server as module

    original_get = module.httpx2.AsyncClient.get

    async def not_found(self, url, *args, **kwargs):
        if "/docs/" in str(url):
            request = module.httpx2.Request("GET", str(url))
            return module.httpx2.Response(404, request=request, text="not found")
        return await original_get(self, url, *args, **kwargs)

    async def run():
        async with Client(mcp_server) as client:
            # The lifespan crawled the real site, so there is a good index to
            # protect. Only now does the site start failing.
            before = (await client.call_tool("get_doc_structure", {})).structured_content
            assert before["doc_count"] == 3

            module.httpx2.AsyncClient.get = not_found
            try:
                result = await client.call_tool("refresh_index", {})
                assert result.is_error is True
                assert "korundu" in result.content[0].text
            finally:
                module.httpx2.AsyncClient.get = original_get

            after = (await client.call_tool("get_doc_structure", {})).structured_content
            assert after["doc_count"] == 3, after

    anyio.run(run)


def test_a_partial_outage_does_not_shrink_the_index(mcp_server):
    """One failing page must not quietly disappear from search and fetch.

    A crawl that loses a page still comes back non-empty, so the emptiness
    check alone would install it and report success while that page stopped
    being findable.
    """
    import docusaurus_mcp.server as module

    original_get = module.httpx2.AsyncClient.get

    async def one_page_down(self, url, *args, **kwargs):
        if "/docs/api/tools" in str(url):
            request = module.httpx2.Request("GET", str(url))
            return module.httpx2.Response(503, request=request, text="unavailable")
        return await original_get(self, url, *args, **kwargs)

    async def run():
        async with Client(mcp_server) as client:
            assert (await client.call_tool("get_doc_structure", {})).structured_content[
                "doc_count"
            ] == 3

            module.httpx2.AsyncClient.get = one_page_down
            try:
                result = await client.call_tool("refresh_index", {})
                assert result.is_error is True
                assert "sayfa alınamadı" in result.content[0].text
            finally:
                module.httpx2.AsyncClient.get = original_get

            # All three are still there, including the one that failed.
            after = (await client.call_tool("get_doc_structure", {})).structured_content
            assert after["doc_count"] == 3
            found = await client.call_tool("fetch_doc", {"doc_ref": "tools"})
            assert found.is_error is False

    anyio.run(run)
