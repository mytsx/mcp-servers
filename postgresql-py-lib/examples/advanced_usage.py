"""Advanced usage examples for PostgreSQL Python library."""

import time
from typing import Dict, Any, List
from postgresql_py_lib import PostgreSQLClient, QueryOptions


def transaction_example():
    """Example 1: Transaction handling."""
    print("=== Transaction Example ===")
    
    with PostgreSQLClient() as client:
        try:
            # Example 1: Multiple queries in a transaction
            queries = [
                {
                    "sql": "CREATE TEMP TABLE temp_log (id SERIAL, message TEXT, created_at TIMESTAMP DEFAULT NOW())",
                    "params": []
                },
                {
                    "sql": "INSERT INTO temp_log (message) VALUES (%s), (%s), (%s)",
                    "params": ["Transaction started", "Processing data", "Transaction completed"]
                },
                {
                    "sql": "SELECT COUNT(*) as log_count FROM temp_log",
                    "params": []
                }
            ]
            
            results = client.query_many(queries)
            print(f"✅ Transaction completed with {len(results)} queries")
            
            # Show results from the SELECT query
            if results[-1].rows:
                count = results[-1].rows[0]['log_count']
                print(f"Log entries created: {count}")
                
        except Exception as e:
            print(f"❌ Transaction failed: {e}")


def custom_transaction_example():
    """Example 2: Custom transaction with callback."""
    print("\n=== Custom Transaction Example ===")
    
    def transaction_callback(cursor) -> Dict[str, Any]:
        """Custom transaction logic."""
        # Create temporary calculations table
        cursor.execute("""
            CREATE TEMP TABLE calculations (
                id SERIAL PRIMARY KEY,
                value NUMERIC,
                square NUMERIC,
                cube NUMERIC
            )
        """)
        
        # Insert some data
        values = [10, 20, 30, 40, 50]
        for val in values:
            cursor.execute(
                "INSERT INTO calculations (value, square, cube) VALUES (%s, %s, %s)",
                [val, val**2, val**3]
            )
        
        # Calculate statistics
        cursor.execute("""
            SELECT 
                COUNT(*) as count,
                AVG(value) as avg_value,
                SUM(square) as sum_squares,
                MAX(cube) as max_cube
            FROM calculations
        """)
        
        return dict(cursor.fetchone())
    
    with PostgreSQLClient() as client:
        try:
            result = client.transaction(transaction_callback)
            print(f"✅ Transaction result: {result}")
            
        except Exception as e:
            print(f"❌ Transaction failed: {e}")


def performance_monitoring_example():
    """Example 3: Performance monitoring and query options."""
    print("\n=== Performance Monitoring Example ===")
    
    with PostgreSQLClient() as client:
        try:
            # Query with performance monitoring
            options: QueryOptions = {
                "limit": 10,
                "log_query": True
            }
            
            start_time = time.time()
            result = client.query(
                """
                SELECT 
                    schemaname,
                    tablename,
                    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size
                FROM pg_tables 
                WHERE schemaname NOT IN ('information_schema', 'pg_catalog')
                ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC
                """,
                options=options
            )
            total_time = (time.time() - start_time) * 1000
            
            print(f"Query completed in {result.execution_time_ms:.2f}ms (total: {total_time:.2f}ms)")
            print(f"Found {result.row_count} tables")
            
            # Show largest tables
            print("\nLargest tables:")
            for row in result.rows:
                print(f"  {row['schemaname']}.{row['tablename']}: {row['size']}")
                
        except Exception as e:
            print(f"❌ Error: {e}")


def schema_exploration_example():
    """Example 4: Comprehensive schema exploration."""
    print("\n=== Schema Exploration Example ===")
    
    with PostgreSQLClient() as client:
        try:
            # Get database statistics
            stats = client.get_database_stats()
            print(f"Database: {stats.database_name}")
            print(f"PostgreSQL Version: {stats.postgresql_version}")
            print(f"Current User: {stats.current_user}")
            
            print("\nSchema Statistics:")
            for schema_stat in stats.schema_stats:
                print(f"  {schema_stat['schemaname']}: {schema_stat['table_count']} tables")
            
            # Explore first schema with tables
            if stats.schema_stats:
                schema_name = stats.schema_stats[0]['schemaname']
                tables = client.get_tables(schema_name)
                
                print(f"\nTables in '{schema_name}' schema:")
                for table in tables[:3]:  # First 3 tables
                    print(f"\n📋 Table: {table.table_name}")
                    print(f"   Owner: {table.table_owner}")
                    print(f"   Has indexes: {table.has_indexes}")
                    print(f"   Has triggers: {table.has_triggers}")
                    
                    # Get detailed table info
                    detailed_info = client.get_table_info(table.table_name, schema_name)
                    if detailed_info and detailed_info.row_count is not None:
                        print(f"   Row count: {detailed_info.row_count:,}")
                        print(f"   Size: {detailed_info.table_size}")
                    
                    # Get columns
                    columns = client.get_table_columns(table.table_name, schema_name)
                    print(f"   Columns ({len(columns)}):")
                    for col in columns[:3]:  # First 3 columns
                        nullable = "NULL" if col.is_nullable else "NOT NULL" 
                        print(f"     • {col.column_name}: {col.data_type} {nullable}")
                    
                    if len(columns) > 3:
                        print(f"     ... and {len(columns) - 3} more columns")
                        
        except Exception as e:
            print(f"❌ Error: {e}")


