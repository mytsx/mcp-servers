#!/usr/bin/env python3
"""
SSH MCP Server
Remote Linux server command execution via SSH.
"""

import base64
import logging
import os
import re
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from shlex import quote
from typing import Annotated, Literal

import anyio
import paramiko
from dotenv import load_dotenv
from mcp.server import MCPServer
from mcp.server.mcpserver import Context, Elicit, Resolve
from mcp.server.mcpserver.exceptions import ResourceError, ToolError
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field
from pydantic.json_schema import SkipJsonSchema

from . import __version__

# Optional activity logger support
try:
    from ssh_activity_logger import get_activity_logger, log_session_end, log_session_start

    ACTIVITY_LOGGING_ENABLED = True
except ImportError:
    ACTIVITY_LOGGING_ENABLED = False

    class _NullLogger:
        """Stub logger that silently ignores all method calls"""

        def __getattr__(self, name):
            return lambda *a, **kw: None

    def get_activity_logger():
        return _NullLogger()

    def log_session_start(*a, **kw):
        pass

    def log_session_end(*a, **kw):
        pass


load_dotenv()

logger = logging.getLogger(__name__)

# Constants
DEFAULT_SSH_PORT = 22
DEFAULT_SSH_TIMEOUT = 30
DEFAULT_COMMAND_TIMEOUT = 30
DEFAULT_FILE_READ_LIMIT = 100
MAX_RETRY_ATTEMPTS = 2
MIN_PORT_NUMBER = 1
MAX_PORT_NUMBER = 65535
CONNECTION_TEST_TIMEOUT = 5
RETRY_DELAY_SECONDS = 1

# Commands that are never run, at any confirmation. These destroy the host
# rather than something on it.
# A destructive flag anywhere in an `rm` invocation. GNU rm accepts options
# before *and after* the file operands — `rm /tmp/missing -rf /var` deletes
# recursively — so scanning only the leading option prefix left a bypass. The
# arguments are scanned up to the end of the command, stopping at a separator
# so a later command cannot be mistaken for this one's operands.
_RM_ARGS = r"(?:[^\s;|&]+\s+)*"
_RM_DESTRUCTIVE_FLAG = r"(?:-[a-zA-Z]*[rRfF]|--(?:recursive|force|dir)\b)"

BLOCKED_PATTERNS = [
    # `rm -rf /` and `rm -rf /*`, but not `rm -rf /var/tmp/build` — that one is
    # legitimate and goes through the confirmation path instead.
    rf"\brm\s+{_RM_ARGS}/\s*\*?\s*(--no-preserve-root\s*)?$",
    rf"\brm\s+{_RM_ARGS}/(bin|boot|dev|etc|lib|lib64|proc|root|sbin|sys|usr|var)(/\*)?(\s|$)",
    r"\bformat\b",
    r"\bmkfs\b",
    r"\bdd\s+.*of=/dev/",
    r"\b:\(\)\{.*\}",  # Fork bomb
    r"sudo\s+passwd",
    r"userdel\s+",
    r"deluser\s+",
]

# Commands that are legitimate but destructive: the user is asked first.
CONFIRM_PATTERNS = [
    (
        # `rm -rf`, `rm -r -f`, `rm -v -r`, `rm --verbose --recursive`,
        # `rm --interactive=never -r`, and `rm file -r dir`.
        re.compile(rf"\brm\s+{_RM_ARGS}{_RM_DESTRUCTIVE_FLAG}", re.I),
        "dosya/dizin siliyor",
    ),
    (
        re.compile(r"\bshutdown\b|\breboot\b|\bhalt\b|\bpoweroff\b|\binit\s+[06]\b", re.I),
        "sunucuyu kapatıyor/yeniden başlatıyor",
    ),
    (re.compile(r"\bkill\s+-9\b|\bkillall\b|\bpkill\b", re.I), "süreçleri zorla sonlandırıyor"),
    (re.compile(r"\btruncate\b|>\s*/", re.I), "dosya içeriğini siliyor"),
    (
        # Case matters here: chmod/chown spell recursive as an uppercase -R, and
        # the long form as --recursive. Matching a lowercased command against an
        # uppercase R never fired at all.
        # The command name is matched case-insensitively, the flag is not.
        re.compile(
            # Like rm, these accept options after their operands:
            # `chmod 755 /srv -R` is recursive.
            rf"\b(?i:chown|chmod)\s+{_RM_ARGS}(?:-[a-zA-Z]*R|--(?i:recursive)\b)"
        ),
        "izinleri özyinelemeli değiştiriyor",
    ),
    (re.compile(r"\b(apt|apt-get|yum|dnf)\s+(remove|purge|autoremove)\b", re.I), "paket kaldırıyor"),
    (re.compile(r"\bdocker\s+(rm|rmi|prune|system\s+prune)\b", re.I), "Docker kaynaklarını siliyor"),
    (re.compile(r"\bdrop\s+(database|table)\b", re.I), "veritabanı nesnesi siliyor"),
    (re.compile(r"\bmv\s+.*\s+/dev/null\b", re.I), "dosyayı yok ediyor"),
    (
        re.compile(r"\bgit\s+(reset\s+--hard|clean\s+-[a-z]*f)\b", re.I),
        "commit edilmemiş değişiklikleri siliyor",
    ),
]


