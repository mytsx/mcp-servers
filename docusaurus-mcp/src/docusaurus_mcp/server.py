#!/usr/bin/env python3
"""
Docusaurus MCP Server
Generic MCP server for any Docusaurus documentation site.
Web-scraping based: works with both standard static and SPA-only sites.
Automatically detects SPA mode and falls back to webpack chunk parsing.

Environment variables:
    DOCUSAURUS_URL         (required) Site base URL, e.g. https://docs.example.com
    DOCUSAURUS_DESCRIPTION (optional) Extra context appended to tool descriptions
    DOCUSAURUS_TIMEOUT     (optional) HTTP timeout in seconds (default: 30)
"""

import json
import logging
import os
import re
import sys
import xml.etree.ElementTree as ET
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Annotated
from urllib.parse import urljoin, urlparse

import anyio
import httpx2
from bs4 import BeautifulSoup
from markdownify import markdownify as md
from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ResourceError, ToolError
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from . import __version__

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
SITE_URL = os.environ.get("DOCUSAURUS_URL", "").rstrip("/")
EXTRA_DESCRIPTION = os.environ.get("DOCUSAURUS_DESCRIPTION", "")
TIMEOUT = int(os.environ.get("DOCUSAURUS_TIMEOUT", "30"))

# How many pages or chunks to fetch at once while indexing.
MAX_CONCURRENT_FETCHES = 10

if not SITE_URL:
    print(
        "HATA: DOCUSAURUS_URL environment variable zorunludur.\n"
        "Örnek: DOCUSAURUS_URL=https://docs.example.com",
        file=sys.stderr,
    )
    sys.exit(1)


def _new_client() -> httpx2.AsyncClient:
    return httpx2.AsyncClient(
        timeout=TIMEOUT,
        follow_redirects=True,
        headers={"User-Agent": f"docusaurus-mcp/{__version__}"},
    )


# ---------------------------------------------------------------------------
# Wire models
# ---------------------------------------------------------------------------


class DocSummary(BaseModel):
    """One documentation page, without its body."""

    id: str = Field(description="Short ID, usable as `doc_ref` in fetch_doc.")
    title: str
    url: str
    path: str = Field(description="Site-relative path, also usable as `doc_ref`.")
    category: str
    description: str = ""


class Category(BaseModel):
    name: str
    page_count: int
    docs: list[DocSummary] = Field(default_factory=list)


class DocStructure(BaseModel):
    site_title: str
    site_url: str
    doc_count: int
    categories: list[Category]


class CategoryListing(BaseModel):
    site_title: str
    category: str = Field(description="The category listed, or empty when listing all of them.")
    categories: list[Category]


class SearchHit(BaseModel):
    score: int = Field(description="Relevance: title matches weigh most, then description, then body.")
    doc: DocSummary
    snippet: str = Field(default="", description="Text around the first body match.")


class SearchResults(BaseModel):
    query: str
    total_matching: int = Field(description="How many pages matched before `limit` was applied.")
    hits: list[SearchHit]


class DocContent(BaseModel):
    """A page with its full body as markdown."""

    id: str
    title: str
    url: str
    path: str
    category: str
    description: str = ""
    content: str = Field(description="The page body, converted to markdown.")


class IndexStatus(BaseModel):
    site_title: str
    site_url: str
    doc_count: int
    spa_mode: bool = Field(
        description="True when the site renders client-side and content came from webpack chunks."
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _unescape_js(s: str) -> str:
    """Unescape JavaScript string literal (handles surrogate pairs)."""
    s = s.replace('\\"', '"').replace("\\'", "'")
    s = s.replace("\\n", "\n").replace("\\t", "\t")
    s = re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), s)
    s = re.sub(r"\\x([0-9a-fA-F]{2})", lambda m: chr(int(m.group(1), 16)), s)
    s = s.replace("\\\\", "\\")
    # Combine surrogate pairs (JS UTF-16 → Python str)
    try:
        s = s.encode("utf-16", "surrogatepass").decode("utf-16")
    except (UnicodeEncodeError, UnicodeDecodeError):
        s = s.encode("utf-8", "replace").decode("utf-8")
    return s


