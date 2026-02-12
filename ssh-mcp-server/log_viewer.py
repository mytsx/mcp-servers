#!/usr/bin/env python3
"""
SSH MCP Activity Log Viewer
Interactive dashboard for viewing SSH MCP server logs
"""

import sqlite3
import json
import argparse
import os
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from pathlib import Path
import sys

class SSHActivityLogViewer:
    """SSH MCP activity log viewer and analyzer"""
    
    def __init__(self, log_dir: str = "logs"):
        # Use same path as activity logger for consistency
        if not os.path.isabs(log_dir):
            self.log_dir = Path.home() / ".ssh_mcp_logs"
        else:
            self.log_dir = Path(log_dir)
        self.db_path = self.log_dir / "ssh_mcp_activities.db"
        
        if not self.db_path.exists():
            print(f"❌ Log database not found at {self.db_path}")
            sys.exit(1)
    
    def _parse_activity_rows(self, rows: list) -> List[Dict[str, Any]]:
        """Helper method to parse activity rows from database"""
        activities = []
        for row in rows:
            activity = dict(row)
            try:
                activity['arguments'] = json.loads(activity['arguments'])
                activity['security_flags'] = json.loads(activity['security_flags'])
            except (json.JSONDecodeError, TypeError):
                activity['arguments'] = {}
                activity['security_flags'] = []
            activities.append(activity)
        return activities
            
    def get_recent_activities(self, limit: int = 50, hours: int = 24) -> List[Dict[str, Any]]:
        """Get recent activities"""
        since = datetime.now() - timedelta(hours=hours)
        
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT * FROM ssh_activities 
                WHERE timestamp >= ? 
                ORDER BY timestamp DESC 
                LIMIT ?
            """, (since.isoformat(), limit))
            
            return self._parse_activity_rows(cursor.fetchall())
            
    def get_activities_by_session(self, session_id: str) -> List[Dict[str, Any]]:
        """Get all activities for a specific session"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT * FROM ssh_activities 
                WHERE user_session_id = ? 
                ORDER BY timestamp ASC
            """, (session_id,))
            
            return self._parse_activity_rows(cursor.fetchall())
            
    def get_sessions_summary(self, days: int = 7) -> List[Dict[str, Any]]:
        """Get summary of all sessions"""
        since = datetime.now() - timedelta(days=days)
        
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
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
                    "total_activities": row['total_activities'],
                    "error_count": row['error_count'],
                    "success_rate": ((row['total_activities'] - row['error_count']) / row['total_activities'] * 100) if row['total_activities'] > 0 else 100,
                    "avg_execution_time_ms": round(row['avg_execution_time'] or 0.0, 2),
                    "total_output_size_bytes": row['total_output_size'],
                    "server_host": row['server_host']
                })
                
            return sessions
            
    def get_activity_statistics(self, days: int = 7) -> Dict[str, Any]:
        """Get comprehensive activity statistics"""
        since = datetime.now() - timedelta(days=days)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Total activities
            cursor.execute(
                "SELECT COUNT(*) FROM ssh_activities WHERE timestamp >= ?",
                (since.isoformat(),)
            )
            total_activities = cursor.fetchone()[0]
            
            # Activities by type
            cursor.execute("""
                SELECT activity_type, COUNT(*) 
                FROM ssh_activities 
                WHERE timestamp >= ?
                GROUP BY activity_type
                ORDER BY COUNT(*) DESC
            """, (since.isoformat(),))
            activities_by_type = dict(cursor.fetchall())
            
            # Activities by status
            cursor.execute("""
                SELECT status, COUNT(*) 
                FROM ssh_activities 
                WHERE timestamp >= ?
                GROUP BY status
            """, (since.isoformat(),))
            activities_by_status = dict(cursor.fetchall())
            
            # Top commands
            cursor.execute("""
                SELECT command_or_action, COUNT(*) 
                FROM ssh_activities 
                WHERE timestamp >= ? AND activity_type = 'command_execution'
                GROUP BY command_or_action
                ORDER BY COUNT(*) DESC
                LIMIT 10
            """, (since.isoformat(),))
            top_commands = dict(cursor.fetchall())
            
            # Security incidents count
            cursor.execute("""
                SELECT COUNT(*) 
                FROM ssh_activities 
                WHERE timestamp >= ? AND security_flags != '[]'
            """, (since.isoformat(),))
            security_incidents = cursor.fetchone()[0]
            
            # Error analysis
            cursor.execute("""
                SELECT error_message, COUNT(*) 
                FROM ssh_activities 
                WHERE timestamp >= ? AND status = 'error' AND error_message IS NOT NULL
                GROUP BY error_message
                ORDER BY COUNT(*) DESC
                LIMIT 10
            """, (since.isoformat(),))
            top_errors = dict(cursor.fetchall())
            
            return {
                "period_days": days,
                "total_activities": total_activities,
                "activities_by_type": activities_by_type,
                "activities_by_status": activities_by_status,
                "top_commands": top_commands,
                "top_errors": top_errors,
                "security_incidents": security_incidents,
                "error_rate": (activities_by_status.get('error', 0) / total_activities * 100) if total_activities > 0 else 0
            }
            
    def search_activities(self, query: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Search activities by command, response, or arguments"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT * FROM ssh_activities 
                WHERE command_or_action LIKE ? 
                   OR response LIKE ? 
                   OR arguments LIKE ?
                ORDER BY timestamp DESC 
                LIMIT ?
            """, (f"%{query}%", f"%{query}%", f"%{query}%", limit))
            
            return self._parse_activity_rows(cursor.fetchall())
            
    def print_activity_summary(self, activity: Dict[str, Any]):
        """Print a formatted activity summary"""
        timestamp = datetime.fromisoformat(activity['timestamp']).strftime('%Y-%m-%d %H:%M:%S')
        
        # Status icon
        status_icon = "✅" if activity['status'] == 'success' else "❌" if activity['status'] == 'error' else "⚠️"
        
        print(f"{status_icon} [{timestamp}] {activity['activity_type']} | {activity['tool_name']}")
        print(f"   Command: {activity['command_or_action']}")
        
        if activity['arguments']:
            args_str = ", ".join([f"{k}={v}" for k, v in activity['arguments'].items()])
            print(f"   Args: {args_str}")
            
        # Response preview
        response = activity['response']
        if len(response) > 100:
            response = response[:100] + "..."
        print(f"   Response: {response}")
        
        if activity['execution_time_ms'] > 0:
            print(f"   Time: {activity['execution_time_ms']:.2f}ms")
            
        if activity['security_flags']:
            print(f"   🔒 Security Flags: {', '.join(activity['security_flags'])}")
            
        if activity['error_message']:
            print(f"   ❌ Error: {activity['error_message']}")
            
        print()