# ---------------------------------------------------------------------------
# Wire models
# ---------------------------------------------------------------------------

Metric = Literal["cpu", "memory", "disk", "network", "all"]
FileOperation = Literal["read", "write", "list", "exists"]
ProcessAction = Literal["list", "kill", "status", "search"]
WriteMode = Literal["overwrite", "append"]


class CommandResult(BaseModel):
    """The outcome of one remote command."""

    command: str
    exit_code: int = Field(description="The command's exit status. 0 means success.")
    stdout: str
    stderr: str
    duration_ms: float = Field(description="How long the command took, in milliseconds.")
    reconnected: bool = Field(
        default=False, description="True when the SSH connection had to be re-established first."
    )


class FileOpResult(BaseModel):
    operation: FileOperation
    path: str
    content: str = Field(default="", description="File contents for read, listing text for list.")
    exists: bool | None = Field(
        default=None, description="For the exists operation: whether the path is there."
    )
    bytes_written: int | None = Field(default=None, description="For write: how much was written.")


class MetricReading(BaseModel):
    metric: Metric
    command: str = Field(description="The command whose output this is.")
    output: str


class MonitorResult(BaseModel):
    requested: Metric
    detailed: bool
    readings: list[MetricReading]


class ProcessResult(BaseModel):
    action: ProcessAction
    target: str = ""
    signal: str | None = Field(default=None, description="For kill: the signal that was sent.")
    output: str


class ConnectionStatus(BaseModel):
    connection: str = Field(description="user@host:port of the configured server.")
    connected: bool
    reconnected: bool = Field(description="True when this call actually re-established the link.")
    detail: str = ""


class DownloadResult(BaseModel):
    remote_path: str
    size_bytes: int
    encoding: str = Field(description="'base64' means content is base64 of the raw bytes.")
    content: str


class UploadResult(BaseModel):
    remote_path: str
    mode: WriteMode
    size_bytes: int = Field(description="Size of the content that was written.")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def _int_env(name: str, default: int, *, minimum: int = 1, maximum: int | None = None) -> int:
    """Read an int from the environment, falling back to `default` on anything unusable."""
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        value = int(raw)
    except ValueError:
        logger.warning("Geçersiz %s değeri: %r. Varsayılan kullanılıyor: %s", name, raw, default)
        return default
    if value < minimum or (maximum is not None and value > maximum):
        logger.warning("Aralık dışı %s değeri: %s. Varsayılan kullanılıyor: %s", name, value, default)
        return default
    return value


@dataclass(frozen=True)
class SSHConfig:
    host: str
    port: int
    username: str
    password: str
    key_file: str
    key_passphrase: str
    timeout: int
    keepalive_interval: int
    keepalive_count_max: int
    banner_timeout: int
    auth_timeout: int

    @classmethod
    def from_env(cls) -> "SSHConfig":
        host = os.getenv("SSH_HOST", "localhost").strip()
        if not host:
            logger.warning("Boş SSH_HOST. 'localhost' kullanılıyor.")
            host = "localhost"
        return cls(
            host=host,
            port=_int_env("SSH_PORT", DEFAULT_SSH_PORT, minimum=MIN_PORT_NUMBER, maximum=MAX_PORT_NUMBER),
            username=os.getenv("SSH_USER", "root"),
            password=os.getenv("SSH_PASSWORD", ""),
            key_file=os.getenv("SSH_KEY_FILE", ""),
            key_passphrase=os.getenv("SSH_KEY_PASSPHRASE", ""),
            timeout=_int_env("SSH_TIMEOUT", DEFAULT_SSH_TIMEOUT),
            keepalive_interval=_int_env("SSH_KEEPALIVE_INTERVAL", 30),
            keepalive_count_max=_int_env("SSH_KEEPALIVE_COUNT_MAX", 3),
            banner_timeout=_int_env("SSH_BANNER_TIMEOUT", 30),
            auth_timeout=_int_env("SSH_AUTH_TIMEOUT", 30),
        )

    def __str__(self) -> str:
        return f"{self.username}@{self.host}:{self.port}"


# ---------------------------------------------------------------------------
# The SSH connection
# ---------------------------------------------------------------------------