def natural_language_advanced_example():
    """Example 5: Advanced natural language processing."""
    print("\n=== Advanced Natural Language Example ===")
    
    with PostgreSQLClient() as client:
        try:
            # Get query suggestions
            print("Query suggestions:")
            suggestions = client.get_query_suggestions("show")
            for suggestion in suggestions:
                print(f"  • {suggestion}")
            
            print("\nTesting various natural language patterns:")
            
            test_queries = [
                "describe users table",
                "count rows in pg_tables", 
                "size of pg_tables",
                "indexes on pg_tables",
                "unknown command test"
            ]
            
            for query in test_queries:
                print(f"\n🗣️  Query: '{query}'")
                response = client.natural_language_query(query)
                
                print(f"   Pattern matched: {response['pattern_matched']}")
                print(f"   Confidence: {response['confidence']}")
                print(f"   Generated SQL: {response['generated_sql']}")
                
                if response['result']:
                    print(f"   Results: {len(response['result'].rows)} rows")
                elif response['message']:
                    print(f"   Message: {response['message'][:100]}...")
                    
        except Exception as e:
            print(f"❌ Error: {e}")


def error_handling_example():
    """Example 6: Comprehensive error handling."""
    print("\n=== Error Handling Example ===")
    
    with PostgreSQLClient() as client:
        # Test 1: Invalid SQL
        print("Test 1: Invalid SQL")
        try:
            client.query("INVALID SQL SYNTAX")
        except Exception as e:
            print(f"   ✅ Caught SQL error: {type(e).__name__}")
        
        # Test 2: Non-existent table
        print("\nTest 2: Non-existent table")
        try:
            client.query("SELECT * FROM non_existent_table_12345")
        except Exception as e:
            print(f"   ✅ Caught table error: {type(e).__name__}")
        
        # Test 3: Transaction rollback
        print("\nTest 3: Transaction rollback")
        try:
            queries = [
                {"sql": "CREATE TEMP TABLE test_rollback (id INT)"},
                {"sql": "INSERT INTO test_rollback VALUES (1)"},
                {"sql": "INVALID SQL IN TRANSACTION"}  # This will cause rollback
            ]
            client.query_many(queries)
        except Exception as e:
            print(f"   ✅ Transaction rolled back: {type(e).__name__}")
        
        # Test 4: Verify rollback worked
        print("\nTest 4: Verify rollback")
        try:
            result = client.query("SELECT COUNT(*) FROM test_rollback")
            print("   ❌ Table should not exist after rollback!")
        except Exception:
            print("   ✅ Table correctly doesn't exist after rollback")


def batch_operations_example():
    """Example 7: Batch operations and bulk processing."""
    print("\n=== Batch Operations Example ===")
    
    with PostgreSQLClient() as client:
        try:
            # Create a temporary table for testing
            client.query("""
                CREATE TEMP TABLE batch_test (
                    id SERIAL PRIMARY KEY,
                    name TEXT,
                    value INTEGER,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
            
            # Batch insert with transaction
            print("Performing batch insert...")
            
            def batch_insert_callback(cursor):
                # Insert multiple records efficiently
                data = [(f"Item {i}", i * 10) for i in range(1, 101)]
                
                cursor.executemany(
                    "INSERT INTO batch_test (name, value) VALUES (%s, %s)",
                    data
                )
                
                # Return count
                cursor.execute("SELECT COUNT(*) as count FROM batch_test")
                return cursor.fetchone()['count']
            
            count = client.transaction(batch_insert_callback)
            print(f"✅ Inserted {count} records")
            
            # Batch processing with pagination
            print("\nProcessing in batches...")
            
            batch_size = 25
            offset = 0
            total_processed = 0
            
            while True:
                result = client.query(
                    "SELECT id, name, value FROM batch_test ORDER BY id LIMIT %s OFFSET %s",
                    [batch_size, offset]
                )
                
                if not result.rows:
                    break
                
                # Process this batch
                batch_sum = sum(row['value'] for row in result.rows)
                total_processed += len(result.rows)
                
                print(f"   Batch {offset // batch_size + 1}: {len(result.rows)} records, sum: {batch_sum}")
                
                offset += batch_size
            
            print(f"✅ Processed {total_processed} total records")
            
        except Exception as e:
            print(f"❌ Error: {e}")


if __name__ == "__main__":
    print("PostgreSQL Python Library - Advanced Usage Examples")
    print("=" * 55)
    
    # Run advanced examples
    transaction_example()
    custom_transaction_example()
    performance_monitoring_example()
    schema_exploration_example()
    natural_language_advanced_example()
    error_handling_example()
    batch_operations_example()
    
    print("\n✅ All advanced examples completed!")