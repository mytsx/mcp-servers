# Oracle MCP Server

[![Python](https://img.shields.io/badge/python-3.10+-blue?logo=python&logoColor=white)](https://python.org)
[![MCP](https://img.shields.io/badge/MCP-2026--07--28-purple)](https://modelcontextprotocol.io)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![PyPI](https://img.shields.io/pypi/v/mapeg-oracle-mcp)](https://pypi.org/project/mapeg-oracle-mcp/)

A Model Context Protocol (MCP) server for Oracle databases. Query, explore, and analyze your Oracle databases directly from any MCP-compatible AI client. Supports Oracle 11g through 23ai with automatic version detection.

## Features

- **Execute SQL** — Run any Oracle SQL with automatic result formatting
- **Schema Tools** — Describe tables, search columns, view indexes and constraints
- **Source Code** — Read PL/SQL functions, procedures, packages, and triggers
- **Execution Plans** — EXPLAIN PLAN via DBMS_XPLAN with configurable detail levels
- **Relationships** — Foreign key analysis with incoming/outgoing direction filtering
- **DBMS_OUTPUT** — Automatic capture of PL/SQL output with buffer management
- **Query History** — Review past queries scoped to your database and workspace
- **Auto Version Detection** — Detects Oracle version (11g–23ai) dynamically
- **Thin Mode** — No Oracle Instant Client required
- **Read-Only Mode** — Optional write protection via `READ_ONLY=true`
- **Structured Output** — Every tool returns typed JSON: `execute_sql` gives `columns`, `rows`,
  `row_count`, `dbms_output` and `duration_ms` as separate fields instead of one text blob
- **Write Confirmation** — INSERT/UPDATE/DELETE/DROP is confirmed with the user before it runs,
  with an extra warning for the irreversible ones
- **Bind Variables** — Every dictionary lookup uses binds; names that must be interpolated are
  validated as Oracle identifiers first
- **Prompts** — `review_plsql` and `analyze_table` as ready-made investigation flows

## Quick Start

### Claude Code

```bash
claude mcp add oracle \
  -e ORACLE_CONNECTION_STRING="User Id=myuser;Password=mypass;Data Source=host:1521/service" \
  -- uvx mapeg-oracle-mcp
```

### Claude Desktop

Add to your config file:

- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "oracle": {
      "command": "uvx",
      "args": ["mapeg-oracle-mcp"],
      "env": {
        "ORACLE_CONNECTION_STRING": "User Id=myuser;Password=mypass;Data Source=(DESCRIPTION=(ADDRESS=(PROTOCOL=tcp)(HOST=localhost)(PORT=1521))(CONNECT_DATA=(SERVICE_NAME=ORCL)))"
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
    "oracle": {
      "command": "uvx",
      "args": ["mapeg-oracle-mcp"],
      "env": {
        "ORACLE_CONNECTION_STRING": "User Id=myuser;Password=mypass;Data Source=host:1521/service"
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
    "oracle": {
      "command": "uvx",
      "args": ["mapeg-oracle-mcp"],
      "env": {
        "ORACLE_CONNECTION_STRING": "User Id=myuser;Password=mypass;Data Source=host:1521/service"
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
    "oracle": {
      "type": "stdio",
      "command": "uvx",
      "args": ["mapeg-oracle-mcp"],
      "env": {
        "ORACLE_CONNECTION_STRING": "User Id=myuser;Password=mypass;Data Source=host:1521/service"
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
    "oracle": {
      "command": "uvx",
      "args": ["mapeg-oracle-mcp"],
      "env": {
        "ORACLE_CONNECTION_STRING": "User Id=myuser;Password=mypass;Data Source=host:1521/service"
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
    "oracle": {
      "command": "uvx",
      "args": ["mapeg-oracle-mcp"],
      "env": {
        "ORACLE_CONNECTION_STRING": "User Id=myuser;Password=mypass;Data Source=host:1521/service"
      }
    }
  }
}
```

### OpenAI Codex

Add to `~/.codex/config.toml`:

```toml
[mcp_servers.oracle]
command = "uvx"
args = ["mapeg-oracle-mcp"]

[mcp_servers.oracle.env]
ORACLE_CONNECTION_STRING = "User Id=myuser;Password=mypass;Data Source=host:1521/service"
```

### Install from Source

```bash
cd mapeg-oracle-mcp
pip install -e .
```

## Configuration

| Environment Variable | Required | Default | Description |
|---------------------|----------|---------|-------------|
| `ORACLE_CONNECTION_STRING` | Yes | — | Connection string: `User Id=...;Password=...;Data Source=...` |
| `READ_ONLY` | No | `false` | Block write operations (INSERT, UPDATE, DELETE, DROP, etc.) |

### Connection String Format

```
User Id=USERNAME;Password=PASSWORD;Data Source=(DESCRIPTION=(ADDRESS=(PROTOCOL=tcp)(HOST=hostname)(PORT=1521))(CONNECT_DATA=(SERVICE_NAME=service)))
```

Or the short form:

```
User Id=USERNAME;Password=PASSWORD;Data Source=hostname:1521/service_name
```

## Tools

<details>
<summary><code>execute_sql</code> — Run SQL queries</summary>

Execute any SQL query on the connected Oracle database. Supports SELECT, DML, DDL, and PL/SQL blocks with automatic DBMS_OUTPUT capture.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `sql` | string | Yes | Oracle SQL query or PL/SQL block |
| `limit` | integer | No | Row limit added to a SELECT with no ROWNUM/FETCH (default: 100) |

Returns `sql` (as actually run), `columns`, `rows`, `row_count`, `limit_applied`,
`dbms_output` and `duration_ms`. Dates become ISO-8601 strings, NUMBER becomes float, and
CLOBs are read into the result.

**Writes are confirmed first.** A statement starting with INSERT, UPDATE, DELETE, DROP,
ALTER, CREATE, TRUNCATE, MERGE, GRANT or REVOKE puts a question in front of the user before
anything runs; DROP, TRUNCATE and DELETE are flagged as irreversible. If the user declines,
nothing is executed. With `READ_ONLY=true` writes are refused without asking.

A PL/SQL block gets DBMS_OUTPUT enabled and drained around it, so whatever it printed comes
back in `dbms_output`.

</details>

<details>
<summary><code>describe_table</code> — Table structure details</summary>

Get column definitions and row count from USER_TAB_COLUMNS.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `table_name` | string | Yes | Table name (case-insensitive) |

</details>

<details>
<summary><code>get_source_code</code> — Read PL/SQL source</summary>

Retrieve source code for functions, procedures, packages, and triggers.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `object_name` | string | Yes | Object name (case-insensitive) |
| `object_type` | string | No | FUNCTION, PROCEDURE, TRIGGER, PACKAGE, PACKAGE BODY |

</details>

<details>
<summary><code>get_view_definition</code> — View SQL definition</summary>

Get the SQL definition of an Oracle view from USER_VIEWS.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `view_name` | string | Yes | View name (case-insensitive) |

</details>

<details>
<summary><code>search_tables</code> — Search tables by pattern</summary>

Find tables matching a name pattern.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `pattern` | string | Yes | Search pattern (supports `%` wildcard) |
| `limit` | integer | No | Max results (default: 100) |

</details>

<details>
<summary><code>search_columns</code> — Search columns across tables</summary>

Find columns matching a pattern, optionally filtered by data type.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `pattern` | string | Yes | Column name pattern (supports `%` wildcard) |
| `data_type` | string | No | Filter by data type (e.g., `VARCHAR2`) |
| `limit` | integer | No | Max results (default: 100) |

</details>

<details>
<summary><code>get_table_indexes</code> — Index information</summary>

List all indexes on a table with column details.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `table_name` | string | Yes | Table name (case-insensitive) |

</details>

<details>
<summary><code>get_table_constraints</code> — Constraint details</summary>

Get primary keys, foreign keys, unique and check constraints.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `table_name` | string | Yes | Table name (case-insensitive) |
| `constraint_type` | string | No | Filter: `P` (PK), `R` (FK), `C` (Check), `U` (Unique) |

</details>

<details>
<summary><code>analyze_table_size</code> — Table size and statistics</summary>

Row count, average row length, block count, and size in MB.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `table_name` | string | Yes | Table name (case-insensitive) |

</details>

<details>
<summary><code>get_table_relationships</code> — Foreign key relationships</summary>

Analyze incoming and outgoing foreign key relationships.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `table_name` | string | Yes | Table name (case-insensitive) |
| `direction` | string | No | `incoming`, `outgoing`, or `both` (default: both) |

</details>

<details>
<summary><code>list_database_objects</code> — List objects by type</summary>

List tables, views, functions, procedures, packages, triggers, sequences, or indexes.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `object_type` | string | Yes | TABLE, VIEW, FUNCTION, PROCEDURE, PACKAGE, TRIGGER, SEQUENCE, INDEX |
| `pattern` | string | No | Name pattern filter (supports `%` wildcard) |
| `limit` | integer | No | Max results (default: 100) |

</details>

<details>
<summary><code>explain_plan</code> — Execution plan analysis</summary>

Generate execution plans using EXPLAIN PLAN and DBMS_XPLAN.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `sql` | string | Yes | SQL query to explain |
| `format` | string | No | Detail level: `basic`, `typical`, `all` (default: typical) |

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
| `oracle://tables` | List all user tables |
| `oracle://schema` | Table columns from USER_TAB_COLUMNS |
| `oracle://stats` | Database version and instance info |
| `oracle://table/{table_name}` | One table's columns and row count |
| `oracle://source/{object_type}/{object_name}` | A PL/SQL object's source code |

## Prompts

| Name | Description |
|------|-------------|
| `review_plsql` | Read an object's source and review it for correctness and performance |
| `analyze_table` | Inspect a table's shape, statistics, indexes, constraints and relationships |

## Requirements

Python 3.10+ and MCP SDK 2.x (`mcp>=2.2,<3`). The server speaks the 2026-07-28 protocol
revision and still serves older MCP clients from the same process. All oracledb calls run on
a worker thread, so a slow query no longer blocks the server.

Verified against Oracle Database 23ai (Free).

## License

MIT
