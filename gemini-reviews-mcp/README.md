# Gemini PR Reviews MCP Server

[![Python](https://img.shields.io/badge/python-3.10+-blue?logo=python&logoColor=white)](https://python.org)
[![MCP](https://img.shields.io/badge/MCP-2026--07--28-purple)](https://modelcontextprotocol.io)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![PyPI](https://img.shields.io/pypi/v/gemini-reviews-mcp)](https://pypi.org/project/gemini-reviews-mcp/)

Fetch [Gemini Code Assist](https://cloud.google.com/gemini/docs/codeassist/overview) PR reviews from GitHub. Auto-detects last PR, filters reviews after your last `/gemini review` comment, and returns raw JSON.

## Features

- **Auto-Auth** — Uses `gh` CLI token automatically, falls back to `GITHUB_TOKEN` env var
- **Smart Defaults** — Auto-detects repository owner and last PR number
- **Filtered Reviews** — Get only reviews after your last `/gemini review` comment
- **All Comment Types** — PR reviews, line comments, and issue comments
- **Full Pagination** — Handles large PRs with many comments
- **Structured Output** — Comments come back as typed JSON with per-kind counts, not a text blob
- **Progress Reporting** — Long fetches report which stage they are on
- **Review Resource** — `review://{owner}/{repo}/{pr}` reads a PR's full Gemini history directly
- **Prompt** — `address_review` walks the model through triaging and fixing the findings

## Quick Start

### Claude Code

```bash
# If you have gh CLI authenticated, no token needed:
claude mcp add gemini-reviews -- uvx gemini-reviews-mcp

# Or with explicit token:
claude mcp add gemini-reviews \
  -e GITHUB_TOKEN="ghp_your_token" \
  -- uvx gemini-reviews-mcp
```

### Claude Desktop

Add to your config file:

- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "gemini-reviews": {
      "command": "uvx",
      "args": ["gemini-reviews-mcp"]
    }
  }
}
```

> If `gh` CLI is installed and authenticated, no `GITHUB_TOKEN` env var is needed.

### Cursor

Add to `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "gemini-reviews": {
      "command": "uvx",
      "args": ["gemini-reviews-mcp"]
    }
  }
}
```

### Windsurf

Add to Windsurf MCP config:

```json
{
  "mcpServers": {
    "gemini-reviews": {
      "command": "uvx",
      "args": ["gemini-reviews-mcp"]
    }
  }
}
```

### VS Code

Add to your VS Code settings (JSON):

```json
"mcp": {
  "servers": {
    "gemini-reviews": {
      "type": "stdio",
      "command": "uvx",
      "args": ["gemini-reviews-mcp"]
    }
  }
}
```

### Gemini CLI

Add to `~/.gemini/settings.json`:

```json
{
  "mcpServers": {
    "gemini-reviews": {
      "command": "uvx",
      "args": ["gemini-reviews-mcp"]
    }
  }
}
```

### GitHub Copilot

Add to `~/.copilot/mcp-config.json`:

```json
{
  "mcpServers": {
    "gemini-reviews": {
      "command": "uvx",
      "args": ["gemini-reviews-mcp"]
    }
  }
}
```

### OpenAI Codex

Add to `~/.codex/config.toml`:

```toml
[mcp_servers.gemini-reviews]
command = "uvx"
args = ["gemini-reviews-mcp"]
```

### Install from Source

```bash
cd gemini-reviews-mcp
pip install -e .
```

## Authentication

The server resolves GitHub authentication in this order:

1. **`gh` CLI** (preferred) — If [GitHub CLI](https://cli.github.com/) is installed and authenticated (`gh auth login`), the token is obtained automatically via `gh auth token`. No configuration needed.

2. **`GITHUB_TOKEN` env var** (fallback) — Set manually if `gh` CLI is not available:
   ```bash
   # Create a token at https://github.com/settings/tokens with `repo` scope
   export GITHUB_TOKEN="ghp_your_token_here"
   ```

3. **No token** — Works for public repos only, with 60 requests/hour rate limit.

## Tool

<details>
<summary><code>get_gemini_reviews</code> — Fetch Gemini Code Assist PR reviews</summary>

Get Gemini Code Assist reviews from a GitHub PR. By default, fetches only reviews after your last `/gemini review` comment.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `repo` | string | Yes | Repository name (`repo`) or full path (`owner/repo`) |
| `pr` | integer | No | PR number (uses last PR if omitted) |
| `after_last_review` | boolean | No | Only fetch reviews after your last `/gemini review` comment (default: true) |
| `username` | string | No | GitHub username for filtering (defaults to authenticated user) |

Returns structured output:

| Field | Type | Description |
|-------|------|-------------|
| `repo` | string | Resolved `owner/repo` |
| `pr` | integer | Resolved PR number |
| `after_date` | string \| null | Cutoff applied, or null when the whole history was returned |
| `counts` | object | `reviews`, `line_comments`, `issue_comments` |
| `comments` | array | Reviews first, then line comments, then issue comments; each group oldest first |

Missing token, unresolvable owner, or no PR found are returned as tool errors the
model can act on, not as text that looks like a successful answer.

</details>

## Resources

| URI | Description |
|-----|-------------|
| `review://{owner}/{repo}/{pr}` | Every Gemini comment on that PR, as JSON |

## Prompts

| Name | Description |
|------|-------------|
| `address_review` | Fetch the review, rank the findings by severity, fix or justify each one |

## Usage Examples

```
# Simplest — auto-detect owner, last PR, filtered reviews
Use get_gemini_reviews for repo MyProject

# Specific PR
Use get_gemini_reviews for repo MyProject pr 42

# Get ALL reviews (not just after last comment)
Use get_gemini_reviews for repo MyProject with after_last_review false

# Full repo path
Use get_gemini_reviews for repo someone/TheirRepo
```

## Requirements

Python 3.10+ and MCP SDK 2.x (`mcp>=2.2,<3`). The server speaks the 2026-07-28 protocol
revision and still serves older MCP clients from the same process.

## License

MIT