def _relpath(url: str) -> str:
    """URL → relative path (no leading slash)."""
    base = urlparse(SITE_URL).path.rstrip("/")
    path = urlparse(url).path
    if base and path.startswith(base):
        path = path[len(base) :]
    return path.strip("/")


def _extract_html(html: str, page_url: str) -> tuple[str, str, str]:
    """Extract (title, description, markdown_content) from Docusaurus HTML."""
    soup = BeautifulSoup(html, "html.parser")

    title = ""
    h1 = soup.select_one("article h1, .markdown h1, main h1")
    if h1:
        title = h1.get_text(strip=True)
    if not title:
        tag = soup.find("title")
        if tag:
            t = tag.get_text(strip=True)
            for sep in (" | ", " - ", " · ", " — "):
                if sep in t:
                    t = t.split(sep)[0].strip()
                    break
            title = t

    desc = ""
    meta = soup.find("meta", attrs={"name": "description"})
    if meta:
        desc = meta.get("content", "")

    el = (
        soup.select_one("article.markdown")
        or soup.select_one("article")
        or soup.select_one(".markdown")
        or soup.select_one("main")
    )
    if not el:
        return title, desc, ""

    for sel in (
        "nav",
        "header",
        "footer",
        "aside",
        ".pagination-nav",
        ".theme-doc-sidebar-container",
        ".theme-doc-footer",
        ".theme-doc-toc-mobile",
        ".breadcrumbs",
        ".table-of-contents",
        "script",
        "style",
    ):
        for tag in el.select(sel):
            tag.decompose()

    for img in el.find_all("img", src=True):
        img["src"] = urljoin(page_url, img["src"])

    content = md(str(el), heading_style="ATX")
    content = re.sub(r"\n{3,}", "\n\n", content)
    return title, desc, content.strip()


def _site_title_from(html: str, fallback: str = "Docusaurus Docs") -> str:
    tag = BeautifulSoup(html, "html.parser").find("title")
    return tag.get_text(strip=True) if tag else fallback


# ---------------------------------------------------------------------------
# The index
# ---------------------------------------------------------------------------


@dataclass
class Doc:
    """One page as it is held in memory, body included."""

    id: str
    title: str
    url: str
    path: str
    category: str
    description: str = ""
    content: str = ""
    full_id: str = ""

    def summary(self) -> DocSummary:
        return DocSummary(
            id=self.id,
            title=self.title,
            url=self.url,
            path=self.path,
            category=self.category,
            description=self.description,
        )


@dataclass
class DocIndex:
    """Everything the tools read: the pages plus the lookups over them."""

    site_title: str
    spa_mode: bool = False
    docs: list[Doc] = field(default_factory=list)
    categories: dict[str, list[Doc]] = field(default_factory=dict)
    by_id: dict[str, Doc] = field(default_factory=dict)
    by_url: dict[str, Doc] = field(default_factory=dict)
    by_path: dict[str, Doc] = field(default_factory=dict)

    def reindex(self) -> None:
        self.categories = {}
        self.by_id = {}
        self.by_url = {}
        self.by_path = {}
        for doc in self.docs:
            self.categories.setdefault(doc.category.lower(), []).append(doc)
            self.by_id[doc.id] = doc
            if doc.full_id:
                self.by_id[doc.full_id] = doc
            self.by_url[doc.url] = doc
            self.by_path[doc.path] = doc

    def find(self, ref: str) -> Doc | None:
        doc = self.by_id.get(ref) or self.by_url.get(ref) or self.by_path.get(ref)
        if doc:
            return doc
        ref_lower = ref.lower()
        for d in self.docs:
            if (
                d.id.lower() == ref_lower
                or ref_lower in d.url.lower()
                or ref_lower in d.path.lower()
            ):
                return d
        return None

    def category_models(self, only: str = "", with_docs: bool = True) -> list[Category]:
        names = [only.lower()] if only else sorted(self.categories)
        out: list[Category] = []
        for name in names:
            docs = self.categories.get(name)
            if docs is None:
                continue
            out.append(
                Category(
                    name=name,
                    page_count=len(docs),
                    docs=[d.summary() for d in sorted(docs, key=lambda d: d.title)]
                    if with_docs
                    else [],
                )
            )
        return out


