# PostgreSQL MCP Server

[![Python](https://img.shields.io/badge/python-3.10+-blue?logo=python&logoColor=white)](https://python.org)
[![MCP](https://img.shields.io/badge/MCP-1.0+-purple)](https://modelcontextprotocol.io)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![PyPI](https://img.shields.io/pypi/v/mapeg-postgres-mcp)](https://pypi.org/project/mapeg-postgres-mcp/)

A Model Context Protocol (MCP) server for PostgreSQL databases. Query, explore, and analyze your PostgreSQL databases directly from any MCP-compatible AI client.

## Features

- **Execute SQL** — Run any SQL query with automatic result formatting
- **Natural Language Queries** — Ask questions in plain English or Turkish
- **Schema Exploration** — List tables, describe columns, view statistics
- **Execution Plans** — EXPLAIN / EXPLAIN ANALYZE with buffer stats
- **Query History** — Review past queries scoped to your database and workspace
- **Read-Only Mode** — Optional write protection via `READ_ONLY=true`
- **Zero Install** — Works with `uvx`, no virtual environment needed

## Quick Start

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
    }
  }
}
```

### Cursor

Add to `~/.cursor/mcp.json`:

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

### Windsurf

Add to Windsurf MCP config:

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
cd mapeg-postgres-mcp
pip install -e .
```

## Configuration

| Environment Variable | Required | Default | Description |
|---------------------|----------|---------|-------------|
| `DB_HOST` | No | `localhost` | PostgreSQL host |
| `DB_PORT` | No | `5432` | PostgreSQL port |
| `DB_NAME` | Yes | — | Database name |
| `DB_USER` | No | `postgres` | Database user |
| `DB_PASSWORD` | Yes | — | Database password |
| `READ_ONLY` | No | `false` | Block write operations (INSERT, UPDATE, DELETE, DROP, etc.) |

## Tools

<details>
<summary><code>execute_sql</code> — Run SQL queries</summary>

Execute any SQL query on the connected PostgreSQL database.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `sql` | string | Yes | SQL query to execute |
| `limit` | integer | No | Max rows to return (default: 100) |

</details>

<details>
<summary><code>natural_language_query</code> — Query in plain language</summary>

Convert natural language to SQL and execute. Supports Turkish and English.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `query` | string | Yes | Natural language query |

**Examples:** "show all tables", "tabloları listele", "show database info"

</details>

<details>
<summary><code>describe_table</code> — Table structure details</summary>

Get column definitions, row count, and table size.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `table_name` | string | Yes | Table name (`schema.table` or `table`) |

</details>

<details>
<summary><code>smart_query</code> — AI-powered query assistant</summary>

Analyzes your schema and suggests queries based on your question.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `question` | string | Yes | Question about your data |

</details>

<details>
<summary><code>explain_query</code> — Execution plan analysis</summary>

Show the EXPLAIN plan for a SQL query.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `sql` | string | Yes | SQL query to explain |
| `analyze` | boolean | No | Run EXPLAIN ANALYZE (default: false) |
| `format` | string | No | Output format: `text`, `json`, `yaml` (default: text) |
| `buffers` | boolean | No | Include buffer usage (requires analyze=true) |

</details>

<details>
<summary><code>get_query_history</code> — Review past queries</summary>

Retrieve recent query history scoped to this database and workspace.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `limit` | integer | No | Number of entries (default: 20) |
| `status` | string | No | Filter: `success` or `error` |
| `tool_name` | string | No | Filter by tool name |

</details>

## Resources

| URI | Description |
|-----|-------------|
| `postgresql://tables` | List all user tables |
| `postgresql://schema` | Detailed schema with columns |
| `postgresql://stats` | Database version and statistics |

## License

MIT