class SSHConnection:
    """One paramiko client, kept alive for the life of the server.

    Every paramiko call is blocking, so each one runs on a worker thread; the
    event loop stays free to serve other requests and to carry a cancellation.
    """

    def __init__(self, config: SSHConfig) -> None:
        self.config = config
        self.client: paramiko.SSHClient | None = None
        self.activity_logger = get_activity_logger()
        self.last_connection_check: float | None = None
        self.connection_failures = 0
        # Held across check/close/connect: two callers finding a dead link would
        # otherwise each build a client, and the later assignment would strand
        # the earlier transport without closing it.
        self._connect_lock = anyio.Lock()


    # -- lifecycle ---------------------------------------------------------

    def _connect_blocking(self) -> None:
        cfg = self.config
        client = paramiko.SSHClient()
        client.load_system_host_keys()
        client.set_missing_host_key_policy(paramiko.WarningPolicy())

        kwargs: dict = {
            "hostname": cfg.host,
            "port": cfg.port,
            "username": cfg.username,
            "timeout": cfg.timeout,
            "banner_timeout": cfg.banner_timeout,
            "auth_timeout": cfg.auth_timeout,
        }
        if cfg.key_file:
            kwargs["key_filename"] = cfg.key_file
            if cfg.key_passphrase:
                kwargs["passphrase"] = cfg.key_passphrase
            logger.info("SSH anahtar kimlik doğrulaması: %s", cfg.key_file)
        elif cfg.password:
            kwargs["password"] = cfg.password
            logger.info("SSH parola kimlik doğrulaması")
        else:
            logger.info("Varsayılan SSH anahtarları ve SSH agent deneniyor")

        client.connect(**kwargs)
        transport = client.get_transport()
        if transport:
            transport.set_keepalive(cfg.keepalive_interval)
        self.client = client

    async def connect(self) -> None:
        try:
            await anyio.to_thread.run_sync(self._connect_blocking)
        except Exception as exc:
            self.connection_failures += 1
            logger.error("SSH bağlantısı kurulamadı: %s", exc)
            self.activity_logger.log_event(
                event_type="connection_failed",
                command="ssh_connect",
                response=f"Connection failed: {exc}",
                execution_time=0,
                status="error",
                error_message=str(exc),
            )
            raise ToolError(f"{self.config} adresine SSH bağlantısı kurulamadı: {exc}") from exc

        self.connection_failures = 0
        logger.info("SSH bağlantısı kuruldu: %s", self.config)
        self.activity_logger.log_event(
            event_type="connection_established",
            command="ssh_connect",
            response=f"Connected to {self.config}",
            execution_time=0,
            status="success",
        )

    def close(self) -> None:
        if self.client:
            try:
                self.client.close()
            except Exception as exc:
                logger.debug("SSH bağlantısı kapatılırken hata: %s", exc)
            finally:
                self.client = None

    def _is_alive_blocking(self) -> bool:
        if not self.client:
            return False
        try:
            transport = self.client.get_transport()
            if not transport or not transport.is_active():
                return False
            _, stdout, _ = self.client.exec_command(
                "echo connection_test", timeout=CONNECTION_TEST_TIMEOUT
            )
            alive = stdout.read().decode().strip() == "connection_test"
            self.last_connection_check = time.time()
            return alive
        except Exception as exc:
            logger.warning("Bağlantı sağlık kontrolü başarısız: %s", exc)
            return False

    async def is_alive(self) -> bool:
        return await anyio.to_thread.run_sync(self._is_alive_blocking)

    async def ensure(self) -> bool:
        """Make sure the link is up. Returns True when it had to reconnect."""
        async with self._connect_lock:
            return await self._ensure_owned()

    async def _ensure_owned(self) -> bool:
        """As above, for a caller already holding the connection lock."""
        if await self.is_alive():
            return False
        logger.info("SSH bağlantısı koptu, yeniden bağlanılıyor")
        self.close()
        await self.connect()
        return True

    async def reconnect(self) -> None:
        """Drop the current link and build a new one, under the lock."""
        async with self._connect_lock:
            self.close()
            await self.connect()

    # -- running commands --------------------------------------------------

    def _exec_blocking(
        self, command: str, timeout: int, channel_holder: dict
    ) -> tuple[str, str, int]:
        assert self.client is not None
        _, stdout, stderr = self.client.exec_command(command, timeout=timeout)
        # Published to this call's own holder, so a cancellation closes the
        # channel of the command it belongs to and not a concurrent one.
        channel_holder["channel"] = stdout.channel
        try:
            out = stdout.read().decode("utf-8", errors="ignore")
            err = stderr.read().decode("utf-8", errors="ignore")
            return out, err, stdout.channel.recv_exit_status()
        finally:
            channel_holder["channel"] = None

    async def _exec_cancellable(self, command: str, timeout: int) -> tuple[str, str, int]:
        """Run a command so that cancelling the call also stops it remotely.

        `anyio.to_thread.run_sync` does not return until the thread finishes, so
        catching the cancellation around it would only run once the command had
        already completed. A watchdog cancelled at the same moment closes the
        channel instead, which makes the reads fail and the thread return.
        """
        state = {"finished": False}
        channel_holder: dict = {"channel": None}

        async def watchdog() -> None:
            try:
                await anyio.sleep_forever()
            except anyio.get_cancelled_exc_class():
                channel = channel_holder["channel"]
                if not state["finished"] and channel is not None:
                    with anyio.CancelScope(shield=True):
                        await anyio.to_thread.run_sync(channel.close)
                raise

        result: tuple[str, str, int] | None = None
        failure: Exception | None = None

        async with anyio.create_task_group() as task_group:
            task_group.start_soon(watchdog)
            try:
                result = await anyio.to_thread.run_sync(
                    self._exec_blocking, command, timeout, channel_holder
                )
            except Exception as exc:
                # Held rather than raised: a task group would wrap it in an
                # ExceptionGroup and the retry loop matches on paramiko's types.
                failure = exc
            finally:
                state["finished"] = True
                task_group.cancel_scope.cancel()

        if failure is not None:
            raise failure
        assert result is not None
        return result

    async def run(self, command: str, timeout: int = DEFAULT_COMMAND_TIMEOUT) -> CommandResult:
        """Run a command, reconnecting and retrying if the link dropped mid-flight."""
        started = time.time()
        reconnected = await self.ensure()

        last_error: Exception | None = None
        for attempt in range(MAX_RETRY_ATTEMPTS + 1):
            try:
                if self.client is None:
                    # A previous attempt's reconnect failed; try again here so
                    # the remaining attempts are not spent on a missing client.
                    await self.connect()
                    reconnected = True
                out, err, exit_code = await self._exec_cancellable(command, timeout)
                return CommandResult(
                    command=command,
                    exit_code=exit_code,
                    stdout=out,
                    stderr=err,
                    duration_ms=(time.time() - started) * 1000,
                    reconnected=reconnected,
                )
            except ToolError:
                raise
            except (paramiko.SSHException, ConnectionError, OSError) as exc:
                last_error = exc
                logger.warning(
                    "SSH bağlantı hatası (deneme %d/%d): %s",
                    attempt + 1,
                    MAX_RETRY_ATTEMPTS + 1,
                    exc,
                )
                if attempt >= MAX_RETRY_ATTEMPTS:
                    break
                try:
                    await self.reconnect()
                    reconnected = True
                    await anyio.sleep(RETRY_DELAY_SECONDS)
                except ToolError as reconnect_error:
                    # Remembered so the final message names the reconnect
                    # failure rather than a stale command error.
                    last_error = reconnect_error
                    logger.error("Yeniden bağlanma başarısız: %s", reconnect_error)
                    await anyio.sleep(RETRY_DELAY_SECONDS)

        raise ToolError(
            f"Komut {MAX_RETRY_ATTEMPTS + 1} denemede çalıştırılamadı: {last_error}"
        )

    async def checked_run(self, command: str, timeout: int = DEFAULT_COMMAND_TIMEOUT) -> str:
        """Run a command and return its stdout, raising if it failed."""
        result = await self.run(command, timeout)
        if result.exit_code != 0:
            raise ToolError(
                f"Komut başarısız (exit {result.exit_code}): {result.stderr.strip() or command}"
            )
        return result.stdout

    # -- SFTP --------------------------------------------------------------

    def _read_file_blocking(self, remote_path: str) -> bytes:
        assert self.client is not None
        with self.client.open_sftp() as sftp, sftp.open(remote_path, "rb") as f:
            return f.read()

    def _write_file_blocking(
        self, remote_path: str, content: str, append: bool, exclusive: bool = False
    ) -> int:
        """Write the file and return the number of bytes *this call* added.

        In append mode the whole file is rewritten, so the buffer that goes to
        the remote host is not the same thing as what the caller supplied.
        Reporting the buffer's length would call a one-byte append a 100 MB one.
        """
        assert self.client is not None
        written = len(content.encode("utf-8"))
        with self.client.open_sftp() as sftp:
            if exclusive:
                # "x" is O_CREAT|O_EXCL: if the file appeared since it was
                # checked, this fails instead of overwriting it unasked.
                mode = "x"
            elif append:
                # "a" appends at the server. Reading the file and rewriting it
                # whole would let two overlapping appends each start from the
                # same contents, and the later write would discard the earlier.
                mode = "a"
            else:
                mode = "w"
            with sftp.open(remote_path, mode) as f:
                f.write(content)
        return written

    def _file_exists_blocking(self, remote_path: str) -> bool:
        assert self.client is not None
        with self.client.open_sftp() as sftp:
            try:
                sftp.stat(remote_path)
                return True
            except FileNotFoundError:
                return False

    async def read_file(self, remote_path: str) -> bytes:
        await self.ensure()
        try:
            return await anyio.to_thread.run_sync(self._read_file_blocking, remote_path)
        except FileNotFoundError as exc:
            raise ToolError(f"Uzak dosya yok: {remote_path}") from exc
        except OSError as exc:
            raise ToolError(f"SFTP okuma hatası ({remote_path}): {exc}") from exc

    async def write_file(
        self,
        remote_path: str,
        content: str,
        append: bool = False,
        exclusive: bool = False,
    ) -> int:
        """Write a file. With `exclusive`, fail rather than replace an existing one."""
        await self.ensure()
        try:
            return await anyio.to_thread.run_sync(
                self._write_file_blocking, remote_path, content, append, exclusive
            )
        except FileExistsError as exc:
            # The only error that means what the exclusive create was guarding
            # against. An unwritable parent or an exhausted quota would leave
            # the path absent, and reporting those as a collision would send the
            # caller round the same loop forever.
            if exclusive:
                raise ToolError(
                    f"'{remote_path}' kontrol edildikten sonra oluşturulmuş; üzerine "
                    "yazmak onay gerektirir. Aynı çağrıyı tekrarla, bu kez sorulacak."
                ) from exc
            raise ToolError(f"SFTP yazma hatası ({remote_path}): {exc}") from exc
        except OSError as exc:
            raise ToolError(f"SFTP yazma hatası ({remote_path}): {exc}") from exc

    async def file_exists(self, remote_path: str) -> bool:
        await self.ensure()
        return await anyio.to_thread.run_sync(self._file_exists_blocking, remote_path)


