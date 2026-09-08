"""Drive the SSH server in-process against a fake remote host.

Every blocking paramiko call is replaced, so the tests exercise the tool
surface, the confirmation flow and the safety rules without a real SSH server.
"""

import os
import sys
from pathlib import Path

import anyio
import pytest
from mcp import Client
from mcp.types import ElicitResult

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


class FakeHost:
    """A remote filesystem and command runner, in memory."""

    def __init__(self) -> None:
        self.files: dict[str, bytes] = {"/etc/motd": b"merhaba dunya\n"}
        self.commands: list[str] = []
        # When set, this path reports absent once and then springs into
        # existence, standing in for another process creating it.
        self.appears_after_check: str | None = None

    def install(self, connection_class, monkeypatch) -> None:
        """Replace every blocking paramiko call with this host's own.

        These are already-bound methods, so the SSHConnection instance is not
        passed to them; they take exactly the arguments the caller supplies.
        """
        monkeypatch.setattr(
            connection_class, "_connect_blocking", lambda conn: setattr(conn, "client", self)
        )
        monkeypatch.setattr(
            connection_class, "_is_alive_blocking", lambda conn: conn.client is not None
        )
        monkeypatch.setattr(connection_class, "_exec_blocking", self._exec)
        monkeypatch.setattr(connection_class, "_read_file_blocking", self._read)
        monkeypatch.setattr(connection_class, "_write_file_blocking", self._write)
        monkeypatch.setattr(connection_class, "_file_exists_blocking", self._exists)

    def _exec(self, command: str, _timeout: int, channel_holder: dict) -> tuple[str, str, int]:
        # Mirrors the real signature: each call publishes its own channel so a
        # cancellation closes the command it belongs to.
        channel_holder["channel"] = None
        self.commands.append(command)
        if command.startswith(("head -n", "cat ")):
            path = command.split("'")[1] if "'" in command else command.split()[-1]
            data = self.files.get(path)
            return ((data or b"").decode(), "" if data else "No such file", 0 if data else 1)
        if command.startswith("ls -la"):
            return ("total 4\ndrwx r-x\n", "", 0)
        if command.startswith("ps "):
            return ("USER PID CMD\nroot 1 init\n", "", 0)
        if command.startswith("kill "):
            return ("", "", 0)
        return (f"output of {command}\n", "", 0)

    def _read(self, path: str) -> bytes:
        if path not in self.files:
            raise FileNotFoundError(path)
        return self.files[path]

    def _write(self, path: str, content: str, append: bool, exclusive: bool = False) -> int:
        if exclusive and path in self.files:
            raise FileExistsError(path)
        existing = self.files.get(path, b"").decode() if append else ""
        self.files[path] = (existing + content).encode()
        return len(content.encode("utf-8"))  # what this call added

    def _exists(self, path: str) -> bool:
        if path == self.appears_after_check:
            self.appears_after_check = None
            self.files[path] = b"someone else got here first"
            return False
        return path in self.files


@pytest.fixture()
def host():
    return FakeHost()


@pytest.fixture()
def raw_module(monkeypatch):
    """The server module with nothing patched, for testing its own internals."""
    monkeypatch.setenv("SSH_HOST", "testhost")
    monkeypatch.setenv("SSH_USER", "ops")
    monkeypatch.setenv("SSH_PORT", "2222")
    monkeypatch.setenv("SSH_KEEPALIVE_INTERVAL", "9999")
    for module in [m for m in sys.modules if m.startswith("mcp_server_ssh")]:
        del sys.modules[module]

    import mcp_server_ssh.server as module

    return module