ProgressCallback = Callable[[int, int, str], Awaitable[None]]


async def _noop_progress(done: int, total: int, message: str) -> None:
    return None


# ---------------------------------------------------------------------------
# Crawling
# ---------------------------------------------------------------------------


async def _fetch_sitemap(client: httpx2.AsyncClient) -> list[str]:
    """Fetch sitemap.xml and return normalized URLs."""
    resp = await client.get(f"{SITE_URL}/sitemap.xml")
    resp.raise_for_status()
    root = ET.fromstring(resp.text)
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    sp = urlparse(SITE_URL)
    urls: list[str] = []
    for loc in root.findall(".//s:loc", ns):
        raw = (loc.text or "").strip()
        if raw:
            p = urlparse(raw)
            urls.append(raw.replace(f"{p.scheme}://{p.netloc}", f"{sp.scheme}://{sp.netloc}"))
    return urls


async def _parse_runtime_chunks(
    client: httpx2.AsyncClient, homepage_html: str
) -> dict[str, tuple[str, str]]:
    """Parse runtime.js → {chunk_id: (name_hash, content_hash)}.

    Docusaurus webpack builds the URL via:
        t.u = e => "assets/js/" + NAME_MAP[e]||e + "." + HASH_MAP[e] + ".js"
    """
    soup = BeautifulSoup(homepage_html, "html.parser")
    runtime_url = None
    for s in soup.find_all("script", src=True):
        if "/runtime" in s["src"]:
            runtime_url = urljoin(SITE_URL + "/", s["src"])
            break
    if not runtime_url:
        return {}

    rt = (await client.get(runtime_url)).text

    # Name hash map (first object in t.u)
    name_map: dict[str, str] = {}
    nm = re.search(r'"assets/js/"\s*\+\s*\(?\{([^}]+)\}\s*\[e\]\s*\|\|\s*e\)?', rt)
    if nm:
        name_map = dict(re.findall(r'(\d+):"([^"]+)"', nm.group(1)))

    # Content hash map (second object in t.u)
    hm = re.search(r'\+"\."\+\{([^}]+)\}\[e\]\+"\.js"', rt)
    if not hm:
        return {}

    return {
        cid: (name_map.get(cid, cid), chash)
        for cid, chash in re.findall(r'(\d+):"([^"]+)"', hm.group(1))
    }


async def _fetch_chunk(
    client: httpx2.AsyncClient, name_hash: str, content_hash: str
) -> Doc | None:
    """Fetch a webpack chunk and extract doc metadata + content, or None if not a doc."""
    url = f"{SITE_URL}/assets/js/{name_hash}.{content_hash}.js"
    try:
        text = (await client.get(url)).text
    except httpx2.HTTPError:
        return None

    # Metadata lives in JSON.parse('{...}')
    meta_match = re.search(r"JSON\.parse\('(\{.*?\})'\)", text)
    if not meta_match:
        return None

    try:
        meta = json.loads(meta_match.group(1))
    except json.JSONDecodeError:
        return None

    # Only doc pages have sourceDirName
    if "sourceDirName" not in meta:
        return None

    title = meta.get("title", "")
    description = meta.get("description", "")
    permalink = meta.get("permalink", "")
    meta_id = meta.get("id", "")

    # --- Extract content from JSX children ---
    parts: list[str] = []
    for m in re.finditer(r'children\s*:\s*"((?:[^"\\]|\\.)*)"', text):
        s = _unescape_js(m.group(1))
        if len(s) >= 2 and s != title:
            parts.append(s)

    # TOC for section structure
    toc: list[tuple[int, str]] = [
        (int(level), _unescape_js(val))
        for val, level in re.findall(
            r'\{value:"((?:[^"\\]|\\.)*)",id:"[^"]*",level:(\d+)\}', text
        )
    ]

    # Build readable markdown
    lines: list[str] = []
    if title:
        lines += [f"# {title}", ""]
    if description:
        lines += [description, ""]
    for lvl, val in toc:
        lines += [f"{'#' * lvl} {val}", ""]
    if parts:
        current: list[str] = []
        for p in parts:
            current.append(p)
            if p.rstrip().endswith((".", ":", "!", "?", ";")):
                lines.append(" ".join(current))
                lines.append("")
                current = []
        if current:
            lines.append(" ".join(current))

    # Category from permalink
    pparts = permalink.strip("/").split("/") if permalink else []
    category = pparts[0] if len(pparts) > 1 else "_root"

    # Short ID (last segment)
    short_id = meta_id.split("/")[-1] if "/" in meta_id else meta_id
    if not short_id and pparts:
        short_id = pparts[-1]

    return Doc(
        id=short_id,
        full_id=meta_id,
        title=title,
        url=f"{SITE_URL}{permalink}" if permalink else "",
        path=permalink.strip("/"),
        category=category,
        content="\n".join(lines).strip(),
        description=description,
    )


