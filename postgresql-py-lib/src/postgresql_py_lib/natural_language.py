"""Natural language query processing for PostgreSQL."""

import re
import logging
from typing import Optional, Dict, Any, List, Tuple
from .connection import ConnectionManager
from .query_executor import QueryExecutor
from .schema_inspector import SchemaInspector
from .types import NaturalLanguageQuery, QueryResult

logger = logging.getLogger(__name__)


class NaturalLanguageProcessor:
    """Process natural language queries and convert them to SQL."""
    
    def __init__(self, connection_manager: ConnectionManager) -> None:
        """Initialize natural language processor."""
        self.connection_manager = connection_manager
        self.query_executor = QueryExecutor(connection_manager)
        self.schema_inspector = SchemaInspector(connection_manager)
        
        # Define query patterns
        self.patterns = [
            {
                "pattern": r"(?:show|list|göster|listele).*(?:table|tablo)",
                "handler": self._handle_list_tables,
                "confidence": 0.9,
                "name": "list_tables"
            },
            {
                "pattern": r"(?:show|list|göster|listele).*(?:user|kullanıcı)",
                "handler": self._handle_list_users,
                "confidence": 0.9,
                "name": "list_users"
            },
            {
                "pattern": r"(?:show|list|göster|listele).*(?:schema|şema)",
                "handler": self._handle_list_schemas,
                "confidence": 0.9,
                "name": "list_schemas"
            },
            {
                "pattern": r"(?:database|veritabanı).*(?:info|bilgi|stats|istatistik)",
                "handler": self._handle_database_info,
                "confidence": 0.9,
                "name": "database_info"
            },
            {
                "pattern": r"(?:describe|açıkla|tanımla)\s+(?:table\s+)?(\w+)",
                "handler": self._handle_describe_table,
                "confidence": 0.8,
                "name": "describe_table"
            },
            {
                "pattern": r"(?:count|say)\s+(?:rows?|kayıt|satır).*(?:in|from)\s+(\w+)",
                "handler": self._handle_count_rows,
                "confidence": 0.8,
                "name": "count_rows"
            },
            {
                "pattern": r"(?:size|boyut).*(?:of|from)\s+(\w+)",
                "handler": self._handle_table_size,
                "confidence": 0.7,
                "name": "table_size"
            },
            {
                "pattern": r"(?:indexes?|indeks).*(?:on|from)\s+(\w+)",
                "handler": self._handle_table_indexes,
                "confidence": 0.7,
                "name": "table_indexes"
            }
        ]
    
    def process_query(self, query: str) -> Tuple[NaturalLanguageQuery, Optional[QueryResult], Optional[str]]:
        """Process a natural language query and return SQL + results."""
        query_lower = query.lower().strip()
        
        # Try each pattern
        for pattern_info in self.patterns:
            match = re.search(pattern_info["pattern"], query_lower, re.IGNORECASE)
            if match:
                try:
                    sql, result = pattern_info["handler"](match, query)
                    
                    nl_query = NaturalLanguageQuery(
                        original_query=query,
                        generated_sql=sql,
                        confidence=pattern_info["confidence"],
                        pattern_matched=pattern_info["name"]
                    )
                    
                    return nl_query, result, None
                    
                except Exception as e:
                    error_msg = f"Error processing query: {e}"
                    logger.error(error_msg)
                    
                    nl_query = NaturalLanguageQuery(
                        original_query=query,
                        confidence=0.0
                    )
                    
                    return nl_query, None, error_msg
        
        # No pattern matched
        nl_query = NaturalLanguageQuery(
            original_query=query,
            confidence=0.0
        )
        
        help_message = self._get_help_message()
        return nl_query, None, help_message
    
    def _handle_list_tables(self, match: re.Match, original_query: str) -> Tuple[str, QueryResult]:
        """Handle table listing queries."""
        sql = """
            SELECT schemaname, tablename, tableowner 
            FROM pg_tables 
            WHERE schemaname NOT IN ('information_schema', 'pg_catalog')
            ORDER BY schemaname, tablename
        """
        result = self.query_executor.execute(sql)
        return sql.strip(), result
    
    def _handle_list_users(self, match: re.Match, original_query: str) -> Tuple[str, QueryResult]:
        """Handle user listing queries."""
        sql = """
            SELECT usename as username, usesuper as is_superuser, usecreatedb as can_create_db
            FROM pg_user 
            ORDER BY usename
        """
        result = self.query_executor.execute(sql)
        return sql.strip(), result
    
    def _handle_list_schemas(self, match: re.Match, original_query: str) -> Tuple[str, QueryResult]:
        """Handle schema listing queries."""
        sql = """
            SELECT schema_name, schema_owner 
            FROM information_schema.schemata 
            WHERE schema_name NOT IN ('information_schema', 'pg_catalog', 'pg_toast')
            ORDER BY schema_name
        """
        result = self.query_executor.execute(sql)
        return sql.strip(), result
    
    def _handle_database_info(self, match: re.Match, original_query: str) -> Tuple[str, QueryResult]:
        """Handle database info queries."""
        sql = """
            SELECT 
                current_database() as database,
                current_user as user,
                version() as postgresql_version
        """
        result = self.query_executor.execute(sql)
        return sql.strip(), result
    
    def _handle_describe_table(self, match: re.Match, original_query: str) -> Tuple[str, QueryResult]:
        """Handle table description queries."""
        table_name = match.group(1)
        sql = """
            SELECT 
                column_name,
                data_type,
                character_maximum_length,
                is_nullable,
                column_default
            FROM information_schema.columns 
            WHERE table_name = %s AND table_schema = 'public'
            ORDER BY ordinal_position
        """
        result = self.query_executor.execute(sql, [table_name])
        return sql.strip(), result
    
    def _handle_count_rows(self, match: re.Match, original_query: str) -> Tuple[str, QueryResult]:
        """Handle row counting queries."""
        table_name = match.group(1)
        # Use psycopg2.sql for safe identifier quoting
        from psycopg2 import sql
        with self.connection_manager.get_cursor() as cursor:
            query = sql.SQL("SELECT COUNT(*) as count FROM {}").format(sql.Identifier(table_name))
            cursor.execute(query)
            rows = cursor.fetchall()
            query_string = query.as_string(cursor)
            
        # Create QueryResult manually since we used raw cursor
        from .types import QueryResult
        result = QueryResult(
            rows=[dict(row) for row in rows],
            row_count=len(rows),
            field_names=["count"]
        )
        return query_string, result
    
    def _handle_table_size(self, match: re.Match, original_query: str) -> Tuple[str, QueryResult]:
        """Handle table size queries."""
        table_name = match.group(1)
        sql = """
            SELECT 
                pg_size_pretty(pg_total_relation_size(%s)) as table_size,
                pg_size_pretty(pg_relation_size(%s)) as data_size
        """
        result = self.query_executor.execute(sql, [table_name, table_name])
        return sql.strip(), result
    
    def _handle_table_indexes(self, match: re.Match, original_query: str) -> Tuple[str, QueryResult]:
        """Handle table index queries."""
        table_name = match.group(1)
        sql = """
            SELECT 
                indexname,
                indexdef
            FROM pg_indexes 
            WHERE tablename = %s AND schemaname = 'public'
            ORDER BY indexname
        """
        result = self.query_executor.execute(sql, [table_name])
        return sql.strip(), result
    
    def _get_help_message(self) -> str:
        """Get help message for supported queries."""
        return """🤖 Desteklenen doğal dil sorguları:

**Tablo İşlemleri:**
• "show tables" / "tabloları listele"
• "describe [table_name]" / "[tablo_adı] açıkla"
• "count rows in [table_name]" / "[tablo_adı] kayıt sayısı"
• "size of [table_name]" / "[tablo_adı] boyutu"
• "indexes on [table_name]" / "[tablo_adı] indeksleri"

**Veritabanı Bilgileri:**
• "show users" / "kullanıcıları göster"
• "show schemas" / "şemaları listele"  
• "database info" / "veritabanı bilgileri"

**Örnekler:**
• "tabloları listele"
• "users tablosunu açıkla"
• "products tablosundaki kayıtları say"
• "orders tablosunun boyutunu göster"

Daha karmaşık sorgular için doğrudan SQL kullanın."""
    
    def get_query_suggestions(self, partial_query: str) -> List[str]:
        """Get query suggestions based on partial input."""
        suggestions = [
            "show tables",
            "show users",
            "show schemas", 
            "database info",
            "describe users",
            "count rows in products",
            "size of orders",
            "indexes on users"
        ]
        
        # Filter suggestions based on partial input
        if partial_query:
            partial_lower = partial_query.lower()
            suggestions = [s for s in suggestions if partial_lower in s.lower()]
        
        return suggestions[:5]  # Return top 5 suggestions