@pytest.fixture()
def server_module(monkeypatch, host):
    monkeypatch.setenv("SSH_HOST", "testhost")
    monkeypatch.setenv("SSH_USER", "ops")
    monkeypatch.setenv("SSH_PORT", "2222")
    # Keep the background keepalive out of the way of a short test.
    monkeypatch.setenv("SSH_KEEPALIVE_INTERVAL", "9999")
    for module in [m for m in sys.modules if m.startswith("mcp_server_ssh")]:
        del sys.modules[module]

    import mcp_server_ssh.server as module

    host.install(module.SSHConnection, monkeypatch)
    return module


def _client(server_module, confirm=True, asked=None):
    async def elicit(context, params):
        if asked is not None:
            asked.append(params.message)
        return ElicitResult(action="accept", content={"confirm": confirm})

    return Client(server_module.mcp, elicitation_callback=elicit)


@pytest.mark.parametrize(
    ("command", "blocked", "needs_confirmation"),
    [
        ("rm -rf /", True, True),
        ("rm -rf /*", True, True),
        ("rm -rf /var", True, True),
        ("mkfs.ext4 /dev/sda", True, False),
        # A path under a system directory is destructive but legitimate: it is
        # confirmed rather than refused.
        ("rm -rf /var/tmp/build", False, True),
        ("rm -rf ./build", False, True),
        # GNU long options are the same command; matching only "-rf" let these
        # run unconfirmed.
        ("rm --recursive --force /", True, True),
        ("rm -r -f /", True, True),
        ("rm --recursive --force /var", True, True),
        ("rm --recursive --force /var/tmp/build", False, True),
        ("rm --recursive ./build", False, True),
        # A destructive flag anywhere in the options, not just the first one.
        ("rm -v -r /", True, True),
        ("rm --verbose --recursive /", True, True),
        ("rm -v -r /tmp/build", False, True),
        ("rm -i -r ./build", False, True),
        # ...but reading the manual is not destructive.
        ("rm --help", False, False),
        ("rm file.txt", False, False),
        # Recursive permission changes: the pattern used to be matched against a
        # lowercased command, so an uppercase -R could never fire.
        ("chmod -R 755 /var/www", False, True),
        ("chown -R user:group /srv", False, True),
        ("chmod --recursive 755 /srv", False, True),
        ("chmod -v -R 755 /srv", False, True),
        ("chmod 755 file", False, False),
        ("chmod a-r file", False, False),
        # GNU rm takes options after the operands too.
        ("rm /tmp/missing -rf /var", True, True),
        ("rm file -r dir", False, True),
        ("rm --interactive=never -r /var/tmp/build", False, True),
        ("rm dosya.txt", False, False),
        # A blocked command stays blocked when something follows it: rules
        # anchored to the end of the input were defeated by a trailing `; true`.
        ("rm --no-preserve-root -rf /; true", True, True),
        ("rm -rf / && echo ok", True, True),
        ("echo hi; rm -rf /var", True, True),
        ("rm -rf /tmp/x; true", False, True),
        ("echo ok; ls", False, False),
        # A nested shell hides the command behind quotes; the closing quote used
        # to stop an end-anchored rule from matching what still runs.
        ("sh -c 'echo ok; rm --no-preserve-root -rf /'", True, True),
        ('bash -c "rm -rf /"', True, True),
        ("sh -c 'ls'", False, False),
        # A shell concatenates the fragments of one word, so this runs `rm`.
        ("r''m -rf --no-preserve-root /", True, True),
        # chmod and chown take options after their operands too.
        ("chmod 755 /srv -R", False, True),
        ("chown user /srv --recursive", False, True),
        ("chmod 755 /srv", False, False),
        ("reboot now", False, True),
        ("docker system prune -f", False, True),
        ("ls -la", False, False),
        ("uptime", False, False),
    ],
)
def test_command_safety_classification(server_module, command, blocked, needs_confirmation):
    assert bool(server_module.blocked_reason(command)) is blocked
    assert (server_module.confirm_reason(command) is not None) is needs_confirmation


