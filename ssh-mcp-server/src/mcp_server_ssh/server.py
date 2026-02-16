#!/usr/bin/env python3
"""
SSH MCP Server for Claude Desktop
Remote Linux server command execution via SSH
"""

import asyncio
import os
import logging
import time
import re
from shlex import quote
from typing import Any, List, Dict, Optional
import paramiko
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    Resource,
    Tool,
    TextContent
)
from dotenv import load_dotenv

# Optional activity logger support
try:
    from ssh_activity_logger import get_activity_logger, log_session_start, log_session_end
    ACTIVITY_LOGGING_ENABLED = True
except ImportError:
    ACTIVITY_LOGGING_ENABLED = False
    class _NullLogger:
        """Stub logger that silently ignores all method calls"""
        def __getattr__(self, name):
            return lambda *a, **kw: None
    def get_activity_logger(): return _NullLogger()
    def log_session_start(*a, **kw): pass
    def log_session_end(*a, **kw): pass

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Constants
DEFAULT_SSH_PORT = 22
DEFAULT_SSH_TIMEOUT = 30
DEFAULT_COMMAND_TIMEOUT = 30
DEFAULT_FILE_READ_LIMIT = 100
MAX_RETRY_ATTEMPTS = 2
MIN_PORT_NUMBER = 1
MAX_PORT_NUMBER = 65535
CONNECTION_TEST_TIMEOUT = 5
RETRY_DELAY_SECONDS = 1

