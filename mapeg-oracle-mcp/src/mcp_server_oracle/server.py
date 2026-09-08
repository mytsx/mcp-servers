#!/usr/bin/env python3
"""
Oracle MCP Server
Query and explore an Oracle database (11g-23ai) over MCP, including PL/SQL
source and DBMS_OUTPUT.
"""

import json
import logging
import os
import re
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

import anyio
import oracledb
from dotenv import load_dotenv
from mcp.server import MCPServer
from mcp.server.mcpserver import Context, Elicit, Resolve
from mcp.server.mcpserver.exceptions import ResourceError, ToolError
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from . import __version__
from .query_logger import direct_log_query_execution, get_query_history

load_dotenv()

logger = logging.getLogger(__name__)

DEFAULT_ROW_LIMIT = 100
DBMS_OUTPUT_BUFFER_BYTES = 100_000_000
DBMS_OUTPUT_MAX_LINES = 1000
DBMS_OUTPUT_CHECK_INTERVAL = 60

WRITE_KEYWORDS = frozenset(
    ["INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "TRUNCATE", "MERGE", "GRANT", "REVOKE"]
)
IRREVERSIBLE_KEYWORDS = frozenset(["DROP", "TRUNCATE", "DELETE"])

# Oracle major version → the name people actually use for it.
VERSION_SUFFIXES = {
    "10": "10g", "11": "11g", "12": "12c", "18": "18c",
    "19": "19c", "21": "21c", "23": "23ai",
}

# An unquoted Oracle identifier. Anything else is refused rather than
# interpolated into a statement.
IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_$#]*$")

SOURCE_TYPES = ("FUNCTION", "PROCEDURE", "TRIGGER", "PACKAGE", "PACKAGE BODY", "TYPE", "TYPE BODY")


# ---------------------------------------------------------------------------
# Wire models
# ---------------------------------------------------------------------------

ObjectType = Literal[
    "TABLE", "VIEW", "FUNCTION", "PROCEDURE", "PACKAGE", "PACKAGE BODY",
    "TRIGGER", "SEQUENCE", "INDEX", "TYPE", "SYNONYM",
]
ConstraintType = Literal["P", "R", "C", "U"]
Direction = Literal["incoming", "outgoing", "both"]
PlanFormat = Literal["basic", "typical", "all"]
HistoryStatus = Literal["success", "error"]


class QueryResult(BaseModel):
    """The outcome of one SQL statement or PL/SQL block."""

    sql: str = Field(description="The statement as it was actually run, row limit included.")
    columns: list[str] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    row_count: int = Field(description="Rows returned, or rows affected for a write.")
    limit_applied: int | None = Field(
        default=None, description="The FETCH FIRST this server added, if the query had none."
    )
    dbms_output: str = Field(
        default="", description="Anything the block wrote with DBMS_OUTPUT.PUT_LINE."
    )
    duration_ms: float


class ColumnInfo(BaseModel):
    name: str
    data_type: str
    length: int | None = None
    nullable: bool
    default: str | None = None
    position: int


class TableDescription(BaseModel):
    table_name: str
    columns: list[ColumnInfo]
    row_count: int


class SourceCode(BaseModel):
    object_name: str
    object_type: str
    other_types: list[str] = Field(
        default_factory=list,
        description="Other object types with this same name, when more than one exists.",
    )
    line_count: int
    source: str


class ViewDefinition(BaseModel):
    view_name: str
    text_length: int
    definition: str


class TableMatch(BaseModel):
    table_name: str
    tablespace: str | None = None
    status: str | None = None
    num_rows: int | None = Field(
        default=None, description="Optimizer statistic; null when the table was never analyzed."
    )


class ColumnMatch(BaseModel):
    table_name: str
    column_name: str
    data_type: str
    length: int | None = None


class IndexColumn(BaseModel):
    name: str
    position: int


class IndexInfo(BaseModel):
    index_name: str
    index_type: str
    unique: bool
    status: str
    columns: list[IndexColumn]


class ConstraintInfo(BaseModel):
    constraint_name: str
    constraint_type: ConstraintType
    type_label: str
    status: str
    columns: list[str] = Field(default_factory=list)
    search_condition: str | None = Field(default=None, description="For a check constraint.")
    references_constraint: str | None = Field(
        default=None, description="For a foreign key: the constraint it points at."
    )


class TableSize(BaseModel):
    table_name: str
    num_rows: int | None = None
    avg_row_len: int | None = None
    blocks: int | None = None
    size_mb: float | None = Field(default=None, description="Segment size on disk, in MB.")
    estimated_mb: float | None = Field(
        default=None, description="num_rows x avg_row_len, for when the segment size is unknown."
    )
    column_count: int = 0
    last_analyzed: str | None = None


class Relationship(BaseModel):
    constraint_name: str
    from_table: str
    from_columns: str
    to_table: str
    to_columns: str


class Relationships(BaseModel):
    table_name: str
    direction: Direction
    outgoing: list[Relationship] = Field(
        default_factory=list, description="Foreign keys this table declares."
    )
    incoming: list[Relationship] = Field(
        default_factory=list, description="Foreign keys other tables have onto this one."
    )


class DatabaseObject(BaseModel):
    object_name: str
    status: str
    created: str | None = None
    last_ddl_time: str | None = None


class ObjectListing(BaseModel):
    object_type: ObjectType
    pattern: str = ""
    objects: list[DatabaseObject]


class ExplainPlan(BaseModel):
    sql: str
    format: PlanFormat
    plan: str


class HistoryEntry(BaseModel):
    timestamp: str
    tool_name: str
    query_text: str
    execution_time_ms: float
    row_count: int
    status: str
    error_message: str = ""
    user_query: str = ""


class QueryHistory(BaseModel):
    db_identifier: str
    workspace_path: str
    entries: list[HistoryEntry]


class DatabaseInfo(BaseModel):
    version: str
    instance: str = ""
    host: str = ""
    table_count: int = 0
    total_size_mb: float | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _jsonable(value: Any) -> Any:
    """Make an oracledb value safe to put in a JSON result."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        # A NUMERIC wider than an IEEE-754 float would be silently rounded on
        # the way out, so it travels as a string. This is a tool for inspecting
        # what is actually in the database; a quietly corrupted number is worse
        # than one the caller has to parse.
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, oracledb.LOB):
        return value.read()
    if isinstance(value, (bytes, memoryview)):
        return f"<{len(bytes(value))} bytes>"
    return str(value)


def statement_keyword(sql: str) -> str:
    """The leading keyword of a statement, with leading comments stripped."""
    cleaned = sql.strip()
    while cleaned.startswith("--") or cleaned.startswith("/*"):
        if cleaned.startswith("--"):
            cleaned = cleaned.split("\n", 1)[-1].strip()
        else:
            end = cleaned.find("*/")
            if end == -1:
                break
            cleaned = cleaned[end + 2 :].strip()
    parts = cleaned.split()
    return parts[0].upper() if parts else ""


def is_write_query(sql: str) -> bool:
    return statement_keyword(sql) in WRITE_KEYWORDS


def identifier(name: str, *, what: str = "Nesne adı") -> str:
    """Validate a name that has to be interpolated, since Oracle cannot bind identifiers."""
    candidate = name.strip().strip('"')
    if not IDENTIFIER.match(candidate):
        raise ToolError(
            f"{what} geçersiz: {name!r}. Yalnızca harf, rakam ve _ $ # kullanılabilir."
        )
    return candidate.upper()


# ---------------------------------------------------------------------------
# Database access
# ---------------------------------------------------------------------------


class Database:
    """The Oracle connection, with every blocking oracledb call on a worker thread."""

    def __init__(self) -> None:
        self.connection: oracledb.Connection | None = None
        self.version = "Oracle"
        self.read_only = os.getenv("READ_ONLY", "").lower() in ("true", "1", "yes")
        self.db_identifier = ""
        self.workspace_path = os.getcwd()
        self.dbms_output_enabled = False
        self.last_dbms_output_check = 0.0
        if self.read_only:
            logger.info("Read-only mode enabled - write queries will be blocked")

    # -- connection --------------------------------------------------------

    @staticmethod
    def _parse_connection_string(raw: str) -> tuple[str, str, str]:
        """Pull user, password and DSN out of the .NET-style connection string."""
        fields = {}
        for part in raw.split(";"):
            if "=" in part:
                key, value = part.split("=", 1)
                fields[key.strip().lower()] = value
        try:
            return fields["user id"], fields["password"], fields["data source"]
        except KeyError as exc:
            raise ToolError(
                "ORACLE_CONNECTION_STRING biçimi hatalı. Beklenen: "
                "'User Id=...;Password=...;Data Source=...'"
            ) from exc

    def _connect_blocking(self, user: str, password: str, dsn: str) -> None:
        self.connection = oracledb.connect(user=user, password=password, dsn=dsn)

    async def connect(self) -> None:
        raw = os.getenv("ORACLE_CONNECTION_STRING")
        if not raw:
            raise ToolError("ORACLE_CONNECTION_STRING ayarlı değil.")
        user, password, dsn = self._parse_connection_string(raw)

        try:
            await anyio.to_thread.run_sync(self._connect_blocking, user, password, dsn)
        except oracledb.Error as exc:
            logger.error("Oracle bağlantısı kurulamadı: %s", exc)
            raise ToolError(f"Oracle bağlantısı kurulamadı ({dsn}): {exc}") from exc

        self.db_identifier = dsn
        logger.info("Oracle bağlantısı kuruldu: %s", dsn)
        await self._detect_version()
        await self.enable_dbms_output()

    def close(self) -> None:
        if self.connection:
            try:
                self.connection.close()
            except Exception as exc:
                logger.debug("Bağlantı kapatılırken hata: %s", exc)
            finally:
                self.connection = None

    async def ensure(self) -> None:
        if self.connection is None:
            await self.connect()

    async def _detect_version(self) -> None:
        """Name the Oracle release, preferring version_full (18c and later)."""
        for column in ("version_full", "version"):
            try:
                value = await self.scalar(f"SELECT {column} FROM v$instance")
            except ToolError:
                continue
            if value:
                major = str(value).split(".")[0]
                self.version = f"Oracle {VERSION_SUFFIXES.get(major, major)}"
                logger.info("Oracle sürümü: %s (%s=%s)", self.version, column, value)
                return
        logger.warning("Oracle sürümü tespit edilemedi, varsayılan kullanılıyor")

    # -- running statements ------------------------------------------------

    def _fetch_blocking(
        self, sql: str, params: dict | None
    ) -> tuple[list[dict], list[str], int]:
        assert self.connection is not None
        with self.connection.cursor() as cursor:
            cursor.execute(sql, params or {})
            if cursor.description is None:
                self.connection.commit()
                return [], [], max(cursor.rowcount, 0)
            columns = [desc[0] for desc in cursor.description]
            rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
            return rows, columns, len(rows)

    async def fetch(
        self, sql: str, params: dict | None = None
    ) -> tuple[list[dict], list[str], int]:
        await self.ensure()
        try:
            return await anyio.to_thread.run_sync(self._fetch_blocking, sql, params)
        except oracledb.Error as exc:
            raise ToolError(f"Oracle SQL hatası: {str(exc).strip()}") from exc

    async def scalar(self, sql: str, params: dict | None = None) -> Any:
        rows, _, _ = await self.fetch(sql, params)
        if not rows:
            return None
        return next(iter(rows[0].values()))

    # -- DBMS_OUTPUT -------------------------------------------------------

    def _enable_dbms_output_blocking(self, buffer_size: int | None) -> None:
        assert self.connection is not None
        with self.connection.cursor() as cursor:
            size = "NULL" if buffer_size is None else str(buffer_size)
            cursor.execute(f"BEGIN DBMS_OUTPUT.ENABLE({size}); END;")

    async def enable_dbms_output(self, buffer_size: int | None = DBMS_OUTPUT_BUFFER_BYTES) -> None:
        """Turn DBMS_OUTPUT on for this session. None means an unlimited buffer."""
        await self.ensure()
        try:
            await anyio.to_thread.run_sync(self._enable_dbms_output_blocking, buffer_size)
        except oracledb.Error as exc:
            logger.error("DBMS_OUTPUT açılamadı: %s", exc)
            self.dbms_output_enabled = False
            return
        self.dbms_output_enabled = True
        self.last_dbms_output_check = time.time()
        logger.info(
            "DBMS_OUTPUT açık (buffer: %s)",
            "sınırsız" if buffer_size is None else f"{buffer_size:,} bayt",
        )

    def _drain_dbms_output_blocking(self, max_lines: int) -> list[str]:
        assert self.connection is not None
        lines: list[str] = []
        with self.connection.cursor() as cursor:
            line = cursor.var(str)
            status = cursor.var(int)
            while len(lines) < max_lines:
                cursor.execute(
                    "BEGIN DBMS_OUTPUT.GET_LINE(:line, :status); END;", line=line, status=status
                )
                if status.getvalue() != 0:
                    break
                lines.append(line.getvalue() or "")
        return lines

    async def drain_dbms_output(self, max_lines: int = DBMS_OUTPUT_MAX_LINES) -> str:
        """Read and clear whatever the session has buffered."""
        if self.connection is None:
            return ""
        try:
            lines = await anyio.to_thread.run_sync(self._drain_dbms_output_blocking, max_lines)
        except oracledb.DatabaseError as exc:
            (error_obj,) = exc.args
            if getattr(error_obj, "code", None) == 20000:  # ORU-10027: buffer overflow
                logger.warning("DBMS_OUTPUT buffer taştı, sınırsıza alınıyor")
                await self.enable_dbms_output(None)
                return "⚠️ DBMS_OUTPUT buffer taştı; buffer temizlendi ve sınırsıza alındı."
            logger.warning("DBMS_OUTPUT okunamadı: %s", exc)
            return ""

        if len(lines) >= max_lines:
            lines.append(f"... (çıktı {max_lines} satırda kesildi)")
        return "\n".join(lines)

    async def refresh_dbms_output(self, force: bool = False) -> None:
        """Re-enable DBMS_OUTPUT if the session lost it, at most once a minute."""
        if not force and time.time() - self.last_dbms_output_check < DBMS_OUTPUT_CHECK_INTERVAL:
            return
        await self.drain_dbms_output()
        await self.enable_dbms_output()

    # -- logging -----------------------------------------------------------

    def log_query(self, tool_name: str, **fields) -> None:
        direct_log_query_execution(
            server_type="oracle",
            tool_name=tool_name,
            db_identifier=self.db_identifier,
            workspace_path=self.workspace_path,
            **fields,
        )


# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------


@dataclass
class AppContext:
    db: Database


# Resources cannot read the lifespan context in v2, so they go through this.
_app: AppContext | None = None


@asynccontextmanager
async def app_lifespan(server: MCPServer) -> AsyncIterator[AppContext]:
    global _app
    db = Database()
    _app = AppContext(db=db)
    try:
        yield _app
    finally:
        db.close()
        _app = None


mcp = MCPServer("oracle-mcp-server", version=__version__, lifespan=app_lifespan)

_READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=False)


def _db(ctx: Context[AppContext]) -> Database:
    return ctx.request_context.lifespan_context.db


def _require_app() -> AppContext:
    if _app is None:
        raise ResourceError("Sunucu henüz hazır değil.")
    return _app


# -- execute_sql -------------------------------------------------------------


class WriteConfirmation(BaseModel):
    """The user's answer to a write-statement question."""

    confirm: bool = Field(description="Run this statement against the database?")


async def confirm_write(
    ctx: Context[AppContext], sql: str = ""
) -> WriteConfirmation | Elicit[WriteConfirmation]:
    """Ask before running anything that changes the database."""
    db = _db(ctx)
    if db.read_only or not is_write_query(sql):
        return WriteConfirmation(confirm=True)

    keyword = statement_keyword(sql)
    warning = " Bu işlem geri alınamaz." if keyword in IRREVERSIBLE_KEYWORDS else ""
    return Elicit(
        f"Bu {keyword} ifadesi '{db.db_identifier}' veritabanını değiştirecek.{warning}\n\n"
        f"    {sql.strip()}\n\nÇalıştırılsın mı?",
        WriteConfirmation,
    )


@mcp.tool(
    title="SQL / PL/SQL çalıştır",
    description="Execute Oracle SQL or a PL/SQL block. Use Oracle dictionary views "
    "(USER_TABLES, ALL_TABLES, USER_TAB_COLUMNS), not information_schema. SELECTs get a "
    "FETCH FIRST if they have none; DBMS_OUTPUT from a PL/SQL block is returned alongside "
    "the result. Writes are confirmed with the user first.",
    annotations=ToolAnnotations(
        read_only_hint=False, destructive_hint=True, idempotent_hint=False, open_world_hint=False
    ),
)
async def execute_sql(
    sql: Annotated[str, Field(min_length=1, description="Oracle SQL query or PL/SQL block.")],
    ctx: Context[AppContext],
    confirmation: Annotated[WriteConfirmation, Resolve(confirm_write)],
    limit: Annotated[
        int,
        Field(ge=1, le=10000, description="Row limit added to a SELECT that has no ROWNUM/FETCH."),
    ] = DEFAULT_ROW_LIMIT,
) -> QueryResult:
    db = _db(ctx)

    if db.read_only and is_write_query(sql):
        raise ToolError(
            "Read-only mod açık: INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, TRUNCATE, "
            "MERGE, GRANT ve REVOKE engellendi. Yazma için READ_ONLY=false yap."
        )
    if not confirmation.confirm:
        raise ToolError("Kullanıcı ifadeyi onaylamadı; veritabanında hiçbir şey değişmedi.")

    return await _run_sql(db, sql, limit)


def _strip_line_comments(sql: str) -> str:
    """The statement without -- comments, for deciding what kind of statement it is."""
    kept = []
    for line in sql.strip().split("\n"):
        if "--" in line:
            line = line[: line.index("--")]
        if line.strip():
            kept.append(line)
    return " ".join(kept).strip()


async def _run_sql(db: Database, sql: str, limit: int) -> QueryResult:
    """Run one statement, apply the row limit, collect DBMS_OUTPUT, and log it."""
    cleaned = _strip_line_comments(sql)
    upper = cleaned.upper()
    is_select = upper.startswith("SELECT") or upper.startswith("WITH")
    is_plsql = any(word in upper for word in ("BEGIN", "DECLARE", "CREATE OR REPLACE"))

    effective_sql = sql.strip()
    limit_applied: int | None = None
    if is_select and "ROWNUM" not in upper and "FETCH" not in upper:
        effective_sql = f"{effective_sql} FETCH FIRST {limit} ROWS ONLY"
        limit_applied = limit

    if is_plsql:
        # A block that prints needs the buffer on and empty before it runs.
        await db.refresh_dbms_output(force="DBMS_OUTPUT" in upper)

    started = time.time()
    try:
        rows, columns, affected = await db.fetch(effective_sql)
    except ToolError as exc:
        db.log_query(
            "execute_sql",
            query_text=effective_sql,
            execution_time_ms=(time.time() - started) * 1000,
            status="error",
            row_count=0,
            error_message=str(exc),
        )
        raise

    dbms_output = await db.drain_dbms_output() if is_plsql else ""
    duration = (time.time() - started) * 1000

    result = QueryResult(
        sql=effective_sql,
        columns=columns,
        rows=[{k: _jsonable(v) for k, v in row.items()} for row in rows],
        row_count=len(rows) if columns else affected,
        limit_applied=limit_applied,
        dbms_output=dbms_output,
        duration_ms=duration,
    )
    db.log_query(
        "execute_sql",
        query_text=effective_sql,
        execution_time_ms=duration,
        status="success",
        row_count=result.row_count,
        error_message="",
    )
    return result


# -- schema exploration ------------------------------------------------------


@mcp.tool(
    title="Tabloyu tanımla",
    description="Get a table's columns and row count from USER_TAB_COLUMNS.",
    annotations=_READ_ONLY,
)
async def describe_table(
    table_name: Annotated[str, Field(min_length=1, description="Table name (case-insensitive).")],
    ctx: Context[AppContext],
) -> TableDescription:
    db = _db(ctx)
    table = identifier(table_name, what="Tablo adı")

    columns = await _fetch_columns(db, table)
    if not columns:
        raise ToolError(f"'{table}' diye bir tablo yok (USER_TAB_COLUMNS'ta bulunamadı).")

    await ctx.report_progress(1, 2, "satır sayısı")
    row_count = await db.scalar(f'SELECT COUNT(*) FROM "{table}"')
    await ctx.report_progress(2, 2, "tamamlandı")

    return TableDescription(
        table_name=table, columns=columns, row_count=int(row_count or 0)
    )


async def _fetch_columns(db: Database, table: str) -> list[ColumnInfo]:
    rows, _, _ = await db.fetch(
        """SELECT column_name, data_type, data_length, nullable, data_default, column_id
           FROM user_tab_columns
           WHERE table_name = :table_name
           ORDER BY column_id""",
        {"table_name": table},
    )
    return [
        ColumnInfo(
            name=row["COLUMN_NAME"],
            data_type=row["DATA_TYPE"],
            length=row["DATA_LENGTH"],
            nullable=row["NULLABLE"] == "Y",
            default=_jsonable(row["DATA_DEFAULT"]),
            position=row["COLUMN_ID"],
        )
        for row in rows
    ]


@mcp.tool(
    title="Kaynak kodu getir",
    description="Get the source of a PL/SQL object (FUNCTION, PROCEDURE, TRIGGER, PACKAGE, "
    "PACKAGE BODY, TYPE) from USER_SOURCE.",
    annotations=_READ_ONLY,
)
async def get_source_code(
    object_name: Annotated[str, Field(min_length=1, description="Object name (case-insensitive).")],
    ctx: Context[AppContext],
    object_type: Annotated[
        str,
        Field(
            description="FUNCTION, PROCEDURE, TRIGGER, PACKAGE, PACKAGE BODY, TYPE. "
            "Empty searches every type and picks the first match."
        ),
    ] = "",
) -> SourceCode:
    db = _db(ctx)
    name = identifier(object_name, what="Nesne adı")

    other_types: list[str] = []
    wanted = object_type.strip().upper()
    if not wanted:
        type_rows, _, _ = await db.fetch(
            "SELECT type FROM user_source WHERE name = :name GROUP BY type ORDER BY type",
            {"name": name},
        )
        if not type_rows:
            raise ToolError(f"'{name}' adında bir kaynak nesnesi yok.")
        found = [row["TYPE"] for row in type_rows]
        wanted = found[0]
        other_types = found[1:]
    elif wanted not in SOURCE_TYPES:
        raise ToolError(f"Bilinmeyen nesne tipi: {object_type!r}. Geçerli: {', '.join(SOURCE_TYPES)}")

    rows, _, _ = await db.fetch(
        """SELECT text FROM user_source
           WHERE name = :name AND type = :type
           ORDER BY line""",
        {"name": name, "type": wanted},
    )
    if not rows:
        raise ToolError(f"'{name}' için {wanted} kaynağı bulunamadı.")

    source = "".join(_jsonable(row["TEXT"]) or "" for row in rows)
    db.log_query(
        "get_source_code",
        query_text=f"GET SOURCE: {name} ({wanted})",
        execution_time_ms=0,
        status="success",
        row_count=len(rows),
        error_message="",
    )
    return SourceCode(
        object_name=name,
        object_type=wanted,
        other_types=other_types,
        line_count=len(rows),
        source=source,
    )


@mcp.tool(
    title="View tanımını getir",
    description="Get a view's SQL definition from USER_VIEWS.",
    annotations=_READ_ONLY,
)
async def get_view_definition(
    view_name: Annotated[str, Field(min_length=1, description="View name (case-insensitive).")],
    ctx: Context[AppContext],
) -> ViewDefinition:
    db = _db(ctx)
    name = identifier(view_name, what="View adı")

    rows, _, _ = await db.fetch(
        "SELECT text, text_length, text_vc FROM user_views WHERE view_name = :name",
        {"name": name},
    )
    if not rows:
        raise ToolError(f"'{name}' diye bir view yok.")

    row = rows[0]
    definition = _jsonable(row["TEXT"]) or _jsonable(row["TEXT_VC"]) or ""
    return ViewDefinition(
        view_name=name, text_length=int(row["TEXT_LENGTH"] or 0), definition=definition
    )


@mcp.tool(
    title="Tablo ara",
    description="Search tables by name pattern (% wildcard) in USER_TABLES.",
    annotations=_READ_ONLY,
)
async def search_tables(
    pattern: Annotated[str, Field(min_length=1, description="Name pattern, % as wildcard.")],
    ctx: Context[AppContext],
    limit: Annotated[int, Field(ge=1, le=1000, description="Maximum results.")] = DEFAULT_ROW_LIMIT,
) -> list[TableMatch]:
    db = _db(ctx)
    rows, _, _ = await db.fetch(
        """SELECT table_name, tablespace_name, status, num_rows
           FROM user_tables
           WHERE UPPER(table_name) LIKE UPPER(:pattern)
           ORDER BY table_name
           FETCH FIRST :row_limit ROWS ONLY""",
        {"pattern": pattern, "row_limit": limit},
    )
    return [
        TableMatch(
            table_name=row["TABLE_NAME"],
            tablespace=row["TABLESPACE_NAME"],
            status=row["STATUS"],
            num_rows=row["NUM_ROWS"],
        )
        for row in rows
    ]


@mcp.tool(
    title="Kolon ara",
    description="Search for columns across every table in USER_TAB_COLUMNS.",
    annotations=_READ_ONLY,
)
async def search_columns(
    pattern: Annotated[str, Field(min_length=1, description="Column name pattern, % as wildcard.")],
    ctx: Context[AppContext],
    data_type: Annotated[
        str, Field(description="Only columns of this type, e.g. NUMBER, VARCHAR2.")
    ] = "",
    limit: Annotated[int, Field(ge=1, le=1000, description="Maximum results.")] = DEFAULT_ROW_LIMIT,
) -> list[ColumnMatch]:
    db = _db(ctx)
    sql = """SELECT DISTINCT table_name, column_name, data_type, data_length
             FROM user_tab_columns
             WHERE UPPER(column_name) LIKE UPPER(:pattern)"""
    params: dict[str, Any] = {"pattern": pattern, "row_limit": limit}
    if data_type:
        sql += " AND UPPER(data_type) = UPPER(:data_type)"
        params["data_type"] = data_type
    sql += " ORDER BY table_name, column_name FETCH FIRST :row_limit ROWS ONLY"

    rows, _, _ = await db.fetch(sql, params)
    return [
        ColumnMatch(
            table_name=row["TABLE_NAME"],
            column_name=row["COLUMN_NAME"],
            data_type=row["DATA_TYPE"],
            length=row["DATA_LENGTH"],
        )
        for row in rows
    ]


@mcp.tool(
    title="Tablo indeksleri",
    description="Get every index on a table, with its columns in order.",
    annotations=_READ_ONLY,
)
async def get_table_indexes(
    table_name: Annotated[str, Field(min_length=1, description="Table name (case-insensitive).")],
    ctx: Context[AppContext],
) -> list[IndexInfo]:
    db = _db(ctx)
    table = identifier(table_name, what="Tablo adı")

    rows, _, _ = await db.fetch(
        """SELECT ui.index_name, ui.index_type, ui.uniqueness, ui.status,
                  uic.column_name, uic.column_position
           FROM user_indexes ui
           JOIN user_ind_columns uic ON ui.index_name = uic.index_name
           WHERE ui.table_name = :table_name
           ORDER BY ui.index_name, uic.column_position""",
        {"table_name": table},
    )
    if not rows:
        raise ToolError(f"'{table}' tablosunda indeks yok ya da tablo bulunamadı.")

    indexes: dict[str, IndexInfo] = {}
    for row in rows:
        info = indexes.get(row["INDEX_NAME"])
        if info is None:
            info = IndexInfo(
                index_name=row["INDEX_NAME"],
                index_type=row["INDEX_TYPE"],
                unique=row["UNIQUENESS"] == "UNIQUE",
                status=row["STATUS"],
                columns=[],
            )
            indexes[row["INDEX_NAME"]] = info
        info.columns.append(
            IndexColumn(name=row["COLUMN_NAME"], position=row["COLUMN_POSITION"])
        )
    return list(indexes.values())


_CONSTRAINT_LABELS = {"P": "Primary Key", "R": "Foreign Key", "C": "Check", "U": "Unique"}


@mcp.tool(
    title="Tablo kısıtları",
    description="Get a table's constraints: primary keys, foreign keys, checks and uniques.",
    annotations=_READ_ONLY,
)
async def get_table_constraints(
    table_name: Annotated[str, Field(min_length=1, description="Table name (case-insensitive).")],
    ctx: Context[AppContext],
    constraint_type: Annotated[
        ConstraintType | None,
        Field(description="P primary, R foreign, C check, U unique. Omit for all of them."),
    ] = None,
) -> list[ConstraintInfo]:
    db = _db(ctx)
    table = identifier(table_name, what="Tablo adı")

    sql = """SELECT uc.constraint_name, uc.constraint_type, uc.status, uc.search_condition,
                    uc.r_constraint_name, ucc.column_name, ucc.position
             FROM user_constraints uc
             LEFT JOIN user_cons_columns ucc ON uc.constraint_name = ucc.constraint_name
             WHERE uc.table_name = :table_name"""
    params: dict[str, Any] = {"table_name": table}
    if constraint_type:
        sql += " AND uc.constraint_type = :constraint_type"
        params["constraint_type"] = constraint_type
    sql += " ORDER BY uc.constraint_type, uc.constraint_name, ucc.position"

    rows, _, _ = await db.fetch(sql, params)
    if not rows:
        raise ToolError(f"'{table}' tablosunda kısıt bulunamadı.")

    constraints: dict[str, ConstraintInfo] = {}
    for row in rows:
        info = constraints.get(row["CONSTRAINT_NAME"])
        if info is None:
            kind = row["CONSTRAINT_TYPE"]
            info = ConstraintInfo(
                constraint_name=row["CONSTRAINT_NAME"],
                constraint_type=kind,
                type_label=_CONSTRAINT_LABELS.get(kind, kind),
                status=row["STATUS"],
                search_condition=_jsonable(row["SEARCH_CONDITION"]),
                references_constraint=row["R_CONSTRAINT_NAME"],
            )
            constraints[row["CONSTRAINT_NAME"]] = info
        if row["COLUMN_NAME"]:
            info.columns.append(row["COLUMN_NAME"])
    return list(constraints.values())


@mcp.tool(
    title="Tablo boyutu",
    description="Analyze a table's size, row count and optimizer statistics.",
    annotations=_READ_ONLY,
)
async def analyze_table_size(
    table_name: Annotated[str, Field(min_length=1, description="Table name (case-insensitive).")],
    ctx: Context[AppContext],
) -> TableSize:
    db = _db(ctx)
    table = identifier(table_name, what="Tablo adı")

    rows, _, _ = await db.fetch(
        """SELECT t.table_name, t.num_rows, t.avg_row_len, t.blocks,
                  ROUND(s.bytes/1024/1024, 2) AS size_mb, t.last_analyzed,
                  COUNT(DISTINCT tc.column_name) AS column_count
           FROM user_tables t
           LEFT JOIN user_segments s
             ON t.table_name = s.segment_name AND s.segment_type = 'TABLE'
           LEFT JOIN user_tab_columns tc ON t.table_name = tc.table_name
           WHERE t.table_name = :table_name
           GROUP BY t.table_name, t.num_rows, t.avg_row_len, t.blocks, s.bytes, t.last_analyzed""",
        {"table_name": table},
    )
    if not rows:
        raise ToolError(f"'{table}' diye bir tablo yok.")

    row = rows[0]
    num_rows = row["NUM_ROWS"]
    avg_row_len = row["AVG_ROW_LEN"]
    estimated = (
        round((num_rows * avg_row_len) / (1024 * 1024), 2) if num_rows and avg_row_len else None
    )
    return TableSize(
        table_name=row["TABLE_NAME"],
        num_rows=num_rows,
        avg_row_len=avg_row_len,
        blocks=row["BLOCKS"],
        size_mb=float(row["SIZE_MB"]) if row["SIZE_MB"] is not None else None,
        estimated_mb=estimated,
        column_count=int(row["COLUMN_COUNT"] or 0),
        last_analyzed=_jsonable(row["LAST_ANALYZED"]),
    )


@mcp.tool(
    title="Tablo ilişkileri",
    description="Get a table's foreign key relationships, in either or both directions.",
    annotations=_READ_ONLY,
)
async def get_table_relationships(
    table_name: Annotated[str, Field(min_length=1, description="Table name (case-insensitive).")],
    ctx: Context[AppContext],
    direction: Annotated[
        Direction,
        Field(
            description="outgoing: keys this table declares. incoming: keys pointing at it. "
            "both: all of them."
        ),
    ] = "both",
) -> Relationships:
    db = _db(ctx)
    table = identifier(table_name, what="Tablo adı")
    result = Relationships(table_name=table, direction=direction)

    base = """SELECT c.constraint_name, c.table_name AS from_table,
                     c2.table_name AS to_table,
                     LISTAGG(cc.column_name, ', ') WITHIN GROUP (ORDER BY cc.position) AS from_columns,
                     LISTAGG(cc2.column_name, ', ') WITHIN GROUP (ORDER BY cc2.position) AS to_columns
              FROM user_constraints c
              JOIN user_constraints c2 ON c.r_constraint_name = c2.constraint_name
              JOIN user_cons_columns cc ON c.constraint_name = cc.constraint_name
              JOIN user_cons_columns cc2 ON c2.constraint_name = cc2.constraint_name
              WHERE c.constraint_type = 'R' AND {filter}
              GROUP BY c.constraint_name, c.table_name, c2.table_name"""

    if direction in ("outgoing", "both"):
        rows, _, _ = await db.fetch(
            base.format(filter="c.table_name = :table_name"), {"table_name": table}
        )
        result.outgoing = [_relationship(row) for row in rows]

    if direction in ("incoming", "both"):
        rows, _, _ = await db.fetch(
            base.format(filter="c2.table_name = :table_name"), {"table_name": table}
        )
        result.incoming = [_relationship(row) for row in rows]

    return result


def _relationship(row: dict) -> Relationship:
    return Relationship(
        constraint_name=row["CONSTRAINT_NAME"],
        from_table=row["FROM_TABLE"],
        from_columns=row["FROM_COLUMNS"],
        to_table=row["TO_TABLE"],
        to_columns=row["TO_COLUMNS"],
    )


@mcp.tool(
    title="Nesneleri listele",
    description="List database objects of one type from USER_OBJECTS.",
    annotations=_READ_ONLY,
)
async def list_database_objects(
    object_type: Annotated[ObjectType, Field(description="Which kind of object to list.")],
    ctx: Context[AppContext],
    pattern: Annotated[
        str, Field(description="Name filter, % as wildcard. Empty means all of them.")
    ] = "",
    limit: Annotated[int, Field(ge=1, le=1000, description="Maximum results.")] = DEFAULT_ROW_LIMIT,
) -> ObjectListing:
    db = _db(ctx)
    sql = """SELECT object_name, status, created, last_ddl_time
             FROM user_objects
             WHERE object_type = :object_type"""
    params: dict[str, Any] = {"object_type": object_type, "row_limit": limit}
    if pattern:
        sql += " AND UPPER(object_name) LIKE UPPER(:pattern)"
        params["pattern"] = pattern
    sql += " ORDER BY object_name FETCH FIRST :row_limit ROWS ONLY"

    rows, _, _ = await db.fetch(sql, params)
    return ObjectListing(
        object_type=object_type,
        pattern=pattern,
        objects=[
            DatabaseObject(
                object_name=row["OBJECT_NAME"],
                status=row["STATUS"],
                created=_jsonable(row["CREATED"]),
                last_ddl_time=_jsonable(row["LAST_DDL_TIME"]),
            )
            for row in rows
        ],
    )


@mcp.tool(
    title="Sorgu planı",
    description="Show a query's execution plan with EXPLAIN PLAN and DBMS_XPLAN. The query "
    "itself is not run.",
    annotations=ToolAnnotations(
        read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=False
    ),
)
async def explain_plan(
    sql: Annotated[str, Field(min_length=1, description="SQL query to explain.")],
    ctx: Context[AppContext],
    format: Annotated[PlanFormat, Field(description="Level of detail in the plan.")] = "typical",
) -> ExplainPlan:
    db = _db(ctx)
    statement_id = f"MCP_{uuid.uuid4().hex[:20]}"

    try:
        await db.fetch(f"EXPLAIN PLAN SET STATEMENT_ID = '{statement_id}' FOR {sql}")
        rows, _, _ = await db.fetch(
            """SELECT plan_table_output
               FROM TABLE(DBMS_XPLAN.DISPLAY('PLAN_TABLE', :statement_id, :fmt))""",
            {"statement_id": statement_id, "fmt": format.upper()},
        )
        plan = "\n".join(str(_jsonable(next(iter(row.values())))) for row in rows)
    finally:
        try:
            await db.fetch(
                "DELETE FROM plan_table WHERE statement_id = :statement_id",
                {"statement_id": statement_id},
            )
        except ToolError as exc:
            logger.warning("PLAN_TABLE temizlenemedi: %s", exc)

    return ExplainPlan(sql=sql, format=format, plan=plan)


@mcp.tool(
    name="get_query_history",
    title="Sorgu geçmişi",
    description="Recent queries run against this database from this workspace, with timings, "
    "statuses and errors.",
    annotations=_READ_ONLY,
)
def get_query_history_tool(
    ctx: Context[AppContext],
    limit: Annotated[int, Field(ge=1, le=500, description="How many entries to return.")] = 20,
    status: Annotated[
        HistoryStatus | None, Field(description="Only successes, or only failures.")
    ] = None,
    tool_name: Annotated[
        str, Field(description="Only entries from this tool, e.g. 'execute_sql'.")
    ] = "",
) -> QueryHistory:
    db = _db(ctx)
    logs = get_query_history(
        db_identifier=db.db_identifier,
        workspace_path=db.workspace_path,
        limit=limit,
        status=status or "",
        tool_name=tool_name,
    )
    return QueryHistory(
        db_identifier=db.db_identifier,
        workspace_path=db.workspace_path,
        entries=[
            HistoryEntry(
                timestamp=log["timestamp"],
                tool_name=log["tool_name"],
                query_text=log["query_text"],
                execution_time_ms=log["execution_time_ms"],
                row_count=log["row_count"],
                status=log["status"],
                error_message=log.get("error_message") or "",
                user_query=log.get("user_query") or "",
            )
            for log in logs
        ],
    )


# ---------------------------------------------------------------------------
# Resources & prompts
# ---------------------------------------------------------------------------


@mcp.resource(
    "oracle://tables",
    name="Database Tables",
    description="Şemadaki tüm tablolar, tablespace ve durum bilgisiyle.",
    mime_type="application/json",
)
async def tables_resource() -> str:
    db = _require_app().db
    rows, _, _ = await db.fetch(
        "SELECT table_name, tablespace_name, status, num_rows FROM user_tables ORDER BY table_name"
    )
    matches = [
        TableMatch(
            table_name=row["TABLE_NAME"],
            tablespace=row["TABLESPACE_NAME"],
            status=row["STATUS"],
            num_rows=row["NUM_ROWS"],
        )
        for row in rows
    ]
    return json.dumps([m.model_dump() for m in matches], ensure_ascii=False, indent=2)


@mcp.resource(
    "oracle://schema",
    name="Database Schema",
    description="Tüm tabloların kolon yapısı.",
    mime_type="application/json",
)
async def schema_resource() -> str:
    db = _require_app().db
    rows, _, _ = await db.fetch(
        """SELECT table_name, column_name, data_type, data_length, nullable, data_default, column_id
           FROM user_tab_columns
           ORDER BY table_name, column_id"""
    )
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        grouped.setdefault(row["TABLE_NAME"], []).append(
            {
                "name": row["COLUMN_NAME"],
                "data_type": row["DATA_TYPE"],
                "length": row["DATA_LENGTH"],
                "nullable": row["NULLABLE"] == "Y",
                "default": _jsonable(row["DATA_DEFAULT"]),
                "position": row["COLUMN_ID"],
            }
        )
    return json.dumps(grouped, ensure_ascii=False, indent=2)


@mcp.resource(
    "oracle://stats",
    name="Database Statistics",
    description="Oracle sürümü, instance bilgisi, tablo sayısı ve toplam segment boyutu.",
    mime_type="application/json",
)
async def stats_resource() -> str:
    db = _require_app().db
    info = DatabaseInfo(version=db.version)

    rows, _, _ = await db.fetch("SELECT instance_name, host_name FROM v$instance")
    if rows:
        info.instance = rows[0]["INSTANCE_NAME"] or ""
        info.host = rows[0]["HOST_NAME"] or ""

    info.table_count = int(await db.scalar("SELECT COUNT(*) FROM user_tables") or 0)
    total = await db.scalar(
        "SELECT ROUND(SUM(bytes)/1024/1024, 2) FROM user_segments WHERE segment_type = 'TABLE'"
    )
    info.total_size_mb = float(total) if total is not None else None
    return info.model_dump_json(indent=2)


@mcp.resource(
    "oracle://table/{table_name}",
    name="Tablo yapısı",
    description="Bir tablonun kolonları ve satır sayısı.",
    mime_type="application/json",
)
async def table_resource(table_name: str) -> str:
    db = _require_app().db
    try:
        table = identifier(table_name, what="Tablo adı")
    except ToolError as exc:
        raise ResourceError(str(exc)) from exc

    columns = await _fetch_columns(db, table)
    if not columns:
        raise ResourceError(f"'{table}' diye bir tablo yok.")
    row_count = await db.scalar(f'SELECT COUNT(*) FROM "{table}"')
    return TableDescription(
        table_name=table, columns=columns, row_count=int(row_count or 0)
    ).model_dump_json(indent=2)


@mcp.resource(
    "oracle://source/{object_type}/{object_name}",
    name="PL/SQL kaynağı",
    description="Bir PL/SQL nesnesinin kaynak kodu. object_type: FUNCTION, PROCEDURE, "
    "TRIGGER, PACKAGE, PACKAGE BODY, TYPE.",
    mime_type="text/plain",
)
async def source_resource(object_type: str, object_name: str) -> str:
    db = _require_app().db
    kind = object_type.replace("_", " ").upper()
    if kind not in SOURCE_TYPES:
        raise ResourceError(f"Bilinmeyen nesne tipi: {object_type!r}")
    try:
        name = identifier(object_name, what="Nesne adı")
    except ToolError as exc:
        raise ResourceError(str(exc)) from exc

    rows, _, _ = await db.fetch(
        "SELECT text FROM user_source WHERE name = :name AND type = :type ORDER BY line",
        {"name": name, "type": kind},
    )
    if not rows:
        raise ResourceError(f"'{name}' için {kind} kaynağı bulunamadı.")
    return "".join(_jsonable(row["TEXT"]) or "" for row in rows)


@mcp.prompt(title="PL/SQL nesnesini incele")
def review_plsql(object_name: str, object_type: str = "") -> str:
    """Read a PL/SQL object's source and review it."""
    which = f"{object_type} {object_name}" if object_type else object_name
    return (
        f"'{which}' PL/SQL nesnesini incele:\n\n"
        f"1. `get_source_code('{object_name}'{f', {object_type!r}' if object_type else ''})` "
        "ile kaynağı al.\n"
        "2. Ne yaptığını, hangi tabloları okuyup yazdığını özetle.\n"
        "3. Doğruluk sorunlarını ara: ele alınmayan istisnalar, NULL kontrolü eksikleri, "
        "commit/rollback yerleri, döngü içindeki tekil DML'ler.\n"
        "4. Performans sorunlarını ara: satır satır işleme, indekslenmemiş kolonda filtre, "
        "gereksiz tam tablo taraması. Gerekirse `explain_plan` ile doğrula.\n"
        "5. Bulguları ciddiyet sırasına koy ve her biri için somut düzeltme öner."
    )


@mcp.prompt(title="Tabloyu analiz et")
def analyze_table(table_name: str) -> str:
    """Look a table over: shape, statistics, indexes and relationships."""
    return (
        f"'{table_name}' tablosunu analiz et:\n\n"
        f"1. `describe_table('{table_name}')` ile kolonları ve satır sayısını al.\n"
        f"2. `analyze_table_size('{table_name}')` ile boyutu ve istatistikleri al — "
        "last_analyzed eskiyse bunu belirt.\n"
        f"3. `get_table_indexes('{table_name}')` ve `get_table_constraints('{table_name}')` "
        "ile indeksleri ve kısıtları listele.\n"
        f"4. `get_table_relationships('{table_name}')` ile hangi tablolara bağlı olduğunu çıkar.\n"
        "5. Eksik indeks, eksik kısıt, şüpheli tip seçimi gibi sorunları ve önerileri yaz."
    )


if __name__ == "__main__":
    mcp.run()
