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

### Verified

All seven Python servers were started as real stdio subprocesses and negotiated
2026-07-28. mapeg-postgres-mcp was exercised against PostgreSQL 16 and mapeg-oracle-mcp
against Oracle Database 23ai. Both JS servers ship a smoke test (`npm test`) and were
verified over stdio.

### Known follow-ups

- The published PyPI/npm packages are still at 1.0.0; a `uvx`/`npx` install keeps getting
  the old, now-broken code until 2.0.0 is published.
- **agent-chat**: `_write_json` truncates the file before taking its lock, and message IDs
  come from `len(messages) + 1`. Concurrent writers to one room can still lose a message
  or collide on an ID. Fixing that means writing to a temp file and `os.replace`-ing it
  under a separate lock file — a change in its own right, not part of this migration.
