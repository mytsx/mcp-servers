# Gemini PR Reviews MCP Server

[![Python](https://img.shields.io/badge/python-3.10+-blue?logo=python&logoColor=white)](https://python.org)
[![MCP](https://img.shields.io/badge/MCP-1.0+-purple)](https://modelcontextprotocol.io)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![PyPI](https://img.shields.io/pypi/v/gemini-reviews-mcp)](https://pypi.org/project/gemini-reviews-mcp/)

Fetch [Gemini Code Assist](https://cloud.google.com/gemini/docs/codeassist/overview) PR reviews from GitHub. Auto-detects last PR, filters reviews after your last `/gemini review` comment, and returns raw JSON.

## Features

- **Auto-Auth** — Uses `gh` CLI token automatically, falls back to `GITHUB_TOKEN` env var
- **Smart Defaults** — Auto-detects repository owner and last PR number
- **Filtered Reviews** — Get only reviews after your last `/gemini review` comment
- **All Comment Types** — PR reviews, line comments, and issue comments
- **Full Pagination** — Handles large PRs with many comments

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

</details>

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

## License

MIT
