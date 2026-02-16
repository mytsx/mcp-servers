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
import os
import re
import sys
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from markdownify import markdownify as md
from mcp.server.fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
SITE_URL = os.environ.get("DOCUSAURUS_URL", "").rstrip("/")
EXTRA_DESCRIPTION = os.environ.get("DOCUSAURUS_DESCRIPTION", "")
TIMEOUT = int(os.environ.get("DOCUSAURUS_TIMEOUT", "30"))

if not SITE_URL:
    print(
        "HATA: DOCUSAURUS_URL environment variable zorunludur.\n"
        "Örnek: DOCUSAURUS_URL=https://docs.example.com",
        file=sys.stderr,
    )
    sys.exit(1)

_client = httpx.Client(
    timeout=TIMEOUT,
    follow_redirects=True,
    headers={"User-Agent": "docusaurus-mcp/1.0"},
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
        path = path[len(base):]
    return path.strip("/")


# ---------------------------------------------------------------------------
# Sitemap
# ---------------------------------------------------------------------------
def _fetch_sitemap() -> list[str]:
    """Fetch sitemap.xml and return normalized URLs."""
    resp = _client.get(f"{SITE_URL}/sitemap.xml")
    resp.raise_for_status()
    root = ET.fromstring(resp.text)
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    sp = urlparse(SITE_URL)
    urls: list[str] = []
    for loc in root.findall(".//s:loc", ns):
        raw = (loc.text or "").strip()
        if raw:
            p = urlparse(raw)
            urls.append(
                raw.replace(
                    f"{p.scheme}://{p.netloc}", f"{sp.scheme}://{sp.netloc}"
                )
            )
    return urls


# ---------------------------------------------------------------------------
# HTML extraction (standard sites)
# ---------------------------------------------------------------------------
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
        "nav", "header", "footer", "aside",
        ".pagination-nav", ".theme-doc-sidebar-container",
        ".theme-doc-footer", ".theme-doc-toc-mobile",
        ".breadcrumbs", ".table-of-contents", "script", "style",
    ):
        for tag in el.select(sel):
            tag.decompose()

    for img in el.find_all("img", src=True):
        img["src"] = urljoin(page_url, img["src"])

    content = md(str(el), heading_style="ATX")
    content = re.sub(r"\n{3,}", "\n\n", content)
    return title, desc, content.strip()


