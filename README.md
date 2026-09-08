# MCP Servers

[![Python](https://img.shields.io/badge/python-3.10+-blue?logo=python&logoColor=white)](https://python.org)
[![TypeScript](https://img.shields.io/badge/typescript-5.0+-blue?logo=typescript&logoColor=white)](https://www.typescriptlang.org)
[![MCP](https://img.shields.io/badge/MCP-2026--07--28-purple)](https://modelcontextprotocol.io)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

A collection of [Model Context Protocol](https://modelcontextprotocol.io) servers for databases, remote access, automation, and developer tools. Each server works standalone with any MCP-compatible client.

All nine servers run on MCP SDK 2.x and speak protocol revision **2026-07-28**, while still
serving 2025-era clients from the same process. What that buys you, across the board:

- **Structured output** — every tool declares an `outputSchema` and returns `structuredContent`,
  so results are typed JSON instead of formatted text a client has to parse back
- **Real tool errors** — failures come back with `isError`, not as text that looks like an answer
- **Confirmation before damage** — destructive operations (write queries, `rm -rf`, killing a
  process, overwriting a file, wiping a chat room) ask the user first, and skip the question
  when there is nothing to lose
- **Progress and cancellation** — long operations report progress; cancelling a call cancels
  the work behind it
- **Resources and prompts** — schemas, logs and histories are readable as resources, with
  ready-made prompts for the common investigations
- **Tool annotations** — `readOnlyHint` / `destructiveHint` / `idempotentHint` on every tool

See [MIGRATION-V2.md](./MIGRATION-V2.md) for the per-server record of what changed.

## Tests

```bash
./scripts/run-tests.sh
```

Each server has its own suite: `pytest` for the Python servers, `npm test` for the Node ones.
The PostgreSQL and Oracle suites need a live database and skip themselves when one is not
configured — `docker-compose.yml` brings up both, and the script's header has the environment
variables to export.

## Servers

### Database

| Server | Package | Description |
|--------|---------|-------------|
| [PostgreSQL MCP](./mapeg-postgres-mcp) | [`mapeg-postgres-mcp`](https://pypi.org/project/mapeg-postgres-mcp/) | Query, explore, and analyze PostgreSQL databases with natural language support |
| [Oracle MCP](./mapeg-oracle-mcp) | [`mapeg-oracle-mcp`](https://pypi.org/project/mapeg-oracle-mcp/) | Oracle 11g–23ai with PL/SQL source, DBMS_OUTPUT, and auto version detection |

### Automation & Integrations

| Server | Package | Description |
|--------|---------|-------------|
| [n8n Chatbot MCP](./n8n-chatbot-mcp) | [`n8n-chatbot-mcp`](https://pypi.org/project/n8n-chatbot-mcp/) | Turn any n8n Chat Trigger webhook into an MCP tool with auto-discovery |
| [GIB API MCP](./gib-api-mcp) | [`gib-api-mcp`](https://www.npmjs.com/package/gib-api-mcp) | Turkish Revenue Administration (GIB) e-invoice API integration |

### Remote Access

| Server | Package | Description |
|--------|---------|-------------|
| [SSH MCP](./ssh-mcp-server) | [`mcp-server-ssh`](https://pypi.org/project/mcp-server-ssh/) | Remote command execution over SSH with session logging |
| [Asger Terminal MCP](./asger-terminal-mcp) | [`asger-terminal-mcp`](https://www.npmjs.com/package/asger-terminal-mcp) | Interactive web terminal with screenshot and OCR support |

### Documentation

| Server | Package | Description |
|--------|---------|-------------|
| [Docusaurus MCP](./docusaurus-mcp) | [`docusaurus-mcp`](https://pypi.org/project/docusaurus-mcp/) | Search, browse, and read any Docusaurus documentation site |

### Developer Tools

| Server | Package | Description |
|--------|---------|-------------|
| [Gemini Reviews MCP](./gemini-reviews-mcp) | [`gemini-reviews-mcp`](https://pypi.org/project/gemini-reviews-mcp/) | Fetch Gemini Code Assist PR reviews from GitHub |
| [Agent Chat MCP](./agent-chat) | [`agent-chat-mcp`](https://pypi.org/project/agent-chat-mcp/) | Multi-room chat for Claude Code agent instances |

## Quick Start

Install any server with a single command — no virtual environment needed:

```bash
# Python servers
uvx mapeg-postgres-mcp
uvx mapeg-oracle-mcp
uvx n8n-chatbot-mcp
uvx docusaurus-mcp
uvx gemini-reviews-mcp
uvx mcp-server-ssh
uvx agent-chat-mcp

# Node.js servers
npx -y asger-terminal-mcp
npx -y gib-api-mcp
```

### Claude Code

```bash
claude mcp add postgres \
  -e DB_HOST=localhost \
  -e DB_PORT=5432 \
  -e DB_NAME=mydb \
  -e DB_USER=postgres \
  -e DB_PASSWORD=secret \
  -- uvx mapeg-postgres-mcp
```

### Claude Desktop

Add to your config file:

- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "postgres": {
      "command": "uvx",
      "args": ["mapeg-postgres-mcp"],
      "env": {
        "DB_HOST": "localhost",
        "DB_PORT": "5432",
        "DB_NAME": "mydb",
        "DB_USER": "postgres",
        "DB_PASSWORD": "secret"
      }
    },
    "oracle": {
      "command": "uvx",
      "args": ["mapeg-oracle-mcp"],
      "env": {
        "ORACLE_CONNECTION_STRING": "User Id=myuser;Password=mypass;Data Source=host:1521/service"
      }
    },
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

Add to `~/.cursor/mcp.json` using the same format as Claude Desktop.

### Windsurf

Add to Windsurf MCP config using the same format as Claude Desktop.

### VS Code

Add to your VS Code settings (JSON):

```json
"mcp": {
  "servers": {
    "postgres": {
      "type": "stdio",
      "command": "uvx",
      "args": ["mapeg-postgres-mcp"],
      "env": {
        "DB_HOST": "localhost",
        "DB_PORT": "5432",
        "DB_NAME": "mydb",
        "DB_USER": "postgres",
        "DB_PASSWORD": "secret"
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
    "postgres": {
      "command": "uvx",
      "args": ["mapeg-postgres-mcp"],
      "env": {
        "DB_HOST": "localhost",
        "DB_PORT": "5432",
        "DB_NAME": "mydb",
        "DB_USER": "postgres",
        "DB_PASSWORD": "secret"
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
    "postgres": {
      "command": "uvx",
      "args": ["mapeg-postgres-mcp"],
      "env": {
        "DB_HOST": "localhost",
        "DB_PORT": "5432",
        "DB_NAME": "mydb",
        "DB_USER": "postgres",
        "DB_PASSWORD": "secret"
      }
    }
  }
}
```

### OpenAI Codex

Add to `~/.codex/config.toml`:

```toml
[mcp_servers.postgres]
command = "uvx"
args = ["mapeg-postgres-mcp"]

[mcp_servers.postgres.env]
DB_HOST = "localhost"
DB_PORT = "5432"
DB_NAME = "mydb"
DB_USER = "postgres"
DB_PASSWORD = "secret"
```

### Install from Source

```bash
# Python servers
cd mapeg-postgres-mcp
pip install -e .

# Node.js servers
cd asger-terminal-mcp
npm install
```

## Query Logging

Database MCP servers include a built-in `query_logger` module that writes to a shared SQLite database at `~/.local/share/mapeg-mcp/query_logs.db`. Each log entry includes:

- **`db_identifier`** — which database (e.g. `localhost:5432/mydb`)
- **`workspace_path`** — which project directory

The `get_query_history` tool lets agents review their own recent queries, scoped to their database and workspace.

### Query Dashboard

Monitor all database queries in real-time:

```bash
cd query_dashboard
pip install flask
python app.py
# Open http://localhost:5555
```

Supports filtering by server type, database, and workspace.

## Security

- Store credentials in environment variables, not in code
- Use `READ_ONLY=true` for database servers when write access isn't needed
- Prefer SSH key-based authentication over passwords
- All `.env` files are gitignored

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Commit your changes
4. Push and open a Pull Request

## Resources

- [MCP Documentation](https://modelcontextprotocol.io)
- [MCP Specification](https://spec.modelcontextprotocol.io)
- [Python MCP SDK](https://github.com/modelcontextprotocol/python-sdk)
- [TypeScript MCP SDK](https://github.com/modelcontextprotocol/typescript-sdk)

## License

MIT