# ---------------------------------------------------------------------------
# Command safety
# ---------------------------------------------------------------------------


# Where one shell command ends and the next begins. Splitting on these is what
# keeps `rm -rf /; true` from escaping a rule anchored to the end of the input.
_SEGMENT_SEPARATOR = re.compile(r"(?:\|\||&&|[;\n|&])")


def command_segments(command: str) -> list[str]:
    """The individual commands in a shell line, each classified on its own.

    Quote characters are removed, not replaced with a space: a shell
    concatenates the fragments of one word, so `r''m -rf /` runs `rm`. Turning
    the quotes into spaces produced `r  m` and matched nothing. Removing them
    can only make a segment look more dangerous than it is, which is the safe
    direction for a blocklist.
    """
    unquoted = command.replace("'", "").replace('"', "").replace("\\", "")
    return [part.strip() for part in _SEGMENT_SEPARATOR.split(unquoted) if part.strip()]


def blocked_reason(command: str) -> str | None:
    """The pattern this command matches, if it is one we never run.

    Each segment is judged separately: an end-anchored rule would otherwise be
    defeated by appending anything at all, and `rm -rf /; true` is still
    `rm -rf /`.
    """
    for segment in command_segments(command):
        lowered = segment.lower()
        for pattern in BLOCKED_PATTERNS:
            if re.search(pattern, lowered):
                return pattern
    return None