def _skeleton_from_sitemap(urls: list[str]) -> list[Doc]:
    """Turn sitemap URLs into empty Docs, skipping the non-documentation sections."""
    skip = {"blog", "tags", "search", "page", "markdown-page"}
    docs: list[Doc] = []
    for url in urls:
        rel = _relpath(url)
        if not rel:
            continue
        parts = rel.split("/")
        if parts[0] in skip:
            continue
        if parts[0] == "docs" and len(parts) > 2:
            cat, did = parts[1], parts[-1]
        elif len(parts) > 1:
            cat, did = parts[0], parts[-1]
        else:
            cat, did = "_root", parts[0]
        docs.append(
            Doc(id=did, title=did.replace("-", " ").title(), url=url, path=rel, category=cat)
        )
    return docs


async def _fill_from_html(client: httpx2.AsyncClient, doc: Doc) -> None:
    """Scrape a static page into an existing skeleton Doc."""
    try:
        html = (await client.get(doc.url)).text
        title, desc, content = _extract_html(html, doc.url)
        if title:
            doc.title = title
        if desc:
            doc.description = desc
        doc.content = content
    except Exception as exc:
        logger.warning("Sayfa yüklenemedi %s: %s", doc.url, exc)
        doc.content = ""


async def _run_bounded(jobs: list[Callable[[], Awaitable[None]]], on_done: ProgressCallback) -> None:
    """Run `jobs` with a concurrency cap, reporting progress as each finishes."""
    limiter = anyio.CapacityLimiter(MAX_CONCURRENT_FETCHES)
    done = 0
    total = len(jobs)

    async def run(job: Callable[[], Awaitable[None]]) -> None:
        nonlocal done
        async with limiter:
            await job()
        done += 1
        await on_done(done, total, f"{done}/{total} sayfa")

    async with anyio.create_task_group() as tg:
        for job in jobs:
            tg.start_soon(run, job)


async def build_index(
    client: httpx2.AsyncClient, progress: ProgressCallback = _noop_progress
) -> DocIndex:
    """Crawl the site once and return a fresh index.

    Cancelling the surrounding scope (a client cancelling the tool call, or the
    server shutting down) cancels every in-flight fetch with it.
    """
    homepage_html = (await client.get(SITE_URL)).text
    index = DocIndex(site_title=_site_title_from(homepage_html))

    await progress(0, 1, "Sitemap alınıyor")
    try:
        sitemap_urls = await _fetch_sitemap(client)
    except Exception as exc:
        logger.warning("Sitemap alınamadı: %s", exc)
        sitemap_urls = []

    # SPA detection: a doc page that comes back byte-identical to the homepage
    # means the server is not rendering per-page HTML.
    test_urls = [u for u in sitemap_urls if _relpath(u)]
    if test_urls:
        try:
            index.spa_mode = (await client.get(test_urls[0])).text == homepage_html
        except httpx2.HTTPError:
            pass

    if index.spa_mode:
        logger.info("SPA modu algılandı, chunk'lar parse ediliyor")
        chunk_info = await _parse_runtime_chunks(client, homepage_html)
        logger.info("%d chunk bulundu", len(chunk_info))

        async def fetch_one(name_hash: str, content_hash: str) -> None:
            doc = await _fetch_chunk(client, name_hash, content_hash)
            if doc:
                index.docs.append(doc)

        jobs = [
            (lambda nh=nh, ch=ch: fetch_one(nh, ch)) for nh, ch in chunk_info.values()
        ]
        await _run_bounded(jobs, progress)
    else:
        logger.info("Standart mod (statik HTML)")
        index.docs = _skeleton_from_sitemap(sitemap_urls)
        logger.info("%d sayfa yükleniyor", len(index.docs))
        jobs = [(lambda d=doc: _fill_from_html(client, d)) for doc in index.docs]
        await _run_bounded(jobs, progress)

    index.reindex()
    logger.info("Hazır: %s — %d döküman", index.site_title, len(index.docs))
    return index


# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------


@dataclass
class AppContext:
    client: httpx2.AsyncClient
    index: DocIndex


# Resources reach the app state through this module-level handle: a resource
# handler's Context carries no request context, so it cannot read the lifespan
# object the way a tool does.
_app: AppContext | None = None


@asynccontextmanager
async def app_lifespan(server: MCPServer) -> AsyncIterator[AppContext]:
    """Crawl the site once at startup; the tools serve from the result."""
    global _app
    async with _new_client() as client:
        try:
            index = await build_index(client)
        except httpx2.HTTPError as exc:
            logger.error("Site indekslenemedi (%s): %s", SITE_URL, exc)
            index = DocIndex(site_title=SITE_URL)
        _app = AppContext(client=client, index=index)
        try:
            yield _app
        finally:
            _app = None


mcp = MCPServer("docusaurus-docs", version=__version__, lifespan=app_lifespan)

_DESC_SUFFIX = f"\n{EXTRA_DESCRIPTION}" if EXTRA_DESCRIPTION else ""
_READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=False)


def _index(ctx: Context[AppContext]) -> DocIndex:
    index = ctx.request_context.lifespan_context.index
    if not index.docs:
        raise ToolError(
            f"{SITE_URL} indekslenemedi ya da hiç döküman bulunamadı. "
            "refresh_index ile yeniden denenebilir."
        )
    return index


@mcp.tool(
    title="Döküman yapısı",
    description=f"Döküman sitesinin tüm yapısını (kategoriler ve sayfalar) gösterir.{_DESC_SUFFIX}",
    annotations=_READ_ONLY,
)
def get_doc_structure(ctx: Context[AppContext]) -> DocStructure:
    index = _index(ctx)
    return DocStructure(
        site_title=index.site_title,
        site_url=SITE_URL,
        doc_count=len(index.docs),
        categories=index.category_models(),
    )


@mcp.tool(
    title="Sayfaları listele",
    description=f"Bir kategorideki sayfaları listeler.{_DESC_SUFFIX}",
    annotations=_READ_ONLY,
)
def list_docs(
    ctx: Context[AppContext],
    category: Annotated[
        str,
        Field(description="Kategori adı. Boş bırakılırsa tüm kategoriler sayfasız özetlenir."),
    ] = "",
) -> CategoryListing:
    index = _index(ctx)

    if not category:
        return CategoryListing(
            site_title=index.site_title,
            category="",
            categories=index.category_models(with_docs=False),
        )

    categories = index.category_models(only=category)
    if not categories:
        available = sorted(c for c in index.categories if c != "_root")
        raise ToolError(f"'{category}' kategorisi yok. Mevcut olanlar: {', '.join(available)}")

    return CategoryListing(site_title=index.site_title, category=category, categories=categories)


