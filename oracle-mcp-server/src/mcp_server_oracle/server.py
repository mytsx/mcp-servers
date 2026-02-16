#!/usr/bin/env python3
"""
Oracle MCP Server for Claude Desktop
Natural language queries to Oracle database
"""

import asyncio
import os
import sys
import logging
import time
from typing import Any, List, Dict
import oracledb
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    Resource,
    Tool,
    TextContent,
    ImageContent,
    EmbeddedResource,
    LoggingLevel
)
from dotenv import load_dotenv

# Optional logging support
try:
    import sys
    parent_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    sys.path.insert(0, parent_dir)
    from shared_logger import direct_log_query_execution
    LOGGING_ENABLED = True
except ImportError:
    LOGGING_ENABLED = False
    def direct_log_query_execution(*args, **kwargs):
        """Stub function when logging is not available"""
        pass

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class OracleMCPServer:
    # Keywords that indicate a write/modify operation
    WRITE_KEYWORDS = frozenset([
        "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE",
        "TRUNCATE", "MERGE", "GRANT", "REVOKE",
    ])

    def __init__(self):
        self.server = Server("oracle-mcp-server")
        self.connection = None
        self.oracle_version = "Oracle"
        self.read_only = os.getenv("READ_ONLY", "").lower() in ("true", "1", "yes")
        self.dbms_output_enabled = False
        self.last_dbms_output_check = 0
        self.dbms_output_check_interval = 60  # Check every 60 seconds
        if self.read_only:
            logger.info("Read-only mode enabled - write queries will be blocked")
        self.setup_handlers()
        
    def setup_handlers(self):
        """Setup MCP server handlers"""
        
        @self.server.list_resources()
        async def list_resources() -> List[Resource]:
            """List available database resources"""
            return [
                Resource(
                    uri="oracle://tables",
                    name="Database Tables",
                    description=f"List all tables in the {self.oracle_version} database using USER_TABLES view",
                    mimeType="application/json"
                ),
                Resource(
                    uri="oracle://schema",
                    name="Database Schema",
                    description=f"Get {self.oracle_version} database schema information from USER_TAB_COLUMNS",
                    mimeType="application/json"
                ),
                Resource(
                    uri="oracle://stats",
                    name="Database Statistics",
                    description=f"Get {self.oracle_version} database statistics and version info",
                    mimeType="application/json"
                )
            ]
        
        @self.server.read_resource()
        async def read_resource(uri: str) -> str:
            """Read database resource"""
            if not self.connection:
                await self.connect_to_oracle()
                
            cursor = self.connection.cursor()
            
            if uri == "oracle://tables":
                cursor.execute("""
                    SELECT table_name, tablespace_name, status 
                    FROM user_tables 
                    ORDER BY table_name
                """)
                tables = cursor.fetchall()
                return f"Database Tables:\n" + "\n".join([f"- {table[0]} (Status: {table[2]})" for table in tables])
                
            elif uri == "oracle://schema":
                # Get table schemas
                cursor.execute("""
                    SELECT table_name FROM user_tables ORDER BY table_name
                """)
                tables = [row[0] for row in cursor.fetchall()]
                
                schema_info = f"{self.oracle_version} Database Schema:\n\n"
                for table in tables[:10]:  # Limit to first 10 tables
                    cursor.execute(f"""
                        SELECT column_name, data_type, nullable, data_default
                        FROM user_tab_columns 
                        WHERE table_name = '{table}'
                        ORDER BY column_id
                    """)
                    columns = cursor.fetchall()
                    schema_info += f"\n📋 Table: {table}\n"
                    for col in columns:
                        nullable = "NULL" if col[2] == "Y" else "NOT NULL"
                        default = f" DEFAULT {col[3]}" if col[3] else ""
                        schema_info += f"  - {col[0]}: {col[1]} {nullable}{default}\n"
                
                cursor.close()
                return schema_info
            
            elif uri == "oracle://stats":
                # Database statistics
                cursor.execute("""
                    SELECT 
                        sys_context('userenv','db_name') as database_name,
                        user as current_user,
                        version
                    FROM v$instance
                """)
                info = cursor.fetchone()
                
                cursor.execute("""
                    SELECT COUNT(*) as table_count FROM user_tables
                """)
                table_count = cursor.fetchone()
                
                cursor.execute("""
                    SELECT bytes/1024/1024 as size_mb
                    FROM user_segments 
                    WHERE segment_type = 'TABLE'
                    AND rownum = 1
                """)
                size_info = cursor.fetchone()
                
                result = f"{self.oracle_version} Database Information:\n\n"
                result += f"• Database: {info[0]}\n"
                result += f"• Current User: {info[1]}\n"
                result += f"• Oracle Version: {info[2]}\n"
                result += f"• Total Tables: {table_count[0]}\n"
                if size_info:
                    result += f"• Sample Table Size: {size_info[0]:.2f} MB\n"
                
                cursor.close()
                return result
            
            cursor.close()
            return "Resource not found"
        
        @self.server.list_tools()
        async def list_tools() -> List[Tool]:
            """List available tools"""
            return [
                Tool(
                    name="execute_sql",
                    description=f"Execute direct SQL query on {self.oracle_version} database. Use Oracle-specific views like USER_TABLES, ALL_TABLES, DBA_TABLES, USER_TAB_COLUMNS, etc.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "sql": {
                                "type": "string",
                                "description": "Oracle SQL query (e.g., SELECT * FROM USER_TABLES, not information_schema)"
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Maximum number of rows to return (default: 100)",
                                "default": 100
                            }
                        },
                        "required": ["sql"]
                    }
                ),
                Tool(
                    name="describe_table",
                    description="Get detailed information about a specific Oracle table using USER_TAB_COLUMNS",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "table_name": {
                                "type": "string",
                                "description": "Name of the Oracle table to describe (UPPERCASE)"
                            }
                        },
                        "required": ["table_name"]
                    }
                ),
                Tool(
                    name="get_source_code",
                    description="Get source code of Oracle objects (FUNCTION, PROCEDURE, TRIGGER, PACKAGE, PACKAGE BODY)",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "object_name": {
                                "type": "string",
                                "description": "Name of the object (case-insensitive)"
                            },
                            "object_type": {
                                "type": "string",
                                "description": "Type: FUNCTION, PROCEDURE, TRIGGER, PACKAGE, PACKAGE BODY (optional - will search all types if not specified)"
                            }
                        },
                        "required": ["object_name"]
                    }
                ),
                Tool(
                    name="get_view_definition",
                    description="Get view definition and metadata",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "view_name": {
                                "type": "string",
                                "description": "Name of the view (case-insensitive)"
                            }
                        },
                        "required": ["view_name"]
                    }
                ),
                Tool(
                    name="search_tables",
                    description="Search tables by name pattern",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "pattern": {
                                "type": "string",
                                "description": "Search pattern (supports % wildcard)"
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Maximum number of results (default: 100)",
                                "default": 100
                            }
                        },
                        "required": ["pattern"]
                    }
                ),
                Tool(
                    name="search_columns",
                    description="Search for columns across all tables",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "pattern": {
                                "type": "string",
                                "description": "Column name pattern (supports % wildcard)"
                            },
                            "data_type": {
                                "type": "string",
                                "description": "Filter by data type (optional)"
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Maximum number of results (default: 100)",
                                "default": 100
                            }
                        },
                        "required": ["pattern"]
                    }
                ),
                Tool(
                    name="get_table_indexes",
                    description="Get all indexes for a table",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "table_name": {
                                "type": "string",
                                "description": "Table name (case-insensitive)"
                            }
                        },
                        "required": ["table_name"]
                    }
                ),
                Tool(
                    name="get_table_constraints",
                    description="Get constraints (PK, FK, Check, Unique) for a table",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "table_name": {
                                "type": "string",
                                "description": "Table name (case-insensitive)"
                            },
                            "constraint_type": {
                                "type": "string",
                                "description": "Filter by type: P (Primary), R (Foreign), C (Check), U (Unique) (optional)"
                            }
                        },
                        "required": ["table_name"]
                    }
                ),
                Tool(
                    name="analyze_table_size",
                    description="Analyze table size, row count, and statistics",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "table_name": {
                                "type": "string",
                                "description": "Table name (case-insensitive)"
                            }
                        },
                        "required": ["table_name"]
                    }
                ),
                Tool(
                    name="get_table_relationships",
                    description="Get foreign key relationships for a table",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "table_name": {
                                "type": "string",
                                "description": "Table name (case-insensitive)"
                            },
                            "direction": {
                                "type": "string",
                                "description": "Direction: incoming, outgoing, or both (default: both)",
                                "default": "both"
                            }
                        },
                        "required": ["table_name"]
                    }
                ),
                Tool(
                    name="list_database_objects",
                    description="List database objects by type",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "object_type": {
                                "type": "string",
                                "description": "Object type: TABLE, VIEW, FUNCTION, PROCEDURE, PACKAGE, TRIGGER, SEQUENCE, INDEX"
                            },
                            "pattern": {
                                "type": "string",
                                "description": "Name pattern filter (optional, supports % wildcard)"
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Maximum number of results (default: 100)",
                                "default": 100
                            }
                        },
                        "required": ["object_type"]
                    }
                ),
                Tool(
                    name="explain_plan",
                    description="Show the execution plan for a SQL query using EXPLAIN PLAN and DBMS_XPLAN",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "sql": {
                                "type": "string",
                                "description": "SQL query to explain"
                            },
                            "format": {
                                "type": "string",
                                "enum": ["typical", "basic", "all"],
                                "description": "Level of detail: basic, typical (default), or all",
                                "default": "typical"
                            }
                        },
                        "required": ["sql"]
                    }
                )
            ]

        @self.server.call_tool()
        async def call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
            """Handle tool calls"""
            if not self.connection:
                await self.connect_to_oracle()
            
            try:
                if name == "execute_sql":
                    return await self.handle_sql_query(arguments["sql"], arguments.get("limit", 100))
                
                elif name == "describe_table":
                    return await self.handle_describe_table(arguments["table_name"])
                
                elif name == "get_source_code":
                    return await self.handle_get_source_code(arguments["object_name"], arguments.get("object_type"))
                
                elif name == "get_view_definition":
                    return await self.handle_get_view_definition(arguments["view_name"])
                
                elif name == "search_tables":
                    return await self.handle_search_tables(arguments["pattern"], arguments.get("limit", 100))
                
                elif name == "search_columns":
                    return await self.handle_search_columns(arguments["pattern"], arguments.get("data_type"), arguments.get("limit", 100))
                
                elif name == "get_table_indexes":
                    return await self.handle_get_table_indexes(arguments["table_name"])
                
                elif name == "get_table_constraints":
                    return await self.handle_get_table_constraints(arguments["table_name"], arguments.get("constraint_type"))
                
                elif name == "analyze_table_size":
                    return await self.handle_analyze_table_size(arguments["table_name"])
                
                elif name == "get_table_relationships":
                    return await self.handle_get_table_relationships(arguments["table_name"], arguments.get("direction", "both"))
                
                elif name == "list_database_objects":
                    return await self.handle_list_database_objects(arguments["object_type"], arguments.get("pattern"), arguments.get("limit", 100))

                elif name == "explain_plan":
                    return await self.handle_explain_plan(arguments["sql"], arguments.get("format", "typical"))

                else:
                    return [TextContent(type="text", text=f"Unknown tool: {name}")]
                    
            except Exception as e:
                logger.error(f"Error in tool call: {e}")
                return [TextContent(type="text", text=f"Error: {str(e)}")]
    
    async def connect_to_oracle(self):
        """Connect to Oracle database"""
        try:
            connection_string = os.getenv("ORACLE_CONNECTION_STRING")
            if not connection_string:
                raise ValueError("ORACLE_CONNECTION_STRING not found in environment")
            
            # Parse connection string
            parts = connection_string.split(';')
            user_id = None
            password = None
            data_source = None
            
            for part in parts:
                if part.strip().startswith("User Id="):
                    user_id = part.split("=", 1)[1]
                elif part.strip().startswith("Password="):
                    password = part.split("=", 1)[1]
                elif part.strip().startswith("Data Source="):
                    data_source = part.split("=", 1)[1]
            
            if not all([user_id, password, data_source]):
                raise ValueError("Invalid connection string format")
            
            self.connection = oracledb.connect(user=user_id, password=password, dsn=data_source)
            logger.info("Successfully connected to Oracle database")

            # Detect Oracle version dynamically
            self._detect_oracle_version()

            # Enable DBMS_OUTPUT for this session
            self.enable_dbms_output()
            logger.info("DBMS_OUTPUT enabled for session")
            
        except Exception as e:
            logger.error(f"Failed to connect to Oracle: {e}")
            raise
    
    def _is_write_query(self, sql: str) -> bool:
        """Check if a SQL query is a write/modify operation"""
        cleaned = sql.strip()
        # Strip leading comments
        while cleaned.startswith("--") or cleaned.startswith("/*"):
            if cleaned.startswith("--"):
                cleaned = cleaned.split("\n", 1)[-1].strip()
            elif cleaned.startswith("/*"):
                end = cleaned.find("*/")
                cleaned = cleaned[end + 2:].strip() if end != -1 else cleaned
        first_word = cleaned.split()[0].upper() if cleaned.split() else ""
        return first_word in self.WRITE_KEYWORDS

    def _detect_oracle_version(self):
        """Detect Oracle version from V$INSTANCE"""
        version_suffix_map = {
            "19": "19c", "18": "18c", "12": "12c", "11": "11g",
            "10": "10g", "21": "21c", "23": "23ai",
        }
        try:
            cursor = self.connection.cursor()
            # Try version_full first (Oracle 18c+)
            try:
                cursor.execute("SELECT version_full FROM v$instance")
                row = cursor.fetchone()
                if row and row[0]:
                    full_ver = row[0]
                    major = full_ver.split('.')[0]
                    suffix = version_suffix_map.get(major, major)
                    self.oracle_version = f"Oracle {suffix}"
                    logger.info(f"Detected Oracle version: {self.oracle_version} (full: {full_ver})")
                    cursor.close()
                    return
            except oracledb.DatabaseError:
                pass  # version_full not available (pre-18c)

            # Fallback to version column
            cursor.execute("SELECT version FROM v$instance")
            row = cursor.fetchone()
            if row and row[0]:
                ver = row[0]
                major = ver.split('.')[0]
                suffix = version_suffix_map.get(major, major)
                self.oracle_version = f"Oracle {suffix}"
                logger.info(f"Detected Oracle version: {self.oracle_version} (version: {ver})")
            cursor.close()
        except Exception as e:
            logger.warning(f"Could not detect Oracle version, using default: {e}")

    def _extract_response_text(self, result: List[TextContent]) -> str:
        """Extract first 500 chars of response for logging"""
        if result and hasattr(result[0], 'text'):
            return result[0].text[:500]
        return ""
    
    def clear_dbms_output_buffer(self):
        """Clear any remaining content in DBMS_OUTPUT buffer"""
        try:
            cursor = self.connection.cursor()
            # First try to enable DBMS_OUTPUT in case it's disabled
            try:
                cursor.execute("BEGIN DBMS_OUTPUT.ENABLE(1000000); END;")
            except:
                pass  # Ignore if already enabled
            
            # Read and discard all remaining lines
            cleared_lines = 0
            while True:
                line = cursor.var(str)
                status = cursor.var(int)
                cursor.execute("""
                    BEGIN
                        DBMS_OUTPUT.GET_LINE(:line, :status);
                    END;
                """, line=line, status=status)
                
                if status.getvalue() != 0:  # No more lines
                    break
                cleared_lines += 1
                
                if cleared_lines > 10000:  # Safety limit
                    logger.warning("Cleared 10000+ lines from DBMS_OUTPUT buffer, stopping")
                    break
            
            cursor.close()
            if cleared_lines > 0:
                logger.info(f"Cleared {cleared_lines} old lines from DBMS_OUTPUT buffer")
        except Exception as e:
            logger.warning(f"Error clearing DBMS_OUTPUT buffer: {e}")
    
    def enable_dbms_output(self, buffer_size: int = 100000000, clear_first: bool = True):
        """Enable DBMS_OUTPUT with specified buffer size (default 100MB)"""
        try:
            # Clear old buffer content first if requested
            if clear_first:
                self.clear_dbms_output_buffer()
            
            cursor = self.connection.cursor()
            
            # Check Oracle compatibility for unlimited buffer support
            # Oracle 10g R2+ (10.2+) supports NULL for unlimited buffer
            # Compatible parameter should be 10.2.0 or higher
            if buffer_size is None:
                cursor.execute("BEGIN DBMS_OUTPUT.ENABLE(NULL); END;")
                logger.info("DBMS_OUTPUT enabled with UNLIMITED buffer size")
            else:
                cursor.execute(f"BEGIN DBMS_OUTPUT.ENABLE({buffer_size}); END;")
                logger.info(f"DBMS_OUTPUT enabled with buffer size {buffer_size:,} bytes ({buffer_size/1024/1024:.1f} MB)")
            cursor.close()
            self.dbms_output_enabled = True
            self.last_dbms_output_check = time.time()
        except Exception as e:
            logger.error(f"Failed to enable DBMS_OUTPUT: {e}")
            self.dbms_output_enabled = False
    
    def check_and_reenable_dbms_output(self, force_check=False):
        """Check if DBMS_OUTPUT needs to be re-enabled"""
        current_time = time.time()
        
        # Check if we should perform the check
        should_check = force_check or (current_time - self.last_dbms_output_check > self.dbms_output_check_interval)
        
        if should_check:
            try:
                # Test if DBMS_OUTPUT is still working
                cursor = self.connection.cursor()
                cursor.execute("BEGIN DBMS_OUTPUT.PUT_LINE('TEST'); END;")
                cursor.close()
                
                # Try to get the test output
                test_output = self.get_dbms_output()
                
                # If we didn't get the test output, re-enable
                if 'TEST' not in test_output:
                    logger.info("DBMS_OUTPUT appears to be disabled, re-enabling...")
                    self.enable_dbms_output()  # Use default 100MB buffer
                    self.dbms_output_enabled = True
                else:
                    self.last_dbms_output_check = current_time
                    self.dbms_output_enabled = True
                    
            except Exception as e:
                logger.warning(f"Error checking DBMS_OUTPUT status: {e}")
                # Try to re-enable anyway
                self.enable_dbms_output()  # Use default 100MB buffer
                self.dbms_output_enabled = True
    
    def get_dbms_output(self) -> str:
        """Get DBMS_OUTPUT buffer contents"""
        try:
            cursor = self.connection.cursor()
            
            # Get output lines
            output_lines = []
            max_lines = 1000  # Prevent infinite loops
            
            # Simple DBMS_OUTPUT fetch
            line_count = 0
            while line_count < max_lines:
                line = cursor.var(str)
                status = cursor.var(int)
                
                cursor.execute("""
                    BEGIN
                        DBMS_OUTPUT.GET_LINE(:line, :status);
                    END;
                """, line=line, status=status)
                
                if status.getvalue() == 0:  # 0 means line was retrieved
                    output_lines.append(line.getvalue())
                    line_count += 1
                else:
                    break
            
            cursor.close()
            
            if line_count >= max_lines:
                output_lines.append(f"\n... (Output truncated at {max_lines} lines)")
            
            return '\n'.join(output_lines) if output_lines else ""
            
        except oracledb.DatabaseError as e:
            error_obj, = e.args
            if error_obj.code == 20000:  # ORU-10027: buffer overflow
                logger.warning("DBMS_OUTPUT buffer overflow detected, clearing and re-enabling")
                try:
                    # Clear the buffer and re-enable
                    cursor = self.connection.cursor()
                    cursor.execute("BEGIN DBMS_OUTPUT.DISABLE; END;")
                    cursor.close()
                    self.enable_dbms_output(None)  # Use unlimited buffer
                    return "⚠️ DBMS_OUTPUT buffer overflow - buffer cleared and set to UNLIMITED"
                except Exception as re_enable_error:
                    logger.error(f"Failed to re-enable DBMS_OUTPUT after overflow: {re_enable_error}")
            else:
                logger.warning(f"Database error getting DBMS_OUTPUT: {e}")
            return ""
        except Exception as e:
            logger.warning(f"Failed to get DBMS_OUTPUT: {e}")
            return ""

    async def handle_sql_query(self, sql: str, limit: int = 100) -> List[TextContent]:
        """Execute SQL query on Oracle database"""
        # Read-only guard
        if self.read_only and self._is_write_query(sql):
            return [TextContent(type="text", text="❌ Read-only mode is enabled. Write operations (INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, TRUNCATE, MERGE, GRANT, REVOKE) are blocked. Set READ_ONLY=false to allow write operations.")]

        start_time = time.time()

        # If query contains DBMS_OUTPUT.PUT_LINE, force check DBMS_OUTPUT status
        if 'DBMS_OUTPUT.PUT_LINE' in sql.upper():
            logger.info("DBMS_OUTPUT.PUT_LINE detected in query, forcing DBMS_OUTPUT check")
            self.check_and_reenable_dbms_output(force_check=True)
        else:
            # Regular periodic check
            self.check_and_reenable_dbms_output()
        
        cursor = self.connection.cursor()
        row_count = 0
        status = "success"
        error_message = ""
        result_text = ""
        
        try:
            # Clean SQL - remove comments and get first actual SQL command
            sql_lines = sql.strip().split('\n')
            clean_sql_lines = []
            for line in sql_lines:
                # Remove single line comments
                if '--' in line:
                    line = line[:line.index('--')]
                if line.strip():
                    clean_sql_lines.append(line)
            clean_sql = ' '.join(clean_sql_lines).strip()
            
            # Check if this is a SELECT query (including WITH clauses)
            is_select_query = (clean_sql.upper().startswith("SELECT") or 
                             clean_sql.upper().startswith("WITH"))
            
            # Add ROWNUM limit for SELECT queries if not already present
            if is_select_query and "ROWNUM" not in sql.upper() and "FETCH" not in sql.upper():
                # Oracle 19c also supports FETCH FIRST syntax
                sql += f" FETCH FIRST {limit} ROWS ONLY"
            
            cursor.execute(sql)
            
            if is_select_query:
                # Get column names
                columns = [desc[0] for desc in cursor.description]
                rows = cursor.fetchall()
                row_count = len(rows)
                
                if not rows:
                    result_text = "Sorgu sonuç döndürmedi."
                else:
                    # Format results
                    result = f"📊 Results ({len(rows)} rows):\n"
                    result += "=" * 60 + "\n"
                    
                    # Add column headers
                    result += " | ".join(columns) + "\n"
                    result += "-" * 60 + "\n"
                    
                    # Add data rows
                    for row in rows:
                        row_data = []
                        for val in row:
                            str_val = str(val) if val is not None else "NULL"
                            # Don't truncate, just format for display
                            row_data.append(str(str_val))
                        result += " | ".join(row_data) + "\n"
                    
                    result_text = result
                
                return [TextContent(type="text", text=result_text)]
            else:
                # For non-SELECT queries
                self.connection.commit()
                
                # Check if this was a PL/SQL block and try to get DBMS_OUTPUT
                if any(keyword in clean_sql.upper() for keyword in ['BEGIN', 'DECLARE', 'CREATE OR REPLACE']):
                    # If SQL contains DBMS_OUTPUT.PUT_LINE, always enable DBMS_OUTPUT first
                    if 'DBMS_OUTPUT.PUT_LINE' in sql.upper():
                        logger.info("DBMS_OUTPUT.PUT_LINE detected, ensuring DBMS_OUTPUT is enabled")
                        # Enable DBMS_OUTPUT with buffer clearing
                        self.enable_dbms_output(clear_first=True)  # This will clear and enable
                    
                    # Get DBMS_OUTPUT content
                    dbms_output = self.get_dbms_output()
                    
                    # If we expected output but didn't get any, try harder
                    if not dbms_output and 'DBMS_OUTPUT.PUT_LINE' in sql.upper():
                        retry_count = 0
                        while not dbms_output and retry_count < 3:
                            logger.info(f"DBMS_OUTPUT retry attempt {retry_count + 1}")
                            # Re-enable with default buffer (don't clear again)
                            self.enable_dbms_output(clear_first=False)
                            # Small delay to let Oracle process
                            time.sleep(0.1)
                            dbms_output = self.get_dbms_output()
                            retry_count += 1
                    
                    if dbms_output:
                        result_text = f"✅ Query executed successfully\n\n📋 DBMS_OUTPUT:\n{dbms_output}"
                    else:
                        result_text = f"✅ Query executed successfully"
                else:
                    result_text = f"✅ Query executed successfully"
                
                return [TextContent(type="text", text=result_text)]
                
        except Exception as e:
            status = "error"
            error_message = str(e)
            result_text = f"❌ Oracle SQL Error: {str(e)}"
            return [TextContent(type="text", text=result_text)]
        finally:
            # Log the query execution
            execution_time = (time.time() - start_time) * 1000  # Convert to milliseconds
            # Direct logging to avoid async queue truncation
            direct_log_query_execution(
                server_type="oracle",
                tool_name="execute_sql",
                query_text=sql,
                execution_time_ms=execution_time,
                status=status,
                row_count=row_count,
                error_message=error_message,
                response_text=result_text
            )
            cursor.close()
    
    async def handle_describe_table(self, table_name: str) -> List[TextContent]:
        """Describe table structure"""
        cursor = self.connection.cursor()
        
        try:
            # Get table columns
            cursor.execute(f"""
                SELECT 
                    column_name,
                    data_type,
                    data_length,
                    nullable,
                    data_default,
                    column_id
                FROM user_tab_columns 
                WHERE table_name = UPPER('{table_name}')
                ORDER BY column_id
            """)
            
            columns = cursor.fetchall()
            
            if not columns:
                return [TextContent(type="text", text=f"Table '{table_name}' not found")]
            
            result = f"Table: {table_name.upper()}\n"
            result += "=" * 50 + "\n\n"
            
            for col in columns:
                nullable = "NULL" if col[3] == "Y" else "NOT NULL"
                default = f" DEFAULT {col[4]}" if col[4] else ""
                result += f"{col[0]}: {col[1]}({col[2]}) {nullable}{default}\n"
            
            # Get row count
            cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            row_count = cursor.fetchone()[0]
            result += f"\nTotal rows: {row_count}"
            
            return [TextContent(type="text", text=result)]
            
        except Exception as e:
            return [TextContent(type="text", text=f"Error describing table: {str(e)}")]
        finally:
            cursor.close()
    
    async def handle_get_source_code(self, object_name: str, object_type: str = None) -> List[TextContent]:
        """Get source code of Oracle objects"""
        start_time = time.time()
        cursor = self.connection.cursor()
        status = "success"
        error_message = ""
        
        try:
            object_name = object_name.upper()
            
            # If object_type is specified, search for specific type
            if object_type:
                object_type = object_type.upper()
                cursor.execute(f"""
                    SELECT text 
                    FROM user_source 
                    WHERE name = '{object_name}' 
                    AND type = '{object_type}'
                    ORDER BY line
                """)
            else:
                # Search in all object types
                cursor.execute(f"""
                    SELECT type, COUNT(*) 
                    FROM user_source 
                    WHERE name = '{object_name}'
                    GROUP BY type
                """)
                types_found = cursor.fetchall()
                
                if not types_found:
                    return [TextContent(type="text", text=f"Object '{object_name}' not found")]
                
                # If multiple types found, list them
                if len(types_found) > 1:
                    result = f"Multiple object types found for '{object_name}':\n"
                    for obj_type, _ in types_found:
                        result += f"- {obj_type}\n"
                    result += "\nPlease specify object_type parameter."
                    return [TextContent(type="text", text=result)]
                
                # Single type found, get its source
                object_type = types_found[0][0]
                cursor.execute(f"""
                    SELECT text 
                    FROM user_source 
                    WHERE name = '{object_name}' 
                    AND type = '{object_type}'
                    ORDER BY line
                """)
            
            lines = cursor.fetchall()
            
            if not lines:
                return [TextContent(type="text", text=f"No source code found for {object_type} '{object_name}'")]
            
            # Format source code with line numbers
            result = f"📄 {object_type}: {object_name}\n"
            result += "=" * 60 + "\n"
            
            for i, (line_text,) in enumerate(lines, 1):
                result += f"{i:4d}: {line_text}"
            
            return [TextContent(type="text", text=result)]
            
        except Exception as e:
            status = "error"
            error_message = str(e)
            return [TextContent(type="text", text=f"❌ Error getting source code: {str(e)}")]
        finally:
            execution_time = (time.time() - start_time) * 1000
            direct_log_query_execution(
                server_type="oracle",
                tool_name="get_source_code",
                query_text=f"GET SOURCE: {object_name} ({object_type or 'AUTO'})",
                execution_time_ms=execution_time,
                status=status,
                row_count=0,
                error_message=error_message
            )
            cursor.close()
    
    async def handle_get_view_definition(self, view_name: str) -> List[TextContent]:
        """Get view definition from USER_VIEWS"""
        start_time = time.time()
        cursor = self.connection.cursor()
        status = "success"
        error_message = ""
        
        try:
            view_name = view_name.upper()
            
            cursor.execute(f"""
                SELECT text, text_length, text_vc, type_text_length, type_text
                FROM user_views
                WHERE view_name = '{view_name}'
            """)
            
            result = cursor.fetchone()
            
            if not result:
                return [TextContent(type="text", text=f"View '{view_name}' not found")]
            
            text, text_length, text_vc, _, _ = result
            
            # Use appropriate text field based on length
            view_text = text if text else text_vc
            
            output = f"📄 VIEW: {view_name}\n"
            output += f"Text Length: {text_length}\n"
            output += "=" * 60 + "\n"
            output += view_text
            
            return [TextContent(type="text", text=output)]
            
        except Exception as e:
            status = "error"
            error_message = str(e)
            return [TextContent(type="text", text=f"❌ Error getting view definition: {str(e)}")]
        finally:
            execution_time = (time.time() - start_time) * 1000
            direct_log_query_execution(
                server_type="oracle",
                tool_name="get_view_definition",
                query_text=f"GET VIEW: {view_name}",
                execution_time_ms=execution_time,
                status=status,
                row_count=0,
                error_message=error_message
            )
            cursor.close()
    
    async def handle_search_tables(self, pattern: str, limit: int = 100) -> List[TextContent]:
        """Search tables by name pattern"""
        start_time = time.time()
        cursor = self.connection.cursor()
        status = "success"
        error_message = ""
        row_count = 0
        
        try:
            sql = f"""
                SELECT table_name, tablespace_name, status, num_rows
                FROM user_tables
                WHERE UPPER(table_name) LIKE UPPER('{pattern}')
                ORDER BY table_name
                FETCH FIRST {limit} ROWS ONLY
            """
            
            cursor.execute(sql)
            tables = cursor.fetchall()
            row_count = len(tables)
            
            if not tables:
                return [TextContent(type="text", text=f"No tables found matching pattern '{pattern}'")]
            
            result = f"📊 Tables matching '{pattern}' ({row_count} found):\n"
            result += "=" * 60 + "\n"
            result += "TABLE_NAME | TABLESPACE | STATUS | ROWS\n"
            result += "-" * 60 + "\n"
            
            for table_name, tablespace, status, num_rows in tables:
                rows_str = str(num_rows) if num_rows is not None else "N/A"
                result += f"{table_name} | {tablespace} | {status} | {rows_str}\n"
            
            return [TextContent(type="text", text=result)]
            
        except Exception as e:
            status = "error"
            error_message = str(e)
            return [TextContent(type="text", text=f"❌ Error searching tables: {str(e)}")]
        finally:
            execution_time = (time.time() - start_time) * 1000
            direct_log_query_execution(
                server_type="oracle",
                tool_name="search_tables",
                query_text=f"SEARCH TABLES: {pattern}",
                execution_time_ms=execution_time,
                status=status,
                row_count=row_count,
                error_message=error_message
            )
            cursor.close()
    
    async def handle_search_columns(self, pattern: str, data_type: str = None, limit: int = 100) -> List[TextContent]:
        """Search columns across all tables"""
        start_time = time.time()
        cursor = self.connection.cursor()
        status = "success"
        error_message = ""
        row_count = 0
        
        try:
            sql = f"""
                SELECT DISTINCT table_name, column_name, data_type, data_length
                FROM user_tab_columns
                WHERE UPPER(column_name) LIKE UPPER('{pattern}')
            """
            
            if data_type:
                sql += f" AND UPPER(data_type) = UPPER('{data_type}')"
            
            sql += f" ORDER BY table_name, column_name FETCH FIRST {limit} ROWS ONLY"
            
            cursor.execute(sql)
            columns = cursor.fetchall()
            row_count = len(columns)
            
            if not columns:
                return [TextContent(type="text", text=f"No columns found matching pattern '{pattern}'")]
            
            result = f"📊 Columns matching '{pattern}' ({row_count} found):\n"
            result += "=" * 60 + "\n"
            result += "TABLE_NAME | COLUMN_NAME | DATA_TYPE | LENGTH\n"
            result += "-" * 60 + "\n"
            
            for table_name, column_name, dtype, length in columns:
                result += f"{table_name} | {column_name} | {dtype} | {length}\n"
            
            return [TextContent(type="text", text=result)]
            
        except Exception as e:
            status = "error"
            error_message = str(e)
            return [TextContent(type="text", text=f"❌ Error searching columns: {str(e)}")]
        finally:
            execution_time = (time.time() - start_time) * 1000
            direct_log_query_execution(
                server_type="oracle",
                tool_name="search_columns",
                query_text=f"SEARCH COLUMNS: {pattern} ({data_type or 'ALL'})",
                execution_time_ms=execution_time,
                status=status,
                row_count=row_count,
                error_message=error_message
            )
            cursor.close()
    
    async def handle_get_table_indexes(self, table_name: str) -> List[TextContent]:
        """Get all indexes for a table"""
        start_time = time.time()
        cursor = self.connection.cursor()
        status = "success"
        error_message = ""
        row_count = 0
        
        try:
            table_name = table_name.upper()
            
            sql = f"""
                SELECT 
                    ui.index_name,
                    ui.index_type,
                    ui.uniqueness,
                    ui.status,
                    uic.column_name,
                    uic.column_position
                FROM user_indexes ui
                JOIN user_ind_columns uic ON ui.index_name = uic.index_name
                WHERE ui.table_name = '{table_name}'
                ORDER BY ui.index_name, uic.column_position
            """
            
            cursor.execute(sql)
            indexes = cursor.fetchall()
            row_count = len(indexes)
            
            if not indexes:
                return [TextContent(type="text", text=f"No indexes found for table '{table_name}'")]
            
            result = f"📊 Indexes for table '{table_name}':\n"
            result += "=" * 60 + "\n"
            
            current_index = None
            for index_name, index_type, uniqueness, status, column_name, position in indexes:
                if current_index != index_name:
                    if current_index:
                        result += "\n"
                    result += f"\n📌 {index_name}\n"
                    result += f"  Type: {index_type}, Unique: {uniqueness}, Status: {status}\n"
                    result += "  Columns: "
                    current_index = index_name
                
                if position > 1:
                    result += ", "
                result += column_name
            
            return [TextContent(type="text", text=result)]
            
        except Exception as e:
            status = "error"
            error_message = str(e)
            return [TextContent(type="text", text=f"❌ Error getting indexes: {str(e)}")]
        finally:
            execution_time = (time.time() - start_time) * 1000
            direct_log_query_execution(
                server_type="oracle",
                tool_name="get_table_indexes",
                query_text=f"GET INDEXES: {table_name}",
                execution_time_ms=execution_time,
                status=status,
                row_count=row_count,
                error_message=error_message
            )
            cursor.close()
    
    async def handle_get_table_constraints(self, table_name: str, constraint_type: str = None) -> List[TextContent]:
        """Get constraints for a table"""
        start_time = time.time()
        cursor = self.connection.cursor()
        status = "success"
        error_message = ""
        row_count = 0
        
        try:
            table_name = table_name.upper()
            
            sql = f"""
                SELECT 
                    uc.constraint_name,
                    uc.constraint_type,
                    uc.status,
                    uc.search_condition,
                    uc.r_constraint_name,
                    ucc.column_name,
                    ucc.position
                FROM user_constraints uc
                LEFT JOIN user_cons_columns ucc ON uc.constraint_name = ucc.constraint_name
                WHERE uc.table_name = '{table_name}'
            """
            
            if constraint_type:
                sql += f" AND uc.constraint_type = '{constraint_type.upper()}'"
            
            sql += " ORDER BY uc.constraint_type, uc.constraint_name, ucc.position"
            
            cursor.execute(sql)
            constraints = cursor.fetchall()
            row_count = len(constraints)
            
            if not constraints:
                return [TextContent(type="text", text=f"No constraints found for table '{table_name}'")]
            
            result = f"📊 Constraints for table '{table_name}':\n"
            result += "=" * 60 + "\n"
            
            constraint_types = {
                'P': 'Primary Key',
                'R': 'Foreign Key',
                'C': 'Check',
                'U': 'Unique'
            }
            
            current_constraint = None
            for con_name, con_type, status, search_cond, r_constraint, col_name, position in constraints:
                if current_constraint != con_name:
                    if current_constraint:
                        result += "\n"
                    result += f"\n📌 {con_name} ({constraint_types.get(con_type, con_type)})\n"
                    result += f"  Status: {status}\n"
                    if search_cond:
                        result += f"  Condition: {search_cond}\n"
                    if r_constraint:
                        result += f"  References: {r_constraint}\n"
                    if col_name:
                        result += "  Columns: "
                    current_constraint = con_name
                
                if col_name:
                    if position and position > 1:
                        result += ", "
                    result += col_name
            
            return [TextContent(type="text", text=result)]
            
        except Exception as e:
            status = "error"
            error_message = str(e)
            return [TextContent(type="text", text=f"❌ Error getting constraints: {str(e)}")]
        finally:
            execution_time = (time.time() - start_time) * 1000
            direct_log_query_execution(
                server_type="oracle",
                tool_name="get_table_constraints",
                query_text=f"GET CONSTRAINTS: {table_name} ({constraint_type or 'ALL'})",
                execution_time_ms=execution_time,
                status=status,
                row_count=row_count,
                error_message=error_message
            )
            cursor.close()
    
    async def handle_analyze_table_size(self, table_name: str) -> List[TextContent]:
        """Analyze table size and statistics"""
        start_time = time.time()
        cursor = self.connection.cursor()
        status = "success"
        error_message = ""
        
        try:
            table_name = table_name.upper()
            
            sql = f"""
                SELECT 
                    t.table_name,
                    t.num_rows,
                    t.avg_row_len,
                    t.blocks,
                    ROUND(s.bytes/1024/1024, 2) as size_mb,
                    t.last_analyzed,
                    COUNT(DISTINCT tc.column_name) as column_count
                FROM user_tables t
                LEFT JOIN user_segments s ON t.table_name = s.segment_name AND s.segment_type = 'TABLE'
                LEFT JOIN user_tab_columns tc ON t.table_name = tc.table_name
                WHERE t.table_name = '{table_name}'
                GROUP BY t.table_name, t.num_rows, t.avg_row_len, t.blocks, s.bytes, t.last_analyzed
            """
            
            cursor.execute(sql)
            result = cursor.fetchone()
            
            if not result:
                return [TextContent(type="text", text=f"Table '{table_name}' not found")]
            
            table_name, num_rows, avg_row_len, blocks, size_mb, last_analyzed, column_count = result
            
            output = f"📊 Table Analysis: {table_name}\n"
            output += "=" * 60 + "\n"
            output += f"Number of Rows: {num_rows if num_rows is not None else 'Not analyzed'}\n"
            output += f"Average Row Length: {avg_row_len if avg_row_len is not None else 'N/A'} bytes\n"
            output += f"Number of Blocks: {blocks if blocks is not None else 'N/A'}\n"
            output += f"Table Size: {size_mb if size_mb is not None else 'N/A'} MB\n"
            output += f"Number of Columns: {column_count}\n"
            output += f"Last Analyzed: {last_analyzed if last_analyzed else 'Never'}\n"
            
            if num_rows and avg_row_len:
                estimated_size = (num_rows * avg_row_len) / (1024 * 1024)
                output += f"Estimated Data Size: {estimated_size:.2f} MB\n"
            
            return [TextContent(type="text", text=output)]
            
        except Exception as e:
            status = "error"
            error_message = str(e)
            return [TextContent(type="text", text=f"❌ Error analyzing table: {str(e)}")]
        finally:
            execution_time = (time.time() - start_time) * 1000
            direct_log_query_execution(
                server_type="oracle",
                tool_name="analyze_table_size",
                query_text=f"ANALYZE TABLE: {table_name}",
                execution_time_ms=execution_time,
                status=status,
                row_count=0,
                error_message=error_message
            )
            cursor.close()
    
    async def handle_get_table_relationships(self, table_name: str, direction: str = "both") -> List[TextContent]:
        """Get foreign key relationships for a table"""
        start_time = time.time()
        cursor = self.connection.cursor()
        status = "success"
        error_message = ""
        row_count = 0
        
        try:
            table_name = table_name.upper()
            results = []
            
            # Outgoing relationships (this table references others)
            if direction in ["outgoing", "both"]:
                sql = f"""
                    SELECT 
                        c.constraint_name,
                        c.r_constraint_name,
                        c2.table_name as referenced_table,
                        listagg(cc.column_name, ', ') within group (order by cc.position) as columns,
                        listagg(cc2.column_name, ', ') within group (order by cc2.position) as referenced_columns
                    FROM user_constraints c
                    JOIN user_constraints c2 ON c.r_constraint_name = c2.constraint_name
                    JOIN user_cons_columns cc ON c.constraint_name = cc.constraint_name
                    JOIN user_cons_columns cc2 ON c2.constraint_name = cc2.constraint_name
                    WHERE c.table_name = '{table_name}' 
                    AND c.constraint_type = 'R'
                    GROUP BY c.constraint_name, c.r_constraint_name, c2.table_name
                """
                
                cursor.execute(sql)
                outgoing = cursor.fetchall()
                
                if outgoing:
                    results.append(("OUTGOING", outgoing))
            
            # Incoming relationships (other tables reference this one)
            if direction in ["incoming", "both"]:
                sql = f"""
                    SELECT 
                        c.constraint_name,
                        c.table_name as referencing_table,
                        listagg(cc.column_name, ', ') within group (order by cc.position) as referencing_columns,
                        listagg(cc2.column_name, ', ') within group (order by cc2.position) as referenced_columns
                    FROM user_constraints c
                    JOIN user_constraints c2 ON c.r_constraint_name = c2.constraint_name
                    JOIN user_cons_columns cc ON c.constraint_name = cc.constraint_name
                    JOIN user_cons_columns cc2 ON c2.constraint_name = cc2.constraint_name
                    WHERE c2.table_name = '{table_name}' 
                    AND c.constraint_type = 'R'
                    GROUP BY c.constraint_name, c.table_name
                """
                
                cursor.execute(sql)
                incoming = cursor.fetchall()
                
                if incoming:
                    results.append(("INCOMING", incoming))
            
            if not results:
                return [TextContent(type="text", text=f"No foreign key relationships found for table '{table_name}'")]
            
            output = f"📊 Foreign Key Relationships for '{table_name}':\n"
            output += "=" * 60 + "\n"
            
            for rel_type, relationships in results:
                output += f"\n{'→' if rel_type == 'OUTGOING' else '←'} {rel_type} RELATIONSHIPS:\n"
                output += "-" * 40 + "\n"
                
                for rel in relationships:
                    if rel_type == "OUTGOING":
                        con_name, _, ref_table, cols, ref_cols = rel
                        output += f"\n{con_name}:\n"
                        output += f"  {table_name}({cols}) → {ref_table}({ref_cols})\n"
                    else:
                        con_name, ref_table, ref_cols, cols = rel
                        output += f"\n{con_name}:\n"
                        output += f"  {ref_table}({ref_cols}) → {table_name}({cols})\n"
                
                row_count += len(relationships)
            
            return [TextContent(type="text", text=output)]
            
        except Exception as e:
            status = "error"
            error_message = str(e)
            return [TextContent(type="text", text=f"❌ Error getting relationships: {str(e)}")]
        finally:
            execution_time = (time.time() - start_time) * 1000
            direct_log_query_execution(
                server_type="oracle",
                tool_name="get_table_relationships",
                query_text=f"GET RELATIONSHIPS: {table_name} ({direction})",
                execution_time_ms=execution_time,
                status=status,
                row_count=row_count,
                error_message=error_message
            )
            cursor.close()
    
    async def handle_list_database_objects(self, object_type: str, pattern: str = None, limit: int = 100) -> List[TextContent]:
        """List database objects by type"""
        start_time = time.time()
        cursor = self.connection.cursor()
        status = "success"
        error_message = ""
        row_count = 0
        
        try:
            object_type = object_type.upper()
            
            sql = f"""
                SELECT object_name, status, created, last_ddl_time
                FROM user_objects
                WHERE object_type = '{object_type}'
            """
            
            if pattern:
                sql += f" AND UPPER(object_name) LIKE UPPER('{pattern}')"
            
            sql += f" ORDER BY object_name FETCH FIRST {limit} ROWS ONLY"
            
            cursor.execute(sql)
            objects = cursor.fetchall()
            row_count = len(objects)
            
            if not objects:
                return [TextContent(type="text", text=f"No {object_type} objects found{' matching pattern ' + pattern if pattern else ''}")]
            
            result = f"📊 {object_type} Objects ({row_count} found):\n"
            result += "=" * 60 + "\n"
            result += "OBJECT_NAME | STATUS | CREATED | LAST_MODIFIED\n"
            result += "-" * 60 + "\n"
            
            for obj_name, status, created, last_ddl in objects:
                created_str = created.strftime("%Y-%m-%d") if created else "N/A"
                modified_str = last_ddl.strftime("%Y-%m-%d %H:%M") if last_ddl else "N/A"
                result += f"{obj_name} | {status} | {created_str} | {modified_str}\n"
            
            return [TextContent(type="text", text=result)]
            
        except Exception as e:
            status = "error"
            error_message = str(e)
            return [TextContent(type="text", text=f"❌ Error listing objects: {str(e)}")]
        finally:
            execution_time = (time.time() - start_time) * 1000
            direct_log_query_execution(
                server_type="oracle",
                tool_name="list_database_objects",
                query_text=f"LIST {object_type} ({pattern or 'ALL'})",
                execution_time_ms=execution_time,
                status=status,
                row_count=row_count,
                error_message=error_message
            )
            cursor.close()

    async def handle_explain_plan(self, sql: str, fmt: str = "typical") -> List[TextContent]:
        """Show execution plan for a SQL query using EXPLAIN PLAN and DBMS_XPLAN"""
        import uuid
        statement_id = f"mcp_{uuid.uuid4().hex[:8]}"
        cursor = self.connection.cursor()
        try:
            # Generate the explain plan
            cursor.execute(f"EXPLAIN PLAN SET STATEMENT_ID = '{statement_id}' FOR {sql}")

            # Retrieve the plan using DBMS_XPLAN
            cursor.execute(f"""
                SELECT plan_table_output
                FROM TABLE(DBMS_XPLAN.DISPLAY('PLAN_TABLE', '{statement_id}', '{fmt.upper()}'))
            """)
            rows = cursor.fetchall()
            plan_output = "\n".join(row[0] for row in rows)

            # Clean up plan table entry
            cursor.execute(f"DELETE FROM PLAN_TABLE WHERE statement_id = '{statement_id}'")
            self.connection.commit()

            result = f"📋 Execution Plan (format: {fmt}):\n"
            result += "=" * 60 + "\n"
            result += plan_output
            return [TextContent(type="text", text=result)]
        except Exception as e:
            # Try to clean up even on error
            try:
                cursor.execute(f"DELETE FROM PLAN_TABLE WHERE statement_id = '{statement_id}'")
                self.connection.commit()
            except Exception:
                pass
            return [TextContent(type="text", text=f"❌ EXPLAIN PLAN error: {str(e)}")]
        finally:
            cursor.close()


async def main():
    """Main function to run the MCP server"""
    oracle_server = OracleMCPServer()
    
    async with stdio_server() as (read_stream, write_stream):
        await oracle_server.server.run(
            read_stream,
            write_stream,
            oracle_server.server.create_initialization_options()
        )

if __name__ == "__main__":
    asyncio.run(main())