def confirm_reason(command: str) -> str | None:
    """A plain-language reason to ask the user first, or None to just run it.

    Matched against the command as written: the patterns carry their own flags,
    because `chmod -R` is not the same option as `chmod -r`. Each segment of a
    shell line is judged on its own.
    """
    for segment in command_segments(command):
        for pattern, reason in CONFIRM_PATTERNS:
            if pattern.search(segment):
                return reason
    return None


class RunConfirmation(BaseModel):
    """The user's answer to a destructive-command question."""

    confirm: bool = Field(description="Run this command on the remote server?")


async def confirm_command(command: str) -> RunConfirmation | Elicit[RunConfirmation]:
    """Ask before running a destructive command; stay silent for ordinary ones."""
    if blocked_reason(command):
        # Never asked, never run: the tool raises below.
        return RunConfirmation(confirm=False)
    reason = confirm_reason(command)
    if reason is None:
        return RunConfirmation(confirm=True)
    return Elicit(
        f"Bu komut {reason}:\n\n    {command}\n\nÇalıştırılsın mı?",
        RunConfirmation,
    )


# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------


@dataclass
class AppContext:
    ssh: SSHConnection


# Resources cannot read the lifespan context in v2, so they go through this.
_app: AppContext | None = None


async def _keepalive_worker(ssh: SSHConnection) -> None:
    """Re-establish the link in the background so the next call is not the one that waits."""
    interval = ssh.config.keepalive_interval * 2
    while True:
        await anyio.sleep(interval)
        try:
            # Through the same lock as everything else: the keepalive finding a
            # dead client while a request is already reconnecting would
            # otherwise build a second one and strand the first.
            if await ssh.ensure():
                logger.info("Keepalive bağlantıyı yeniledi")
        except ToolError as exc:
            logger.error("Keepalive yeniden bağlanamadı: %s", exc)
        except Exception as exc:
            logger.error("Keepalive hatası: %s", exc)


@asynccontextmanager
async def app_lifespan(server: MCPServer) -> AsyncIterator[AppContext]:
    global _app
    ssh = SSHConnection(SSHConfig.from_env())
    log_session_start()
    _app = AppContext(ssh=ssh)

    try:
        async with anyio.create_task_group() as tg:
            tg.start_soon(_keepalive_worker, ssh)
            try:
                yield _app
            finally:
                tg.cancel_scope.cancel()
    finally:
        ssh.close()
        _app = None
        log_session_end()


mcp = MCPServer("ssh-mcp-server", version=__version__, lifespan=app_lifespan)

_READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=True)
_WRITES = ToolAnnotations(
    read_only_hint=False, destructive_hint=True, idempotent_hint=False, open_world_hint=True
)


def _ssh(ctx: Context[AppContext]) -> SSHConnection:
    return ctx.request_context.lifespan_context.ssh


@mcp.tool(
    title="Komut çalıştır",
    description="Execute a shell command on the remote server. Destructive commands are "
    "confirmed with the user first; a few catastrophic ones are refused outright.",
    annotations=_WRITES,
)
async def execute_command(
    command: Annotated[str, Field(min_length=1, description="Shell command to execute.")],
    ctx: Context[AppContext],
    confirmation: Annotated[RunConfirmation, Resolve(confirm_command)],
    timeout: Annotated[
        int, Field(ge=1, le=3600, description="Command timeout in seconds.")
    ] = DEFAULT_COMMAND_TIMEOUT,
) -> CommandResult:
    pattern = blocked_reason(command)
    if pattern:
        raise ToolError(
            f"Komut güvenlik nedeniyle reddedildi (eşleşen desen: {pattern}): {command}"
        )
    if not confirmation.confirm:
        raise ToolError("Kullanıcı komutu onaylamadı; hiçbir şey çalıştırılmadı.")

    ssh = _ssh(ctx)
    result = await ssh.run(command, timeout)

    ssh.activity_logger.log_command_execution(
        command=command,
        arguments={"command": command, "timeout": timeout},
        response=result.stdout or result.stderr,
        execution_time=result.duration_ms,
        status="success" if result.exit_code == 0 else "error",
        error_message=result.stderr if result.exit_code != 0 else None,
        security_flags=[],
    )
    return result


