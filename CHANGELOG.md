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
- **docusaurus-mcp**: a webpack chunk that fails to load is recorded as a failure rather than
  treated as a chunk holding no document, so an SPA site's partial outage is refused like a
  static one's.
- **ssh-mcp-server**: the keepalive worker and ssh_reconnect go through the same connection
  lock as everything else, so a background reconnect cannot race a request's.
- **ssh-mcp-server**: only an actual collision is reported as one — an unwritable parent or an
  exhausted quota now says what it is instead of sending the caller round the same retry.
- **mapeg-oracle-mcp**: the read-only transaction is renewed per call. Opening one at connect
  froze its snapshot, so every later call served the startup view of the database.
  `explain_plan` says plainly that it needs `READ_ONLY=false`, since it writes to PLAN_TABLE.
- **ssh-mcp-server**: SFTP append uses the server's append mode instead of rewriting the
  whole file, so two overlapping appends cannot discard each other.
- **ssh-mcp-server** and **asger-terminal-mcp**: quote removal concatenates the way a shell
  does — `r''m -rf /` runs `rm` — and `chmod`/`chown` options are recognised after the
  operands as well.
- **ssh-mcp-server**: establishing the connection is serialized, so two callers finding a
  dead link cannot each build a client and strand one of them.
- **mapeg-oracle-mcp**: LOB values are normalized on the worker thread; reading a CLOB is
  blocking I/O that was happening on the event loop.
- **mapeg-oracle-mcp**: `get_table_constraints` asks only for the four types it models, and
  `get_source_code` records failures in the query history like the other exploration tools.
- **docusaurus-mcp**: a crawl that lost pages is refused rather than installed — losing one
  page of three still leaves a non-empty index, and those pages would silently stop being
  findable.
- **gemini-reviews-mcp**: a token is required only for what needs one. A fully specified
  public PR reads through unauthenticated endpoints again, as the README says it does.
- The exploration tools and `extract_text` are no longer advertised read-only: they write a
  query-history row and a screenshot directory respectively.
- **mapeg-postgres-mcp** and **mapeg-oracle-mcp**: read-only mode is enforced by the database,
  not only by reading the statement. A plain `SELECT destructive_function()` is a write that
  no classifier can see, so the session itself is opened read-only.
- **ssh-mcp-server** and **asger-terminal-mcp**: quotes cannot shield a nested command —
  `sh -c 'echo ok; rm --no-preserve-root -rf /'` is still a root removal.
- **agent-chat**: an auto-approved clear refuses state that appeared after the check, rather
  than deleting it unasked.
- **agent-chat**: pruning stale agents is one locked read-modify-write, so a join landing
  mid-prune is no longer erased.
- **agent-chat**: valid JSON of the wrong shape is reset before the mutator sees it, instead
  of failing halfway through an operation that has already written another file.
- **mapeg-postgres-mcp** and **mapeg-oracle-mcp**: `get_query_history` is not advertised
  read-only — opening the history database creates its directory and runs migrations.
- **mapeg-postgres-mcp** and **mapeg-oracle-mcp**: write detection is an allowlist. Anything
  not provably read-only counts as a write, so the classifier no longer has to have heard of
  every statement that can change data — `COPY ... FROM PROGRAM`, `PURGE`, `LOCK`, `SET` and
  whatever comes next are all covered by default.
- **ssh-mcp-server** and **asger-terminal-mcp**: each command in a shell line is classified
  on its own. `rm --no-preserve-root -rf /; true` escaped a rule anchored to the end of the
  input.
- **agent-chat**: `touch` is an atomic read-modify-write and never creates a room, so a
  polling call cannot write a stale roster back over a clear.
- **agent-chat**: a room written by the 1.x server stays readable — `priority` was an
  unconstrained string there, and an unknown value used to fail the whole history.
- **agent-chat**: replacing a room file writes the requested type rather than mutating
  whatever was decoded, so an `agents.json` holding `[]` cannot turn a join into a list
  append that disappears on the next read.
- **docusaurus-mcp**: pages that answer 404 or 503 are left out of the index instead of being
  stored as error pages, which a non-empty check would then accept as a good crawl.