def test_ordinary_command_runs_without_asking(server_module):
    asked: list[str] = []

    async def run():
        async with _client(server_module, asked=asked) as client:
            result = await client.call_tool("execute_command", {"command": "uptime"})
            assert result.structured_content["exit_code"] == 0
            assert result.structured_content["stdout"] == "output of uptime\n"
            assert asked == []

    anyio.run(run)


def test_destructive_command_is_confirmed(server_module, host):
    asked: list[str] = []

    async def run():
        async with _client(server_module, confirm=True, asked=asked) as client:
            result = await client.call_tool(
                "execute_command", {"command": "rm -rf /var/tmp/build"}
            )
            assert result.is_error is False
            assert asked and "dosya/dizin siliyor" in asked[0]

    anyio.run(run)


def test_declined_command_never_runs(server_module, host):
    async def run():
        async with _client(server_module, confirm=False) as client:
            result = await client.call_tool("execute_command", {"command": "reboot now"})
            assert result.is_error is True
            assert "onaylamadı" in result.content[0].text
            assert "reboot now" not in host.commands

    anyio.run(run)


def test_blocked_command_is_refused_outright(server_module, host):
    async def run():
        async with _client(server_module, confirm=True) as client:
            result = await client.call_tool("execute_command", {"command": "rm -rf /"})
            assert result.is_error is True
            assert "güvenlik" in result.content[0].text
            assert "rm -rf /" not in host.commands

    anyio.run(run)


def test_file_operations(server_module, host):
    async def run():
        async with _client(server_module) as client:
            read = await client.call_tool(
                "file_operations", {"operation": "read", "path": "/etc/motd"}
            )
            assert read.structured_content["content"].startswith("merhaba")

            missing = await client.call_tool(
                "file_operations", {"operation": "exists", "path": "/nope"}
            )
            assert missing.structured_content["exists"] is False

            # Creating a new file has nothing to lose, so nothing is asked.
            created = await client.call_tool(
                "file_operations",
                {"operation": "write", "path": "/tmp/new.txt", "content": "x"},
            )
            assert created.structured_content["bytes_written"] == 1

    anyio.run(run)


def test_overwriting_an_existing_file_is_confirmed(server_module, host):
    asked: list[str] = []

    async def run():
        async with _client(server_module, confirm=False, asked=asked) as client:
            result = await client.call_tool(
                "file_operations",
                {"operation": "write", "path": "/etc/motd", "content": "y"},
            )
            assert result.is_error is True
            assert asked and "/etc/motd" in asked[0]
            # The original content survived the refusal.
            assert host.files["/etc/motd"] == b"merhaba dunya\n"

    anyio.run(run)


def test_kill_requires_a_numeric_pid(server_module):
    async def run():
        async with _client(server_module) as client:
            result = await client.call_tool(
                "process_manager", {"action": "kill", "target": "nginx"}
            )
            assert result.is_error is True
            assert "sayısal PID" in result.content[0].text

    anyio.run(run)


def test_system_monitor_reports_every_metric(server_module):
    seen: list[tuple] = []

    async def on_progress(progress, total, message):
        seen.append((progress, total, message))

    async def run():
        async with _client(server_module) as client:
            result = await client.call_tool(
                "system_monitor", {"metric": "all"}, progress_callback=on_progress
            )
            metrics = [r["metric"] for r in result.structured_content["readings"]]
            assert metrics == ["cpu", "memory", "disk", "network"]
            assert len(seen) == len(metrics) + 1

    anyio.run(run)


def test_status_resources_are_listed(server_module):
    async def run():
        async with Client(server_module.mcp) as client:
            uris = [str(r.uri) for r in (await client.list_resources()).resources]
            assert uris == [
                "ssh://system",
                "ssh://processes",
                "ssh://disk",
                "ssh://network",
                "ssh://logs",
            ]
            body = (await client.read_resource("ssh://disk")).contents[0].text
            assert body.startswith("Disk Usage — ops@testhost:2222")

            assert [p.name for p in (await client.list_prompts()).prompts] == ["diagnose_server"]

    anyio.run(run)


