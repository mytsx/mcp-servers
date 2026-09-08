#!/usr/bin/env python3
"""Install every built artifact into a throwaway environment and start it.

This is the check that catches packaging bugs the test suites cannot: a missing
console script, a module left out of the wheel, an entry point that does not
run when the file is reached through npm's bin symlink. Nothing is published.

    ./scripts/build-release.sh
    ./scripts/verify-release.py

Requires the `mcp` client library (`pip install mcp`), plus uv and npm.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import anyio
from mcp import Client, StdioServerParameters

ROOT = Path(__file__).resolve().parents[1]

# Environment that lets each server start without reaching a real system. The
# point is that it starts and answers, not that it can do its job here.
PYTHON_SERVERS = [
    ("agent-chat", "agent-chat-mcp", {"AGENT_CHAT_DIR": "/tmp/verify-release-chat"}),
    ("docusaurus-mcp", "docusaurus-mcp", {"DOCUSAURUS_URL": "http://127.0.0.1:9"}),
    ("gemini-reviews-mcp", "gemini-reviews-mcp", {}),
    (
        "mapeg-oracle-mcp",
        "mapeg-oracle-mcp",
        {"ORACLE_CONNECTION_STRING": "User Id=x;Password=y;Data Source=127.0.0.1:9/X"},
    ),
    (
        "mapeg-postgres-mcp",
        "mapeg-postgres-mcp",
        {"DB_HOST": "127.0.0.1", "DB_PORT": "9", "DB_NAME": "x", "DB_USER": "x", "DB_PASSWORD": "x"},
    ),
    ("n8n-chatbot-mcp", "n8n-chatbot-mcp", {"N8N_CHATBOT_URL": "http://127.0.0.1:9/x"}),
    (
        "ssh-mcp-server",
        "mcp-server-ssh",
        {"SSH_HOST": "127.0.0.1", "SSH_PORT": "9", "SSH_KEEPALIVE_INTERVAL": "9999"},
    ),
]

NODE_SERVERS = [
    ("gib-api-mcp", "gib-api-mcp", {"GIB_API_URL": "http://127.0.0.1:9"}),
    (
        "asger-terminal-mcp",
        "asger-terminal-mcp",
        {
            "TERMINAL_URL": "https://example.invalid/",
            "SESSION_FILE": "/tmp/verify-release-session.json",
        },
    ),
]

EXPECTED_PROTOCOL = "2026-07-28"


async def _start(command: Path, env: dict[str, str], label: str) -> bool:
    params = StdioServerParameters(command=str(command), env={**os.environ, **env})
    try:
        with anyio.fail_after(120):
            async with Client(params) as client:
                tools = (await client.list_tools()).tools
                protocol = client.protocol_version
                status = "OK  " if protocol == EXPECTED_PROTOCOL else "WARN"
                print(f"{status} {label:22} proto={protocol} tools={len(tools)}")
                return protocol == EXPECTED_PROTOCOL
    except Exception as exc:  # noqa: BLE001 - the report is the point
        print(f"FAIL {label:22} {type(exc).__name__}: {str(exc)[:120]}")
        return False


async def check_python(directory: str, script: str, env: dict[str, str]) -> bool:
    wheels = sorted((ROOT / directory / "dist").glob("*.whl"))
    if not wheels:
        print(f"FAIL {directory:22} wheel yok — önce scripts/build-release.sh")
        return False

    venv = Path(tempfile.mkdtemp(prefix="verify-release-"))
    try:
        # No check=True and no pinned interpreter: a machine without the exact
        # version should fail this one package, not abort the whole run.
        created = subprocess.run(
            ["uv", "venv", str(venv), "-q"], capture_output=True, text=True
        )
        if created.returncode != 0:
            print(f"FAIL {directory:22} venv: {created.stderr.strip()[:120]}")
            return False

        python = venv / "bin" / "python"
        install = subprocess.run(
            ["uv", "pip", "install", "-q", "--python", str(python), str(wheels[-1])],
            capture_output=True,
            text=True,
        )
        if install.returncode != 0:
            print(f"FAIL {directory:22} kurulum: {install.stderr.strip()[:120]}")
            return False

        command = venv / "bin" / script
        if not command.exists():
            print(f"FAIL {directory:22} konsol betiği yok: {script}")
            return False
        return await _start(command, env, directory)
    finally:
        shutil.rmtree(venv, ignore_errors=True)


async def check_node(name: str, binary: str, env: dict[str, str]) -> bool:
    tarballs = sorted((ROOT / "dist" / "npm").glob(f"{name}-*.tgz"))
    if not tarballs:
        print(f"FAIL {name:22} tarball yok — önce scripts/build-release.sh")
        return False

    project = Path(tempfile.mkdtemp(prefix="verify-release-"))
    try:
        started = subprocess.run(
            ["npm", "init", "-y"], cwd=project, capture_output=True, text=True
        )
        if started.returncode != 0:
            print(f"FAIL {name:22} npm init: {started.stderr.strip()[:120]}")
            return False

        install = subprocess.run(
            ["npm", "install", "--silent", str(tarballs[-1])],
            cwd=project,
            capture_output=True,
            text=True,
        )
        if install.returncode != 0:
            print(f"FAIL {name:22} kurulum: {install.stderr.strip()[:120]}")
            return False

        # Deliberately the bin symlink, not the file: that is what npx runs.
        command = project / "node_modules" / ".bin" / binary
        if not command.exists():
            print(f"FAIL {name:22} bin yok: {binary}")
            return False
        return await _start(command, env, name)
    finally:
        shutil.rmtree(project, ignore_errors=True)


async def main() -> None:
    results: list[bool] = []
    print("== Python paketleri ==")
    for directory, script, env in PYTHON_SERVERS:
        results.append(await check_python(directory, script, env))

    print("== Node paketleri ==")
    for name, binary, env in NODE_SERVERS:
        results.append(await check_node(name, binary, env))

    failed = results.count(False)
    print()
    if failed:
        print(f"{failed} paket doğrulanamadı — yayınlama.")
        sys.exit(1)
    print(f"{len(results)} paketin tamamı kuruldu ve {EXPECTED_PROTOCOL} konuşuyor.")


if __name__ == "__main__":
    anyio.run(main)
