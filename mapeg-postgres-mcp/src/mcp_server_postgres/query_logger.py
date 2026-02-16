"""
Query Logger - Logs MCP query executions to a shared SQLite database.
Well-known path: ~/.local/share/mapeg-mcp/query_logs.db
"""

import os
import sqlite3
from datetime import datetime
from pathlib import Path


def _get_db_path() -> Path:
    db_dir = Path.home() / ".local" / "share" / "mapeg-mcp"
    db_dir.mkdir(parents=True, exist_ok=True)
    return db_dir / "query_logs.db"


def _ensure_table(conn: sqlite3.Connection):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS query_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            server_type TEXT NOT NULL,
            tool_name TEXT NOT NULL,
            query_text TEXT NOT NULL,
            execution_time_ms REAL NOT NULL,
            status TEXT NOT NULL,
            row_count INTEGER DEFAULT 0,
            error_message TEXT DEFAULT '',
            user_query TEXT DEFAULT '',
            response_text TEXT DEFAULT '',
            db_identifier TEXT DEFAULT '',
            workspace_path TEXT DEFAULT ''
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_timestamp
        ON query_logs(timestamp DESC)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_server_type
        ON query_logs(server_type)
    """)
    # Migrate: add columns if missing (existing DB)
    cursor = conn.execute("PRAGMA table_info(query_logs)")
    columns = {row[1] for row in cursor.fetchall()}
    if "db_identifier" not in columns:
        conn.execute("ALTER TABLE query_logs ADD COLUMN db_identifier TEXT DEFAULT ''")
    if "workspace_path" not in columns:
        conn.execute("ALTER TABLE query_logs ADD COLUMN workspace_path TEXT DEFAULT ''")
    conn.commit()


def direct_log_query_execution(
    server_type: str,
    tool_name: str,
    query_text: str,
    execution_time_ms: float,
    status: str,
    row_count: int = 0,
    error_message: str = "",
    user_query: str = "",
    response_text: str = "",
    db_identifier: str = "",
    workspace_path: str = "",
) -> int:
    """Log a query execution synchronously to the shared SQLite database."""
    try:
        db_path = _get_db_path()
        conn = sqlite3.connect(str(db_path))
        _ensure_table(conn)

        timestamp = datetime.now().isoformat()
        cursor = conn.execute(
            """
            INSERT INTO query_logs (
                timestamp, server_type, tool_name, query_text,
                execution_time_ms, status, row_count, error_message,
                user_query, response_text, db_identifier, workspace_path
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                timestamp, server_type, tool_name, query_text,
                execution_time_ms, status, row_count, error_message,
                user_query, response_text, db_identifier, workspace_path,
            ),
        )
        log_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return log_id
    except Exception:
        return 0
