#!/usr/bin/env python3
"""
Query Dashboard - Flask Web Interface for MCP Server Query Logs
Beautiful web interface to monitor database queries and performance
"""

from flask import Flask, render_template, jsonify, request
import sys
import os
from datetime import datetime, timedelta

# Add parent directory to path to import shared_logger
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared_logger import get_logger

app = Flask(__name__)
app.config['SECRET_KEY'] = 'mcp-dashboard-secret-key'

@app.route('/')
def dashboard():
    """Main dashboard page"""
    return render_template('dashboard.html')

@app.route('/api/stats')
def api_stats():
    """API endpoint for dashboard statistics"""
    logger = get_logger()
    stats = logger.get_stats()
    return jsonify(stats)

@app.route('/api/logs')
def api_logs():
    """API endpoint for recent query logs"""
    limit = request.args.get('limit', 50, type=int)
    server_type = request.args.get('server_type', None)
    
    logger = get_logger()
    logs = logger.get_recent_logs(limit=limit, server_type=server_type)
    
    return jsonify(logs)

@app.route('/api/logs/search')
def api_logs_search():
    """API endpoint for searching logs"""
    query = request.args.get('q', '', type=str)
    limit = request.args.get('limit', 50, type=int)
    
    # For now, simple search in query_text
    # Could be enhanced with full-text search
    logger = get_logger()
    all_logs = logger.get_recent_logs(limit=1000)
    
    if query:
        filtered_logs = [
            log for log in all_logs 
            if query.lower() in log['query_text'].lower() 
            or query.lower() in log['user_query'].lower()
        ]
        logs = filtered_logs[:limit]
    else:
        logs = all_logs[:limit]
    
    return jsonify(logs)

@app.route('/logs')
def logs_page():
    """Logs detail page"""
    return render_template('logs.html')

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5008)