@mcp.tool(
    title="Dökümanlarda ara",
    description=f"Başlık, açıklama ve içerik üzerinde anahtar kelime araması yapar.{_DESC_SUFFIX}",
    annotations=_READ_ONLY,
)
def search_docs(
    query: Annotated[str, Field(min_length=1, description="Aranacak kelime veya ifade.")],
    ctx: Context[AppContext],
    limit: Annotated[int, Field(ge=1, le=50, description="Maksimum sonuç sayısı.")] = 5,
) -> SearchResults:
    index = _index(ctx)
    q = query.strip().lower()
    if not q:
        raise ToolError("Arama terimi boş olamaz.")

    hits: list[SearchHit] = []
    for doc in index.docs:
        score = 0
        snippet = ""

        if q in doc.title.lower():
            score += 10
        if q in doc.description.lower():
            score += 3

        content_lower = doc.content.lower()
        if q in content_lower:
            score += min(content_lower.count(q), 5)
            idx = content_lower.index(q)
            start = max(0, idx - 100)
            end = min(len(doc.content), idx + len(q) + 200)
            raw = doc.content[start:end].replace("\n", " ").strip()
            snippet = ("..." if start > 0 else "") + raw + ("..." if end < len(doc.content) else "")

        if score > 0:
            hits.append(SearchHit(score=score, doc=doc.summary(), snippet=snippet))

    hits.sort(key=lambda h: h.score, reverse=True)
    return SearchResults(query=query, total_matching=len(hits), hits=hits[:limit])


@mcp.tool(
    title="Dökümanı getir",
    description=f"Bir dökümanın tam içeriğini markdown olarak döner. ID, path veya URL ile.{_DESC_SUFFIX}",
    annotations=_READ_ONLY,
)
def fetch_doc(
    doc_ref: Annotated[
        str,
        Field(description="Döküman ID'si (ör. 'yeni-izin-talebi'), site içi path'i veya tam URL'i."),
    ],
    ctx: Context[AppContext],
) -> DocContent:
    index = _index(ctx)
    doc = index.find(doc_ref)
    if not doc:
        raise ToolError(
            f"Döküman bulunamadı: '{doc_ref}'. Mevcut ID'ler için get_doc_structure kullan."
        )
    return DocContent(
        id=doc.id,
        title=doc.title,
        url=doc.url,
        path=doc.path,
        category=doc.category,
        description=doc.description,
        content=doc.content or "(İçerik yüklenemedi)",
    )


@mcp.tool(
    title="İndeksi yenile",
    description="Siteyi baştan tarayıp indeksi tazeler. Dökümanlar güncellendiyse kullan."
    + _DESC_SUFFIX,
    annotations=ToolAnnotations(
        read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=True
    ),
)
async def refresh_index(ctx: Context[AppContext]) -> IndexStatus:
    app = ctx.request_context.lifespan_context

    async def report(done: int, total: int, message: str) -> None:
        await ctx.report_progress(done, total, message)

    try:
        app.index = await build_index(app.client, progress=report)
    except httpx2.HTTPError as exc:
        raise ToolError(f"{SITE_URL} taranamadı: {exc}") from exc

    return IndexStatus(
        site_title=app.index.site_title,
        site_url=SITE_URL,
        doc_count=len(app.index.docs),
        spa_mode=app.index.spa_mode,
    )


@mcp.resource(
    "docs://{doc_ref}",
    name="Döküman sayfası",
    description="Bir döküman sayfasının markdown içeriği. doc_ref: ID, path veya URL.",
    mime_type="text/markdown",
)
def doc_resource(doc_ref: str) -> str:
    if _app is None:
        raise ResourceError("Sunucu henüz hazır değil.")
    doc = _app.index.find(doc_ref)
    if not doc:
        raise ResourceError(f"Döküman bulunamadı: '{doc_ref}'")

    header = f"# {doc.title}\n\n"
    if doc.url:
        header += f"**URL:** {doc.url}\n"
    if doc.description:
        header += f"**Açıklama:** {doc.description}\n"
    header += f"**Kategori:** {doc.category}\n\n---\n\n"
    return header + (doc.content or "(İçerik yüklenemedi)")


@mcp.prompt(title="Konuyu dökümanlardan açıkla")
def explain_topic(topic: str) -> str:
    """Explain a topic using only what the documentation site says about it."""
    return (
        f"'{topic}' konusunu bu döküman sitesindeki bilgilere dayanarak açıkla.\n\n"
        f"1. `search_docs` ile '{topic}' ara.\n"
        "2. En alakalı sayfaları `fetch_doc` ile tam olarak oku.\n"
        "3. Yalnızca dökümanlarda yazana dayanarak açıkla; eksik kalan noktaları eksik olarak belirt.\n"
        "4. Her iddianın yanına kaynak sayfanın başlığını ve URL'sini koy."
    )


if __name__ == "__main__":
    mcp.run()
