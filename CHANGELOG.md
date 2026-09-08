# Changelog

## 2.0.0 — MCP SDK v2 migration

All nine servers moved to MCP SDK 2.x and protocol revision 2026-07-28. Every server
still serves 2025-era clients from the same process, so no client has to move with them.

| Server | From | To |
|--------|------|-----|
| agent-chat | `mcp[cli]>=1.0.0` | `mcp[cli]>=2.2,<3` |
| docusaurus-mcp | `mcp[cli]>=1.0.0` | `mcp[cli]>=2.2,<3` |
| gemini-reviews-mcp | `mcp>=1.0.0` | `mcp[cli]>=2.2,<3` |
| mapeg-oracle-mcp | `mcp>=1.0.0` | `mcp[cli]>=2.2,<3` |
| mapeg-postgres-mcp | `mcp>=1.0.0` | `mcp[cli]>=2.2,<3` |
| n8n-chatbot-mcp | `mcp[cli]>=1.0.0` | `mcp[cli]>=2.2,<3` |
| ssh-mcp-server | `mcp>=1.0.0` | `mcp[cli]>=2.2,<3` |
| asger-terminal-mcp | `@modelcontextprotocol/sdk@^0.5.0` | `@modelcontextprotocol/server@^2` |
| gib-api-mcp | `@modelcontextprotocol/sdk@^0.5.0` | `@modelcontextprotocol/server@^2` |

### Why this was not optional

`mcp.server.fastmcp` does not exist in SDK 2.x — it was removed, not deprecated. Any
environment that resolved `mcp` to 2.x could no longer start the Python servers at all.

### Across every server

- **Structured output.** Tools return typed models; each declares an `outputSchema` and
  returns `structuredContent`. Query results, command output, search hits and chat
  messages are JSON, not pre-rendered text.
- **Errors are errors.** Failures raise `ToolError` (or throw) instead of returning
  `"❌ ..."` / `"Hata: ..."` strings, which clients previously read as successful results.
- **Confirmation before damage.** Write queries, destructive shell commands, killing a
  process, overwriting a file and clearing a chat room now ask the user first, via
  elicitation. The question is skipped when there is nothing to lose — a new file, an
  append, an already-empty room.
- **No blocking the event loop.** psycopg2, oracledb and paramiko calls run on worker
  threads; the HTTP servers use async clients.
- **Lifespan-managed connections.** Database, SSH and HTTP clients are opened once by the
  lifespan and closed on shutdown, instead of being created lazily in module globals.
- **Progress and cancellation** on long operations, stdlib `logging` instead of `print`,
  tool titles and annotations, and per-argument descriptions from type hints.
- **Resources and prompts** per server: schemas, source code, logs and histories are
  readable directly, with prompts for the common investigations.

### Fixes that came with the rewrites

- **mapeg-oracle-mcp**: dictionary lookups now use bind variables, and names that must be
  interpolated are validated as Oracle identifiers first. `explain_plan` uses a random
  statement id, so concurrent calls no longer read each other's plan.
- **mapeg-postgres-mcp**: `EXPLAIN ANALYZE` is refused on a writing statement — it would
  have executed the write while claiming to only explain it.
- **ssh-mcp-server**: the blocklist is narrowed to what actually destroys the host.
  `rm -rf /` is still refused; `rm -rf /var/tmp/build`, which the old pattern also
  blocked, now goes through confirmation instead.
- **asger-terminal-mcp**: screenshots go to a temp directory instead of the package
  directory, `SESSION_FILE` is configurable, and `take_screenshot` returns the image
  rather than only a filename the client cannot open.
- **gib-api-mcp**: dates and amounts are validated before the call instead of being
  forwarded to the API as-is; `node-fetch` dropped for Node 20's built-in `fetch`.
- **mapeg-postgres-mcp**: every statement in the input is classified, not just the first.
  psycopg2 runs `SELECT 1; DELETE FROM t` as one call, and the leading `SELECT` used to
  clear it past both read-only mode and the confirmation.
