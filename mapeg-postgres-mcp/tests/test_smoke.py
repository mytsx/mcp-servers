"""Drive the PostgreSQL server against a real database.

Skipped unless MCP_TEST_PG_DSN-style environment variables point at a database
the test may create and drop a table in. To run it locally:

    docker run -d --name mcp-pg-test -e POSTGRES_PASSWORD=testpw \\
        -e POSTGRES_DB=testdb -p 55432:5432 postgres:16-alpine
    DB_HOST=127.0.0.1 DB_PORT=55432 DB_NAME=testdb DB_USER=postgres \\
        DB_PASSWORD=testpw pytest
"""

import json
import os
import sys
import time
from pathlib import Path

import anyio
import pytest
from mcp import Client
from mcp.types import ElicitResult

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

pytest.importorskip("psycopg2")
import psycopg2  # noqa: E402

REQUIRED_ENV = ("DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD")

SEED = """
DROP TABLE IF EXISTS mcp_test_musteriler;
CREATE TABLE mcp_test_musteriler (
    id serial PRIMARY KEY,
    ad text NOT NULL,
    bakiye numeric(10, 2) DEFAULT 0,
    kayit_tarihi timestamptz DEFAULT now()
);
INSERT INTO mcp_test_musteriler (ad, bakiye)
VALUES ('Ali', 1200.50), ('Ayse', 0), ('Mehmet', 87.25);
"""


def _dsn() -> dict[str, str]:
    return {
        "host": os.environ["DB_HOST"],
        "port": os.environ["DB_PORT"],
        "dbname": os.environ["DB_NAME"],
        "user": os.environ["DB_USER"],
        "password": os.environ["DB_PASSWORD"],
    }


@pytest.fixture(scope="module")
def database():
    missing = [name for name in REQUIRED_ENV if not os.environ.get(name)]
    if missing:
        pytest.skip(f"PostgreSQL bağlantı değişkenleri eksik: {', '.join(missing)}")
    try:
        connection = psycopg2.connect(**_dsn())
    except psycopg2.Error as exc:
        pytest.skip(f"PostgreSQL'e bağlanılamadı: {exc}")

    connection.autocommit = True
    with connection.cursor() as cursor:
        cursor.execute(SEED)
    try:
        yield connection
    finally:
        with connection.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS mcp_test_musteriler")
        connection.close()


@pytest.fixture()
def mcp_server(database):
    for module in [m for m in sys.modules if m.startswith("mcp_server_postgres")]:
        del sys.modules[module]
    from mcp_server_postgres.server import mcp

    return mcp


def _client(mcp_server, confirm=True, asked=None):
    async def elicit(context, params):
        if asked is not None:
            asked.append(params.message)
        return ElicitResult(action="accept", content={"confirm": confirm})

    return Client(mcp_server, elicitation_callback=elicit)


def test_select_returns_typed_rows(mcp_server):
    async def run():
        async with _client(mcp_server) as client:
            result = await client.call_tool(
                "execute_sql",
                {"sql": "SELECT id, ad, bakiye, kayit_tarihi FROM mcp_test_musteriler ORDER BY id"},
            )
            content = result.structured_content
            assert content["columns"] == ["id", "ad", "bakiye", "kayit_tarihi"]
            assert content["row_count"] == 3
            assert content["limit_applied"] == 100  # the SELECT had no LIMIT of its own

            first = content["rows"][0]
            assert first["ad"] == "Ali"
            # NUMERIC travels as a string so nothing is rounded on the way out,
            # and timestamptz as ISO-8601, so the row survives JSON intact.
            assert first["bakiye"] == "1200.50"
            assert first["kayit_tarihi"].startswith("20")

    anyio.run(run)


def test_write_is_confirmed_and_a_refusal_changes_nothing(mcp_server, database):
    asked: list[str] = []

    async def run():
        async with _client(mcp_server, confirm=False, asked=asked) as client:
            result = await client.call_tool(
                "execute_sql", {"sql": "DELETE FROM mcp_test_musteriler WHERE id = 3"}
            )
            assert result.is_error is True
            assert asked and "geri alınamaz" in asked[0]  # DELETE is flagged irreversible

    anyio.run(run)

    with database.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM mcp_test_musteriler")
        assert cursor.fetchone()[0] == 3


def test_confirmed_write_applies(mcp_server, database):
    async def run():
        async with _client(mcp_server, confirm=True) as client:
            result = await client.call_tool(
                "execute_sql",
                {"sql": "UPDATE mcp_test_musteriler SET bakiye = 1 WHERE id = 2"},
            )
            assert result.structured_content["row_count"] == 1

    anyio.run(run)

    with database.cursor() as cursor:
        cursor.execute("SELECT bakiye FROM mcp_test_musteriler WHERE id = 2")
        assert float(cursor.fetchone()[0]) == 1.0


def test_wide_numerics_are_not_rounded(mcp_server):
    """A NUMERIC wider than a float must arrive unchanged, not silently rounded."""
    wide = "12345678901234567890.12"

    async def run():
        async with _client(mcp_server) as client:
            result = await client.call_tool(
                "execute_sql", {"sql": f"SELECT {wide}::numeric AS büyük"}
            )
            assert result.structured_content["rows"][0]["büyük"] == wide

    anyio.run(run)


