# PostgreSQL MCP Server

[![Python](https://img.shields.io/badge/python-3.10+-blue?logo=python&logoColor=white)](https://python.org)
[![MCP](https://img.shields.io/badge/MCP-2026--07--28-purple)](https://modelcontextprotocol.io)
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
- **Structured Output** — Results come back as typed JSON (`columns`, `rows`, `row_count`,
  `duration_ms`), not an ASCII table you have to parse back
- **Write Confirmation** — Any INSERT/UPDATE/DELETE/DROP is confirmed with the user before it
  runs, with an extra warning for the irreversible ones
- **Prompts** — `analyze_table` and `optimize_query` as ready-made investigation flows

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
| `limit` | integer | No | Row limit added to a SELECT that has no LIMIT (default: 100) |

Returns `sql` (as actually run), `columns`, `rows`, `row_count`, `limit_applied` and
`duration_ms`. Non-JSON column types are converted: numerics become floats, timestamps
become ISO-8601 strings, bytes become a size marker.

**Writes are confirmed first.** A statement starting with INSERT, UPDATE, DELETE, DROP,
ALTER, CREATE, TRUNCATE, MERGE, GRANT or REVOKE puts a question in front of the user before
anything runs; DROP, TRUNCATE and DELETE are flagged as irreversible in that question. If the
user declines, nothing is executed. With `READ_ONLY=true` writes are refused without asking.

</details>

<details>
<summary><code>natural_language_query</code> — Query in plain language</summary>

Answers a fixed set of questions without writing SQL: list tables, list users, list schemas,
show database info. Supports Turkish and English phrasing.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `query` | string | Yes | Natural language query |

**Examples:** "show all tables", "tabloları listele", "show database info"

This is keyword matching, not a text-to-SQL model. Anything outside those four questions
returns a tool error naming what it does understand — write the SQL yourself and use
`execute_sql`.

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

Returns the public schema's tables and columns as context for answering a question. It does
not write or run SQL: read the returned schema, then use `execute_sql`.

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

`analyze=true` actually runs the query, so it is refused on a statement that writes.

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
| `postgresql://table/{schema}/{table}` | One table's columns, row count and size |

## Prompts

| Name | Description |
|------|-------------|
| `analyze_table` | Inspect a table's shape, sample its data, and report data-quality issues |
| `optimize_query` | Read the plan, find the expensive step, propose and re-check a fix |

## Requirements

Python 3.10+ and MCP SDK 2.x (`mcp>=2.2,<3`). The server speaks the 2026-07-28 protocol
revision and still serves older MCP clients from the same process. All psycopg2 calls run on
a worker thread, so a slow query no longer blocks the server.

## License

MIT
