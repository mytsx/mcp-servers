"""PostgreSQL Python Library - Modern database operations with natural language support."""

from .connection import ConnectionManager
from .query_executor import QueryExecutor, QueryExecutionError, TransactionError
from .schema_inspector import SchemaInspector
from .natural_language import NaturalLanguageProcessor
from .types import (
    PostgreSQLConfig,
    QueryResult,
    QueryOptions,
    TableInfo,
    TableColumn,
    DatabaseStats,
    NaturalLanguageQuery,
    ConnectionPoolStats
)

__version__ = "1.0.0"
__author__ = "AI DB Library"
__description__ = "Modern PostgreSQL database library with natural language query support"

# Main client class
class PostgreSQLClient:
    """
    Main PostgreSQL client with comprehensive database operations.
    
    Features:
    - Automatic .env configuration loading
    - Connection pooling
    - Natural language query processing
    - Schema inspection utilities
    - Transaction support
    - Type-safe operations with modern Python features
    """
    
    def __init__(self, config: PostgreSQLConfig = None) -> None:
        """
        Initialize PostgreSQL client.
        
        Args:
            config: Optional configuration override. If not provided,
                   configuration will be loaded from environment variables.
        """
        self.connection_manager = ConnectionManager(config)
        self.query_executor = QueryExecutor(self.connection_manager)
        self.schema_inspector = SchemaInspector(self.connection_manager)
        self.natural_language = NaturalLanguageProcessor(self.connection_manager)
    
    # Connection Management
    def connect(self) -> None:
        """Establish database connection pool."""
        self.connection_manager.connect()
    
    def disconnect(self) -> None:
        """Close all database connections."""
        self.connection_manager.disconnect()
    
    def test_connection(self) -> bool:
        """Test if database connection is working."""
        return self.connection_manager.test_connection()
    
    @property
    def is_connected(self) -> bool:
        """Check if client is connected to database."""
        return self.connection_manager.is_connected
    
    # Query Execution
    def query(self, sql: str, params: list = None, options: QueryOptions = None) -> QueryResult:
        """
        Execute a SQL query.
        
        Args:
            sql: SQL query string
            params: Query parameters for prepared statements
            options: Query execution options
            
        Returns:
            QueryResult with rows, metadata, and execution time
        """
        return self.query_executor.execute(sql, params, options)
    
    def query_many(self, queries: list, options: QueryOptions = None) -> list:
        """
        Execute multiple queries in a transaction.
        
        Args:
            queries: List of query dictionaries with 'sql' and optional 'params'
            options: Query execution options
            
        Returns:
            List of QueryResult objects
        """
        return self.query_executor.execute_many(queries, options)
    
    def transaction(self, callback, options: QueryOptions = None):
        """
        Execute callback within a transaction context.
        
        Args:
            callback: Function that receives a cursor and returns a result
            options: Query execution options
            
        Returns:
            Result from callback function
        """
        return self.query_executor.execute_with_transaction(callback, options)
    
    # Natural Language Processing
    def natural_language_query(self, query: str) -> dict:
        """
        Process a natural language query.
        
        Args:
            query: Natural language query string
            
        Returns:
            Dictionary with 'sql', 'result', and optional 'message'
        """
        nl_query, result, message = self.natural_language.process_query(query)
        
        return {
            "original_query": nl_query.original_query,
            "generated_sql": nl_query.generated_sql,
            "confidence": nl_query.confidence,
            "pattern_matched": nl_query.pattern_matched,
            "result": result,
            "message": message
        }
    
    def get_query_suggestions(self, partial_query: str = "") -> list:
        """Get natural language query suggestions."""
        return self.natural_language.get_query_suggestions(partial_query)
    
    # Schema Inspection
    def get_tables(self, schema_name: str = "public") -> list:
        """Get all tables in specified schema."""
        return self.schema_inspector.get_tables(schema_name)
    
    def get_all_tables(self, exclude_system: bool = True) -> list:
        """Get all tables across all schemas."""
        return self.schema_inspector.get_all_tables(exclude_system)
    
    def get_table_columns(self, table_name: str, schema_name: str = "public") -> list:
        """Get column information for a table."""
        return self.schema_inspector.get_table_columns(table_name, schema_name)
    
    def get_table_info(self, table_name: str, schema_name: str = "public") -> TableInfo:
        """Get comprehensive table information."""
        return self.schema_inspector.get_table_info(table_name, schema_name)
    
    def describe_table(self, table_name: str, schema_name: str = "public") -> dict:
        """Get complete table description including columns, indexes, constraints."""
        return self.schema_inspector.describe_table(table_name, schema_name)
    
    def get_schemas(self, exclude_system: bool = True) -> list:
        """Get list of all schemas."""
        return self.schema_inspector.get_schemas(exclude_system)
    
    def table_exists(self, table_name: str, schema_name: str = "public") -> bool:
        """Check if table exists."""
        return self.schema_inspector.table_exists(table_name, schema_name)
    
    def get_database_stats(self) -> DatabaseStats:
        """Get comprehensive database statistics."""
        return self.schema_inspector.get_database_stats()
    
    # Utility Methods
    def format_results(self, result: QueryResult) -> str:
        """Format query results as readable table."""
        return self.query_executor.format_results(result)
    
    def get_pool_stats(self) -> ConnectionPoolStats:
        """Get connection pool statistics."""
        return self.connection_manager.get_pool_stats()
    
    # Context Manager Support
    def __enter__(self) -> "PostgreSQLClient":
        """Context manager entry."""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.disconnect()


# Convenience exports
__all__ = [
    "PostgreSQLClient",
    "ConnectionManager", 
    "QueryExecutor",
    "SchemaInspector",
    "NaturalLanguageProcessor",
    "PostgreSQLConfig",
    "QueryResult",
    "QueryOptions", 
    "TableInfo",
    "TableColumn",
    "DatabaseStats",
    "NaturalLanguageQuery",
    "ConnectionPoolStats",
    "QueryExecutionError",
    "TransactionError"
]