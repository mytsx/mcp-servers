#!/usr/bin/env python3
"""
Shared Query Logger for MCP Servers
Centralized logging system for PostgreSQL and Oracle MCP servers
"""

import json
import os
import sqlite3
import threading
import queue
from datetime import datetime
from typing import Optional, Dict, Any, Callable
from dataclasses import dataclass, asdict
from pathlib import Path

@dataclass
class QueryLog:
    id: Optional[int] = None
    timestamp: str = ""
    server_type: str = ""  # "postgresql" or "oracle"
    tool_name: str = ""    # "execute_sql", "natural_language_query", etc.
    query_text: str = ""
    execution_time_ms: float = 0.0
    status: str = ""       # "success" or "error"
    row_count: int = 0
    error_message: str = ""
    user_query: str = ""   # Original natural language query if applicable
    response_text: str = ""  # Query response/result

class QueryLogger:
    def __init__(self, db_path: str = None):
        """Initialize the query logger with SQLite database"""
        if db_path is None:
            # Create logs directory in ai_db folder
            log_dir = Path(__file__).parent / "logs"
            log_dir.mkdir(exist_ok=True)
            db_path = log_dir / "query_logs.db"
        
        self.db_path = db_path
        self._init_database()
        
        # Real-time notification callback
        self.notification_callback: Optional[Callable] = None
        
        # Asynchronous logging setup
        self.log_queue = queue.Queue()
        self.log_thread = threading.Thread(target=self._log_worker, daemon=True)
        self.log_thread.start()
    
    def _init_database(self):
        """Initialize SQLite database with query logs table"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
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
                response_text TEXT DEFAULT ''
            )
        """)
        
        # Create index for faster queries
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_timestamp 
            ON query_logs(timestamp DESC)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_server_type 
            ON query_logs(server_type)
        """)
        
        conn.commit()
        conn.close()
    
    def _log_worker(self):
        """Background thread worker for asynchronous logging"""
        while True:
            try:
                log_entry = self.log_queue.get(timeout=1)
                if log_entry is None:  # Shutdown signal
                    break
                self._write_log_to_db(log_entry)
                self.log_queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                print(f"Logging error: {e}")
    
    def _write_log_to_db(self, log_entry: QueryLog) -> int:
        """Write log entry to database (called by worker thread)"""
        if not log_entry.timestamp:
            log_entry.timestamp = datetime.now().isoformat()
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO query_logs (
                timestamp, server_type, tool_name, query_text, 
                execution_time_ms, status, row_count, error_message, user_query, response_text
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            log_entry.timestamp,
            log_entry.server_type,
            log_entry.tool_name,
            log_entry.query_text,
            log_entry.execution_time_ms,
            log_entry.status,
            log_entry.row_count,
            log_entry.error_message,
            log_entry.user_query,
            log_entry.response_text
        ))
        
        log_id = cursor.lastrowid
        log_entry.id = log_id
        conn.commit()
        conn.close()
        
        # Trigger real-time notification
        if self.notification_callback:
            try:
                log_dict = asdict(log_entry)
                self.notification_callback(log_dict)
            except Exception as e:
                print(f"Notification callback error: {e}")
        
        return log_id
    
    def set_notification_callback(self, callback: Callable):
        """Set callback function for real-time notifications"""
        self.notification_callback = callback
    
    def log_query(self, log_entry: QueryLog) -> int:
        """Log a query execution asynchronously"""
        # Add to queue for background processing
        self.log_queue.put(log_entry)
        return 0  # Return immediately, actual ID will be assigned by worker
    
    def get_recent_logs(self, limit: int = 100, server_type: str = None) -> list:
        """Get recent query logs"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        if server_type:
            cursor.execute("""
                SELECT * FROM query_logs 
                WHERE server_type = ?
                ORDER BY timestamp DESC 
                LIMIT ?
            """, (server_type, limit))
        else:
            cursor.execute("""
                SELECT * FROM query_logs 
                ORDER BY timestamp DESC 
                LIMIT ?
            """, (limit,))
        
        rows = cursor.fetchall()
        conn.close()
        
        # Convert to list of dictionaries
        columns = ['id', 'timestamp', 'server_type', 'tool_name', 'query_text', 
                  'execution_time_ms', 'status', 'row_count', 'error_message', 'user_query', 'response_text']
        
        return [dict(zip(columns, row)) for row in rows]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about logged queries"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Total queries
        cursor.execute("SELECT COUNT(*) FROM query_logs")
        total_queries = cursor.fetchone()[0]
        
        # Success rate
        cursor.execute("SELECT COUNT(*) FROM query_logs WHERE status = 'success'")
        successful_queries = cursor.fetchone()[0]
        
        # Average execution time
        cursor.execute("SELECT AVG(execution_time_ms) FROM query_logs WHERE status = 'success'")
        avg_execution_time = cursor.fetchone()[0] or 0
        
        # Queries by server type
        cursor.execute("""
            SELECT server_type, COUNT(*) 
            FROM query_logs 
            GROUP BY server_type
        """)
        queries_by_server = dict(cursor.fetchall())
        
        # Recent errors
        cursor.execute("""
            SELECT timestamp, server_type, error_message 
            FROM query_logs 
            WHERE status = 'error' 
            ORDER BY timestamp DESC 
            LIMIT 10
        """)
        recent_errors = cursor.fetchall()
        
        conn.close()
        
        success_rate = (successful_queries / total_queries * 100) if total_queries > 0 else 0
        
        return {
            'total_queries': total_queries,
            'successful_queries': successful_queries,
            'success_rate': round(success_rate, 2),
            'avg_execution_time_ms': round(avg_execution_time, 2),
            'queries_by_server': queries_by_server,
            'recent_errors': [
                {
                    'timestamp': error[0],
                    'server_type': error[1], 
                    'error_message': error[2]
                } for error in recent_errors
            ]
        }

# Global logger instance
_logger_instance = None

def get_logger() -> QueryLogger:
    """Get the global query logger instance"""
    global _logger_instance
    if _logger_instance is None:
        _logger_instance = QueryLogger()
    return _logger_instance

def log_query_execution(
    server_type: str,
    tool_name: str, 
    query_text: str,
    execution_time_ms: float,
    status: str,
    row_count: int = 0,
    error_message: str = "",
    user_query: str = "",
    response_text: str = ""
) -> int:
    """Convenience function to log a query execution"""
    logger = get_logger()
    log_entry = QueryLog(
        server_type=server_type,
        tool_name=tool_name,
        query_text=query_text,
        execution_time_ms=execution_time_ms,
        status=status,
        row_count=row_count,
        error_message=error_message,
        user_query=user_query,
        response_text=response_text
    )
    return logger.log_query(log_entry)

def direct_log_query_execution(
    server_type: str,
    tool_name: str, 
    query_text: str,
    execution_time_ms: float,
    status: str,
    row_count: int = 0,
    error_message: str = "",
    user_query: str = "",
    response_text: str = ""
) -> int:
    """Direct synchronous logging to avoid async queue truncation"""
    logger = get_logger()
    log_entry = QueryLog(
        server_type=server_type,
        tool_name=tool_name,
        query_text=query_text,
        execution_time_ms=execution_time_ms,
        status=status,
        row_count=row_count,
        error_message=error_message,
        user_query=user_query,
        response_text=response_text
    )
    return logger._write_log_to_db(log_entry)