# n8n Chatbot MCP Server

[![Python](https://img.shields.io/badge/python-3.10+-blue?logo=python&logoColor=white)](https://python.org)
[![MCP](https://img.shields.io/badge/MCP-1.0+-purple)](https://modelcontextprotocol.io)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![PyPI](https://img.shields.io/pypi/v/n8n-chatbot-mcp)](https://pypi.org/project/n8n-chatbot-mcp/)

Turn any [n8n](https://n8n.io) Chat Trigger webhook into an MCP tool. Just provide the webhook URL — the server auto-discovers the chatbot name, description, welcome message, and required headers from the n8n Chat Trigger page.

## Features

- **Zero Config** — Only the webhook URL is required, everything else is auto-discovered
- **Auto-Discovery** — Extracts name, description, welcome message, and `X-Instance-Id` from the chat UI
- **Multi-Turn** — Session ID support for contextual conversations
- **Multiple Bots** — Register as many n8n chatbots as you want, each as a separate MCP server
- **Additive Description** — Auto-discovered subtitle + optional extra context via env var

## Quick Start

### Claude Code

```bash
claude mcp add my-chatbot \
  -e N8N_CHATBOT_URL="https://n8n.example.com/webhook/my-bot/chat" \
  -- uvx n8n-chatbot-mcp
```

### Claude Desktop

Add to your config file:

- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "my-chatbot": {
      "command": "uvx",
      "args": ["n8n-chatbot-mcp"],
      "env": {
        "N8N_CHATBOT_URL": "https://n8n.example.com/webhook/my-bot/chat"
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
    "my-chatbot": {
      "command": "uvx",
      "args": ["n8n-chatbot-mcp"],
      "env": {
        "N8N_CHATBOT_URL": "https://n8n.example.com/webhook/my-bot/chat"
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
    "my-chatbot": {
      "command": "uvx",
      "args": ["n8n-chatbot-mcp"],
      "env": {
        "N8N_CHATBOT_URL": "https://n8n.example.com/webhook/my-bot/chat"
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
    "my-chatbot": {
      "type": "stdio",
      "command": "uvx",
      "args": ["n8n-chatbot-mcp"],
      "env": {
        "N8N_CHATBOT_URL": "https://n8n.example.com/webhook/my-bot/chat"
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
    "my-chatbot": {
      "command": "uvx",
      "args": ["n8n-chatbot-mcp"],
      "env": {
        "N8N_CHATBOT_URL": "https://n8n.example.com/webhook/my-bot/chat"
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
    "my-chatbot": {
      "command": "uvx",
      "args": ["n8n-chatbot-mcp"],
      "env": {
        "N8N_CHATBOT_URL": "https://n8n.example.com/webhook/my-bot/chat"
      }
    }
  }
}
```

### OpenAI Codex

Add to `~/.codex/config.toml`:

```toml
[mcp_servers.my-chatbot]
command = "uvx"
args = ["n8n-chatbot-mcp"]

[mcp_servers.my-chatbot.env]
N8N_CHATBOT_URL = "https://n8n.example.com/webhook/my-bot/chat"
```

### Install from Source

```bash
cd n8n-chatbot-mcp
pip install -e .
```

## Configuration

| Environment Variable | Required | Default | Description |
|---------------------|----------|---------|-------------|
| `N8N_CHATBOT_URL` | Yes | — | Full n8n Chat Trigger webhook URL |
| `N8N_CHATBOT_DESCRIPTION` | No | — | Extra context **appended** to auto-discovered description |
| `N8N_CHATBOT_TIMEOUT` | No | `120` | Request timeout in seconds |

### Auto-Discovery

At startup the server makes a single GET request to the webhook URL and parses the n8n Chat Trigger HTML to extract:

- **Chatbot name** (from `i18n.title`) — used as the MCP server name
- **Chatbot description** (from `i18n.subtitle`) — used in the tool description
- **Welcome message** (from `initialMessages`) — included in tool context
- **X-Instance-Id header** — sent with every POST request

`N8N_CHATBOT_DESCRIPTION` is **additive**: the auto-discovered subtitle is always included, and the env var value is appended after it.

## Multiple Chatbots

Register as many n8n chatbots as you need — each one is a separate MCP server entry:

```json
{
  "mcpServers": {
    "hr-bot": {
      "command": "uvx",
      "args": ["n8n-chatbot-mcp"],
      "env": {
        "N8N_CHATBOT_URL": "https://n8n.example.com/webhook/hr-bot/chat"
      }
    },
    "it-bot": {
      "command": "uvx",
      "args": ["n8n-chatbot-mcp"],
      "env": {
        "N8N_CHATBOT_URL": "https://n8n.example.com/webhook/it-bot/chat",
        "N8N_CHATBOT_DESCRIPTION": "Also helps with VPN and system access issues"
      }
    }
  }
}
```

## Tool

<details>
<summary><code>ask_chatbot</code> — Send a question to the chatbot</summary>

Sends a question to the n8n chatbot and returns the response.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `question` | string | Yes | The question to ask |
| `session_id` | string | No | Session ID for multi-turn conversations (auto-generated if omitted) |

</details>

## License

MIT
