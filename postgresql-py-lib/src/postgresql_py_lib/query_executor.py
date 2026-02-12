"""SQL query execution with modern Python features."""

import time
import logging
from typing import Any, Dict, List, Optional, Union
import psycopg2
from psycopg2.extras import RealDictCursor

from .connection import ConnectionManager
from .types import QueryResult, QueryOptions

logger = logging.getLogger(__name__)


class QueryExecutor:
    """Modern SQL query executor with comprehensive error handling."""
    
    def __init__(self, connection_manager: ConnectionManager) -> None:
        """Initialize query executor with connection manager."""
        self.connection_manager = connection_manager
    
    def execute(
        self, 
        sql: str, 
        params: Optional[List[Any]] = None, 
        options: Optional[QueryOptions] = None
    ) -> QueryResult:
        """Execute a SQL query with comprehensive error handling."""
        start_time = time.time()
        options = options or {}
        params = params or []
        
        # Add LIMIT if specified and query is SELECT without existing LIMIT
        final_sql = self._apply_limit(sql, options.get("limit"))
        
        try:
            with self.connection_manager.get_cursor() as cursor:
                if options.get("log_query", False):
                    logger.info(f"Executing query: {final_sql[:200]}...")
                
                cursor.execute(final_sql, params)
                
                # Handle different query types
                if final_sql.strip().upper().startswith("SELECT"):
                    rows = cursor.fetchall()
                    field_names = [desc[0] for desc in cursor.description] if cursor.description else []
                    row_count = len(rows)
                else:
                    # For INSERT, UPDATE, DELETE, etc.
                    rows = []
                    field_names = []
                    row_count = cursor.rowcount or 0
                
                execution_time = (time.time() - start_time) * 1000
                
                return QueryResult(
                    rows=[dict(row) if hasattr(row, 'keys') else {} for row in rows],
                    row_count=row_count,
                    field_names=field_names,
                    execution_time_ms=execution_time
                )
                
        except psycopg2.Error as e:
            execution_time = (time.time() - start_time) * 1000
            logger.error(f"Query execution failed ({execution_time:.2f}ms): {e}")
            raise QueryExecutionError(f"SQL execution failed: {e}") from e
        except Exception as e:
            execution_time = (time.time() - start_time) * 1000
            logger.error(f"Unexpected error ({execution_time:.2f}ms): {e}")
            raise QueryExecutionError(f"Unexpected query error: {e}") from e
    
    def execute_many(
        self, 
        queries: List[Dict[str, Any]], 
        options: Optional[QueryOptions] = None
    ) -> List[QueryResult]:
        """Execute multiple queries in a transaction."""
        results: List[QueryResult] = []
        
        try:
            with self.connection_manager.get_connection() as conn:
                # Disable autocommit for transaction
                conn.autocommit = False
                
                try:
                    for query_data in queries:
                        sql = query_data["sql"]
                        params = query_data.get("params", [])
                        
                        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                            start_time = time.time()
                            cursor.execute(sql, params)
                            
                            if sql.strip().upper().startswith("SELECT"):
                                rows = cursor.fetchall()
                                field_names = [desc[0] for desc in cursor.description] if cursor.description else []
                                row_count = len(rows)
                            else:
                                rows = []
                                field_names = []
                                row_count = cursor.rowcount or 0
                            
                            execution_time = (time.time() - start_time) * 1000
                            
                            results.append(QueryResult(
                                rows=[dict(row) if hasattr(row, 'keys') else {} for row in rows],
                                row_count=row_count,
                                field_names=field_names,
                                execution_time_ms=execution_time
                            ))
                    
                    # Commit transaction
                    conn.commit()
                    logger.info(f"Transaction completed successfully with {len(queries)} queries")
                    
                except Exception as e:
                    # Rollback on error
                    conn.rollback()
                    logger.error(f"Transaction failed, rolled back: {e}")
                    raise TransactionError(f"Transaction failed: {e}") from e
                finally:
                    # Restore autocommit
                    conn.autocommit = True
                    
        except Exception as e:
            logger.error(f"Transaction execution failed: {e}")
            raise TransactionError(f"Transaction execution failed: {e}") from e
        
        return results
    
    def execute_with_transaction(
        self, 
        callback, 
        options: Optional[QueryOptions] = None
    ) -> Any:
        """Execute a callback function within a transaction context."""
        try:
            with self.connection_manager.get_connection() as conn:
                conn.autocommit = False
                
                try:
                    # Create a cursor for the callback
                    with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                        result = callback(cursor)
                    
                    conn.commit()
                    logger.info("Transaction callback completed successfully")
                    return result
                    
                except Exception as e:
                    conn.rollback()
                    logger.error(f"Transaction callback failed, rolled back: {e}")
                    raise TransactionError(f"Transaction callback failed: {e}") from e
                finally:
                    conn.autocommit = True
                    
        except Exception as e:
            logger.error(f"Transaction execution failed: {e}")
            raise TransactionError(f"Transaction execution failed: {e}") from e
    
    def _apply_limit(self, sql: str, limit: Optional[int]) -> str:
        """Apply LIMIT clause to SELECT queries if specified."""
        if limit and sql.strip().upper().startswith("SELECT") and "LIMIT" not in sql.upper():
            return f"{sql.rstrip(';')} LIMIT {limit}"
        return sql
    
    def format_results(self, result: QueryResult) -> str:
        """Format query results as a readable table."""
        if not result.rows:
            return f"No results found. Query executed in {result.execution_time_ms:.2f}ms"
        
        # Get column names
        columns = result.field_names
        if not columns:
            return f"Query executed successfully. Affected rows: {result.row_count}"
        
        # Create formatted output
        output = f"Query Results ({result.row_count} rows, {result.execution_time_ms:.2f}ms):\n"
        output += "=" * 80 + "\n"
        
        # Add headers
        header = " | ".join(columns)
        output += header + "\n"
        output += "-" * len(header) + "\n"
        
        # Add data rows
        for row in result.rows:
            values = []
            for col in columns:
                val = row.get(col)
                if val is None:
                    values.append("NULL")
                else:
                    # Truncate long values
                    str_val = str(val)
                    if len(str_val) > 50:
                        str_val = str_val[:47] + "..."
                    values.append(str_val)
            output += " | ".join(values) + "\n"
        
        return output


class QueryExecutionError(Exception):
    """Exception raised when query execution fails."""
    pass


class TransactionError(Exception):
    """Exception raised when transaction fails."""
    pass