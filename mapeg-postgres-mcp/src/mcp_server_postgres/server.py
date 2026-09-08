#!/usr/bin/env python3
"""
PostgreSQL MCP Server
Query, explore and analyze a PostgreSQL database over MCP.
"""

import json
import logging
import os
import re
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import date, datetime, time as dtime
from decimal import Decimal
from typing import Annotated, Any, Literal
from uuid import UUID

import anyio
import psycopg2
from dotenv import load_dotenv
from mcp.server import MCPServer
from mcp.server.mcpserver import Context, Elicit, Resolve
from mcp.server.mcpserver.exceptions import ResourceError, ToolError
from mcp.types import ToolAnnotations
from psycopg2.extras import RealDictCursor
from pydantic import BaseModel, Field

from . import __version__
from .query_logger import direct_log_query_execution, get_query_history

load_dotenv()

logger = logging.getLogger(__name__)

DEFAULT_ROW_LIMIT = 100

# Statements that change the database. Anything starting with one of these
# is a write, and is refused in read-only mode and confirmed otherwise.
WRITE_KEYWORDS = frozenset(
    ["INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "TRUNCATE", "MERGE", "GRANT", "REVOKE"]
)

# Writes that cannot be undone once they run.
IRREVERSIBLE_KEYWORDS = frozenset(["DROP", "TRUNCATE", "DELETE"])


# ---------------------------------------------------------------------------
# Wire models
# ---------------------------------------------------------------------------

ExplainFormat = Literal["text", "json", "yaml"]
HistoryStatus = Literal["success", "error"]


class QueryResult(BaseModel):
    """The outcome of one SQL statement."""

    sql: str = Field(description="The statement as it was actually run, LIMIT included.")
    columns: list[str] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(
        default_factory=list, description="Result rows. Empty for statements that return nothing."
    )
    row_count: int = Field(description="Rows returned, or rows affected for a write.")
    limit_applied: int | None = Field(
        default=None, description="The LIMIT this server added, if the query had none."
    )
    duration_ms: float


class ColumnInfo(BaseModel):
    name: str
    data_type: str
    nullable: bool
    default: str | None = None
    max_length: int | None = None
    position: int


class TableDescription(BaseModel):
    schema_name: str
    table_name: str
    columns: list[ColumnInfo]
    row_count: int
    size: str = Field(description="Total on-disk size, human readable.")


class TableRef(BaseModel):
    schema_name: str
    table_name: str
    owner: str = ""
    has_indexes: bool = False
    has_triggers: bool = False


class DatabaseInfo(BaseModel):
    database: str
    user: str
    version: str
    tables_per_schema: dict[str, int]


class ExplainPlan(BaseModel):
    sql: str
    analyzed: bool = Field(description="True when the query was actually run to get real timings.")
    format: ExplainFormat
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


class SchemaContext(BaseModel):
    """The tables and columns a question could be answered from."""

    question: str
    tables: dict[str, list[str]] = Field(
        description="Table name → its columns, as 'name (type)' strings."
    )
    guidance: str


# ---------------------------------------------------------------------------
# Database access
# ---------------------------------------------------------------------------


def _jsonable(value: Any) -> Any:
    """Make a psycopg2 value safe to put in a JSON result."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        # A NUMERIC wider than an IEEE-754 float would be silently rounded on
        # the way out, so it travels as a string. This is a tool for inspecting
        # what is actually in the database; a quietly corrupted number is worse
        # than one the caller has to parse.
        return str(value)
    if isinstance(value, (datetime, date, dtime)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
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


# A data-modifying statement inside a CTE, e.g.
#   WITH removed AS (DELETE FROM t RETURNING *) SELECT * FROM removed
# The leading keyword there is WITH, so the first token alone is not enough.
_CTE_WRITE = re.compile(
    r"\b(INSERT\s+INTO|UPDATE\s|DELETE\s+FROM|MERGE\s+INTO|TRUNCATE\s)", re.IGNORECASE
)


def _strip_literals(sql: str) -> str:
    """Blank out string literals and comments, so their contents cannot match."""
    without_block = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    without_line = re.sub(r"--[^\n]*", " ", without_block)
    return re.sub(r"'(?:''|[^'])*'", "''", without_line)


def is_write_query(sql: str) -> bool:
    """Whether this statement can change data.

    Conservative by design: the answer gates both read-only mode and the
    confirmation prompt, so a false negative runs an unconfirmed write while a
    false positive only asks a question that was not strictly needed.
    """
    keyword = statement_keyword(sql)
    if keyword in WRITE_KEYWORDS:
        return True
    if keyword == "WITH":
        return _CTE_WRITE.search(_strip_literals(sql)) is not None
    return False


class Database:
    """The PostgreSQL connection, with every blocking call on a worker thread."""

    def __init__(self) -> None:
        self.connection = None
        self.read_only = os.getenv("READ_ONLY", "").lower() in ("true", "1", "yes")
        self.db_identifier = (
            f"{os.getenv('DB_HOST', 'localhost')}:{os.getenv('DB_PORT', '5432')}"
            f"/{os.getenv('DB_NAME', '')}"
        )
        self.workspace_path = os.getcwd()
        if self.read_only:
            logger.info("Read-only mode enabled - write queries will be blocked")

    def _connect_blocking(self) -> None:
        self.connection = psycopg2.connect(
            host=os.getenv("DB_HOST", "localhost"),
            port=os.getenv("DB_PORT", "5432"),
            database=os.getenv("DB_NAME", "docsmapeg"),
            user=os.getenv("DB_USER", "postgres"),
            password=os.getenv("DB_PASSWORD", "postgres"),
        )
        self.connection.set_session(autocommit=True)

    async def connect(self) -> None:
        try:
            await anyio.to_thread.run_sync(self._connect_blocking)
        except Exception as exc:
            logger.error("PostgreSQL bağlantısı kurulamadı: %s", exc)
            raise ToolError(f"PostgreSQL bağlantısı kurulamadı ({self.db_identifier}): {exc}") from exc
        logger.info("PostgreSQL bağlantısı kuruldu: %s", self.db_identifier)

    def close(self) -> None:
        if self.connection:
            try:
                self.connection.close()
            except Exception as exc:
                logger.debug("Bağlantı kapatılırken hata: %s", exc)
            finally:
                self.connection = None

    async def ensure(self) -> None:
        if self.connection is None or self.connection.closed:
            await self.connect()

    def _fetch_blocking(self, sql: str, params: tuple | None) -> tuple[list[dict], list[str], int]:
        assert self.connection is not None
        with self.connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(sql, params)
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            rows = [dict(row) for row in cursor.fetchall()] if cursor.description else []
            affected = cursor.rowcount
        return rows, columns, affected

    async def _run_cancellable(
        self, sql: str, params: tuple | None
    ) -> tuple[list[dict], list[str], int]:
        """Run the statement so that cancelling the call also cancels the query.

        `anyio.to_thread.run_sync` cannot interrupt the thread it started: on
        cancellation it simply stops waiting, leaving the statement running and
        holding its locks. Asking the server to cancel is what actually stops
        the work, and it is safe to call from another thread.
        """
        try:
            return await anyio.to_thread.run_sync(self._fetch_blocking, sql, params)
        except anyio.get_cancelled_exc_class():
            connection = self.connection
            if connection is not None:
                with anyio.CancelScope(shield=True):
                    await anyio.to_thread.run_sync(connection.cancel)
            raise

    async def fetch(self, sql: str, params: tuple | None = None) -> tuple[list[dict], list[str], int]:
        """Run a statement and return (rows, columns, rowcount)."""
        await self.ensure()
        try:
            return await self._run_cancellable(sql, params)
        except psycopg2.Error as exc:
            raise ToolError(f"SQL hatası: {str(exc).strip()}") from exc

    async def scalar(self, sql: str, params: tuple | None = None) -> Any:
        rows, _, _ = await self.fetch(sql, params)
        if not rows:
            return None
        return next(iter(rows[0].values()))

    def log_query(self, tool_name: str, **fields) -> None:
        direct_log_query_execution(
            server_type="postgresql",
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


mcp = MCPServer("postgresql-mcp-server", version=__version__, lifespan=app_lifespan)

_READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=False)


def _db(ctx: Context[AppContext]) -> Database:
    return ctx.request_context.lifespan_context.db


def _split_table(table_name: str) -> tuple[str, str]:
    if "." in table_name:
        schema, table = table_name.split(".", 1)
        return schema, table
    return "public", table_name


# -- execute_sql -------------------------------------------------------------


class WriteConfirmation(BaseModel):
    """The user's answer to a write-query question."""

    confirm: bool = Field(description="Run this statement against the database?")


async def confirm_write(ctx: Context[AppContext], sql: str = "") -> WriteConfirmation | Elicit[WriteConfirmation]:
    """Ask before running anything that changes the database."""
    db = _db(ctx)
    if db.read_only or not is_write_query(sql):
        return WriteConfirmation(confirm=True)  # refused below, or harmless

    keyword = statement_keyword(sql)
    warning = (
        " Bu işlem geri alınamaz." if keyword in IRREVERSIBLE_KEYWORDS else ""
    )
    return Elicit(
        f"Bu {keyword} ifadesi '{db.db_identifier}' veritabanını değiştirecek.{warning}\n\n"
        f"    {sql.strip()}\n\nÇalıştırılsın mı?",
        WriteConfirmation,
    )


@mcp.tool(
    title="SQL çalıştır",
    description="Execute a SQL statement. SELECTs get a LIMIT if they have none; writes are "
    "confirmed with the user first, and refused outright in read-only mode.",
    annotations=ToolAnnotations(
        read_only_hint=False, destructive_hint=True, idempotent_hint=False, open_world_hint=False
    ),
)
async def execute_sql(
    sql: Annotated[str, Field(min_length=1, description="SQL statement to execute.")],
    ctx: Context[AppContext],
    confirmation: Annotated[WriteConfirmation, Resolve(confirm_write)],
    limit: Annotated[
        int,
        Field(ge=1, le=10000, description="Row limit added to a SELECT that has no LIMIT."),
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

    return await _run_sql(db, sql, limit, tool_name="execute_sql")


async def _run_sql(
    db: Database, sql: str, limit: int, *, tool_name: str, user_query: str = ""
) -> QueryResult:
    """Run one statement, apply the row limit, and record it in the query log."""
    effective_sql = sql.strip()
    limit_applied: int | None = None
    if statement_keyword(effective_sql) == "SELECT" and "LIMIT" not in effective_sql.upper():
        effective_sql = f"{effective_sql} LIMIT {limit}"
        limit_applied = limit

    started = time.time()
    try:
        rows, columns, affected = await db.fetch(effective_sql)
    except ToolError as exc:
        db.log_query(
            tool_name,
            query_text=effective_sql,
            execution_time_ms=(time.time() - started) * 1000,
            status="error",
            row_count=0,
            error_message=str(exc),
            user_query=user_query,
        )
        raise

    duration = (time.time() - started) * 1000
    result = QueryResult(
        sql=effective_sql,
        columns=columns,
        rows=[{k: _jsonable(v) for k, v in row.items()} for row in rows],
        row_count=len(rows) if columns else max(affected, 0),
        limit_applied=limit_applied,
        duration_ms=duration,
    )

    db.log_query(
        tool_name,
        query_text=effective_sql,
        execution_time_ms=duration,
        status="success",
        row_count=result.row_count,
        error_message="",
        user_query=user_query,
    )
    return result


# -- natural_language_query --------------------------------------------------

# The phrases this server can answer without a model writing SQL. Anything else
# is better served by execute_sql.
_NL_PATTERNS: list[tuple[tuple[str, ...], str, str]] = [
    (
        ("tablo", "table", "liste", "list", "göster", "show"),
        "tabloları listele",
        """SELECT schemaname, tablename, tableowner
           FROM pg_tables
           WHERE schemaname NOT IN ('information_schema', 'pg_catalog')
           ORDER BY schemaname, tablename""",
    ),
    (
        ("kullanıcı", "user", "kullanıcılar", "users"),
        "kullanıcıları listele",
        """SELECT usename AS username, usesuper AS is_superuser, usecreatedb AS can_create_db
           FROM pg_user ORDER BY usename""",
    ),
    (
        ("şema", "schema", "schemas"),
        "şemaları listele",
        """SELECT schema_name, schema_owner
           FROM information_schema.schemata
           WHERE schema_name NOT IN ('information_schema', 'pg_catalog', 'pg_toast')
           ORDER BY schema_name""",
    ),
    (
        ("istatistik", "statistics", "stats", "bilgi", "info"),
        "veritabanı bilgisi",
        """SELECT current_database() AS database, current_user AS "user",
                  version() AS postgresql_version""",
    ),
]


@mcp.tool(
    title="Doğal dil sorgusu",
    description="Answer a handful of fixed questions about the database (tables, users, "
    "schemas, database info) without writing SQL. Anything else: use execute_sql.",
    annotations=_READ_ONLY,
)
async def natural_language_query(
    query: Annotated[str, Field(min_length=1, description="Question in Turkish or English.")],
    ctx: Context[AppContext],
) -> QueryResult:
    db = _db(ctx)
    lowered = query.lower()

    for keywords, _, sql in _NL_PATTERNS:
        if any(word in lowered for word in keywords):
            return await _run_sql(
                db, " ".join(sql.split()), 50, tool_name="natural_language_query", user_query=query
            )

    db.log_query(
        "natural_language_query",
        query_text="NO_PATTERN_MATCH",
        execution_time_ms=0,
        status="error",
        row_count=0,
        error_message="no pattern matched",
        user_query=query,
    )
    understood = ", ".join(label for _, label, _ in _NL_PATTERNS)
    raise ToolError(
        f"Bu soruyu eşleştiremedim. Bu araç yalnızca şunları biliyor: {understood}. "
        "Başka her şey için SQL'i kendin yaz ve execute_sql ile çalıştır."
    )


# -- describe_table ----------------------------------------------------------


@mcp.tool(
    title="Tabloyu tanımla",
    description="Get a table's columns, row count and on-disk size.",
    annotations=_READ_ONLY,
)
async def describe_table(
    table_name: Annotated[
        str, Field(min_length=1, description="Table as 'schema.table', or just the table name.")
    ],
    ctx: Context[AppContext],
) -> TableDescription:
    db = _db(ctx)
    schema, table = _split_table(table_name)

    await ctx.report_progress(0, 3, "kolonlar")
    columns = await _fetch_columns(db, schema, table)
    if not columns:
        raise ToolError(f"'{schema}.{table}' diye bir tablo yok.")

    await ctx.report_progress(1, 3, "satır sayısı")
    row_count = await db.scalar(f'SELECT COUNT(*) FROM "{schema}"."{table}"')

    await ctx.report_progress(2, 3, "boyut")
    size = await db.scalar(
        "SELECT pg_size_pretty(pg_total_relation_size(%s))", (f'"{schema}"."{table}"',)
    )

    await ctx.report_progress(3, 3, "tamamlandı")
    return TableDescription(
        schema_name=schema,
        table_name=table,
        columns=columns,
        row_count=int(row_count or 0),
        size=str(size or "?"),
    )


async def _fetch_columns(db: Database, schema: str, table: str) -> list[ColumnInfo]:
    rows, _, _ = await db.fetch(
        """SELECT column_name, data_type, character_maximum_length, is_nullable,
                  column_default, ordinal_position
           FROM information_schema.columns
           WHERE table_schema = %s AND table_name = %s
           ORDER BY ordinal_position""",
        (schema, table),
    )
    return [
        ColumnInfo(
            name=row["column_name"],
            data_type=row["data_type"],
            nullable=row["is_nullable"] == "YES",
            default=row["column_default"],
            max_length=row["character_maximum_length"],
            position=row["ordinal_position"],
        )
        for row in rows
    ]


# -- smart_query -------------------------------------------------------------


@mcp.tool(
    title="Şema bağlamı getir",
    description="Return the public schema's tables and columns as context for answering a "
    "question. It does not write or run SQL — read the context, then use execute_sql.",
    annotations=_READ_ONLY,
)
async def smart_query(
    question: Annotated[str, Field(min_length=1, description="Your question about the data.")],
    ctx: Context[AppContext],
) -> SchemaContext:
    db = _db(ctx)
    rows, _, _ = await db.fetch(
        """SELECT table_name, column_name, data_type
           FROM information_schema.columns
           WHERE table_schema = 'public'
           ORDER BY table_name, ordinal_position
           LIMIT 500"""
    )

    tables: dict[str, list[str]] = {}
    for row in rows:
        tables.setdefault(row["table_name"], []).append(
            f"{row['column_name']} ({row['data_type']})"
        )

    return SchemaContext(
        question=question,
        tables=tables,
        guidance=(
            "Bu şemayı kullanarak soruyu cevaplayan SQL'i yaz ve execute_sql ile çalıştır. "
            "Bir tablonun satır sayısı, boyutu ve varsayılan değerleri için describe_table kullan."
        ),
    )


# -- explain_query -----------------------------------------------------------


@mcp.tool(
    title="Sorgu planını göster",
    description="Show a query's execution plan with EXPLAIN. With analyze=true the query is "
    "actually run, so do not analyze a statement that writes.",
    annotations=ToolAnnotations(
        read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=False
    ),
)
async def explain_query(
    sql: Annotated[str, Field(min_length=1, description="SQL query to explain.")],
    ctx: Context[AppContext],
    analyze: Annotated[
        bool,
        Field(
            description="Run the query to get real timings. False gives the planner's estimate "
            "without touching any data."
        ),
    ] = False,
    format: Annotated[ExplainFormat, Field(description="Plan output format.")] = "text",
    buffers: Annotated[
        bool, Field(description="Include buffer usage. Only meaningful with analyze=true.")
    ] = False,
) -> ExplainPlan:
    db = _db(ctx)

    if analyze and is_write_query(sql):
        raise ToolError(
            "EXPLAIN ANALYZE sorguyu gerçekten çalıştırır; yazan bir ifadeyle kullanılamaz. "
            "analyze=false ile plan tahminini alabilirsin."
        )

    options = []
    if analyze:
        options.append("ANALYZE true")
    if buffers and analyze:
        options.append("BUFFERS true")
    if format != "text":
        options.append(f"FORMAT {format}")

    prefix = f"EXPLAIN ({', '.join(options)})" if options else "EXPLAIN"
    rows, _, _ = await db.fetch(f"{prefix} {sql}")

    plan = "\n".join(str(next(iter(row.values()))) for row in rows)
    return ExplainPlan(sql=sql, analyzed=analyze, format=format, plan=plan)


# -- get_query_history -------------------------------------------------------


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


def _require_app() -> AppContext:
    if _app is None:
        raise ResourceError("Sunucu henüz hazır değil.")
    return _app


@mcp.resource(
    "postgresql://tables",
    name="Database Tables",
    description="Veritabanındaki tüm tablolar, sahibi ve indeks/tetikleyici durumu.",
    mime_type="application/json",
)
async def tables_resource() -> str:
    db = _require_app().db
    rows, _, _ = await db.fetch(
        """SELECT schemaname, tablename, tableowner, hasindexes, hastriggers
           FROM pg_tables
           WHERE schemaname NOT IN ('information_schema', 'pg_catalog')
           ORDER BY schemaname, tablename"""
    )
    refs = [
        TableRef(
            schema_name=row["schemaname"],
            table_name=row["tablename"],
            owner=row["tableowner"],
            has_indexes=row["hasindexes"],
            has_triggers=row["hastriggers"],
        )
        for row in rows
    ]
    return _dump_list(refs)


@mcp.resource(
    "postgresql://schema",
    name="Database Schema",
    description="Tüm şemaların tablo ve kolon yapısı.",
    mime_type="application/json",
)
async def schema_resource() -> str:
    db = _require_app().db
    rows, _, _ = await db.fetch(
        """SELECT t.table_schema, t.table_name, c.column_name, c.data_type,
                  c.is_nullable, c.column_default, c.ordinal_position
           FROM information_schema.tables t
           JOIN information_schema.columns c
             ON t.table_name = c.table_name AND t.table_schema = c.table_schema
           WHERE t.table_schema NOT IN ('information_schema', 'pg_catalog')
           ORDER BY t.table_schema, t.table_name, c.ordinal_position
           LIMIT 500"""
    )
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        key = f"{row['table_schema']}.{row['table_name']}"
        grouped.setdefault(key, []).append(
            {
                "name": row["column_name"],
                "data_type": row["data_type"],
                "nullable": row["is_nullable"] == "YES",
                "default": row["column_default"],
                "position": row["ordinal_position"],
            }
        )
    return json.dumps(grouped, ensure_ascii=False, indent=2)


@mcp.resource(
    "postgresql://stats",
    name="Database Statistics",
    description="Veritabanı adı, kullanıcı, sürüm ve şema başına tablo sayısı.",
    mime_type="application/json",
)
async def stats_resource() -> str:
    db = _require_app().db
    info_rows, _, _ = await db.fetch(
        """SELECT current_database() AS database, current_user AS "user",
                  version() AS version"""
    )
    count_rows, _, _ = await db.fetch(
        """SELECT schemaname, COUNT(*) AS table_count
           FROM pg_tables
           WHERE schemaname NOT IN ('information_schema', 'pg_catalog')
           GROUP BY schemaname ORDER BY table_count DESC"""
    )
    info = info_rows[0] if info_rows else {"database": "", "user": "", "version": ""}
    return DatabaseInfo(
        database=info["database"],
        user=info["user"],
        version=info["version"],
        tables_per_schema={row["schemaname"]: row["table_count"] for row in count_rows},
    ).model_dump_json(indent=2)


@mcp.resource(
    "postgresql://table/{schema}/{table}",
    name="Tablo yapısı",
    description="Bir tablonun kolonları, satır sayısı ve disk boyutu.",
    mime_type="application/json",
)
async def table_resource(schema: str, table: str) -> str:
    db = _require_app().db
    columns = await _fetch_columns(db, schema, table)
    if not columns:
        raise ResourceError(f"'{schema}.{table}' diye bir tablo yok.")
    row_count = await db.scalar(f'SELECT COUNT(*) FROM "{schema}"."{table}"')
    size = await db.scalar(
        "SELECT pg_size_pretty(pg_total_relation_size(%s))", (f'"{schema}"."{table}"',)
    )
    return TableDescription(
        schema_name=schema,
        table_name=table,
        columns=columns,
        row_count=int(row_count or 0),
        size=str(size or "?"),
    ).model_dump_json(indent=2)


def _dump_list(models: list[BaseModel]) -> str:
    return json.dumps([m.model_dump() for m in models], ensure_ascii=False, indent=2)


@mcp.prompt(title="Tabloyu analiz et")
def analyze_table(table_name: str) -> str:
    """Look a table over: shape, data quality, and what it is for."""
    return (
        f"'{table_name}' tablosunu analiz et:\n\n"
        f"1. `describe_table('{table_name}')` ile kolonları, satır sayısını ve boyutunu al.\n"
        "2. Birkaç örnek satır çek (`SELECT * ... LIMIT 10`) ve verinin neye benzediğine bak.\n"
        "3. Veri kalitesini yokla: null oranı yüksek kolonlar, hep aynı değeri taşıyan kolonlar, "
        "beklenmedik tipler, kullanılmayan alanlar.\n"
        "4. Tablonun ne işe yaradığını ve hangi tablolarla ilişkili göründüğünü yaz.\n"
        "5. Gördüğün sorunları ve iyileştirme önerilerini (indeks, tip, kısıt) sırala."
    )


@mcp.prompt(title="Sorguyu optimize et")
def optimize_query(sql: str) -> str:
    """Find out why a query is slow and what to do about it."""
    return (
        "Aşağıdaki sorguyu optimize et:\n\n"
        f"```sql\n{sql}\n```\n\n"
        "1. `explain_query` ile planı al (yazma yoksa analyze=true ile gerçek süreleri de al).\n"
        "2. Planda en pahalı adımı bul: seq scan, nested loop, sort, hash join.\n"
        "3. İlgili tabloları `describe_table` ile incele; mevcut indeksleri kontrol et.\n"
        "4. Somut öneri ver: hangi kolona hangi indeks, hangi join sırası, hangi yeniden yazım.\n"
        "5. Önerdiğin haliyle planı tekrar al ve farkı göster."
    )


if __name__ == "__main__":
    mcp.run()