# ---------------------------------------------------------------------------
# SPA chunk extraction
# ---------------------------------------------------------------------------
def _parse_runtime_chunks(
    homepage_html: str,
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

    rt = _client.get(runtime_url).text

    # Name hash map (first object in t.u)
    name_map: dict[str, str] = {}
    nm = re.search(
        r'"assets/js/"\s*\+\s*\(?\{([^}]+)\}\s*\[e\]\s*\|\|\s*e\)?', rt
    )
    if nm:
        name_map = dict(re.findall(r'(\d+):"([^"]+)"', nm.group(1)))

    # Content hash map (second object in t.u)
    hm = re.search(r'\+"\."\+\{([^}]+)\}\[e\]\+"\.js"', rt)
    if not hm:
        return {}

    chunks: dict[str, tuple[str, str]] = {}
    for cid, chash in re.findall(r'(\d+):"([^"]+)"', hm.group(1)):
        chunks[cid] = (name_map.get(cid, cid), chash)

    return chunks


def _fetch_chunk(
    chunk_id: str, name_hash: str, content_hash: str
) -> dict | None:
    """Fetch a webpack chunk and extract doc metadata + content.
    Returns a doc dict or None if not a doc chunk.
    """
    url = f"{SITE_URL}/assets/js/{name_hash}.{content_hash}.js"
    try:
        text = _client.get(url).text
    except httpx.HTTPError:
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
    toc: list[tuple[int, str]] = []
    for val, level in re.findall(
        r'\{value:"((?:[^"\\]|\\.)*)",id:"[^"]*",level:(\d+)\}', text
    ):
        toc.append((int(level), _unescape_js(val)))

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

    content = "\n".join(lines).strip()

    # Category from permalink
    pparts = permalink.strip("/").split("/") if permalink else []
    category = pparts[0] if len(pparts) > 1 else "_root"

    # Short ID (last segment)
    short_id = meta_id.split("/")[-1] if "/" in meta_id else meta_id
    if not short_id and pparts:
        short_id = pparts[-1]

    return {
        "id": short_id,
        "full_id": meta_id,
        "title": title,
        "url": f"{SITE_URL}{permalink}" if permalink else "",
        "path": permalink.strip("/"),
        "category": category,
        "content": content,
        "description": description,
    }


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------
print(f"Başlatılıyor: {SITE_URL}", file=sys.stderr)

# 1. Homepage
try:
    _homepage_html = _client.get(SITE_URL).text
except httpx.HTTPError as e:
    print(f"HATA: Ana sayfa alınamadı: {e}", file=sys.stderr)
    sys.exit(1)

_site_title = "Docusaurus Docs"
_soup = BeautifulSoup(_homepage_html, "html.parser")
if _title_tag := _soup.find("title"):
    _site_title = _title_tag.get_text(strip=True)

# 2. Sitemap
print("Sitemap alınıyor...", file=sys.stderr)
try:
    _sitemap_urls = _fetch_sitemap()
except Exception as e:
    print(f"Sitemap alınamadı: {e}", file=sys.stderr)
    _sitemap_urls = []

# 3. SPA detection: fetch one doc page, compare with homepage
_spa_mode = False
_test_urls = [u for u in _sitemap_urls if _relpath(u)]
if _test_urls:
    try:
        _spa_mode = _client.get(_test_urls[0]).text == _homepage_html
    except httpx.HTTPError:
        pass

# 4. Load content
_all_docs: list[dict] = []

if _spa_mode:
    # --- SPA mode: parse webpack chunks ---
    print("SPA modu algılandı, chunk'lar parse ediliyor...", file=sys.stderr)
    _chunk_info = _parse_runtime_chunks(_homepage_html)
    print(f"  {len(_chunk_info)} chunk bulundu", file=sys.stderr)

    def _do_fetch(item):
        cid, (nhash, chash) = item
        return _fetch_chunk(cid, nhash, chash)

    with ThreadPoolExecutor(max_workers=15) as pool:
        futs = {pool.submit(_do_fetch, it): it for it in _chunk_info.items()}
        for f in as_completed(futs):
            try:
                doc = f.result()
                if doc:
                    _all_docs.append(doc)
            except Exception as exc:
                print(f"  Chunk hatası: {exc}", file=sys.stderr)

else:
    # --- Standard mode: scrape HTML pages ---
    print("Standart mod (statik HTML)", file=sys.stderr)
    skip = {"blog", "tags", "search", "page", "markdown-page"}
    for url in _sitemap_urls:
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
        _all_docs.append({
            "id": did, "title": did.replace("-", " ").title(),
            "url": url, "path": rel, "category": cat,
            "content": None, "description": "",
        })

    def _scrape(doc):
        try:
            html = _client.get(doc["url"]).text
            title, desc, content = _extract_html(html, doc["url"])
            if title:
                doc["title"] = title
            if desc:
                doc["description"] = desc
            doc["content"] = content
        except Exception:
            doc["content"] = ""

    if _all_docs:
        print(f"  {len(_all_docs)} sayfa yükleniyor...", file=sys.stderr)
        with ThreadPoolExecutor(max_workers=10) as pool:
            list(pool.map(_scrape, _all_docs))

# 5. Build indexes
_categories = {}
for d in _all_docs:
    _categories.setdefault(d["category"].lower(), []).append(d)

_doc_count = len(_all_docs)
_by_id: dict[str, dict] = {}
_by_url: dict[str, dict] = {}
_by_path: dict[str, dict] = {}

for d in _all_docs:
    _by_id[d["id"]] = d
    if d.get("full_id"):
        _by_id[d["full_id"]] = d
    _by_url[d["url"]] = d
    _by_path[d["path"]] = d

print(f"Hazır: {_site_title} — {_doc_count} döküman", file=sys.stderr)

# ---------------------------------------------------------------------------
# MCP Server & Tools
# ---------------------------------------------------------------------------
mcp = FastMCP("docusaurus-docs")
_base_desc = f"{_site_title} döküman sitesinde"
_desc_suffix = f"\n{EXTRA_DESCRIPTION}" if EXTRA_DESCRIPTION else ""


@mcp.tool(
    description=f"{_base_desc} tüm döküman yapısını (kategoriler ve sayfalar) gösterir.{_desc_suffix}"
)
def get_doc_structure() -> str:
    """
    Returns:
        Döküman sitesinin kategori ağacı
    """
    lines = [f"{_site_title} ({_doc_count} döküman)", ""]
    for cat in sorted(_categories.keys()):
        if cat == "_root":
            continue
        docs = _categories[cat]
        lines.append(f"📁 {cat} ({len(docs)} sayfa)")
        for doc in sorted(docs, key=lambda d: d["title"]):
            lines.append(f"  ├── {doc['title']}  [{doc['id']}]")
        lines.append("")

    root = _categories.get("_root", [])
    if root:
        lines.append(f"📄 Diğer ({len(root)} sayfa)")
        for doc in sorted(root, key=lambda d: d["title"]):
            lines.append(f"  ├── {doc['title']}  [{doc['id']}]")

    return "\n".join(lines)


@mcp.tool(
    description=f"{_base_desc} bir kategorideki sayfaları listeler.{_desc_suffix}"
)
def list_docs(category: str = "") -> str:
    """
    Args:
        category: Kategori adı. Boş bırakılırsa tüm kategoriler özetlenir.
    """
    if not category:
        lines = [f"{_site_title} — Kategoriler:", ""]
        for cat in sorted(_categories.keys()):
            if cat == "_root":
                continue
            lines.append(f"  📁 {cat} — {len(_categories[cat])} sayfa")
        lines.append("")
        lines.append("Detay için: list_docs(category='kategori_adı')")
        return "\n".join(lines)

    cat_key = category.lower()
    docs = _categories.get(cat_key)
    if not docs:
        available = [c for c in _categories if c != "_root"]
        return (
            f"'{category}' bulunamadı. Mevcut: {', '.join(sorted(available))}"
        )

    lines = [f"📁 {category} ({len(docs)} sayfa)", ""]
    for doc in sorted(docs, key=lambda d: d["title"]):
        lines.append(f"  • {doc['title']}")
        if doc["description"]:
            lines.append(f"    {doc['description']}")
        lines.append(f"    ID: {doc['id']}  |  {doc['url']}")
        lines.append("")
    return "\n".join(lines)


@mcp.tool(
    description=f"{_base_desc} anahtar kelime araması yapar. Başlık, açıklama ve içerik üzerinde arar.{_desc_suffix}"
)
def search_docs(query: str, limit: int = 5) -> str:
    """
    Args:
        query: Aranacak kelime veya ifade
        limit: Maksimum sonuç sayısı (varsayılan: 5)
    """
    if not query.strip():
        return "Lütfen bir arama terimi girin."

    q = query.lower()
    results: list[tuple[int, dict, str]] = []

    for doc in _all_docs:
        score = 0
        snippet = ""

        if q in doc["title"].lower():
            score += 10
        if q in doc["description"].lower():
            score += 3

        content = (doc["content"] or "").lower()
        if q in content:
            count = content.count(q)
            score += min(count, 5)
            idx = content.index(q)
            start = max(0, idx - 100)
            end = min(len(content), idx + len(query) + 200)
            raw = (doc["content"] or "")[start:end].replace("\n", " ").strip()
            snippet = ("..." if start > 0 else "") + raw + (
                "..." if end < len(content) else ""
            )

        if score > 0:
            results.append((score, doc, snippet))

    results.sort(key=lambda x: x[0], reverse=True)
    results = results[:limit]

    if not results:
        return f"'{query}' için sonuç bulunamadı."

    lines = [f"🔍 '{query}' — {len(results)} sonuç:", ""]
    for _, doc, snippet in results:
        lines.append(f"  📄 {doc['title']}")
        lines.append(f"     {doc['url']}")
        if snippet:
            lines.append(f"     {snippet}")
        lines.append("")
    return "\n".join(lines)


@mcp.tool(
    description=f"{_base_desc} bir dökümanın tam içeriğini markdown olarak döner. ID veya URL ile erişilir.{_desc_suffix}"
)
def fetch_doc(doc_ref: str) -> str:
    """
    Args:
        doc_ref: Döküman ID'si (ör. 'yeni-izin-talebi'), URL'i veya path'i
    """
    doc = _by_id.get(doc_ref) or _by_url.get(doc_ref) or _by_path.get(doc_ref)

    if not doc:
        ref_lower = doc_ref.lower()
        for d in _all_docs:
            if (
                d["id"].lower() == ref_lower
                or ref_lower in d["url"].lower()
                or ref_lower in d["path"].lower()
            ):
                doc = d
                break

    if not doc:
        return (
            f"Döküman bulunamadı: '{doc_ref}'\n"
            "Mevcut ID'ler için get_doc_structure() kullanın."
        )

    header = f"# {doc['title']}\n\n"
    if doc["url"]:
        header += f"**URL:** {doc['url']}\n"
    if doc["description"]:
        header += f"**Açıklama:** {doc['description']}\n"
    header += f"**Kategori:** {doc['category']}\n\n---\n\n"

    return header + (doc["content"] or "(İçerik yüklenemedi)")


if __name__ == "__main__":
    mcp.run()