class SSHMCPServer:
    def __init__(self):
        self.server = Server("ssh-mcp-server")
        self.ssh_client = None
        self.activity_logger = get_activity_logger()
        self.last_connection_check = None
        self.connection_failures = 0
        # Cache connection parameters to avoid duplication
        self._connection_params = None
        self._keepalive_task = None
        self._running = True
        self.setup_handlers()
        
        # Log session start
        log_session_start()
        
    def setup_handlers(self):
        """Setup MCP server handlers"""
        
        @self.server.list_resources()
        async def list_resources() -> List[Resource]:
            """List available SSH resources"""
            return [
                Resource(
                    uri="ssh://system",
                    name="System Information",
                    description="Get remote server system information",
                    mimeType="text/plain"
                ),
                Resource(
                    uri="ssh://processes",
                    name="Running Processes",
                    description="List running processes on remote server",
                    mimeType="text/plain"
                ),
                Resource(
                    uri="ssh://disk",
                    name="Disk Usage",
                    description="Show disk usage and mounted filesystems",
                    mimeType="text/plain"
                ),
                Resource(
                    uri="ssh://network",
                    name="Network Information",
                    description="Show network configuration and connections",
                    mimeType="text/plain"
                ),
                Resource(
                    uri="ssh://logs",
                    name="System Logs",
                    description="View recent system logs",
                    mimeType="text/plain"
                )
            ]
        
        @self.server.read_resource()
        async def read_resource(uri: str) -> str:
            """Read SSH resource"""
            if not self.ssh_client:
                await self.connect_ssh()
            
            try:
                if uri == "ssh://system":
                    commands = [
                        "uname -a",
                        "cat /etc/os-release | head -5",
                        "uptime",
                        "whoami",
                        "pwd"
                    ]
                    result = "🖥️ System Information:\n\n"
                    for cmd in commands:
                        output, status, security_flags = await self.execute_command(cmd)
                        result += f"$ {cmd}\n{output}\n\n"
                    return result
                
                elif uri == "ssh://processes":
                    output, status, security_flags = await self.execute_command("ps aux | head -20")
                    return f"🔄 Running Processes (Top 20):\n\n{output}"
                
                elif uri == "ssh://disk":
                    commands = ["df -h", "lsblk"]
                    result = "💾 Disk Information:\n\n"
                    for cmd in commands:
                        output, status, security_flags = await self.execute_command(cmd)
                        result += f"$ {cmd}\n{output}\n\n"
                    return result
                
                elif uri == "ssh://network":
                    commands = ["ip addr show", "ss -tuln | head -10"]
                    result = "🌐 Network Information:\n\n"
                    for cmd in commands:
                        output, status, security_flags = await self.execute_command(cmd)
                        result += f"$ {cmd}\n{output}\n\n"
                    return result
                
                elif uri == "ssh://logs":
                    commands = [
                        "tail -20 /var/log/syslog 2>/dev/null || tail -20 /var/log/messages 2>/dev/null || echo 'No system logs accessible'",
                        "dmesg | tail -10"
                    ]
                    result = "📋 System Logs:\n\n"
                    for cmd in commands:
                        output, status, security_flags = await self.execute_command(cmd)
                        result += f"$ {cmd}\n{output}\n\n"
                    return result
                
                return "Resource not found"
                
            except Exception as e:
                logger.error(f"Error reading resource {uri}: {e}")
                return f"Error reading resource: {str(e)}"
        
        @self.server.list_tools()
        async def list_tools() -> List[Tool]:
            """List available tools"""
            return [
                Tool(
                    name="execute_command",
                    description="Execute shell command on remote server",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "command": {
                                "type": "string",
                                "description": "Shell command to execute"
                            },
                            "timeout": {
                                "type": "integer",
                                "description": f"Command timeout in seconds (default: {DEFAULT_COMMAND_TIMEOUT})",
                                "default": DEFAULT_COMMAND_TIMEOUT
                            }
                        },
                        "required": ["command"]
                    }
                ),
                Tool(
                    name="file_operations",
                    description="File operations (read, write, list directory)",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "operation": {
                                "type": "string",
                                "enum": ["read", "write", "list", "exists"],
                                "description": "File operation to perform"
                            },
                            "path": {
                                "type": "string",
                                "description": "File or directory path"
                            },
                            "content": {
                                "type": "string",
                                "description": "Content to write (for write operation)"
                            },
                            "limit": {
                                "type": "integer",
                                "description": f"Limit lines for read operation (default: {DEFAULT_FILE_READ_LIMIT})",
                                "default": DEFAULT_FILE_READ_LIMIT
                            }
                        },
                        "required": ["operation", "path"]
                    }
                ),
                Tool(
                    name="system_monitor",
                    description="Monitor system resources (CPU, memory, disk)",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "metric": {
                                "type": "string",
                                "enum": ["cpu", "memory", "disk", "network", "all"],
                                "description": "System metric to monitor"
                            },
                            "detailed": {
                                "type": "boolean",
                                "description": "Show detailed information",
                                "default": False
                            }
                        },
                        "required": ["metric"]
                    }
                ),
                Tool(
                    name="process_manager",
                    description="Manage processes (list, kill, status)",
                    inputSchema={
                        "type": "object", 
                        "properties": {
                            "action": {
                                "type": "string",
                                "enum": ["list", "kill", "status", "search"],
                                "description": "Process management action"
                            },
                            "target": {
                                "type": "string",
                                "description": "Process name, PID, or search term"
                            },
                            "signal": {
                                "type": "string",
                                "description": "Signal to send (for kill action)",
                                "default": "TERM"
                            }
                        },
                        "required": ["action"]
                    }
                ),
                Tool(
                    name="ssh_reconnect",
                    description="Reconnect to SSH server (force reconnection)",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "force": {
                                "type": "boolean",
                                "description": "Force reconnection even if connection appears healthy",
                                "default": False
                            }
                        }
                    }
                )
            ]
        
        @self.server.call_tool()
        async def call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
            """Handle tool calls"""
            if not self.ssh_client:
                await self.connect_ssh()
            
            try:
                if name == "execute_command":
                    return await self.handle_execute_command(arguments)
                
                elif name == "file_operations":
                    return await self.handle_file_operations(arguments)
                
                elif name == "system_monitor":
                    return await self.handle_system_monitor(arguments)
                
                elif name == "process_manager":
                    return await self.handle_process_manager(arguments)
                
                elif name == "ssh_reconnect":
                    return await self.handle_ssh_reconnect(arguments)
                
                else:
                    return [TextContent(type="text", text=f"Unknown tool: {name}")]
                    
            except Exception as e:
                logger.error(f"Error in tool call {name}: {e}")
                return [TextContent(type="text", text=f"Error: {str(e)}")]
    
    def _get_connection_params(self) -> dict:
        """Get SSH connection parameters (cached) with validation"""
        if self._connection_params is None:
            # Validate and parse port number
            try:
                port = int(os.getenv("SSH_PORT", str(DEFAULT_SSH_PORT)))
                if not (MIN_PORT_NUMBER <= port <= MAX_PORT_NUMBER):
                    logger.warning(f"Invalid SSH_PORT value: {port}. Using default {DEFAULT_SSH_PORT}.")
                    port = DEFAULT_SSH_PORT
            except ValueError:
                logger.warning(f"Invalid SSH_PORT value: {os.getenv('SSH_PORT')}. Using default {DEFAULT_SSH_PORT}.")
                port = DEFAULT_SSH_PORT
            
            # Validate and parse timeout
            try:
                timeout = int(os.getenv("SSH_TIMEOUT", str(DEFAULT_SSH_TIMEOUT)))
                if timeout <= 0:
                    logger.warning(f"Invalid SSH_TIMEOUT value: {timeout}. Using default {DEFAULT_SSH_TIMEOUT}.")
                    timeout = DEFAULT_SSH_TIMEOUT
            except ValueError:
                logger.warning(f"Invalid SSH_TIMEOUT value: {os.getenv('SSH_TIMEOUT')}. Using default {DEFAULT_SSH_TIMEOUT}.")
                timeout = DEFAULT_SSH_TIMEOUT
            
            host = os.getenv("SSH_HOST", "localhost").strip()
            if not host:
                logger.warning("Empty SSH_HOST value. Using default 'localhost'.")
                host = "localhost"
            
            # Keepalive settings
            try:
                keepalive_interval = int(os.getenv("SSH_KEEPALIVE_INTERVAL", "30"))
                if keepalive_interval <= 0:
                    keepalive_interval = 30
            except ValueError:
                keepalive_interval = 30
            
            try:
                keepalive_count_max = int(os.getenv("SSH_KEEPALIVE_COUNT_MAX", "3"))
                if keepalive_count_max <= 0:
                    keepalive_count_max = 3
            except ValueError:
                keepalive_count_max = 3
            
            try:
                banner_timeout = int(os.getenv("SSH_BANNER_TIMEOUT", "30"))
                if banner_timeout <= 0:
                    banner_timeout = 30
            except ValueError:
                banner_timeout = 30
            
            try:
                auth_timeout = int(os.getenv("SSH_AUTH_TIMEOUT", "30"))
                if auth_timeout <= 0:
                    auth_timeout = 30
            except ValueError:
                auth_timeout = 30

            self._connection_params = {
                "host": host,
                "port": port,
                "username": os.getenv("SSH_USER", "root"),
                "password": os.getenv("SSH_PASSWORD", ""),
                "timeout": timeout,
                "keepalive_interval": keepalive_interval,
                "keepalive_count_max": keepalive_count_max,
                "banner_timeout": banner_timeout,
                "auth_timeout": auth_timeout
            }
        return self._connection_params
    
    def _close_ssh_connection(self):
        """Safely close SSH connection"""
        if self.ssh_client:
            try:
                self.ssh_client.close()
            except Exception as e:
                logger.debug(f"Error while closing SSH connection: {e}")
            finally:
                self.ssh_client = None
    
    def _get_connection_string(self) -> str:
        """Get formatted connection string for display"""
        params = self._get_connection_params()
        return f"{params['username']}@{params['host']}:{params['port']}"
    
    def is_connection_alive(self) -> bool:
        """Check if SSH connection is still alive"""
        if not self.ssh_client:
            return False
        
        try:
            # Check if transport is active
            transport = self.ssh_client.get_transport()
            if not transport or not transport.is_active():
                return False
            
            # Try a lightweight test command
            stdin, stdout, stderr = self.ssh_client.exec_command("echo connection_test", timeout=CONNECTION_TEST_TIMEOUT)
            output = stdout.read().decode().strip()
            
            # Update last check time
            self.last_connection_check = time.time()
            
            return output == "connection_test"
        except Exception as e:
            logger.warning(f"Connection health check failed: {e}")
            return False
    
    async def ensure_connection(self):
        """Ensure SSH connection is alive, reconnect if necessary"""
        if not self.is_connection_alive():
            logger.info("SSH connection lost, attempting to reconnect...")
            self._close_ssh_connection()
            await self.connect_ssh()
    
    async def connect_ssh(self):
        """Connect to SSH server"""
        try:
            params = self._get_connection_params()
            host = params["host"]
            port = params["port"]
            username = params["username"]
            password = params["password"]
            timeout = params["timeout"]
            keepalive_interval = params["keepalive_interval"]
            banner_timeout = params["banner_timeout"]
            auth_timeout = params["auth_timeout"]
            
            self.ssh_client = paramiko.SSHClient()
            # Load system host keys for security
            self.ssh_client.load_system_host_keys()
            # Use WarningPolicy instead of AutoAddPolicy for better security
            # This will warn about unknown hosts but still allow connection
            # For production, consider using RejectPolicy with proper known_hosts management
            self.ssh_client.set_missing_host_key_policy(paramiko.WarningPolicy())
            
            self.ssh_client.connect(
                hostname=host,
                port=port,
                username=username,
                password=password,
                timeout=timeout,
                banner_timeout=banner_timeout,
                auth_timeout=auth_timeout
            )
            
            # Enable keepalive to prevent connection timeout
            transport = self.ssh_client.get_transport()
            if transport:
                transport.set_keepalive(keepalive_interval)
                logger.info(f"SSH keepalive enabled with {keepalive_interval}s interval")
            
            connection_string = f"{username}@{host}:{port}"
            logger.info(f"Successfully connected to SSH server: {connection_string}")
            
            # Start keepalive background task if not already running
            if self._keepalive_task is None:
                await self.start_keepalive_task()
            
            # Reset failure count and log successful connection
            self.connection_failures = 0
            self.activity_logger.log_event(
                event_type="connection_established",
                command="ssh_connect",
                response=f"Connected to {connection_string}",
                execution_time=0,
                status="success"
            )
            
        except Exception as e:
            self.connection_failures += 1
            logger.error(f"Failed to connect to SSH server: {e}")
            
            # Log connection failure
            self.activity_logger.log_event(
                event_type="connection_failed",
                command="ssh_connect", 
                response=f"Connection failed: {str(e)}",
                execution_time=0,
                status="error",
                error_message=str(e)
            )
            raise
    
    async def start_keepalive_task(self):
        """Start background keepalive task"""
        if self._keepalive_task is None:
            self._keepalive_task = asyncio.create_task(self._keepalive_worker())
            logger.info("SSH keepalive background task started")
    
    async def stop_keepalive_task(self):
        """Stop background keepalive task"""
        self._running = False
        if self._keepalive_task:
            self._keepalive_task.cancel()
            try:
                await self._keepalive_task
            except asyncio.CancelledError:
                pass
            self._keepalive_task = None
            logger.info("SSH keepalive background task stopped")
    
    async def _keepalive_worker(self):
        """Background worker to maintain SSH connection"""
        params = self._get_connection_params()
        check_interval = params["keepalive_interval"] * 2  # Check twice as often as keepalive
        
        while self._running:
            try:
                await asyncio.sleep(check_interval)
                if not self._running:
                    break
                
                # Check connection health
                if not self.is_connection_alive():
                    logger.info("Keepalive task detected dead connection, reconnecting...")
                    try:
                        await self.connect_ssh()
                    except Exception as e:
                        logger.error(f"Keepalive reconnection failed: {e}")
                        
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Keepalive worker error: {e}")
                await asyncio.sleep(5)  # Brief pause before retrying
    
    async def execute_command(self, command: str, timeout: int = DEFAULT_COMMAND_TIMEOUT) -> tuple[str, str, list[str]]:
        """Execute command on remote server
        
        Returns:
            tuple: (output, status, security_flags)
        """
        # Ensure we have a healthy connection and log connection status
        connection_was_healthy = self.is_connection_alive()
        await self.ensure_connection()
        
        # Log reconnection if connection was restored
        if not connection_was_healthy and self.is_connection_alive():
            self.activity_logger.log_event(
                event_type="auto_reconnection",
                command="connection_check",
                response="SSH connection automatically restored before command execution",
                execution_time=0,
                status="success"
            )
        
        max_retries = MAX_RETRY_ATTEMPTS
        
        # Security check - prevent dangerous commands (only check once)
        if self.is_dangerous_command(command):
            return (
                f"❌ Command blocked for security reasons: {command}",
                "error",
                ["dangerous_command_blocked"]
            )
        
        last_error = None
        
        for attempt in range(max_retries + 1):
            try:
                stdin, stdout, stderr = self.ssh_client.exec_command(command, timeout=timeout)
                
                # Read output
                output = stdout.read().decode('utf-8', errors='ignore')
                error = stderr.read().decode('utf-8', errors='ignore')
                exit_code = stdout.channel.recv_exit_status()
                
                if exit_code != 0 and error:
                    return (
                        f"Command failed (exit code {exit_code}):\n{error}",
                        "error",
                        []
                    )
                
                return (
                    output if output else "(no output)",
                    "success",
                    []
                )
                
            except (paramiko.SSHException, ConnectionError, OSError) as e:
                last_error = e
                logger.warning(f"SSH connection error (attempt {attempt + 1}/{max_retries + 1}): {e}")
                
                # If this is the last attempt, don't try to reconnect
                if attempt >= max_retries:
                    break
                    
                logger.info("Attempting to reconnect...")
                try:
                    self._close_ssh_connection()
                    await self.connect_ssh()
                    # Small delay before retry
                    await asyncio.sleep(RETRY_DELAY_SECONDS)
                except (paramiko.SSHException, ConnectionError, OSError) as reconnect_error:
                    logger.error(f"Reconnection failed: {reconnect_error}")
                    # Continue to next attempt
                    continue
                    
            except Exception as e:
                # Non-connection errors (command errors, etc.) - don't retry
                logger.error(f"Error executing command '{command}': {e}")
                return (
                    f"Error executing command: {str(e)}",
                    "error",
                    []
                )
        
        # All retries failed
        error_msg = str(last_error) if last_error else "Unknown connection error"
        return (
            f"Connection failed after {max_retries + 1} attempts: {error_msg}",
            "connection_error", 
            ["connection_failed", f"max_attempts_{max_retries + 1}"]
        )
    
    def is_dangerous_command(self, command: str) -> bool:
        """Check if command is potentially dangerous"""
        dangerous_patterns = [
            r'\brm\s+-rf\s+/',
            r'\bformat\b',
            r'\bmkfs\b',
            r'\bdd\s+.*of=/dev/',
            r'\b:\(\)\{.*\}',  # Fork bomb
            r'sudo\s+passwd',
            r'userdel\s+',
            r'deluser\s+',
            r'shutdown\s+',
            r'reboot\s+',
            r'halt\s+',
            r'poweroff\s+',
            r'init\s+0',
            r'init\s+6'
        ]
        
        command_lower = command.lower()
        for pattern in dangerous_patterns:
            if re.search(pattern, command_lower):
                return True
        return False
    
    async def handle_execute_command(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """Handle execute_command tool"""
        command = arguments["command"]
        timeout = arguments.get("timeout", DEFAULT_COMMAND_TIMEOUT)
        
        start_time = time.time()
        output, status, security_flags = await self.execute_command(command, timeout)
        execution_time = (time.time() - start_time) * 1000  # Convert to milliseconds
        
        # Set error message for failed commands
        error_message = output if status in ["error", "connection_error"] else None
        
        # Log the activity
        self.activity_logger.log_command_execution(
            command=command,
            arguments=arguments,
            response=output,
            execution_time=execution_time,
            status=status,
            error_message=error_message,
            security_flags=security_flags
        )
        
        # Format result based on status
        result = f"🖥️ Command: {command}\n"
        result += f"⏱️ Execution time: {execution_time/1000:.2f}s\n"
        
        if status == "connection_error":
            result += f"🔌 Connection Status: ⚠️ Connection issues detected\n"
            # Extract attempt count from security flags (simplified)
            attempt_flags = [flag for flag in security_flags if flag.startswith("max_attempts_")]
            if attempt_flags:
                attempts = attempt_flags[0].split("_")[-1]
                result += f"🔄 Connection failed after {attempts} retry attempts\n"
            else:
                result += f"🔄 Connection failed after multiple retry attempts\n"
        elif status == "error":
            result += f"❌ Command Status: Failed\n"
        else:
            result += f"✅ Command Status: Success\n"
            
        result += f"\nOutput:\n{output}"
        
        return [TextContent(type="text", text=result)]
    
    async def handle_file_operations(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """Handle file operations"""
        operation = arguments["operation"]
        path = arguments["path"]
        
        start_time = time.time()
        status = "success"
        error_message = None
        response = ""
        
        try:
            if operation == "read":
                limit = arguments.get("limit", DEFAULT_FILE_READ_LIMIT)
                if limit > 0:
                    cmd = f"head -n {limit} '{path}'"
                else:
                    cmd = f"cat '{path}'"
                output, cmd_status, cmd_flags = await self.execute_command(cmd)
                if cmd_status == "error":
                    status = "error"
                    error_message = output
                response = f"📄 File: {path}\n\n{output}"
                
            elif operation == "write":
                content = arguments.get("content", "")
                # Use SFTP for safe file writing to prevent command injection
                try:
                    with self.ssh_client.open_sftp() as sftp:
                        with sftp.open(path, 'w') as f:
                            f.write(content)
                    response = f"✅ File written: {path}"
                except Exception as e:
                    status = "error"
                    error_message = str(e)
                    response = f"❌ Failed to write file: {e}"
            
            elif operation == "list":
                cmd = f"ls -la '{path}'"
                output, cmd_status, cmd_flags = await self.execute_command(cmd)
                if cmd_status == "error":
                    status = "error"
                    error_message = output
                response = f"📁 Directory: {path}\n\n{output}"
            
            elif operation == "exists":
                cmd = f"test -e '{path}' && echo 'EXISTS' || echo 'NOT_EXISTS'"
                output, cmd_status, cmd_flags = await self.execute_command(cmd)
                if cmd_status == "error":
                    status = "error"
                    error_message = output
                exists = "EXISTS" in output
                response = f"📍 Path {path}: {'✅ EXISTS' if exists else '❌ NOT EXISTS'}"
            
        except Exception as e:
            status = "error"
            error_message = str(e)
            response = f"❌ File operation error: {str(e)}"
            
        # Log the activity
        execution_time = (time.time() - start_time) * 1000
        self.activity_logger.log_file_operation(
            operation=operation,
            path=path,
            arguments=arguments,
            response=response,
            execution_time=execution_time,
            status=status,
            error_message=error_message
        )
        
        return [TextContent(type="text", text=response)]
    
    async def handle_system_monitor(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """Handle system monitoring"""
        metric = arguments["metric"]
        detailed = arguments.get("detailed", False)
        
        try:
            if metric == "cpu" or metric == "all":
                if detailed:
                    cmd = "top -bn1 | head -20"
                else:
                    cmd = "top -bn1 | grep 'Cpu(s)' || grep -i cpu /proc/stat | head -1"
                cpu_output, _, _ = await self.execute_command(cmd)
                
            if metric == "memory" or metric == "all":
                cmd = "free -h"
                if detailed:
                    cmd += " && cat /proc/meminfo | head -10"
                mem_output, _, _ = await self.execute_command(cmd)
                
            if metric == "disk" or metric == "all":
                cmd = "df -h"
                if detailed:
                    cmd += " && iostat -x 1 1 2>/dev/null || echo 'iostat not available'"
                disk_output, _, _ = await self.execute_command(cmd)
                
            if metric == "network" or metric == "all":
                cmd = "ss -tuln | head -10"
                if detailed:
                    cmd += " && netstat -i 2>/dev/null || ip -s link"
                net_output, _, _ = await self.execute_command(cmd)
            
            # Format output
            result = f"📊 System Monitor - {metric.upper()}\n\n"
            
            if metric == "cpu" or metric == "all":
                result += f"🔧 CPU Usage:\n{cpu_output}\n\n"
            if metric == "memory" or metric == "all":
                result += f"💾 Memory Usage:\n{mem_output}\n\n"
            if metric == "disk" or metric == "all":
                result += f"💽 Disk Usage:\n{disk_output}\n\n"
            if metric == "network" or metric == "all":
                result += f"🌐 Network:\n{net_output}\n\n"
                
            return [TextContent(type="text", text=result)]
            
        except Exception as e:
            return [TextContent(type="text", text=f"❌ System monitor error: {str(e)}")]
    
    async def handle_ssh_reconnect(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """Handle SSH reconnection"""
        force = arguments.get("force", False)
        
        try:
            # Check current connection status
            connection_status = "🔴 Disconnected"
            connection_info = ""
            
            if self.ssh_client:
                if self.is_connection_alive():
                    connection_status = "🟢 Connected"
                    if not force:
                        connection_info = f"Current connection: {self._get_connection_string()}\n"
                        if self.last_connection_check:
                            last_check = time.time() - self.last_connection_check
                            connection_info += f"Last health check: {last_check:.1f}s ago\n\n"
                        
                        return [TextContent(type="text", text=f"✅ SSH Connection Status: {connection_status}\n\n{connection_info}Connection is healthy. Use 'force: true' to reconnect anyway.")]
                else:
                    connection_status = "🟡 Connection Lost"
            
            # Close existing connection if any
            self._close_ssh_connection()
            
            # Attempt reconnection
            await self.connect_ssh()
            
            # Verify new connection
            if self.is_connection_alive():
                connection_info = f"✅ Successfully reconnected to: {self._get_connection_string()}\n"
                connection_info += f"Connection health verified\n"
                
                # Log reconnection event
                self.activity_logger.log_event(
                    event_type="reconnection",
                    command="ssh_reconnect",
                    response="SSH connection restored",
                    execution_time=0,
                    status="success"
                )
                
                return [TextContent(type="text", text=f"🔄 SSH Reconnection Complete\n\n{connection_info}")]
            else:
                return [TextContent(type="text", text="❌ Reconnection failed - connection health check failed")]
                
        except Exception as e:
            error_msg = f"❌ Reconnection failed: {str(e)}"
            logger.error(f"SSH reconnection error: {e}")
            
            # Log failed reconnection
            self.activity_logger.log_event(
                event_type="reconnection_failed", 
                command="ssh_reconnect",
                response=error_msg,
                execution_time=0,
                status="error",
                error_message=str(e)
            )
            
            return [TextContent(type="text", text=error_msg)]
    
    async def handle_process_manager(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """Handle process management"""
        action = arguments["action"]
        target = arguments.get("target", "")
        signal = arguments.get("signal", "TERM")
        
        try:
            if action == "list":
                cmd = "ps aux | head -20"
                if target:
                    cmd = f"ps aux | grep {quote(target)} | grep -v grep"
                output, _, _ = await self.execute_command(cmd)
                return [TextContent(type="text", text=f"🔄 Processes:\n\n{output}")]
            
            elif action == "search":
                if not target:
                    return [TextContent(type="text", text="❌ Search target required")]
                cmd = f"ps aux | grep {quote(target)} | grep -v grep"
                output, _, _ = await self.execute_command(cmd)
                return [TextContent(type="text", text=f"🔍 Search '{target}':\n\n{output}")]
            
            elif action == "status":
                if not target:
                    return [TextContent(type="text", text="❌ Process name/PID required")]
                # For numeric PID, use directly; for process name, use quote()
                if target.isdigit():
                    cmd = f"ps -p {target} 2>/dev/null"
                else:
                    cmd = f"ps aux | grep {quote(target)} | grep -v grep"
                output, _, _ = await self.execute_command(cmd)
                return [TextContent(type="text", text=f"📋 Process Status '{target}':\n\n{output}")]
            
            elif action == "kill":
                if not target:
                    return [TextContent(type="text", text="❌ Process PID required for kill")]
                # Safety check - only allow numeric PIDs
                if not target.isdigit():
                    return [TextContent(type="text", text="❌ Only numeric PIDs allowed for kill operation")]
                cmd = f"kill -{signal} {target}"
                output, _, _ = await self.execute_command(cmd)
                return [TextContent(type="text", text=f"⚡ Kill signal {signal} sent to PID {target}\n{output}")]
            
        except Exception as e:
            return [TextContent(type="text", text=f"❌ Process manager error: {str(e)}")]

async def main():
    """Main function to run the MCP server"""
    ssh_server = SSHMCPServer()
    
    try:
        async with stdio_server() as (read_stream, write_stream):
            await ssh_server.server.run(
                read_stream,
                write_stream,
                ssh_server.server.create_initialization_options()
            )
    finally:
        # Stop keepalive task and log session end
        await ssh_server.stop_keepalive_task()
        log_session_end()

if __name__ == "__main__":
    asyncio.run(main())