def main():
    """Main CLI interface"""
    parser = argparse.ArgumentParser(description="SSH MCP Activity Log Viewer")
    parser.add_argument("--log-dir", default="logs", help="Log directory path")
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Recent activities
    recent_parser = subparsers.add_parser("recent", help="Show recent activities")
    recent_parser.add_argument("--limit", type=int, default=20, help="Number of activities to show")
    recent_parser.add_argument("--hours", type=int, default=24, help="Hours to look back")
    
    # Sessions
    sessions_parser = subparsers.add_parser("sessions", help="Show session summary")
    sessions_parser.add_argument("--days", type=int, default=7, help="Days to look back")
    
    # Session details
    session_parser = subparsers.add_parser("session", help="Show session details")
    session_parser.add_argument("session_id", help="Session ID to show")
    
    # Statistics
    stats_parser = subparsers.add_parser("stats", help="Show activity statistics")
    stats_parser.add_argument("--days", type=int, default=7, help="Days to look back")
    
    # Search
    search_parser = subparsers.add_parser("search", help="Search activities")
    search_parser.add_argument("query", help="Search query")
    search_parser.add_argument("--limit", type=int, default=50, help="Number of results")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
        
    viewer = SSHActivityLogViewer(args.log_dir)
    
    if args.command == "recent":
        print(f"📋 Recent SSH MCP Activities (last {args.hours} hours)")
        print("=" * 60)
        activities = viewer.get_recent_activities(args.limit, args.hours)
        for activity in activities:
            viewer.print_activity_summary(activity)
            
    elif args.command == "sessions":
        print(f"📊 SSH MCP Sessions Summary (last {args.days} days)")
        print("=" * 60)
        sessions = viewer.get_sessions_summary(args.days)
        for session in sessions:
            duration_str = f"{session['duration_seconds']:.1f}s"
            success_rate = session['success_rate']
            print(f"🔗 {session['session_id']}")
            print(f"   📅 {session['session_start']} - {session['session_end']} ({duration_str})")
            print(f"   📊 {session['total_activities']} activities, {success_rate:.1f}% success rate")
            print(f"   🏠 Host: {session['server_host']}")
            if session['error_count'] > 0:
                print(f"   ❌ {session['error_count']} errors")
            print()
            
    elif args.command == "session":
        print(f"📋 Session Details: {args.session_id}")
        print("=" * 60)
        activities = viewer.get_activities_by_session(args.session_id)
        if not activities:
            print("❌ Session not found")
            return
        for activity in activities:
            viewer.print_activity_summary(activity)
            
    elif args.command == "stats":
        print(f"📈 SSH MCP Activity Statistics (last {args.days} days)")
        print("=" * 60)
        stats = viewer.get_activity_statistics(args.days)
        
        print(f"📊 Total Activities: {stats['total_activities']}")
        print(f"❌ Error Rate: {stats['error_rate']:.1f}%")
        print(f"🔒 Security Incidents: {stats['security_incidents']}")
        print()
        
        print("📋 Activities by Type:")
        for activity_type, count in stats['activities_by_type'].items():
            print(f"   {activity_type}: {count}")
        print()
        
        print("📊 Activities by Status:")
        for status, count in stats['activities_by_status'].items():
            print(f"   {status}: {count}")
        print()
        
        if stats['top_commands']:
            print("💻 Top Commands:")
            for command, count in stats['top_commands'].items():
                print(f"   {command}: {count}")
            print()
            
        if stats['top_errors']:
            print("❌ Top Errors:")
            for error, count in stats['top_errors'].items():
                print(f"   {error}: {count}")
            
    elif args.command == "search":
        print(f"🔍 Search Results for: '{args.query}'")
        print("=" * 60)
        activities = viewer.search_activities(args.query, args.limit)
        if not activities:
            print("❌ No results found")
            return
        for activity in activities:
            viewer.print_activity_summary(activity)

if __name__ == "__main__":
    main()