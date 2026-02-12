#!/usr/bin/env python3
"""
SSH MCP Activity Log Dashboard
Modern Flask web application for viewing and analyzing SSH MCP activities
"""

import os
import sqlite3
import json
from datetime import datetime, timedelta
from pathlib import Path
from flask import Flask, render_template, jsonify, request, Response, g

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24)

# Configuration - Use same path as activity logger
LOG_DIR = Path.home() / ".ssh_mcp_logs"
DB_PATH = LOG_DIR / "ssh_mcp_activities.db"

def get_db_connection():
    """Get database connection with row factory using Flask application context"""
    if 'db' not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(error):
    """Close database connection at the end of the request"""
    db = getattr(g, 'db', None)
    if db is not None:
        db.close()

def parse_activity(row):
    """Parse activity row into dictionary"""
    activity = dict(row)
    try:
        activity['arguments'] = json.loads(activity['arguments'])
        activity['security_flags'] = json.loads(activity['security_flags'])
    except (json.JSONDecodeError, TypeError):
        activity['arguments'] = {}
        activity['security_flags'] = []
    # Format timestamp
    activity['formatted_time'] = datetime.fromisoformat(activity['timestamp']).strftime('%Y-%m-%d %H:%M:%S')
    return activity

# Routes
@app.route('/')
def index():
    """Main dashboard page"""
    return render_template('dashboard.html')

@app.route('/api/activities/recent')
def api_recent_activities():
    """Get recent activities API"""
    hours = int(request.args.get('hours', 24))
    limit = int(request.args.get('limit', 100))
    
    since = datetime.now() - timedelta(hours=hours)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT * FROM ssh_activities 
        WHERE timestamp >= ? 
        ORDER BY timestamp DESC 
        LIMIT ?
    """, (since.isoformat(), limit))
    
    activities = [parse_activity(row) for row in cursor.fetchall()]
    
    return jsonify(activities)

@app.route('/api/activities/<int:activity_id>')
def api_activity_detail(activity_id):
    """Get single activity detail"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM ssh_activities WHERE id = ?", (activity_id,))
    row = cursor.fetchone()
    
    if row:
        return jsonify(parse_activity(row))
    return jsonify({"error": "Activity not found"}), 404

@app.route('/api/sessions')
def api_sessions():
    """Get sessions list API"""
    days = int(request.args.get('days', 7))
    since = datetime.now() - timedelta(days=days)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT 
            user_session_id,
            MIN(timestamp) as session_start,
            MAX(timestamp) as session_end,
            COUNT(*) as total_activities,
            SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) as error_count,
            AVG(execution_time_ms) as avg_execution_time,
            SUM(output_size_bytes) as total_output_size,
            server_host
        FROM ssh_activities 
        WHERE timestamp >= ?
        GROUP BY user_session_id
        ORDER BY session_start DESC
    """, (since.isoformat(),))
    
    sessions = []
    for row in cursor.fetchall():
        session_start = datetime.fromisoformat(row['session_start'])
        session_end = datetime.fromisoformat(row['session_end'])
        duration = (session_end - session_start).total_seconds()
        
        sessions.append({
            "session_id": row['user_session_id'],
            "session_start": row['session_start'],
            "session_end": row['session_end'],
            "duration_seconds": duration,
            "duration_formatted": f"{int(duration//3600)}h {int((duration%3600)//60)}m {int(duration%60)}s",
            "total_activities": row['total_activities'],
            "error_count": row['error_count'],
            "success_rate": ((row['total_activities'] - row['error_count']) / row['total_activities'] * 100) if row['total_activities'] > 0 else 100,
            "avg_execution_time_ms": round(row['avg_execution_time'] or 0.0, 2),
            "total_output_size_kb": round(row['total_output_size'] / 1024, 2),
            "server_host": row['server_host']
        })
    
    return jsonify(sessions)

@app.route('/api/session/<session_id>')
def api_session_activities(session_id):
    """Get activities for specific session"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT * FROM ssh_activities 
        WHERE user_session_id = ? 
        ORDER BY timestamp ASC
    """, (session_id,))
    
    activities = [parse_activity(row) for row in cursor.fetchall()]
    
    return jsonify(activities)

@app.route('/api/statistics')
def api_statistics():
    """Get comprehensive statistics"""
    days = int(request.args.get('days', 7))
    since = datetime.now() - timedelta(days=days)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Total activities
    cursor.execute(
        "SELECT COUNT(*) FROM ssh_activities WHERE timestamp >= ?",
        (since.isoformat(),)
    )
    total_activities = cursor.fetchone()[0]
    
    # Activities by type
    cursor.execute("""
        SELECT activity_type, COUNT(*) as count
        FROM ssh_activities 
        WHERE timestamp >= ?
        GROUP BY activity_type
        ORDER BY count DESC
    """, (since.isoformat(),))
    activities_by_type = [{
        "type": row[0], 
        "count": row[1]
    } for row in cursor.fetchall()]
    
    # Activities by status
    cursor.execute("""
        SELECT status, COUNT(*) as count
        FROM ssh_activities 
        WHERE timestamp >= ?
        GROUP BY status
    """, (since.isoformat(),))
    activities_by_status = [{
        "status": row[0], 
        "count": row[1]
    } for row in cursor.fetchall()]
    
    # Top commands
    cursor.execute("""
        SELECT command_or_action, COUNT(*) as count
        FROM ssh_activities 
        WHERE timestamp >= ? AND activity_type = 'command_execution'
        GROUP BY command_or_action
        ORDER BY count DESC
        LIMIT 10
    """, (since.isoformat(),))
    top_commands = [{
        "command": row[0], 
        "count": row[1]
    } for row in cursor.fetchall()]
    
    # Error analysis
    cursor.execute("""
        SELECT error_message, COUNT(*) as count
        FROM ssh_activities 
        WHERE timestamp >= ? AND status = 'error' AND error_message IS NOT NULL
        GROUP BY error_message
        ORDER BY count DESC
        LIMIT 10
    """, (since.isoformat(),))
    top_errors = [{
        "error": row[0], 
        "count": row[1]
    } for row in cursor.fetchall()]
    
    # Activity timeline (hourly)
    cursor.execute("""
        SELECT 
            strftime('%Y-%m-%d %H:00:00', timestamp) as hour,
            COUNT(*) as count,
            SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) as error_count
        FROM ssh_activities 
        WHERE timestamp >= ?
        GROUP BY hour
        ORDER BY hour
    """, (since.isoformat(),))
    
    timeline_data = []
    for row in cursor.fetchall():
        timeline_data.append({
            "hour": row[0],
            "total": row[1],
            "errors": row[2],
            "success": row[1] - row[2]
        })
    
    # Security incidents
    cursor.execute("""
        SELECT COUNT(*) 
        FROM ssh_activities 
        WHERE timestamp >= ? AND security_flags != '[]'
    """, (since.isoformat(),))
    security_incidents = cursor.fetchone()[0]
    
    
    # Calculate error rate
    error_count = sum(item['count'] for item in activities_by_status if item['status'] == 'error')
    error_rate = (error_count / total_activities * 100) if total_activities > 0 else 0
    
    return jsonify({
        "period_days": days,
        "total_activities": total_activities,
        "error_rate": round(error_rate, 2),
        "security_incidents": security_incidents,
        "activities_by_type": activities_by_type,
        "activities_by_status": activities_by_status,
        "top_commands": top_commands,
        "top_errors": top_errors,
        "timeline_data": timeline_data
    })

@app.route('/api/search')
def api_search():
    """Search activities API"""
    query = request.args.get('q', '')
    limit = int(request.args.get('limit', 100))
    
    if not query:
        return jsonify([])
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT * FROM ssh_activities 
        WHERE command_or_action LIKE ? 
           OR response LIKE ? 
           OR arguments LIKE ?
           OR error_message LIKE ?
        ORDER BY timestamp DESC 
        LIMIT ?
    """, (f"%{query}%", f"%{query}%", f"%{query}%", f"%{query}%", limit))
    
    activities = [parse_activity(row) for row in cursor.fetchall()]
    
    return jsonify(activities)

