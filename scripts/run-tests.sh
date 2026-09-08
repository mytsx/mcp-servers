#!/usr/bin/env bash
# Run every server's test suite.
#
# The two database servers need a live database; without one their tests skip
# rather than fail. To include them:
#
#   docker compose up -d postgres oracle
#   export DB_HOST=127.0.0.1 DB_PORT=5433 DB_NAME=testdb \
#          DB_USER=testuser DB_PASSWORD=testpass
#   export ORACLE_CONNECTION_STRING='User Id=testuser;Password=testpass;Data Source=127.0.0.1:1522/XEPDB1'
#
# No `set -e` on purpose: every suite runs even when an earlier one fails, and
# the exit status comes from the tally at the end.
set -uo pipefail

cd "$(dirname "$0")/.." || exit 1

PYTHON_SERVERS=(
  agent-chat
  docusaurus-mcp
  gemini-reviews-mcp
  mapeg-oracle-mcp
  mapeg-postgres-mcp
  n8n-chatbot-mcp
  ssh-mcp-server
)
NODE_SERVERS=(asger-terminal-mcp gib-api-mcp)

PYTHON="${PYTHON:-python3}"
failures=0

for server in "${PYTHON_SERVERS[@]}"; do
  printf '=== %s ===\n' "$server"
  if ! (cd "$server" && "$PYTHON" -m pytest tests -q); then
    failures=$((failures + 1))
  fi
done

for server in "${NODE_SERVERS[@]}"; do
  printf '=== %s ===\n' "$server"
  if ! (cd "$server" && npm test --silent); then
    failures=$((failures + 1))
  fi
done

if [ "$failures" -ne 0 ]; then
  printf '\n%d suite(s) failed\n' "$failures"
  exit 1
fi
printf '\nall suites passed\n'
