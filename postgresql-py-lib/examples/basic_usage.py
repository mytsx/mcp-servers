"""Basic usage examples for PostgreSQL Python library."""

import os
from postgresql_py_lib import PostgreSQLClient, PostgreSQLConfig


def basic_connection_example():
    """Example 1: Basic connection using .env file."""
    print("=== Basic Connection Example ===")
    
    # Create client - automatically reads from .env
    client = PostgreSQLClient()
    
    try:
        # Connect to database
        client.connect()
        print("✅ Connected to database!")
        
        # Test connection
        if client.test_connection():
            print("✅ Connection test passed")
        
        # Execute a simple query
        result = client.query("SELECT NOW() as current_time, version() as pg_version")
        if result.rows:
            print(f"Current time: {result.rows[0]['current_time']}")
            print(f"PostgreSQL version: {result.rows[0]['pg_version']}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        client.disconnect()
        print("Disconnected from database")


def custom_config_example():
    """Example 2: Using custom configuration."""
    print("\n=== Custom Configuration Example ===")
    
    # Override specific config values
    config = PostgreSQLConfig(
        host="localhost",
        database="custom_db",
        user="custom_user",
        # Other values can still come from .env or use defaults
    )
    
    client = PostgreSQLClient(config)
    
    try:
        client.connect()
        stats = client.get_database_stats()
        print(f"Database: {stats.database_name}")
        print(f"User: {stats.current_user}")
        
    except Exception as e:
        print(f"❌ Connection failed (expected if custom_db doesn't exist): {e}")
    finally:
        client.disconnect()


def context_manager_example():
    """Example 3: Using context manager for automatic cleanup."""
    print("\n=== Context Manager Example ===")
    
    try:
        # Automatic connect/disconnect with context manager
        with PostgreSQLClient() as client:
            print("✅ Connected using context manager")
            
            # Execute query
            result = client.query("SELECT current_database() as db_name")
            if result.rows:
                print(f"Database name: {result.rows[0]['db_name']}")
                
    except Exception as e:
        print(f"❌ Error: {e}")
    
    print("✅ Automatically disconnected")


def table_operations_example():
    """Example 4: Working with tables and schema."""
    print("\n=== Table Operations Example ===")
    
    with PostgreSQLClient() as client:
        try:
            # Get all tables
            tables = client.get_all_tables()
            print(f"Found {len(tables)} tables:")
            
            for table in tables[:5]:  # Show first 5 tables
                print(f"  • {table.schema_name}.{table.table_name} (owner: {table.table_owner})")
            
            # Check if a specific table exists
            if tables:
                first_table = tables[0]
                exists = client.table_exists(first_table.table_name, first_table.schema_name)
                print(f"Table {first_table.table_name} exists: {exists}")
                
                # Get table columns
                columns = client.get_table_columns(first_table.table_name, first_table.schema_name)
                print(f"Table {first_table.table_name} has {len(columns)} columns:")
                
                for col in columns[:3]:  # Show first 3 columns
                    nullable = "NULL" if col.is_nullable else "NOT NULL"
                    print(f"    {col.column_name}: {col.data_type} {nullable}")
            
            # Get schemas
            schemas = client.get_schemas()
            print(f"\nAvailable schemas: {', '.join(schemas)}")
            
        except Exception as e:
            print(f"❌ Error: {e}")


def natural_language_example():
    """Example 5: Natural language queries."""
    print("\n=== Natural Language Example ===")
    
    with PostgreSQLClient() as client:
        queries = [
            "show tables",
            "database info", 
            "list schemas",
            "show users"
        ]
        
        for query in queries:
            print(f"\n🗣️  Query: '{query}'")
            
            try:
                response = client.natural_language_query(query)
                
                print(f"Generated SQL: {response['generated_sql']}")
                print(f"Confidence: {response['confidence']}")
                
                if response['result'] and response['result'].rows:
                    print("Results:")
                    # Show first few results
                    for row in response['result'].rows[:3]:
                        print(f"  {dict(row)}")
                elif response['message']:
                    print(f"Message: {response['message']}")
                    
            except Exception as e:
                print(f"❌ Error: {e}")


def query_with_parameters_example():
    """Example 6: Parameterized queries for safety."""
    print("\n=== Parameterized Queries Example ===")
    
    with PostgreSQLClient() as client:
        try:
            # Safe parameterized query - prevents SQL injection
            schema_name = "public"
            result = client.query(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = %s LIMIT 5",
                [schema_name]
            )
            
            print(f"Tables in {schema_name} schema:")
            for row in result.rows:
                print(f"  • {row['table_name']}")
            
            print(f"Query executed in {result.execution_time_ms:.2f}ms")
            
        except Exception as e:
            print(f"❌ Error: {e}")


def formatted_results_example():
    """Example 7: Formatting query results."""
    print("\n=== Formatted Results Example ===")
    
    with PostgreSQLClient() as client:
        try:
            # Execute a query
            result = client.query(
                "SELECT schemaname, tablename, tableowner FROM pg_tables LIMIT 5"
            )
            
            # Format results as a table
            formatted = client.format_results(result)
            print("Formatted Results:")
            print(formatted)
            
        except Exception as e:
            print(f"❌ Error: {e}")


if __name__ == "__main__":
    # Make sure you have a .env file with database configuration:
    # DB_HOST=localhost
    # DB_PORT=5432  
    # DB_NAME=your_database
    # DB_USER=your_user
    # DB_PASSWORD=your_password
    
    print("PostgreSQL Python Library - Basic Usage Examples")
    print("=" * 50)
    
    # Check if .env variables are available
    if not os.getenv("DB_NAME"):
        print("⚠️  Warning: No DB_NAME found in environment variables.")
        print("Please create a .env file with your database configuration.")
        print("\nExample .env file:")
        print("DB_HOST=localhost")
        print("DB_PORT=5432")
        print("DB_NAME=your_database") 
        print("DB_USER=your_user")
        print("DB_PASSWORD=your_password")
        print()
    
    # Run examples
    basic_connection_example()
    custom_config_example()
    context_manager_example()
    table_operations_example()
    natural_language_example()
    query_with_parameters_example()
    formatted_results_example()
    
    print("\n✅ All examples completed!")