class WriteConfirmation(BaseModel):
    confirm: bool = Field(description="Overwrite the file on the remote server?")
    # Server-computed, and hidden from the elicitation schema: it records why no
    # question was asked, so the write can be made exclusive and lose the race
    # instead of silently overwriting a file that appeared in the meantime.
    approved_because_absent: SkipJsonSchema[bool] = False


async def confirm_write(
    ctx: Context[AppContext],
    operation: FileOperation = "read",
    path: str = "",
) -> WriteConfirmation | Elicit[WriteConfirmation]:
    """Ask before overwriting a file that already exists."""
    if operation != "write":
        return WriteConfirmation(confirm=True)
    ssh = _ssh(ctx)
    if not await ssh.file_exists(path):
        # Nothing to lose *right now*; the write is made exclusive so that a file
        # created in between fails the call rather than being overwritten.
        return WriteConfirmation(confirm=True, approved_because_absent=True)
    return Elicit(f"'{path}' zaten var ve üzerine yazılacak. Onaylıyor musun?", WriteConfirmation)


@mcp.tool(
    title="Dosya işlemleri",
    description="Read, write, list or check files on the remote server. Overwriting an "
    "existing file is confirmed with the user first.",
    annotations=_WRITES,
)
async def file_operations(
    operation: Annotated[FileOperation, Field(description="File operation to perform.")],
    path: Annotated[str, Field(min_length=1, description="File or directory path.")],
    ctx: Context[AppContext],
    confirmation: Annotated[WriteConfirmation, Resolve(confirm_write)],
    content: Annotated[str, Field(description="Content to write, for the write operation.")] = "",
    limit: Annotated[
        int, Field(ge=0, description="Lines to read. 0 means the whole file.")
    ] = DEFAULT_FILE_READ_LIMIT,
) -> FileOpResult:
    ssh = _ssh(ctx)
    started = time.time()

    if operation == "read":
        command = f"head -n {limit} {quote(path)}" if limit > 0 else f"cat {quote(path)}"
        result = FileOpResult(operation=operation, path=path, content=await ssh.checked_run(command))
    elif operation == "list":
        result = FileOpResult(
            operation=operation, path=path, content=await ssh.checked_run(f"ls -la {quote(path)}")
        )
    elif operation == "exists":
        result = FileOpResult(operation=operation, path=path, exists=await ssh.file_exists(path))
    else:  # write
        if not confirmation.confirm:
            raise ToolError(f"Kullanıcı '{path}' üzerine yazmayı onaylamadı.")
        written = await ssh.write_file(
            path, content, exclusive=confirmation.approved_because_absent
        )
        result = FileOpResult(operation=operation, path=path, bytes_written=written)

    ssh.activity_logger.log_file_operation(
        operation=operation,
        path=path,
        arguments={"operation": operation, "path": path, "limit": limit},
        response=result.model_dump_json(),
        execution_time=(time.time() - started) * 1000,
        status="success",
        error_message=None,
    )
    return result


# The command behind each metric, as (plain, detailed).
_METRIC_COMMANDS: dict[str, tuple[str, str]] = {
    "cpu": (
        "top -bn1 | grep 'Cpu(s)' || grep -i cpu /proc/stat | head -1",
        "top -bn1 | head -20",
    ),
    "memory": ("free -h", "free -h && cat /proc/meminfo | head -10"),
    "disk": ("df -h", "df -h && iostat -x 1 1 2>/dev/null || echo 'iostat not available'"),
    "network": (
        "ss -tuln | head -10",
        "ss -tuln | head -10 && netstat -i 2>/dev/null || ip -s link",
    ),
}


@mcp.tool(
    title="Sistem izleme",
    description="Monitor system resources (CPU, memory, disk, network) on the remote server.",
    annotations=_READ_ONLY,
)
async def system_monitor(
    metric: Annotated[Metric, Field(description="Which resource to look at, or 'all' for every one.")],
    ctx: Context[AppContext],
    detailed: Annotated[bool, Field(description="Ask for the longer, noisier output.")] = False,
) -> MonitorResult:
    ssh = _ssh(ctx)
    wanted = list(_METRIC_COMMANDS) if metric == "all" else [metric]

    readings: list[MetricReading] = []
    for index, name in enumerate(wanted):
        await ctx.report_progress(index, len(wanted), f"{name} okunuyor")
        command = _METRIC_COMMANDS[name][1 if detailed else 0]
        result = await ssh.run(command)
        readings.append(
            MetricReading(metric=name, command=command, output=result.stdout or result.stderr)
        )

    await ctx.report_progress(len(wanted), len(wanted), "tamamlandı")
    return MonitorResult(requested=metric, detailed=detailed, readings=readings)


class KillConfirmation(BaseModel):
    confirm: bool = Field(description="Send the signal to this process?")