- **gib-api-mcp**: the prompt validates its arguments the way its tools do.
- **mapeg-postgres-mcp**: `SELECT ... INTO t` is treated as a write — it creates that table.
- **ssh-mcp-server** and **asger-terminal-mcp**: the whole `rm` argument list is scanned, not
  only the leading options. GNU rm accepts options after the operands, so
  `rm /tmp/missing -rf /var` deleted recursively without being confirmed or blocked.
- **mapeg-postgres-mcp** and **mapeg-oracle-mcp**: the connection is established under the
  same lock that owns the query, so two first requests cannot each build one and leave the
  loser leaked while a watchdog cancels the wrong connection.
- **mapeg-oracle-mcp**: a PL/SQL block's DBMS_OUTPUT is enabled, run and drained under one
  lock. The buffer belongs to the session, so overlapping blocks could read each other's
  output.
- **mapeg-oracle-mcp**: a BLOB reports its size without being read into memory first.
- **agent-chat**: `send_message` writes presence and the message under the room lock, so a
  clear cannot land between them; and the mutating tools no longer claim to be idempotent.
- **mapeg-postgres-mcp**: `EXPLAIN ANALYZE <write>` is treated as a write. PostgreSQL runs
  the statement it wraps, so `EXPLAIN ANALYZE DELETE FROM t` used to delete rows through
  `execute_sql` unconfirmed and under read-only mode.
- **mapeg-postgres-mcp**: the row-count and size queries for a table go through
  `psycopg2.sql.Identifier` and bind parameters. A table can legally be named
  `x"; DELETE FROM t; --`, and hand-quoting it turned reading that table into running it.
- **mapeg-postgres-mcp** and **mapeg-oracle-mcp**: one query at a time per connection.
  Every request shared a connection, so a request cancelled while waiting for it could
  cancel the query another request was running.
- **ssh-mcp-server**: each command's cancellation closes its own channel. A single shared
  field meant one call's cancellation could close a concurrent call's command.
- **ssh-mcp-server** and **asger-terminal-mcp**: options that carry a value no longer hide a
  destructive flag — `rm --interactive=never -r /path` used to run unconfirmed.
- **mapeg-postgres-mcp**: `CALL` and `DO` are treated as writes — they run code this server
  cannot see into, the way a PL/SQL block does on the Oracle side.
- **mapeg-postgres-mcp**: literal and comment masking preserves offsets. It was used to find
  statement boundaries in the original text, so a shorter replacement shifted every later
  offset and split `SELECT 'x'; DELETE FROM t` in the wrong place.
- **ssh-mcp-server**: cancelling a call closes the command's channel, so the remote command
  stops instead of running on to its timeout.
- **ssh-mcp-server**: a failed reconnect no longer burns the remaining retries on a missing
  client, and the error reported names the reconnect failure.
- **agent-chat**: clearing a room holds a room-wide lock, so a join cannot interleave between
  the two files and leave a room that is neither cleared nor intact.
- **asger-terminal-mcp**: `take_screenshot` is no longer advertised read-only — it writes a
  PNG and keeps it.
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

### Release

`scripts/build-release.sh` builds every distributable and `scripts/verify-release.py`
installs each one into a throwaway environment and starts it over stdio. All nine
packages install clean and negotiate 2026-07-28; `RELEASING.md` has the upload steps.

That check earned its keep immediately: both Node servers were packaged with an entry
point that did nothing when installed. npm links the bin into `node_modules/.bin`, so
`process.argv[1]` is that symlink while `import.meta.url` is the real file — comparing
them unresolved meant `npx -y gib-api-mcp` started a process that exited silently. The
paths are resolved now, and both suites drive the server through a symlink to keep it
that way.

### Known follow-ups

- The published PyPI/npm packages are still at 1.0.0; a `uvx`/`npx` install keeps getting
  the old, now-broken code until 2.0.0 is published.
- **ssh-mcp-server**: `ssh_activity_logger.py` sits next to the package rather than inside
  it, and `[tool.setuptools] packages` only ships `mcp_server_ssh`. In a published install
  the import fails and the optional-logger shim silently disables activity logging. Moving
  the module into the package would turn logging on for everyone by default — it writes a
  SQLite database of every command run — so where those logs live and whether they should
  be on is a decision of its own, not a migration fix.
