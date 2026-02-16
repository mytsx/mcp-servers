#!/usr/bin/env python3
"""
Query Dashboard - Flask Web Interface for MCP Server Query Logs
Reads query logs directly from the shared SQLite database at
~/.local/share/mapeg-mcp/query_logs.db
"""

from flask import Flask, render_template, jsonify, request
import os
import sqlite3
from pathlib import Path

app = Flask(__name__)
app.config['SECRET_KEY'] = 'mcp-dashboard-secret-key'


def _get_db_path() -> str:
    return str(Path.home() / ".local" / "share" / "mapeg-mcp" / "query_logs.db")


def _get_connection() -> sqlite3.Connection:
    db_path = _get_db_path()
    if not os.path.exists(db_path):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _rows_to_dicts(rows):
    return [dict(row) for row in rows]


@app.route('/')
def dashboard():
    """Main dashboard page"""
    return render_template('dashboard.html')


@app.route('/api/filters')
def api_filters():
    """Return distinct db_identifier and workspace_path values for dropdowns"""
    conn = _get_connection()
    try:
        db_ids = [r[0] for r in conn.execute(
            "SELECT DISTINCT db_identifier FROM query_logs WHERE db_identifier != '' ORDER BY db_identifier"
        ).fetchall()]
        workspaces = [r[0] for r in conn.execute(
            "SELECT DISTINCT workspace_path FROM query_logs WHERE workspace_path != '' ORDER BY workspace_path"
        ).fetchall()]
        return jsonify({"db_identifiers": db_ids, "workspace_paths": workspaces})
    finally:
        conn.close()


@app.route('/api/stats')
def api_stats():
    """API endpoint for dashboard statistics"""
    server_type = request.args.get('server_type', None)
    db_identifier = request.args.get('db_identifier', None)
    workspace_path = request.args.get('workspace_path', None)

    conn = _get_connection()
    try:
        where_parts = []
        params = []
        if server_type:
            where_parts.append("server_type = ?")
            params.append(server_type)
        if db_identifier:
            where_parts.append("db_identifier = ?")
            params.append(db_identifier)
        if workspace_path:
            where_parts.append("workspace_path = ?")
            params.append(workspace_path)

        where_clause = (" WHERE " + " AND ".join(where_parts)) if where_parts else ""

        total = conn.execute(f"SELECT COUNT(*) FROM query_logs{where_clause}", params).fetchone()[0]
        success = conn.execute(f"SELECT COUNT(*) FROM query_logs{where_clause} {'AND' if where_parts else 'WHERE'} status = 'success'".replace("WHERE  AND", "WHERE"), params + ([] if not where_parts else [])).fetchone()[0]

        # Rebuild properly for success count
        success_parts = list(where_parts) + ["status = 'success'"]
        success_clause = " WHERE " + " AND ".join(success_parts)
        success = conn.execute(f"SELECT COUNT(*) FROM query_logs{success_clause}", params).fetchone()[0]

        avg_row = conn.execute(f"SELECT AVG(execution_time_ms) FROM query_logs{success_clause}", params).fetchone()
        avg_time = avg_row[0] or 0

        servers = dict(conn.execute(
            f"SELECT server_type, COUNT(*) FROM query_logs{where_clause} GROUP BY server_type", params
        ).fetchall())

        error_parts = list(where_parts) + ["status = 'error'"]
        error_clause = " WHERE " + " AND ".join(error_parts)
        recent_errors = _rows_to_dicts(conn.execute(
            f"SELECT timestamp, server_type, error_message, db_identifier, workspace_path FROM query_logs{error_clause} ORDER BY timestamp DESC LIMIT 10",
            params
        ).fetchall())

        success_rate = (success / total * 100) if total > 0 else 0

        return jsonify({
            'total_queries': total,
            'successful_queries': success,
            'success_rate': round(success_rate, 2),
            'avg_execution_time_ms': round(avg_time, 2),
            'queries_by_server': servers,
            'recent_errors': recent_errors,
        })
    finally:
        conn.close()


@app.route('/api/logs')
def api_logs():
    """API endpoint for recent query logs"""
    limit = request.args.get('limit', 50, type=int)
    server_type = request.args.get('server_type', None)
    db_identifier = request.args.get('db_identifier', None)
    workspace_path = request.args.get('workspace_path', None)

    conn = _get_connection()
    try:
        where_parts = []
        params = []
        if server_type:
            where_parts.append("server_type = ?")
            params.append(server_type)
        if db_identifier:
            where_parts.append("db_identifier = ?")
            params.append(db_identifier)
        if workspace_path:
            where_parts.append("workspace_path = ?")
            params.append(workspace_path)

        where_clause = (" WHERE " + " AND ".join(where_parts)) if where_parts else ""
        params.append(limit)

        rows = conn.execute(
            f"SELECT * FROM query_logs{where_clause} ORDER BY timestamp DESC LIMIT ?",
            params
        ).fetchall()

        return jsonify(_rows_to_dicts(rows))
    finally:
        conn.close()


@app.route('/api/logs/search')
def api_logs_search():
    """API endpoint for searching logs"""
    query = request.args.get('q', '', type=str)
    limit = request.args.get('limit', 50, type=int)
    db_identifier = request.args.get('db_identifier', None)
    workspace_path = request.args.get('workspace_path', None)

    conn = _get_connection()
    try:
        where_parts = []
        params = []
        if query:
            where_parts.append("(query_text LIKE ? OR user_query LIKE ?)")
            params.extend([f"%{query}%", f"%{query}%"])
        if db_identifier:
            where_parts.append("db_identifier = ?")
            params.append(db_identifier)
        if workspace_path:
            where_parts.append("workspace_path = ?")
            params.append(workspace_path)

        where_clause = (" WHERE " + " AND ".join(where_parts)) if where_parts else ""
        params.append(limit)

        rows = conn.execute(
            f"SELECT * FROM query_logs{where_clause} ORDER BY timestamp DESC LIMIT ?",
            params
        ).fetchall()

        return jsonify(_rows_to_dicts(rows))
    finally:
        conn.close()


@app.route('/logs')
def logs_page():
    """Logs detail page"""
    return render_template('logs.html')


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5008)