async def confirm_kill(
    ctx: Context[AppContext],
    action: ProcessAction = "list",
    target: str = "",
    signal: str = "TERM",
) -> KillConfirmation | Elicit[KillConfirmation]:
    """Ask before signalling a process; listing and searching are free."""
    if action != "kill":
        return KillConfirmation(confirm=True)

    ssh = _ssh(ctx)
    described = target
    if target.isdigit():
        listing = await ssh.run(f"ps -p {target} -o pid=,comm=,args= 2>/dev/null")
        described = listing.stdout.strip() or f"PID {target} (bulunamadı)"

    return Elicit(
        f"{signal} sinyali şu sürece gönderilecek:\n\n    {described}\n\nOnaylıyor musun?",
        KillConfirmation,
    )


@mcp.tool(
    title="Süreç yönetimi",
    description="List, search, inspect or signal processes on the remote server. "
    "Killing a process is confirmed with the user first.",
    annotations=_WRITES,
)
async def process_manager(
    action: Annotated[ProcessAction, Field(description="What to do with processes.")],
    ctx: Context[AppContext],
    confirmation: Annotated[KillConfirmation, Resolve(confirm_kill)],
    target: Annotated[
        str, Field(description="Process name or search term; a numeric PID for kill and status.")
    ] = "",
    signal: Annotated[str, Field(description="Signal to send, for the kill action.")] = "TERM",
) -> ProcessResult:
    ssh = _ssh(ctx)

    if action == "list":
        command = f"ps aux | grep {quote(target)} | grep -v grep" if target else "ps aux | head -20"
        result = await ssh.run(command)
        return ProcessResult(action=action, target=target, output=result.stdout)

    if action == "search":
        if not target:
            raise ToolError("Arama için `target` gerekli.")
        result = await ssh.run(f"ps aux | grep {quote(target)} | grep -v grep")
        return ProcessResult(action=action, target=target, output=result.stdout)

    if action == "status":
        if not target:
            raise ToolError("Durum sorgusu için süreç adı ya da PID gerekli.")
        command = (
            f"ps -p {target} 2>/dev/null"
            if target.isdigit()
            else f"ps aux | grep {quote(target)} | grep -v grep"
        )
        result = await ssh.run(command)
        return ProcessResult(action=action, target=target, output=result.stdout)

    # kill
    if not target:
        raise ToolError("Kill için PID gerekli.")
    if not target.isdigit():
        raise ToolError("Kill yalnızca sayısal PID kabul eder.")
    if not confirmation.confirm:
        raise ToolError(f"Kullanıcı {target} sürecini sonlandırmayı onaylamadı.")

    result = await ssh.run(f"kill -{quote(signal)} {target}")
    if result.exit_code != 0:
        raise ToolError(f"Sinyal gönderilemedi: {result.stderr.strip()}")
    return ProcessResult(
        action=action,
        target=target,
        signal=signal,
        output=result.stdout or f"{signal} sinyali PID {target} sürecine gönderildi.",
    )


@mcp.tool(
    title="SSH yeniden bağlan",
    description="Check the SSH connection and re-establish it. Without force, a healthy "
    "connection is left alone.",
    annotations=ToolAnnotations(
        read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=True
    ),
)
async def ssh_reconnect(
    ctx: Context[AppContext],
    force: Annotated[
        bool, Field(description="Reconnect even when the connection looks healthy.")
    ] = False,
) -> ConnectionStatus:
    ssh = _ssh(ctx)

    if not force and await ssh.is_alive():
        last = ssh.last_connection_check
        detail = f"Son sağlık kontrolü {time.time() - last:.1f} sn önce." if last else ""
        return ConnectionStatus(
            connection=str(ssh.config), connected=True, reconnected=False, detail=detail
        )

    await ssh.reconnect()
    alive = await ssh.is_alive()
    if not alive:
        raise ToolError("Yeniden bağlanıldı ama sağlık kontrolü geçilemedi.")

    ssh.activity_logger.log_event(
        event_type="reconnection",
        command="ssh_reconnect",
        response="SSH connection restored",
        execution_time=0,
        status="success",
    )
    return ConnectionStatus(
        connection=str(ssh.config), connected=True, reconnected=True, detail="Bağlantı tazelendi."
    )


@mcp.tool(
    title="Dosya indir (SFTP)",
    description="Download a file from the remote server via SFTP.",
    annotations=_READ_ONLY,
)
async def sftp_download(
    remote_path: Annotated[str, Field(min_length=1, description="Full path on the remote server.")],
    ctx: Context[AppContext],
    encoding: Annotated[
        str,
        Field(description="Text encoding to decode with. Use 'base64' for binary files."),
    ] = "utf-8",
) -> DownloadResult:
    ssh = _ssh(ctx)
    data = await ssh.read_file(remote_path)

    if encoding == "base64":
        content = base64.b64encode(data).decode("ascii")
    else:
        try:
            content = data.decode(encoding, errors="replace")
        except LookupError as exc:
            raise ToolError(f"Bilinmeyen kodlama: {encoding}") from exc

    ssh.activity_logger.log_file_operation(
        operation="sftp_download",
        path=remote_path,
        arguments={"remote_path": remote_path, "encoding": encoding},
        response=f"Downloaded {len(data)} bytes",
        execution_time=0,
        status="success",
        error_message=None,
    )
    return DownloadResult(
        remote_path=remote_path, size_bytes=len(data), encoding=encoding, content=content
    )