- **ssh-mcp-server**: `chmod -R` and `chown -R` are recognised. The command was lowercased
  before being matched against a pattern that required an uppercase `R`, so a recursive
  permission change never asked for confirmation at all.
- **ssh-mcp-server**: when a write was auto-approved because the path did not exist, it is
  now an exclusive create. A file that appeared in between was previously overwritten
  without anyone being asked.
- **agent-chat**: reading a room no longer creates it. A mistyped room name in a read-only
  tool used to leave an empty phantom room behind in `list_rooms`.
- **mapeg-oracle-mcp**: Oracle native JSON keeps its object/array shape instead of being
  turned into a Python repr string.
- **mapeg-oracle-mcp**: a PL/SQL block is treated as a write. `BEGIN DELETE FROM t; END;`
  starts with `BEGIN`, so it used to skip both the confirmation and read-only mode.
- **mapeg-postgres-mcp**: a data-modifying CTE is treated as a write. The leading keyword of
  `WITH removed AS (DELETE ...) SELECT ...` is `WITH`, so it used to run unconfirmed.
- **mapeg-postgres-mcp** and **mapeg-oracle-mcp**: cancelling a call now cancels the query.
  A worker thread cannot be interrupted, so the statement kept running and holding its locks;
  the connection is asked to cancel instead.
- **mapeg-oracle-mcp**: the exploration tools record their calls in the query history again —
  the rewrite had left only `execute_sql` visible to `get_query_history`.
- **mapeg-oracle-mcp**: a BLOB read out of a LOB is normalized instead of putting raw bytes
  into a JSON result.
- **docusaurus-mcp**: a refresh that comes back empty keeps the working index instead of
  installing the empty one and reporting success with `doc_count=0`.
- **mapeg-postgres-mcp**: a `numeric` wider than an IEEE-754 float was converted to `float`
  and silently rounded on its way into the result. Decimals now travel as strings.
- **gib-api-mcp**: dates are checked against the calendar, not just for eight digits, so
  `20260231` and `20261301` no longer reach the tax API.
- **ssh-mcp-server** and **asger-terminal-mcp**: the destructive-command patterns only
  matched short flags, so `rm --recursive --force /` ran without confirmation — and, on the
  SSH server, without being blocked either. Both spellings are recognised now.
- **ssh-mcp-server**: `sftp_upload` in append mode reported the size of the whole rewritten
  file rather than the bytes it appended.
- **agent-chat**: `list_rooms` and the `chat://rooms` resource are advertised read-only but
  pruned stale agents from disk as a side effect of being read. They no longer write.
- **n8n-chatbot-mcp**: TLS certificate verification is on by default. It was disabled
  unconditionally (`verify=False`), which silently accepted any certificate. An n8n behind
  a self-signed certificate now needs `N8N_CHATBOT_VERIFY_TLS=false`, and the error names
  that flag so the fix is obvious.
- **agent-chat**: the read-modify-write of a room file happens under one exclusive lock and
  no longer truncates before locking, so concurrent agents cannot lose a message or derive
  the same next id from the same snapshot.

### Verified

All seven Python servers were started as real stdio subprocesses and negotiated
2026-07-28. mapeg-postgres-mcp was exercised against PostgreSQL 16 and mapeg-oracle-mcp
against Oracle Database 23ai. Both JS servers ship a smoke test (`npm test`) and were
verified over stdio.

### Known follow-ups

- The published PyPI/npm packages are still at 1.0.0; a `uvx`/`npx` install keeps getting
  the old, now-broken code until 2.0.0 is published.
- **ssh-mcp-server**: `ssh_activity_logger.py` sits next to the package rather than inside
  it, and `[tool.setuptools] packages` only ships `mcp_server_ssh`. In a published install
  the import fails and the optional-logger shim silently disables activity logging. Moving
  the module into the package would turn logging on for everyone by default — it writes a
  SQLite database of every command run — so where those logs live and whether they should
  be on is a decision of its own, not a migration fix.
