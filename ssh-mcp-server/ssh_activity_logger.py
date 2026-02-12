#!/usr/bin/env python3
"""
SSH MCP Server Activity Logger
Comprehensive logging system for tracking AI commands and responses
"""

import os
import sys
import json
import sqlite3
import asyncio
import atexit
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from pathlib import Path
import logging
from dataclasses import dataclass
from enum import Enum

class ActivityType(Enum):
    """Types of SSH MCP activities"""
    COMMAND_EXECUTION = "command_execution"
    FILE_OPERATION = "file_operation"
    SYSTEM_MONITOR = "system_monitor"
    PROCESS_MANAGER = "process_manager"
    RESOURCE_ACCESS = "resource_access"
    CONNECTION = "connection"
    ERROR = "error"

class LogLevel(Enum):
    """Log severity levels"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

@dataclass
class SSHActivity:
    """SSH activity data structure"""
    timestamp: str
    activity_type: str
    tool_name: str
    command_or_action: str
    arguments: Dict[str, Any]
    response: str
    execution_time_ms: float
    status: str  # success, error, warning
    user_session_id: str
    server_host: str
    error_message: Optional[str] = None
    output_size_bytes: int = 0
    security_flags: List[str] = None

    def __post_init__(self):
        if self.security_flags is None:
            self.security_flags = []

class SSHActivityLogger:
    """Comprehensive SSH MCP activity logger"""
    
    def __init__(self, log_dir: str = "logs"):
        # For Claude Desktop compatibility, use absolute path in user home
        if not os.path.isabs(log_dir):
            # Use ~/.ssh_mcp_logs instead of relative logs directory
            self.log_dir = Path.home() / ".ssh_mcp_logs"
        else:
            self.log_dir = Path(log_dir)
        
        try:
            self.log_dir.mkdir(exist_ok=True)
        except OSError as e:
            # Fallback to temp directory if home directory fails
            import tempfile
            self.log_dir = Path(tempfile.gettempdir()) / "ssh_mcp_logs"
            self.log_dir.mkdir(exist_ok=True)
            print(f"Using fallback log directory: {self.log_dir}", file=sys.stderr)
        
        # Initialize database
        self.db_path = self.log_dir / "ssh_mcp_activities.db"
        self.init_database()
        
        # Initialize file logger
        self.init_file_logger()
        
        # Session tracking
        self.session_id = self.generate_session_id()
        self.connection_start = datetime.now(timezone.utc)
        
        # Connection pool for performance
        self._connection = None
        
        # Register cleanup function to close connection on exit
        atexit.register(self.close_connection)
        
    def get_connection(self):
        """Get persistent database connection"""
        if self._connection is None:
            self._connection = sqlite3.connect(self.db_path, check_same_thread=False)
        return self._connection
    
    def close_connection(self):
        """Close database connection"""
        if self._connection:
            self._connection.close()
            self._connection = None
        
    def init_database(self):
        """Initialize SQLite database for structured logging"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ssh_activities (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    activity_type TEXT NOT NULL,
                    tool_name TEXT NOT NULL,
                    command_or_action TEXT NOT NULL,
                    arguments TEXT NOT NULL,
                    response TEXT NOT NULL,
                    execution_time_ms REAL NOT NULL,
                    status TEXT NOT NULL,
                    user_session_id TEXT NOT NULL,
                    server_host TEXT NOT NULL,
                    error_message TEXT,
                    output_size_bytes INTEGER DEFAULT 0,
                    security_flags TEXT DEFAULT '[]',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create indexes for performance
            conn.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON ssh_activities(timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_activity_type ON ssh_activities(activity_type)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_session_id ON ssh_activities(user_session_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_status ON ssh_activities(status)")
            
    def init_file_logger(self):
        """Initialize file-based logging"""
        log_file = self.log_dir / f"ssh_mcp_{datetime.now().strftime('%Y%m%d')}.log"
        
        # Configure logger
        self.file_logger = logging.getLogger('ssh_mcp_activity')
        self.file_logger.setLevel(logging.INFO)
        
        # Remove existing handlers
        for handler in self.file_logger.handlers[:]:
            self.file_logger.removeHandler(handler)
            
        # File handler
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_formatter = logging.Formatter(
            '%(asctime)s | %(levelname)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_formatter)
        self.file_logger.addHandler(file_handler)
        
    def generate_session_id(self) -> str:
        """Generate unique session identifier"""
        return f"ssh_session_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{os.getpid()}"
        
    def log_activity(self, activity: SSHActivity):
        """Log activity to both database and file"""
        try:
            # Check if we're in an async context
            try:
                loop = asyncio.get_running_loop()
                # We're in an async context, run database ops in executor
                asyncio.create_task(self._log_to_database_async(activity))
            except RuntimeError:
                # No event loop running, use synchronous method
                self._log_to_database(activity)
            
            # Log to file (this is fast, safe to run synchronously)
            self._log_to_file(activity)
            
        except Exception as e:
            # Fallback logging
            print(f"Error logging activity: {e}", file=sys.stderr)
    
    async def _log_to_database_async(self, activity: SSHActivity):
        """Store activity in SQLite database using thread executor"""
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._log_to_database, activity)
        except Exception as e:
            print(f"Async database logging error: {e}", file=sys.stderr)
            
    def _log_to_database(self, activity: SSHActivity):
        """Store activity in SQLite database"""
        conn = self.get_connection()
        try:
            conn.execute("""
                INSERT INTO ssh_activities (
                    timestamp, activity_type, tool_name, command_or_action,
                    arguments, response, execution_time_ms, status,
                    user_session_id, server_host, error_message,
                    output_size_bytes, security_flags
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                activity.timestamp,
                activity.activity_type,
                activity.tool_name,
                activity.command_or_action,
                json.dumps(activity.arguments, ensure_ascii=False),
                activity.response,
                activity.execution_time_ms,
                activity.status,
                activity.user_session_id,
                activity.server_host,
                activity.error_message,
                activity.output_size_bytes,
                json.dumps(activity.security_flags)
            ))
            conn.commit()
        except Exception as e:
            print(f"Database logging error: {e}", file=sys.stderr)
            
    def _log_to_file(self, activity: SSHActivity):
        """Write activity to log file"""
        log_entry = {
            "timestamp": activity.timestamp,
            "session": activity.user_session_id,
            "type": activity.activity_type,
            "tool": activity.tool_name,
            "action": activity.command_or_action,
            "args": activity.arguments,
            "response_preview": activity.response[:200] + "..." if len(activity.response) > 200 else activity.response,
            "execution_time": f"{activity.execution_time_ms:.2f}ms",
            "status": activity.status,
            "host": activity.server_host,
            "response_size": f"{activity.output_size_bytes} bytes",
            "security_flags": activity.security_flags
        }
        
        if activity.error_message:
            log_entry["error"] = activity.error_message
            
        log_message = json.dumps(log_entry, ensure_ascii=False, separators=(',', ':'))
        
        if activity.status == "error":
            self.file_logger.error(log_message)
        elif activity.security_flags:
            self.file_logger.warning(log_message)
        else:
            self.file_logger.info(log_message)
            
    def log_command_execution(self, command: str, arguments: Dict[str, Any], 
                            response: str, execution_time: float, status: str = "success",
                            error_message: str = None, security_flags: List[str] = None):
        """Log command execution activity"""
        activity = SSHActivity(
            timestamp=datetime.now(timezone.utc).isoformat(),
            activity_type=ActivityType.COMMAND_EXECUTION.value,
            tool_name="execute_command",
            command_or_action=command,
            arguments=arguments,
            response=response,
            execution_time_ms=execution_time,
            status=status,
            user_session_id=self.session_id,
            server_host=os.getenv("SSH_HOST", "unknown"),
            error_message=error_message,
            output_size_bytes=len(response.encode('utf-8')),
            security_flags=security_flags or []
        )
        self.log_activity(activity)
        
    def log_file_operation(self, operation: str, path: str, arguments: Dict[str, Any],
                          response: str, execution_time: float, status: str = "success",
                          error_message: str = None):
        """Log file operation activity"""
        activity = SSHActivity(
            timestamp=datetime.now(timezone.utc).isoformat(),
            activity_type=ActivityType.FILE_OPERATION.value,
            tool_name="file_operations",
            command_or_action=f"{operation}:{path}",
            arguments=arguments,
            response=response,
            execution_time_ms=execution_time,
            status=status,
            user_session_id=self.session_id,
            server_host=os.getenv("SSH_HOST", "unknown"),
            error_message=error_message,
            output_size_bytes=len(response.encode('utf-8'))
        )
        self.log_activity(activity)
        
    def log_system_monitor(self, metric: str, arguments: Dict[str, Any],
                          response: str, execution_time: float, status: str = "success",
                          error_message: str = None):
        """Log system monitoring activity"""
        activity = SSHActivity(
            timestamp=datetime.now(timezone.utc).isoformat(),
            activity_type=ActivityType.SYSTEM_MONITOR.value,
            tool_name="system_monitor",
            command_or_action=f"monitor:{metric}",
            arguments=arguments,
            response=response,
            execution_time_ms=execution_time,
            status=status,
            user_session_id=self.session_id,
            server_host=os.getenv("SSH_HOST", "unknown"),
            error_message=error_message,
            output_size_bytes=len(response.encode('utf-8'))
        )
        self.log_activity(activity)
        
    def log_process_manager(self, action: str, target: str, arguments: Dict[str, Any],
                           response: str, execution_time: float, status: str = "success",
                           error_message: str = None, security_flags: List[str] = None):
        """Log process management activity"""
        activity = SSHActivity(
            timestamp=datetime.now(timezone.utc).isoformat(),
            activity_type=ActivityType.PROCESS_MANAGER.value,
            tool_name="process_manager",
            command_or_action=f"{action}:{target}",
            arguments=arguments,
            response=response,
            execution_time_ms=execution_time,
            status=status,
            user_session_id=self.session_id,
            server_host=os.getenv("SSH_HOST", "unknown"),
            error_message=error_message,
            output_size_bytes=len(response.encode('utf-8')),
            security_flags=security_flags or []
        )
        self.log_activity(activity)
        
    def log_resource_access(self, resource_uri: str, response: str, 
                           execution_time: float, status: str = "success",
                           error_message: str = None):
        """Log resource access activity"""
        activity = SSHActivity(
            timestamp=datetime.now(timezone.utc).isoformat(),
            activity_type=ActivityType.RESOURCE_ACCESS.value,
            tool_name="resource_access",
            command_or_action=resource_uri,
            arguments={"uri": resource_uri},
            response=response,
            execution_time_ms=execution_time,
            status=status,
            user_session_id=self.session_id,
            server_host=os.getenv("SSH_HOST", "unknown"),
            error_message=error_message,
            output_size_bytes=len(response.encode('utf-8'))
        )
        self.log_activity(activity)
        
    def log_connection_event(self, event: str, details: str, status: str = "success"):
        """Log connection events"""
        activity = SSHActivity(
            timestamp=datetime.now(timezone.utc).isoformat(),
            activity_type=ActivityType.CONNECTION.value,
            tool_name="ssh_connection",
            command_or_action=event,
            arguments={"event": event, "details": details},
            response=details,
            execution_time_ms=0.0,
            status=status,
            user_session_id=self.session_id,
            server_host=os.getenv("SSH_HOST", "unknown"),
            output_size_bytes=len(details.encode('utf-8'))
        )
        self.log_activity(activity)
    
    def log_event(self, event_type: str, command: str, response: str, 
                  execution_time: float = 0, status: str = "success", 
                  error_message: str = None, metadata: Dict[str, Any] = None):
        """General purpose event logging method"""
        # Map event types to appropriate activity types
        activity_type_map = {
            "connection_established": ActivityType.CONNECTION.value,
            "connection_failed": ActivityType.CONNECTION.value,
            "auto_reconnection": ActivityType.CONNECTION.value,
            "reconnection": ActivityType.CONNECTION.value,
            "reconnection_failed": ActivityType.CONNECTION.value,
        }
        
        activity_type = activity_type_map.get(event_type, ActivityType.CONNECTION.value)
        
        activity = SSHActivity(
            timestamp=datetime.now(timezone.utc).isoformat(),
            activity_type=activity_type,
            tool_name=event_type,
            command_or_action=command,
            arguments=metadata or {},
            response=response,
            execution_time_ms=execution_time,
            status=status,
            error_message=error_message,
            user_session_id=self.session_id,
            server_host=os.getenv("SSH_HOST", "unknown"),
            output_size_bytes=len(response.encode('utf-8'))
        )
        self.log_activity(activity)
        
    def get_session_stats(self) -> Dict[str, Any]:
        """Get current session statistics"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Total activities
        cursor.execute(
            "SELECT COUNT(*) FROM ssh_activities WHERE user_session_id = ?",
            (self.session_id,)
        )
        total_activities = cursor.fetchone()[0]
        
        # Activities by type
        cursor.execute("""
            SELECT activity_type, COUNT(*) 
            FROM ssh_activities 
            WHERE user_session_id = ? 
            GROUP BY activity_type
        """, (self.session_id,))
        activities_by_type = dict(cursor.fetchall())
        
        # Error count
        cursor.execute(
            "SELECT COUNT(*) FROM ssh_activities WHERE user_session_id = ? AND status = 'error'",
            (self.session_id,)
        )
        error_count = cursor.fetchone()[0]
        
        # Average execution time
        cursor.execute(
            "SELECT AVG(execution_time_ms) FROM ssh_activities WHERE user_session_id = ?",
            (self.session_id,)
        )
        avg_execution_time = cursor.fetchone()[0] or 0.0
        
        session_duration = (datetime.now(timezone.utc) - self.connection_start).total_seconds()
        
        return {
            "session_id": self.session_id,
            "session_duration_seconds": session_duration,
            "total_activities": total_activities,
            "activities_by_type": activities_by_type,
            "error_count": error_count,
            "success_rate": ((total_activities - error_count) / total_activities * 100) if total_activities > 0 else 100,
            "average_execution_time_ms": round(avg_execution_time, 2),
            "server_host": os.getenv("SSH_HOST", "unknown"),
            "connection_start": self.connection_start.isoformat()
        }

# Global logger instance
activity_logger = None

def get_activity_logger() -> SSHActivityLogger:
    """Get or create global activity logger instance"""
    global activity_logger
    if activity_logger is None:
        activity_logger = SSHActivityLogger()
    return activity_logger

def log_session_start():
    """Log session start event"""
    logger = get_activity_logger()
    logger.log_connection_event(
        "session_start", 
        f"SSH MCP session started at {datetime.now(timezone.utc).isoformat()}"
    )

def log_session_end():
    """Log session end event with statistics"""
    logger = get_activity_logger()
    stats = logger.get_session_stats()
    logger.log_connection_event(
        "session_end",
        f"Session ended. Stats: {json.dumps(stats, separators=(',', ':'))}"
    )