class UploadConfirmation(BaseModel):
    confirm: bool = Field(description="Overwrite the existing file?")
    approved_because_absent: SkipJsonSchema[bool] = False


async def confirm_upload(
    ctx: Context[AppContext],
    remote_path: str = "",
    mode: WriteMode = "overwrite",
) -> UploadConfirmation | Elicit[UploadConfirmation]:
    """Ask before replacing a file that is already there; appending never asks."""
    if mode == "append":
        return UploadConfirmation(confirm=True)
    ssh = _ssh(ctx)
    if not await ssh.file_exists(remote_path):
        return UploadConfirmation(confirm=True, approved_because_absent=True)
    return Elicit(
        f"'{remote_path}' zaten var ve tamamen değiştirilecek. Onaylıyor musun?",
        UploadConfirmation,
    )


@mcp.tool(
    title="Dosya yükle (SFTP)",
    description="Upload content to a file on the remote server via SFTP. Replacing an "
    "existing file is confirmed with the user first.",
    annotations=_WRITES,
)
async def sftp_upload(
    remote_path: Annotated[str, Field(min_length=1, description="Full path on the remote server.")],
    content: Annotated[str, Field(description="Content to write to the file.")],
    ctx: Context[AppContext],
    confirmation: Annotated[UploadConfirmation, Resolve(confirm_upload)],
    mode: Annotated[
        WriteMode, Field(description="Replace the file, or add to the end of it.")
    ] = "overwrite",
) -> UploadResult:
    if not confirmation.confirm:
        raise ToolError(f"Kullanıcı '{remote_path}' dosyasını değiştirmeyi onaylamadı.")

    ssh = _ssh(ctx)
    size = await ssh.write_file(
        remote_path,
        content,
        append=(mode == "append"),
        exclusive=confirmation.approved_because_absent,
    )

    ssh.activity_logger.log_file_operation(
        operation="sftp_upload",
        path=remote_path,
        arguments={"remote_path": remote_path, "mode": mode, "content": f"<{size} bytes>"},
        response=f"Uploaded {size} bytes",
        execution_time=0,
        status="success",
        error_message=None,
    )
    return UploadResult(remote_path=remote_path, mode=mode, size_bytes=size)


# ---------------------------------------------------------------------------
# Resources & prompts
# ---------------------------------------------------------------------------

_RESOURCE_COMMANDS: dict[str, tuple[str, str, list[str]]] = {
    "system": (
        "System Information",
        "Remote server system information",
        ["uname -a", "cat /etc/os-release | head -5", "uptime", "whoami", "pwd"],
    ),
    "processes": ("Running Processes", "Top processes on the remote server", ["ps aux | head -20"]),
    "disk": ("Disk Usage", "Disk usage and mounted filesystems", ["df -h", "lsblk"]),
    "network": (
        "Network Information",
        "Network configuration and listening sockets",
        ["ip addr show", "ss -tuln | head -10"],
    ),
    "logs": (
        "System Logs",
        "Recent system logs",
        [
            "tail -20 /var/log/syslog 2>/dev/null || tail -20 /var/log/messages 2>/dev/null "
            "|| echo 'No system logs accessible'",
            "dmesg | tail -10",
        ],
    ),
}


async def _render_resource(kind: str) -> str:
    if _app is None:
        raise ResourceError("Sunucu henüz hazır değil.")
    entry = _RESOURCE_COMMANDS.get(kind)
    if entry is None:
        raise ResourceError(f"Bilinmeyen kaynak: ssh://{kind}")

    title, _, commands = entry
    sections = [f"{title} — {_app.ssh.config}", ""]
    for command in commands:
        result = await _app.ssh.run(command)
        sections.append(f"$ {command}\n{result.stdout or result.stderr}")
    return "\n\n".join(sections)


def _register_resources() -> None:
    """Register one static resource per report, so they show up in resources/list."""
    for kind, (title, description, _) in _RESOURCE_COMMANDS.items():

        def make_handler(kind: str):
            async def handler() -> str:
                return await _render_resource(kind)

            handler.__name__ = f"ssh_{kind}_resource"
            return handler

        handler = make_handler(kind)
        mcp.resource(
            f"ssh://{kind}",
            name=title,
            description=description,
            mime_type="text/plain",
        )(handler)


_register_resources()


@mcp.prompt(title="Sunucu sorununu teşhis et")
def diagnose_server(symptom: str) -> str:
    """Investigate a problem on the remote server, from symptom to cause."""
    return (
        f"Uzak sunucuda şu sorun bildirildi: {symptom}\n\n"
        "Şu sırayla ilerle ve her adımda ne gördüğünü yaz:\n"
        "1. `ssh://system` ve `system_monitor(metric='all')` ile genel duruma bak.\n"
        "2. Belirtiye göre daralt: disk doluluğu, bellek baskısı, CPU, ağ, süreç durumu.\n"
        "3. `ssh://logs` ve ilgili servis loglarını oku.\n"
        "4. Bulduğun nedeni kanıtla — hangi çıktı bunu gösteriyor?\n"
        "5. Düzeltme öner. Yıkıcı bir komut gerekiyorsa önce ne yapacağını açıkla; "
        "komut zaten çalıştırılmadan önce kullanıcıya onay sorusu soracak."
    )


if __name__ == "__main__":
    mcp.run()
