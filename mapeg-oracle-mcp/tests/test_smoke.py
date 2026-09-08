"""Drive the Oracle server against a real database.

Skipped unless ORACLE_CONNECTION_STRING points at a schema the test may create
and drop objects in. To run it locally:

    docker run -d --name mcp-ora-test -e ORACLE_PASSWORD=testpw \\
        -p 51521:1521 gvenzl/oracle-free:23-slim
    # then create a demo user and:
    ORACLE_CONNECTION_STRING='User Id=demo;Password=demopw;Data Source=127.0.0.1:51521/FREEPDB1' \\
        pytest
"""

import json
import os
import sys
from pathlib import Path

import anyio
import pytest
from mcp import Client
from mcp.types import ElicitResult

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

pytest.importorskip("oracledb")
import oracledb  # noqa: E402

SETUP = [
    """CREATE TABLE mcp_test_musteriler (
           id NUMBER PRIMARY KEY,
           ad VARCHAR2(100) NOT NULL,
           bakiye NUMBER(10, 2) DEFAULT 0,
           kayit_tarihi DATE DEFAULT SYSDATE
       )""",
    """CREATE TABLE mcp_test_siparisler (
           id NUMBER PRIMARY KEY,
           musteri_id NUMBER NOT NULL,
           tutar NUMBER(10, 2),
           CONSTRAINT mcp_test_fk_siparis
               FOREIGN KEY (musteri_id) REFERENCES mcp_test_musteriler(id)
       )""",
    "CREATE INDEX mcp_test_idx_ad ON mcp_test_musteriler(ad)",
    "INSERT INTO mcp_test_musteriler (id, ad, bakiye) VALUES (1, 'Ali', 1200.50)",
    "INSERT INTO mcp_test_musteriler (id, ad, bakiye) VALUES (2, 'Ayse', 0)",
    "INSERT INTO mcp_test_siparisler (id, musteri_id, tutar) VALUES (1, 1, 350.75)",
    """CREATE OR REPLACE FUNCTION mcp_test_toplam RETURN NUMBER IS
           v NUMBER;
       BEGIN
           SELECT SUM(bakiye) INTO v FROM mcp_test_musteriler;
           RETURN v;
       END;""",
]

TEARDOWN = [
    "DROP FUNCTION mcp_test_toplam",
    "DROP TABLE mcp_test_siparisler",
    "DROP TABLE mcp_test_musteriler",
]


def _connect() -> oracledb.Connection:
    raw = os.environ["ORACLE_CONNECTION_STRING"]
    fields = {}
    for part in raw.split(";"):
        if "=" in part:
            key, value = part.split("=", 1)
            fields[key.strip().lower()] = value
    return oracledb.connect(
        user=fields["user id"], password=fields["password"], dsn=fields["data source"]
    )


@pytest.fixture(scope="module")
def database():
    if not os.environ.get("ORACLE_CONNECTION_STRING"):
        pytest.skip("ORACLE_CONNECTION_STRING ayarlı değil")
    try:
        connection = _connect()
    except oracledb.Error as exc:
        pytest.skip(f"Oracle'a bağlanılamadı: {exc}")

    connection.autocommit = True
    with connection.cursor() as cursor:
        for statement in TEARDOWN:  # leftovers from an interrupted run
            try:
                cursor.execute(statement)
            except oracledb.DatabaseError:
                pass
        for statement in SETUP:
            cursor.execute(statement)
    try:
        yield connection
    finally:
        with connection.cursor() as cursor:
            for statement in TEARDOWN:
                try:
                    cursor.execute(statement)
                except oracledb.DatabaseError:
                    pass
        connection.close()


@pytest.fixture()
def mcp_server(database):
    for module in [m for m in sys.modules if m.startswith("mcp_server_oracle")]:
        del sys.modules[module]
    from mcp_server_oracle.server import mcp

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
                {
                    "sql": "SELECT id, ad, bakiye, kayit_tarihi "
                    "FROM mcp_test_musteriler ORDER BY id"
                },
            )
            content = result.structured_content
            assert content["columns"] == ["ID", "AD", "BAKIYE", "KAYIT_TARIHI"]
            assert content["row_count"] == 2
            assert content["limit_applied"] == 100

            first = content["rows"][0]
            assert first["AD"] == "Ali"
            assert first["BAKIYE"] == 1200.5
            assert first["KAYIT_TARIHI"].startswith("20")  # DATE became ISO-8601

    anyio.run(run)


