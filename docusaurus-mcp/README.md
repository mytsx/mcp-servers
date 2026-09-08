# Docusaurus MCP Server

[![Python](https://img.shields.io/badge/python-3.10+-blue?logo=python&logoColor=white)](https://python.org)
[![MCP](https://img.shields.io/badge/MCP-2026--07--28-purple)](https://modelcontextprotocol.io)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

Generic MCP server for any [Docusaurus](https://docusaurus.io) documentation site. Point it at a URL and get full-text search, browsing, and content extraction — works with both static HTML and SPA-only builds.

## Features

- **Auto SPA Detection** — Detects SPA-only sites and falls back to webpack chunk parsing
- **Full-Text Search** — Search across titles, descriptions, and page content
- **Category Browsing** — Navigate the doc structure by categories
- **Markdown Extraction** — Returns clean markdown from any doc page
- **Sitemap Support** — Automatically discovers all pages via sitemap.xml
- **Structured Output** — Every tool returns typed JSON (`DocSummary`, `SearchHit`, `DocContent`)
- **Live Refresh** — `refresh_index` re-crawls the site and reports progress while it works
- **Doc Resource** — `docs://{doc_ref}` reads any page directly, no tool call needed
- **Prompt** — `explain_topic` walks the model through answering from the docs with citations

## Quick Start

### Claude Code

```bash
claude mcp add docusaurus \
  -e DOCUSAURUS_URL="https://docs.example.com" \
  -- uvx docusaurus-mcp
```

### Claude Desktop

Add to your config file:

- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "docusaurus": {
      "command": "uvx",
      "args": ["docusaurus-mcp"],
      "env": {
        "DOCUSAURUS_URL": "https://docs.example.com"
      }
    }
  }
}
```

### Cursor

Add to `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "docusaurus": {
      "command": "uvx",
      "args": ["docusaurus-mcp"],
      "env": {
        "DOCUSAURUS_URL": "https://docs.example.com"
      }
    }
  }
}
```

### Windsurf

Add to Windsurf MCP config:

```json
{
  "mcpServers": {
    "docusaurus": {
      "command": "uvx",
      "args": ["docusaurus-mcp"],
      "env": {
        "DOCUSAURUS_URL": "https://docs.example.com"
      }
    }
  }
}
```

### VS Code

Add to your VS Code settings (JSON):

```json
"mcp": {
  "servers": {
    "docusaurus": {
      "type": "stdio",
      "command": "uvx",
      "args": ["docusaurus-mcp"],
      "env": {
        "DOCUSAURUS_URL": "https://docs.example.com"
      }
    }
  }
}
```

### Gemini CLI

Add to `~/.gemini/settings.json`:

```json
{
  "mcpServers": {
    "docusaurus": {
      "command": "uvx",
      "args": ["docusaurus-mcp"],
      "env": {
        "DOCUSAURUS_URL": "https://docs.example.com"
      }
    }
  }
}
```

### GitHub Copilot

Add to `~/.copilot/mcp-config.json`:

```json
{
  "mcpServers": {
    "docusaurus": {
      "command": "uvx",
      "args": ["docusaurus-mcp"],
      "env": {
        "DOCUSAURUS_URL": "https://docs.example.com"
      }
    }
  }
}
```

### OpenAI Codex

Add to `~/.codex/config.toml`:

```toml
[mcp_servers.docusaurus]
command = "uvx"
args = ["docusaurus-mcp"]

[mcp_servers.docusaurus.env]
DOCUSAURUS_URL = "https://docs.example.com"
```

### Install from Source

```bash
cd docusaurus-mcp
pip install -e .
```

## Configuration

| Environment Variable | Required | Description |
|---------------------|----------|-------------|
| `DOCUSAURUS_URL` | Yes | Docusaurus site base URL (e.g. `https://docs.example.com`) |
| `DOCUSAURUS_DESCRIPTION` | No | Extra context appended to tool descriptions |
| `DOCUSAURUS_TIMEOUT` | No | HTTP timeout in seconds (default: `30`) |

## Tools

<details>
<summary><code>get_doc_structure</code> — Show full document tree</summary>

Returns the complete category and page structure of the documentation site.

No parameters required.

</details>

<details>
<summary><code>list_docs</code> — List docs by category</summary>

Lists all pages in a given category with titles, descriptions, and IDs.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `category` | string | No | Category name. Empty returns all categories. |

</details>

<details>
<summary><code>search_docs</code> — Full-text search</summary>

Searches across titles, descriptions, and page content. Returns ranked results with snippets.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `query` | string | Yes | Search term or phrase |
| `limit` | integer | No | Max results (default: `5`) |

</details>

<details>
<summary><code>fetch_doc</code> — Read a document</summary>

Returns the full content of a document as clean markdown.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `doc_ref` | string | Yes | Document ID, URL, or path |

</details>

<details>
<summary><code>refresh_index</code> — Re-crawl the site</summary>

Crawls the site again and replaces the in-memory index. Use it after the documentation
has been updated. Reports progress per page while crawling, and can be cancelled by the
client — cancelling stops the in-flight fetches.

No parameters required.

</details>

## Resources

| URI | Description |
|-----|-------------|
| `docs://{doc_ref}` | A page's markdown, addressed by ID, path, or URL |

## Prompts

| Name | Description |
|------|-------------|
| `explain_topic` | Search the docs for a topic, read the relevant pages, and answer with citations |

## How It Works

1. **Startup**: Fetches the homepage and sitemap.xml
2. **SPA Detection**: Compares a doc page response with the homepage — if identical, the site is SPA-only
3. **Static Mode**: Scrapes each page's HTML and extracts article content via BeautifulSoup + markdownify
4. **SPA Mode**: Parses `runtime.js` to find webpack chunk URLs, fetches each chunk, and extracts doc metadata + content from `JSON.parse()` calls and JSX children
5. **Indexing**: Builds in-memory indexes by ID, URL, path, and category for fast lookups

Crawling runs in the server's lifespan, not at import, and fetches pages concurrently
with an async HTTP client (10 at a time). A failed crawl leaves the server running with
an empty index; the tools then say so and point at `refresh_index`.

## Usage Examples

```
# Browse the doc structure
What categories are in the documentation?

# Search for a topic
Search for "authentication" in the docs

# Read a specific page
Show me the "getting-started" page content

# Category browsing
List all pages in the "guides" category
```

## Requirements

Python 3.10+ and MCP SDK 2.x (`mcp>=2.2,<3`). The server speaks the 2026-07-28 protocol
revision and still serves older MCP clients from the same process.

## License

MIT