class _StubSFTP:
    """The two SFTP calls _write_file_blocking makes, over an in-memory file."""

    def __init__(self, files: dict[str, bytes]) -> None:
        self.files = files

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def open(self, path: str, mode: str):
        stub = self

        class _Handle:
            def __enter__(self_inner):
                if "r" in mode and path not in stub.files:
                    raise FileNotFoundError(path)
                if "x" in mode and path in stub.files:
                    raise FileExistsError(path)
                return self_inner

            def __exit__(self_inner, *args):
                return False

            def read(self_inner) -> bytes:
                return stub.files[path]

            def write(self_inner, data: str) -> None:
                if "a" in mode:
                    stub.files[path] = stub.files.get(path, b"") + data.encode("utf-8")
                else:
                    stub.files[path] = data.encode("utf-8")

        return _Handle()


def test_write_file_blocking_reports_only_what_it_added(raw_module):
    """size_bytes is what this call added, not the size of the whole file.

    This drives the real _write_file_blocking, not the fake host, because the
    inflated count came from that function rewriting the whole file in append
    mode and then measuring the buffer it wrote. It appends at the server now,
    so there is no buffer to measure and no read-modify-write to race.
    """
    files = {"/var/log/app.log": b"x" * 1000}
    connection = raw_module.SSHConnection(raw_module.SSHConfig.from_env())
    connection.client = type("_Client", (), {"open_sftp": lambda self: _StubSFTP(files)})()

    appended = connection._write_file_blocking("/var/log/app.log", "yz", append=True)
    assert appended == 2
    assert len(files["/var/log/app.log"]) == 1002

    replaced = connection._write_file_blocking("/var/log/app.log", "abc", append=False)
    assert replaced == 3
    assert files["/var/log/app.log"] == b"abc"


def test_append_reports_only_the_appended_bytes(server_module, host):
    """The same contract, seen through the tool."""
    host.files["/var/log/app.log"] = b"x" * 1000

    async def run():
        async with _client(server_module) as client:
            result = await client.call_tool(
                "sftp_upload",
                {"remote_path": "/var/log/app.log", "content": "yz", "mode": "append"},
            )
            assert result.structured_content["size_bytes"] == 2
            assert len(host.files["/var/log/app.log"]) == 1002

    anyio.run(run)


def test_activity_logger_is_importable_from_any_directory(tmp_path):
    """`python -m mcp_server_ssh` must find the sidecar activity logger.

    ssh_activity_logger.py lives next to the package, not inside it, so it is
    only importable because the entry point puts the project root on the path.
    Without that, logging silently switched itself off unless the process
    happened to start in ssh-mcp-server/.
    """
    import subprocess

    project = Path(__file__).resolve().parents[1]
    script = (
        "import mcp_server_ssh.__main__\n"
        "import mcp_server_ssh.server as server\n"
        "print(server.ACTIVITY_LOGGING_ENABLED)\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,  # deliberately not the project directory
        env={**os.environ, "PYTHONPATH": str(project / "src"), "SSH_HOST": "testhost"},
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "True", result.stderr


def test_a_file_that_appears_after_the_check_is_not_overwritten(server_module, host):
    """The confirmation was skipped because the path was absent; it must stay absent.

    Between the resolver's check and the write, another process can create the
    file. An exclusive create turns that race into a refusal instead of an
    unconfirmed overwrite.
    """
    host.appears_after_check = "/tmp/racy.txt"

    async def run():
        async with _client(server_module) as client:
            result = await client.call_tool(
                "file_operations",
                {"operation": "write", "path": "/tmp/racy.txt", "content": "mine"},
            )
            assert result.is_error is True
            assert "onay gerektirir" in result.content[0].text

    anyio.run(run)
    assert host.files["/tmp/racy.txt"] == b"someone else got here first"