@app.route('/api/export')
def api_export():
    """Export activities as JSON or CSV with true memory-efficient streaming"""
    format = request.args.get('format', 'json')
    days = int(request.args.get('days', 7))
    limit = int(request.args.get('limit', 10000))  # Default limit to prevent memory issues
    since = datetime.now() - timedelta(days=days)
    
    def generate_csv():
        """Generator for CSV export that streams data row by row"""
        import csv
        import io
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM ssh_activities 
            WHERE timestamp >= ?
            ORDER BY timestamp DESC
            LIMIT ?
        """, (since.isoformat(), limit))
        
        output = io.StringIO()
        writer = None

        # Stream rows
        for i, row in enumerate(cursor):
            activity = parse_activity(row)

            if i == 0:
                # First row, create writer and write header
                fieldnames = list(activity.keys())
                writer = csv.DictWriter(output, fieldnames=fieldnames)
                writer.writeheader()
                yield output.getvalue()
                
                # Reset buffer for next iteration
                output.seek(0)
                output.truncate(0)
            
            if writer:
                writer.writerow(activity)
                yield output.getvalue()
                
                # Reset buffer for next iteration
                output.seek(0)
                output.truncate(0)
    
    def generate_json():
        """Generator for JSON export that streams data row by row"""
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM ssh_activities 
            WHERE timestamp >= ?
            ORDER BY timestamp DESC
            LIMIT ?
        """, (since.isoformat(), limit))
        
        yield '[\n'
        first = True
        
        while True:
            row = cursor.fetchone()
            if row is None:
                break
            activity = parse_activity(row)
            if not first:
                yield ',\n'
            yield '  ' + json.dumps(activity, ensure_ascii=False)
            first = False
        
        yield '\n]'
    
    if format == 'csv':
        return Response(
            generate_csv(),
            mimetype='text/csv',
            headers={'Content-Disposition': f'attachment; filename=ssh_activities_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'}
        )
    else:
        return Response(
            generate_json(),
            mimetype='application/json',
            headers={'Content-Disposition': f'attachment; filename=ssh_activities_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'}
        )

# Error handlers
@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Not found"}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({"error": "Internal server error"}), 500

if __name__ == '__main__':
    # Ensure database exists
    if not DB_PATH.exists():
        print(f"❌ Database not found at {DB_PATH}")
        print("Please run the SSH MCP server first to create the database.")
        exit(1)
    
    print("🚀 Starting SSH MCP Activity Log Dashboard...")
    print(f"📊 Dashboard URL: http://localhost:5555")
    app.run(host='0.0.0.0', port=5555, debug=os.environ.get('FLASK_DEBUG', 'false').lower() == 'true')