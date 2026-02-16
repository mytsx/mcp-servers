#!/usr/bin/env python3
"""
PostgreSQL MCP Server for Claude Desktop
Natural language queries to PostgreSQL database
"""

import asyncio
import os
import logging
import time
from typing import Any, List, Dict
import psycopg2
from psycopg2.extras import RealDictCursor
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

from .query_logger import direct_log_query_execution, get_query_history

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PostgreSQLMCPServer:
    # Keywords that indicate a write/modify operation
    WRITE_KEYWORDS = frozenset([
        "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE",
        "TRUNCATE", "MERGE", "GRANT", "REVOKE",
    ])

    def __init__(self):
        self.server = Server("postgresql-mcp-server")
        self.connection = None
        self.read_only = os.getenv("READ_ONLY", "").lower() in ("true", "1", "yes")
        self.db_identifier = f"{os.getenv('DB_HOST', 'localhost')}:{os.getenv('DB_PORT', '5432')}/{os.getenv('DB_NAME', '')}"
        self.workspace_path = os.getcwd()
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
                    uri="postgresql://tables",
                    name="Database Tables",
                    description="List all tables in the PostgreSQL database",
                    mimeType="application/json"
                ),
                Resource(
                    uri="postgresql://schema",
                    name="Database Schema",
                    description="Get database schema information",
                    mimeType="application/json"
                ),
                Resource(
                    uri="postgresql://stats",
                    name="Database Statistics",
                    description="Get database statistics and info",
                    mimeType="application/json"
                )
            ]
        
        @self.server.read_resource()
        async def read_resource(uri: str) -> str:
            """Read database resource"""
            if not self.connection:
                await self.connect_to_postgresql()
                
            cursor = self.connection.cursor(cursor_factory=RealDictCursor)
            
            if uri == "postgresql://tables":
                cursor.execute("""
                    SELECT 
                        schemaname,
                        tablename,
                        tableowner,
                        hasindexes,
                        hasrules,
                        hastriggers
                    FROM pg_tables 
                    WHERE schemaname NOT IN ('information_schema', 'pg_catalog')
                    ORDER BY schemaname, tablename
                """)
                tables = cursor.fetchall()
                result = "Database Tables:\n\n"
                for table in tables:
                    result += f"• {table['schemaname']}.{table['tablename']} (Owner: {table['tableowner']})\n"
                    if table['hasindexes']:
                        result += "  - Has indexes\n"
                    if table['hastriggers']:
                        result += "  - Has triggers\n"
                cursor.close()
                return result
                
            elif uri == "postgresql://schema":
                # Get detailed schema information
                cursor.execute("""
                    SELECT 
                        t.table_schema,
                        t.table_name,
                        c.column_name,
                        c.data_type,
                        c.is_nullable,
                        c.column_default,
                        c.ordinal_position
                    FROM information_schema.tables t
                    JOIN information_schema.columns c ON t.table_name = c.table_name 
                        AND t.table_schema = c.table_schema
                    WHERE t.table_schema NOT IN ('information_schema', 'pg_catalog')
                    ORDER BY t.table_schema, t.table_name, c.ordinal_position
                    LIMIT 500
                """)
                
                columns = cursor.fetchall()
                schema_info = "Database Schema:\n\n"
                current_table = None
                
                for col in columns:
                    table_full_name = f"{col['table_schema']}.{col['table_name']}"
                    if current_table != table_full_name:
                        current_table = table_full_name
                        schema_info += f"\n📋 Table: {table_full_name}\n"
                        schema_info += "-" * 50 + "\n"
                    
                    nullable = "NULL" if col['is_nullable'] == 'YES' else "NOT NULL"
                    default = f" DEFAULT {col['column_default']}" if col['column_default'] else ""
                    schema_info += f"  {col['column_name']}: {col['data_type']} {nullable}{default}\n"
                
                cursor.close()
                return schema_info
            
            elif uri == "postgresql://stats":
                # Database statistics
                cursor.execute("""
                    SELECT 
                        current_database() as database_name,
                        current_user as current_user,
                        version() as postgresql_version
                """)
                info = cursor.fetchone()
                
                cursor.execute("""
                    SELECT 
                        schemaname,
                        COUNT(*) as table_count
                    FROM pg_tables 
                    WHERE schemaname NOT IN ('information_schema', 'pg_catalog')
                    GROUP BY schemaname
                    ORDER BY table_count DESC
                """)
                schema_stats = cursor.fetchall()
                
                result = f"Database Information:\n\n"
                result += f"• Database: {info['database_name']}\n"
                result += f"• Current User: {info['current_user']}\n"
                result += f"• PostgreSQL Version: {info['postgresql_version']}\n\n"
                result += "Schema Statistics:\n"
                for stat in schema_stats:
                    result += f"• {stat['schemaname']}: {stat['table_count']} tables\n"
                
                cursor.close()
                return result
            
            cursor.close()
            return "Resource not found"
        
        @self.server.list_tools()
        async def list_tools() -> List[Tool]:
            """List available tools"""
            return [
                Tool(
                    name="natural_language_query",
                    description="Execute natural language queries on PostgreSQL database",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Natural language query in Turkish or English"
                            }
                        },
                        "required": ["query"]
                    }
                ),
                Tool(
                    name="execute_sql",
                    description="Execute direct SQL query on PostgreSQL database",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "sql": {
                                "type": "string",
                                "description": "SQL query to execute"
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
                    description="Get detailed information about a specific table",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "table_name": {
                                "type": "string",
                                "description": "Name of the table to describe (format: schema.table or just table)"
                            }
                        },
                        "required": ["table_name"]
                    }
                ),
                Tool(
                    name="smart_query",
                    description="AI-powered smart query with context understanding",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "question": {
                                "type": "string",
                                "description": "Your question about the data in natural language"
                            }
                        },
                        "required": ["question"]
                    }
                ),
                Tool(
                    name="explain_query",
                    description="Show the execution plan for a SQL query using EXPLAIN",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "sql": {
                                "type": "string",
                                "description": "SQL query to explain"
                            },
                            "analyze": {
                                "type": "boolean",
                                "description": "Actually execute the query to get real timing (default: false - safe/estimated only)",
                                "default": False
                            },
                            "format": {
                                "type": "string",
                                "enum": ["text", "json", "yaml"],
                                "description": "Output format (default: text)",
                                "default": "text"
                            },
                            "buffers": {
                                "type": "boolean",
                                "description": "Include buffer usage information (only with analyze=true)",
                                "default": False
                            }
                        },
                        "required": ["sql"]
                    }
                ),
                Tool(
                    name="get_query_history",
                    description="Get recent query history for this database connection. Shows past queries, execution times, statuses and errors. Useful for reviewing what was run before.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "limit": {
                                "type": "integer",
                                "description": "Maximum number of recent queries to return (default: 20)",
                                "default": 20
                            },
                            "status": {
                                "type": "string",
                                "enum": ["success", "error"],
                                "description": "Filter by status (optional - omit for all)"
                            },
                            "tool_name": {
                                "type": "string",
                                "description": "Filter by tool name, e.g. 'execute_sql', 'natural_language_query' (optional)"
                            }
                        }
                    }
                )
            ]

        @self.server.call_tool()
        async def call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
            """Handle tool calls"""
            if name == "get_query_history":
                return self.handle_get_query_history(arguments)

            if not self.connection:
                await self.connect_to_postgresql()

            try:
                if name == "natural_language_query":
                    return await self.handle_natural_language_query(arguments["query"])

                elif name == "execute_sql":
                    return await self.handle_sql_query(arguments["sql"], arguments.get("limit", 100))

                elif name == "describe_table":
                    return await self.handle_describe_table(arguments["table_name"])

                elif name == "smart_query":
                    return await self.handle_smart_query(arguments["question"])

                elif name == "explain_query":
                    return await self.handle_explain_query(
                        arguments["sql"],
                        arguments.get("analyze", False),
                        arguments.get("format", "text"),
                        arguments.get("buffers", False)
                    )

                else:
                    return [TextContent(type="text", text=f"Unknown tool: {name}")]
                    
            except Exception as e:
                logger.error(f"Error in tool call: {e}")
                return [TextContent(type="text", text=f"Error: {str(e)}")]
    
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

    async def connect_to_postgresql(self):
        """Connect to PostgreSQL database"""
        try:
            host = os.getenv("DB_HOST", "localhost")
            port = os.getenv("DB_PORT", "5432")
            database = os.getenv("DB_NAME", "docsmapeg")
            user = os.getenv("DB_USER", "postgres")
            password = os.getenv("DB_PASSWORD", "postgres")
            
            self.connection = psycopg2.connect(
                host=host,
                port=port,
                database=database,
                user=user,
                password=password
            )
            self.connection.set_session(autocommit=True)
            logger.info(f"Successfully connected to PostgreSQL database: {database}")
            
        except Exception as e:
            logger.error(f"Failed to connect to PostgreSQL: {e}")
            raise
    
    async def handle_natural_language_query(self, query: str) -> List[TextContent]:
        """Convert natural language to SQL and execute"""
        start_time = time.time()
        query_lower = query.lower()
        generated_sql = ""
        status = "success"
        error_message = ""
        
        try:
            # Enhanced pattern matching for common queries
            if any(word in query_lower for word in ["tablo", "table", "liste", "list", "göster", "show"]):
                if any(word in query_lower for word in ["liste", "list", "göster", "show", "all"]):
                    generated_sql = """
                        SELECT schemaname, tablename, tableowner 
                        FROM pg_tables 
                        WHERE schemaname NOT IN ('information_schema', 'pg_catalog')
                        ORDER BY schemaname, tablename
                    """
                    result = await self.handle_sql_query(generated_sql.strip(), 50)
                    
                    # Log the natural language query
                    execution_time = (time.time() - start_time) * 1000
                    direct_log_query_execution(
                        server_type="postgresql",
                        tool_name="natural_language_query",
                        query_text=generated_sql.strip(),
                        execution_time_ms=execution_time,
                        status="success",
                        row_count=0,  # Will be logged by handle_sql_query too
                        error_message="",
                        user_query=query,
                        db_identifier=self.db_identifier,
                        workspace_path=self.workspace_path,
                    )
                    return result

            if any(word in query_lower for word in ["kullanıcı", "user", "kullanıcılar", "users"]):
                generated_sql = """
                    SELECT usename as username, usesuper as is_superuser, usecreatedb as can_create_db
                    FROM pg_user 
                    ORDER BY usename
                """
                result = await self.handle_sql_query(generated_sql.strip(), 20)
                
                execution_time = (time.time() - start_time) * 1000
                direct_log_query_execution(
                    server_type="postgresql",
                    tool_name="natural_language_query",
                    query_text=generated_sql.strip(),
                    execution_time_ms=execution_time,
                    status="success",
                    row_count=0,
                    error_message="",
                    user_query=query,
                    db_identifier=self.db_identifier,
                    workspace_path=self.workspace_path,
                )
                return result

            if any(word in query_lower for word in ["şema", "schema", "schemas"]):
                generated_sql = """
                    SELECT schema_name, schema_owner 
                    FROM information_schema.schemata 
                    WHERE schema_name NOT IN ('information_schema', 'pg_catalog', 'pg_toast')
                    ORDER BY schema_name
                """
                result = await self.handle_sql_query(generated_sql.strip(), 20)
                
                execution_time = (time.time() - start_time) * 1000
                direct_log_query_execution(
                    server_type="postgresql",
                    tool_name="natural_language_query",
                    query_text=generated_sql.strip(),
                    execution_time_ms=execution_time,
                    status="success",
                    row_count=0,
                    error_message="",
                    user_query=query,
                    db_identifier=self.db_identifier,
                    workspace_path=self.workspace_path,
                )
                return result

            if any(word in query_lower for word in ["istatistik", "statistics", "stats", "bilgi", "info"]):
                generated_sql = """
                    SELECT 
                        current_database() as database,
                        current_user as user,
                        version() as postgresql_version
                """
                result = await self.handle_sql_query(generated_sql.strip(), 1)
                
                execution_time = (time.time() - start_time) * 1000
                direct_log_query_execution(
                    server_type="postgresql",
                    tool_name="natural_language_query",
                    query_text=generated_sql.strip(),
                    execution_time_ms=execution_time,
                    status="success",
                    row_count=0,
                    error_message="",
                    user_query=query,
                    db_identifier=self.db_identifier,
                    workspace_path=self.workspace_path,
                )
                return result

            # If no pattern matches, return helpful message
            execution_time = (time.time() - start_time) * 1000
            direct_log_query_execution(
                server_type="postgresql",
                tool_name="natural_language_query",
                query_text="NO_PATTERN_MATCH",
                execution_time_ms=execution_time,
                status="success",
                row_count=0,
                error_message="",
                user_query=query,
                db_identifier=self.db_identifier,
                workspace_path=self.workspace_path,
            )
            
            return [TextContent(
                type="text", 
                text=f"""🤖 Doğal dil sorgusu: "{query}"

Anlayabildiğim komutlar:
• "tabloları listele" / "show tables" 
• "kullanıcıları göster" / "show users"
• "şemaları listele" / "show schemas"
• "veritabanı bilgilerini göster" / "show database info"

Gelişmiş sorgular için:
• 'execute_sql' aracını kullanın
• 'smart_query' aracıyla AI destekli sorgular yapın

Örnek SQL sorguları:
• SELECT * FROM pg_tables WHERE schemaname = 'public'
• SELECT table_name, column_name, data_type FROM information_schema.columns
"""
            )]
        except Exception as e:
            status = "error"
            error_message = str(e)
            execution_time = (time.time() - start_time) * 1000
            direct_log_query_execution(
                server_type="postgresql",
                tool_name="natural_language_query",
                query_text=generated_sql or "PATTERN_MATCHING_ERROR",
                execution_time_ms=execution_time,
                status=status,
                row_count=0,
                error_message=error_message,
                user_query=query,
                db_identifier=self.db_identifier,
                workspace_path=self.workspace_path,
            )
            return [TextContent(type="text", text=f"❌ Error processing natural language query: {str(e)}")]
    
    async def handle_sql_query(self, sql: str, limit: int = 100) -> List[TextContent]:
        """Execute SQL query"""
        # Read-only guard
        if self.read_only and self._is_write_query(sql):
            return [TextContent(type="text", text="❌ Read-only mode is enabled. Write operations (INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, TRUNCATE, MERGE, GRANT, REVOKE) are blocked. Set READ_ONLY=false to allow write operations.")]

        start_time = time.time()
        cursor = self.connection.cursor(cursor_factory=RealDictCursor)
        row_count = 0
        status = "success"
        error_message = ""
        result_text = ""
        
        try:
            # Add LIMIT for SELECT queries if not already present
            if sql.strip().upper().startswith("SELECT") and "LIMIT" not in sql.upper():
                sql += f" LIMIT {limit}"
            
            cursor.execute(sql)
            
            if sql.strip().upper().startswith("SELECT"):
                rows = cursor.fetchall()
                row_count = len(rows)
                
                if not rows:
                    result_text = "Sorgu sonuç döndürmedi."
                else:
                    # Format results
                    result = f"🔍 SQL Query: {sql}\n\n"
                    result += f"📊 Results ({len(rows)} rows):\n"
                    result += "=" * 60 + "\n"
                    
                    # Get column names
                    columns = [desc[0] for desc in cursor.description]
                    
                    # Add column headers
                    result += " | ".join(columns) + "\n"
                    result += "-" * 60 + "\n"
                    
                    # Add data rows
                    for row in rows:
                        row_data = []
                        for col in columns:
                            val = row[col] if row[col] is not None else "NULL"
                            row_data.append(str(val))
                        result += " | ".join(row_data) + "\n"
                    
                    result_text = result
                
                return [TextContent(type="text", text=result_text)]
            else:
                # For non-SELECT queries
                result_text = f"✅ Query executed successfully: {sql}"
                return [TextContent(type="text", text=result_text)]
                
        except Exception as e:
            status = "error"
            error_message = str(e)
            result_text = f"❌ SQL Error: {str(e)}"
            return [TextContent(type="text", text=result_text)]
        finally:
            # Log the query execution
            execution_time = (time.time() - start_time) * 1000  # Convert to milliseconds
            # Direct logging to avoid async queue truncation
            direct_log_query_execution(
                server_type="postgresql",
                tool_name="execute_sql",
                query_text=sql,
                execution_time_ms=execution_time,
                status=status,
                row_count=row_count,
                error_message=error_message,
                response_text=result_text,
                db_identifier=self.db_identifier,
                workspace_path=self.workspace_path,
            )
            cursor.close()
    
    async def handle_describe_table(self, table_name: str) -> List[TextContent]:
        """Describe table structure"""
        cursor = self.connection.cursor(cursor_factory=RealDictCursor)
        
        try:
            # Handle schema.table format
            if '.' in table_name:
                schema, table = table_name.split('.', 1)
            else:
                schema = 'public'
                table = table_name
            
            # Get table columns
            cursor.execute("""
                SELECT 
                    column_name,
                    data_type,
                    character_maximum_length,
                    is_nullable,
                    column_default,
                    ordinal_position
                FROM information_schema.columns 
                WHERE table_schema = %s AND table_name = %s
                ORDER BY ordinal_position
            """, (schema, table))
            
            columns = cursor.fetchall()
            
            if not columns:
                return [TextContent(type="text", text=f"❌ Table '{schema}.{table}' not found")]
            
            result = f"📋 Table: {schema}.{table}\n"
            result += "=" * 60 + "\n\n"
            
            for col in columns:
                nullable = "NULL" if col['is_nullable'] == 'YES' else "NOT NULL"
                length = f"({col['character_maximum_length']})" if col['character_maximum_length'] else ""
                default = f" DEFAULT {col['column_default']}" if col['column_default'] else ""
                result += f"• {col['column_name']}: {col['data_type']}{length} {nullable}{default}\n"
            
            # Get row count
            cursor.execute(f'SELECT COUNT(*) as count FROM "{schema}"."{table}"')
            row_count = cursor.fetchone()['count']
            result += f"\n📊 Total rows: {row_count:,}"
            
            # Get table size
            cursor.execute("""
                SELECT pg_size_pretty(pg_total_relation_size(%s)) as size
            """, (f'"{schema}"."{table}"',))
            size_info = cursor.fetchone()
            result += f"\n💾 Table size: {size_info['size']}"
            
            return [TextContent(type="text", text=result)]
            
        except Exception as e:
            return [TextContent(type="text", text=f"❌ Error describing table: {str(e)}")]
        finally:
            cursor.close()
    
    async def handle_smart_query(self, question: str) -> List[TextContent]:
        """AI-powered smart query"""
        try:
            # First, get schema information to provide context
            cursor = self.connection.cursor(cursor_factory=RealDictCursor)
            cursor.execute("""
                SELECT table_name, column_name, data_type
                FROM information_schema.columns 
                WHERE table_schema = 'public'
                ORDER BY table_name, ordinal_position
                LIMIT 100
            """)
            schema_info = cursor.fetchall()
            cursor.close()
            
            # Build schema context
            schema_context = "Available tables and columns:\n"
            current_table = None
            for item in schema_info:
                if current_table != item['table_name']:
                    current_table = item['table_name']
                    schema_context += f"\n{item['table_name']}:\n"
                schema_context += f"  - {item['column_name']} ({item['data_type']})\n"
            
            # For now, provide helpful guidance
            # In a full implementation, you would use the Anthropic API here
            return [TextContent(
                type="text",
                text=f"""🤖 Smart Query for: "{question}"

Şu anda basit pattern matching kullanıyorum. Tam AI özelliği için:

1. Schema analizi:
{schema_context[:500]}...

2. Önerilen yaklaşım:
• Sorunuzu daha spesifik hale getirin
• 'execute_sql' ile doğrudan SQL yazın
• 'describe_table' ile tablo yapısını inceleyin

Örnek sorgular:
• "users tablosundaki tüm kayıtları göster"
• "en son eklenen 10 kaydı listele"
• "boş olmayan email adreslerini say"
"""
            )]
            
        except Exception as e:
            return [TextContent(type="text", text=f"❌ Smart query error: {str(e)}")]

    async def handle_explain_query(self, sql: str, analyze: bool = False, fmt: str = "text", buffers: bool = False) -> List[TextContent]:
        """Show execution plan for a SQL query"""
        cursor = self.connection.cursor()
        try:
            parts = ["EXPLAIN"]
            options = []
            if analyze:
                options.append("ANALYZE true")
            if buffers and analyze:
                options.append("BUFFERS true")
            if fmt != "text":
                options.append(f"FORMAT {fmt}")
            if options:
                parts.append(f"({', '.join(options)})")
            parts.append(sql)
            explain_sql = " ".join(parts)

            cursor.execute(explain_sql)
            rows = cursor.fetchall()

            plan_output = "\n".join(row[0] if isinstance(row[0], str) else str(row[0]) for row in rows)
            result = f"📋 Execution Plan{' (ANALYZE)' if analyze else ''}:\n"
            result += "=" * 60 + "\n"
            result += plan_output
            return [TextContent(type="text", text=result)]
        except Exception as e:
            return [TextContent(type="text", text=f"❌ EXPLAIN error: {str(e)}")]
        finally:
            cursor.close()

    def handle_get_query_history(self, arguments: Dict[str, Any]) -> List[TextContent]:
        """Return recent query history for this db+workspace"""
        logs = get_query_history(
            db_identifier=self.db_identifier,
            workspace_path=self.workspace_path,
            limit=arguments.get("limit", 20),
            status=arguments.get("status", ""),
            tool_name=arguments.get("tool_name", ""),
        )

        if not logs:
            return [TextContent(type="text", text="No query history found for this database/workspace.")]

        result = f"Query History ({len(logs)} entries):\n"
        result += f"DB: {self.db_identifier} | Workspace: {self.workspace_path}\n"
        result += "=" * 70 + "\n\n"

        for log in logs:
            status_icon = "OK" if log["status"] == "success" else "ERR"
            time_str = log["timestamp"][:19].replace("T", " ")
            result += f"[{status_icon}] {time_str} | {log['tool_name']} | {log['execution_time_ms']:.0f}ms | {log['row_count']} rows\n"
            query_preview = log["query_text"][:120].replace("\n", " ")
            result += f"     {query_preview}\n"
            if log["error_message"]:
                result += f"     Error: {log['error_message'][:100]}\n"
            if log["user_query"]:
                result += f"     User: {log['user_query'][:100]}\n"
            result += "\n"

        return [TextContent(type="text", text=result)]

async def main():
    """Main function to run the MCP server"""
    postgresql_server = PostgreSQLMCPServer()
    
    async with stdio_server() as (read_stream, write_stream):
        await postgresql_server.server.run(
            read_stream,
            write_stream,
            postgresql_server.server.create_initialization_options()
        )

if __name__ == "__main__":
    asyncio.run(main())