def test_plsql_block_returns_dbms_output(mcp_server):
    async def run():
        async with _client(mcp_server) as client:
            result = await client.call_tool(
                "execute_sql",
                {
                    "sql": "BEGIN DBMS_OUTPUT.PUT_LINE('merhaba plsql'); "
                    "DBMS_OUTPUT.PUT_LINE('ikinci'); END;"
                },
            )
            assert result.structured_content["dbms_output"] == "merhaba plsql\nikinci"

    anyio.run(run)


def test_write_is_confirmed_and_a_refusal_changes_nothing(mcp_server, database):
    asked: list[str] = []

    async def run():
        async with _client(mcp_server, confirm=False, asked=asked) as client:
            result = await client.call_tool(
                "execute_sql", {"sql": "DELETE FROM mcp_test_musteriler WHERE id = 2"}
            )
            assert result.is_error is True
            assert asked and "geri alınamaz" in asked[0]

    anyio.run(run)

    with database.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM mcp_test_musteriler")
        assert cursor.fetchone()[0] == 2


def test_identifier_injection_is_refused(mcp_server):
    async def run():
        async with _client(mcp_server) as client:
            result = await client.call_tool(
                "describe_table", {"table_name": "mcp_test_musteriler; DROP TABLE x"}
            )
            assert result.is_error is True
            assert "geçersiz" in result.content[0].text

    anyio.run(run)


def test_schema_exploration(mcp_server):
    async def run():
        async with _client(mcp_server) as client:
            described = await client.call_tool(
                "describe_table", {"table_name": "mcp_test_musteriler"}
            )
            assert described.structured_content["row_count"] == 2

            indexes = await client.call_tool(
                "get_table_indexes", {"table_name": "mcp_test_musteriler"}
            )
            names = {i["index_name"] for i in indexes.structured_content["result"]}
            assert "MCP_TEST_IDX_AD" in names

            constraints = await client.call_tool(
                "get_table_constraints", {"table_name": "mcp_test_siparisler"}
            )
            labels = {c["type_label"] for c in constraints.structured_content["result"]}
            assert {"Primary Key", "Foreign Key"} <= labels

            relationships = await client.call_tool(
                "get_table_relationships", {"table_name": "mcp_test_musteriler"}
            )
            incoming = relationships.structured_content["incoming"]
            assert [r["from_table"] for r in incoming] == ["MCP_TEST_SIPARISLER"]

    anyio.run(run)


def test_plsql_source_is_readable(mcp_server):
    async def run():
        async with _client(mcp_server) as client:
            source = await client.call_tool(
                "get_source_code", {"object_name": "mcp_test_toplam"}
            )
            assert source.structured_content["object_type"] == "FUNCTION"
            assert "RETURN NUMBER" in source.structured_content["source"]

            body = (
                await client.read_resource("oracle://source/FUNCTION/MCP_TEST_TOPLAM")
            ).contents[0].text
            assert "SUM(bakiye)" in body

    anyio.run(run)


def test_explain_plan(mcp_server):
    async def run():
        async with _client(mcp_server) as client:
            result = await client.call_tool(
                "explain_plan", {"sql": "SELECT * FROM mcp_test_musteriler WHERE id = 1"}
            )
            assert "Plan hash value" in result.structured_content["plan"]

    anyio.run(run)


def test_resources_and_prompts(mcp_server):
    async def run():
        async with _client(mcp_server) as client:
            uris = [str(r.uri) for r in (await client.list_resources()).resources]
            assert uris == ["oracle://tables", "oracle://schema", "oracle://stats"]

            table = json.loads(
                (
                    await client.read_resource("oracle://table/MCP_TEST_MUSTERILER")
                ).contents[0].text
            )
            assert table["row_count"] == 2

            stats = json.loads((await client.read_resource("oracle://stats")).contents[0].text)
            assert stats["version"].startswith("Oracle")

            assert {p.name for p in (await client.list_prompts()).prompts} == {
                "review_plsql",
                "analyze_table",
            }

    anyio.run(run)
