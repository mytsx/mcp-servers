#!/usr/bin/env bash
# Build and verify every distributable, without publishing anything.
#
# For each Python server this builds an sdist and a wheel, runs `twine check`,
# installs the wheel into a throwaway environment and starts the installed
# console script over stdio. For each Node server it packs a tarball and does
# the same through the packed bin. Nothing is uploaded.
#
#   ./scripts/build-release.sh
#
# Artifacts land in <server>/dist (Python) and dist/npm (Node).
set -euo pipefail

cd "$(dirname "$0")/.."

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

echo "== Python dağıtımları =="
for server in "${PYTHON_SERVERS[@]}"; do
  rm -rf "$server/dist"
  "$PYTHON" -m build --outdir "$server/dist" "$server" >/dev/null
  "$PYTHON" -m twine check "$server"/dist/* >/dev/null
  printf '  %-22s %s\n' "$server" "$(ls "$server/dist" | tr '\n' ' ')"
done

echo "== Node paketleri =="
mkdir -p dist/npm
rm -f dist/npm/*.tgz
for server in "${NODE_SERVERS[@]}"; do
  (cd "$server" && npm pack --pack-destination ../dist/npm --silent >/dev/null)
  printf '  %-22s %s\n' "$server" "$(ls dist/npm | grep "^$server-" || true)"
done

echo
echo "Yapıldı. Yayınlamadan önce doğrulama için:"
echo "  scripts/verify-release.py"