@pytest.mark.parametrize(
    ("sql", "is_write"),
    [
        ("SELECT 1", False),
        ("WITH x AS (SELECT 1) SELECT * FROM x", False),
        ("SELECT 'delete from t' AS s", False),
        ("DELETE FROM t", True),
        # A data-modifying CTE: the leading keyword is WITH, but this deletes.
        ("WITH removed AS (DELETE FROM t RETURNING *) SELECT * FROM removed", True),
        ("WITH n AS (INSERT INTO t VALUES (1) RETURNING *) SELECT * FROM n", True),
    ],
)
def test_write_detection(mcp_server, sql, is_write):
    import mcp_server_postgres.server as module

    assert module.is_write_query(sql) is is_write


def test_a_write_hidden_in_a_cte_is_confirmed(mcp_server, database):
    """The user must be asked before a DELETE that hides inside a WITH."""
    asked: list[str] = []

    async def run():
        async with _client(mcp_server, confirm=False, asked=asked) as client:
            result = await client.call_tool(
                "execute_sql",
                {
                    "sql": "WITH removed AS (DELETE FROM mcp_test_musteriler "
                    "WHERE id = 3 RETURNING *) SELECT * FROM removed"
                },
            )
            assert result.is_error is True
            assert asked, "a CTE that deletes must be confirmed"

    anyio.run(run)

    with database.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM mcp_test_musteriler")
        assert cursor.fetchone()[0] == 3


def test_sql_errors_are_tool_errors(mcp_server):
    async def run():
        async with _client(mcp_server) as client:
            result = await client.call_tool("execute_sql", {"sql": "SELECT * FROM yok_boyle"})
            assert result.is_error is True
            assert "SQL hatası" in result.content[0].text

    anyio.run(run)


def test_describe_table(mcp_server):
    async def run():
        async with _client(mcp_server) as client:
            result = await client.call_tool(
                "describe_table", {"table_name": "mcp_test_musteriler"}
            )
            content = result.structured_content
            assert content["schema_name"] == "public"
            assert content["row_count"] == 3
            assert [c["name"] for c in content["columns"]] == [
                "id",
                "ad",
                "bakiye",
                "kayit_tarihi",
            ]

            missing = await client.call_tool("describe_table", {"table_name": "yok_boyle"})
            assert missing.is_error is True

    anyio.run(run)


def test_explain_refuses_to_analyze_a_write(mcp_server):
    async def run():
        async with _client(mcp_server) as client:
            plan = await client.call_tool(
                "explain_query", {"sql": "SELECT * FROM mcp_test_musteriler WHERE id = 1"}
            )
            assert "Scan" in plan.structured_content["plan"]

            # ANALYZE runs the statement, so it must not be allowed on a write.
            refused = await client.call_tool(
                "explain_query",
                {"sql": "DELETE FROM mcp_test_musteriler", "analyze": True},
            )
            assert refused.is_error is True
            assert "EXPLAIN ANALYZE" in refused.content[0].text

    anyio.run(run)


def test_natural_language_query_says_what_it_cannot_do(mcp_server):
    async def run():
        async with _client(mcp_server) as client:
            known = await client.call_tool(
                "natural_language_query", {"query": "tabloları listele"}
            )
            assert known.structured_content["row_count"] >= 1

            unknown = await client.call_tool(
                "natural_language_query", {"query": "kaç müşteri kayıp gitti"}
            )
            assert unknown.is_error is True
            assert "yalnızca şunları biliyor" in unknown.content[0].text

    anyio.run(run)


def test_resources_and_prompts(mcp_server):
    async def run():
        async with _client(mcp_server) as client:
            uris = [str(r.uri) for r in (await client.list_resources()).resources]
            assert uris == ["postgresql://tables", "postgresql://schema", "postgresql://stats"]

            table = json.loads(
                (
                    await client.read_resource("postgresql://table/public/mcp_test_musteriler")
                ).contents[0].text
            )
            assert table["row_count"] == 3

            stats = json.loads((await client.read_resource("postgresql://stats")).contents[0].text)
            assert stats["database"] == os.environ["DB_NAME"]

            assert {p.name for p in (await client.list_prompts()).prompts} == {
                "analyze_table",
                "optimize_query",
            }

    anyio.run(run)


def test_cancelling_a_call_cancels_the_query(mcp_server, database):
    """A cancelled call must stop the statement, not just stop waiting for it.

    A worker thread cannot be interrupted, so without asking the server to
    cancel, `pg_sleep` would keep running and holding its resources long after
    the caller gave up.
    """

    async def run():
        async with _client(mcp_server) as client:
            with anyio.move_on_after(2):
                await client.call_tool(
                    "execute_sql", {"sql": "SELECT pg_sleep(30)"}, read_timeout_seconds=None
                )

    started = time.monotonic()
    anyio.run(run)
    # The call gave up quickly rather than waiting out the sleep.
    assert time.monotonic() - started < 20

    # And the backend is no longer running it.
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        with database.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) FROM pg_stat_activity "
                "WHERE query LIKE 'SELECT pg_sleep(30)%' AND state = 'active'"
            )
            if cursor.fetchone()[0] == 0:
                return
        time.sleep(0.25)

    raise AssertionError("pg_sleep hâlâ çalışıyor: iptal veritabanına ulaşmadı")
