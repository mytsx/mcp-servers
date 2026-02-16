# n8n Chatbot MCP Server

Generic MCP server that turns any n8n Chat Trigger webhook into an MCP tool.

n8n'deki herhangi bir Chat Trigger webhook'unu MCP tool'una donusturur. Claude Desktop veya herhangi bir MCP client uzerinden n8n chatbot'larinizla konusabilirsiniz.

## Features

- Any n8n Chat Trigger webhook as an MCP tool
- Multi-turn conversation support via session IDs
- Auto-discovers n8n instance headers (X-Instance-Id)
- Fully configurable via environment variables
- Works with `uvx` - no installation needed

## Installation

### Using uvx (Recommended)

```json
{
  "mcpServers": {
    "my-chatbot": {
      "command": "uvx",
      "args": ["n8n-chatbot-mcp"],
      "env": {
        "N8N_CHATBOT_URL": "https://n8n.example.com/webhook/my-bot/chat",
        "N8N_CHATBOT_NAME": "HR Asistani",
        "N8N_CHATBOT_DESCRIPTION": "Sirket icin HR ve izin sorulari"
      }
    }
  }
}
```

### From source

```bash
cd n8n-chatbot-mcp
pip install -e .
```

## Configuration

| Environment Variable | Required | Default | Description |
|---------------------|----------|---------|-------------|
| `N8N_CHATBOT_URL` | Yes | - | Full n8n Chat Trigger webhook URL |
| `N8N_CHATBOT_NAME` | No | `n8n Chatbot` | Display name shown to the agent |
| `N8N_CHATBOT_DESCRIPTION` | No | - | What the chatbot knows about (helps the agent decide when to use it) |
| `N8N_CHATBOT_TIMEOUT` | No | `120` | Request timeout in seconds |

## Multiple Chatbots

You can register multiple n8n chatbots by adding separate MCP server entries:

```json
{
  "mcpServers": {
    "hr-bot": {
      "command": "uvx",
      "args": ["n8n-chatbot-mcp"],
      "env": {
        "N8N_CHATBOT_URL": "https://n8n.example.com/webhook/hr-bot/chat",
        "N8N_CHATBOT_NAME": "HR Asistani",
        "N8N_CHATBOT_DESCRIPTION": "Izin, maas ve yan haklar hakkinda bilgi verir"
      }
    },
    "it-bot": {
      "command": "uvx",
      "args": ["n8n-chatbot-mcp"],
      "env": {
        "N8N_CHATBOT_URL": "https://n8n.example.com/webhook/it-bot/chat",
        "N8N_CHATBOT_NAME": "IT Destek",
        "N8N_CHATBOT_DESCRIPTION": "VPN, email ve sistem erisim sorunlari"
      }
    }
  }
}
```

## Tool

### `ask_chatbot`

Sends a question to the n8n chatbot and returns the response.

**Parameters:**
- `question` (required) - The question to ask
- `session_id` (optional) - Session ID for multi-turn conversations. Auto-generated if omitted.

## License

MIT
