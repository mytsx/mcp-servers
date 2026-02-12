"""Database schema inspection utilities."""

import logging
from typing import List, Optional, Dict, Any
from psycopg2 import sql
from .connection import ConnectionManager
from .query_executor import QueryExecutor
from .types import TableInfo, TableColumn, DatabaseStats

logger = logging.getLogger(__name__)


class SchemaInspector:
    """Database schema inspection with comprehensive metadata retrieval."""
    
    def __init__(self, connection_manager: ConnectionManager) -> None:
        """Initialize schema inspector."""
        self.connection_manager = connection_manager
        self.query_executor = QueryExecutor(connection_manager)
    
    def get_tables(self, schema_name: str = "public") -> List[TableInfo]:
        """Get all tables in a specific schema."""
        sql = """
            SELECT 
                schemaname as schema_name,
                tablename as table_name,
                tableowner as table_owner,
                hasindexes as has_indexes,
                hasrules as has_rules,
                hastriggers as has_triggers
            FROM pg_tables 
            WHERE schemaname = %s
            ORDER BY tablename
        """
        
        result = self.query_executor.execute(sql, [schema_name])
        
        tables = []
        for row in result.rows:
            tables.append(TableInfo(
                schema_name=row["schema_name"],
                table_name=row["table_name"],
                table_owner=row["table_owner"],
                has_indexes=row["has_indexes"],
                has_rules=row["has_rules"],
                has_triggers=row["has_triggers"]
            ))
        
        return tables
    
    def get_all_tables(self, exclude_system_schemas: bool = True) -> List[TableInfo]:
        """Get all tables across all schemas."""
        where_clause = ""
        params = []
        
        if exclude_system_schemas:
            where_clause = "WHERE schemaname NOT IN ('information_schema', 'pg_catalog', 'pg_toast')"
        
        sql = f"""
            SELECT 
                schemaname as schema_name,
                tablename as table_name,
                tableowner as table_owner,
                hasindexes as has_indexes,
                hasrules as has_rules,
                hastriggers as has_triggers
            FROM pg_tables 
            {where_clause}
            ORDER BY schemaname, tablename
        """
        
        result = self.query_executor.execute(sql, params)
        
        tables = []
        for row in result.rows:
            tables.append(TableInfo(
                schema_name=row["schema_name"],
                table_name=row["table_name"],
                table_owner=row["table_owner"],
                has_indexes=row["has_indexes"],
                has_rules=row["has_rules"],
                has_triggers=row["has_triggers"]
            ))
        
        return tables
    
    def get_table_columns(self, table_name: str, schema_name: str = "public") -> List[TableColumn]:
        """Get detailed column information for a table."""
        sql = """
            SELECT 
                column_name,
                data_type,
                is_nullable,
                column_default,
                character_maximum_length,
                ordinal_position
            FROM information_schema.columns 
            WHERE table_schema = %s AND table_name = %s
            ORDER BY ordinal_position
        """
        
        result = self.query_executor.execute(sql, [schema_name, table_name])
        
        columns = []
        for row in result.rows:
            columns.append(TableColumn(
                column_name=row["column_name"],
                data_type=row["data_type"],
                is_nullable=row["is_nullable"] == "YES",
                column_default=row["column_default"],
                character_maximum_length=row["character_maximum_length"],
                ordinal_position=row["ordinal_position"]
            ))
        
        return columns
    
    def get_table_info(self, table_name: str, schema_name: str = "public") -> Optional[TableInfo]:
        """Get comprehensive table information including size and row count."""
        # Get basic table info
        basic_info = self.get_tables(schema_name)
        table_info = next((t for t in basic_info if t.table_name == table_name), None)
        
        if not table_info:
            return None
        
        try:
            # Get row count - using psycopg2.sql for safe identifier quoting
            with self.connection_manager.get_cursor() as cursor:
                count_query = sql.SQL("SELECT COUNT(*) as count FROM {}.{}").format(
                    sql.Identifier(schema_name),
                    sql.Identifier(table_name)
                )
                cursor.execute(count_query)
                count_result = cursor.fetchone()
                row_count = count_result["count"] if count_result else 0
                
                # Get table size
                size_query = sql.SQL("SELECT pg_size_pretty(pg_total_relation_size({})) as size").format(
                    sql.Literal(f"{schema_name}.{table_name}")
                )
                cursor.execute(size_query)
                size_result = cursor.fetchone()
                table_size = size_result["size"] if size_result else "Unknown"
            
            # Update table info with additional data
            table_info.row_count = row_count
            table_info.table_size = table_size
            
        except Exception as e:
            logger.warning(f"Could not get extended info for table {schema_name}.{table_name}: {e}")
        
        return table_info
    
    def get_database_stats(self) -> DatabaseStats:
        """Get comprehensive database statistics."""
        # Get basic database info
        info_sql = """
            SELECT 
                current_database() as database_name,
                current_user as current_user,
                version() as postgresql_version
        """
        info_result = self.query_executor.execute(info_sql)
        info = info_result.rows[0] if info_result.rows else {}
        
        # Get schema statistics
        schema_sql = """
            SELECT 
                schemaname,
                COUNT(*) as table_count
            FROM pg_tables 
            WHERE schemaname NOT IN ('information_schema', 'pg_catalog', 'pg_toast')
            GROUP BY schemaname
            ORDER BY table_count DESC
        """
        schema_result = self.query_executor.execute(schema_sql)
        
        return DatabaseStats(
            database_name=info.get("database_name", "Unknown"),
            current_user=info.get("current_user", "Unknown"),
            postgresql_version=info.get("postgresql_version", "Unknown"),
            schema_stats=[dict(row) for row in schema_result.rows]
        )
    
    def get_schemas(self, exclude_system_schemas: bool = True) -> List[str]:
        """Get list of all schemas in the database."""
        where_clause = ""
        if exclude_system_schemas:
            where_clause = "WHERE schema_name NOT IN ('information_schema', 'pg_catalog', 'pg_toast')"
        
        sql = f"""
            SELECT schema_name 
            FROM information_schema.schemata 
            {where_clause}
            ORDER BY schema_name
        """
        
        result = self.query_executor.execute(sql)
        return [row["schema_name"] for row in result.rows]
    
    def table_exists(self, table_name: str, schema_name: str = "public") -> bool:
        """Check if a table exists in the specified schema."""
        sql = """
            SELECT EXISTS (
                SELECT 1 
                FROM information_schema.tables 
                WHERE table_schema = %s AND table_name = %s
            ) as exists
        """
        
        result = self.query_executor.execute(sql, [schema_name, table_name])
        return result.rows[0]["exists"] if result.rows else False
    
    def get_table_indexes(self, table_name: str, schema_name: str = "public") -> List[Dict[str, Any]]:
        """Get index information for a table."""
        sql = """
            SELECT 
                indexname,
                indexdef,
                tablespace
            FROM pg_indexes 
            WHERE schemaname = %s AND tablename = %s
            ORDER BY indexname
        """
        
        result = self.query_executor.execute(sql, [schema_name, table_name])
        return [dict(row) for row in result.rows]
    
    def get_table_constraints(self, table_name: str, schema_name: str = "public") -> List[Dict[str, Any]]:
        """Get constraint information for a table."""
        sql = """
            SELECT 
                constraint_name,
                constraint_type,
                column_name,
                foreign_table_name,
                foreign_column_name
            FROM information_schema.table_constraints tc
            LEFT JOIN information_schema.key_column_usage kcu 
                ON tc.constraint_name = kcu.constraint_name
            LEFT JOIN information_schema.referential_constraints rc 
                ON tc.constraint_name = rc.constraint_name
            LEFT JOIN information_schema.key_column_usage fkcu 
                ON rc.unique_constraint_name = fkcu.constraint_name
            WHERE tc.table_schema = %s AND tc.table_name = %s
            ORDER BY constraint_type, constraint_name
        """
        
        result = self.query_executor.execute(sql, [schema_name, table_name])
        return [dict(row) for row in result.rows]
    
    def describe_table(self, table_name: str, schema_name: str = "public") -> Dict[str, Any]:
        """Get comprehensive table description including columns, indexes, and constraints."""
        table_info = self.get_table_info(table_name, schema_name)
        if not table_info:
            return {}
        
        columns = self.get_table_columns(table_name, schema_name)
        indexes = self.get_table_indexes(table_name, schema_name)
        constraints = self.get_table_constraints(table_name, schema_name)
        
        return {
            "table_info": table_info,
            "columns": columns,
            "indexes": indexes,
            "constraints": constraints
        }