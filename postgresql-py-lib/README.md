# PostgreSQL Python Library

Modern PostgreSQL database library with natural language query support and comprehensive Python features.

## Features

- 🔌 **Automatic .env configuration** - Reads database settings from environment variables
- 🗣️ **Natural language queries** - Convert plain language to SQL (Turkish/English)
- 📊 **Schema inspection** - Explore database structure programmatically
- 🔄 **Transaction support** - Execute multiple queries atomically
- 🏊 **Connection pooling** - Efficient connection management
- 📝 **Type hints** - Full type safety with modern Python
- 🔍 **Query formatting** - Beautiful result display
- 🛡️ **Error handling** - Comprehensive exception management
- 🎯 **Context managers** - Automatic resource cleanup

## Installation

### For Development
```bash
# Clone and install in development mode
cd postgresql-py-lib
pip install -e .
```

### From Source
```bash
pip install -r requirements.txt
```

## Quick Start

### 1. Configure Environment

Create a `.env` file in your project:

```env
DB_HOST=localhost
DB_PORT=5432
DB_NAME=your_database
DB_USER=your_username
DB_PASSWORD=your_password
DB_SSL=false
```

### 2. Basic Usage

```python
from postgresql_py_lib import PostgreSQLClient

# Automatically reads from .env
with PostgreSQLClient() as client:
    # Execute SQL query
    result = client.query("SELECT * FROM users LIMIT 10")
    print(f"Found {result.row_count} users")
    
    # Natural language query
    response = client.natural_language_query("show all tables")
    print(response['result'].rows)
    
    # Get table information
    tables = client.get_all_tables()
    for table in tables:
        print(f"{table.schema_name}.{table.table_name}")
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DB_HOST` | localhost | Database host |
| `DB_PORT` | 5432 | Database port |
| `DB_NAME` | postgres | Database name |
| `DB_USER` | postgres | Database user |
| `DB_PASSWORD` | | Database password |
| `DB_SSL` | false | Enable SSL connection |
| `DB_MAX_CONNECTIONS` | 20 | Maximum pool connections |
| `DB_IDLE_TIMEOUT` | 30000 | Idle timeout (ms) |
| `DB_CONNECTION_TIMEOUT` | 2000 | Connection timeout (ms) |

### Custom Configuration

```python
from postgresql_py_lib import PostgreSQLClient, PostgreSQLConfig

config = PostgreSQLConfig(
    host="custom-host.com",
    database="custom_db",
    user="custom_user",
    password="custom_pass",
    max_connections=50
)

client = PostgreSQLClient(config)
```

## API Reference

### Connection Management

```python
# Manual connection
client = PostgreSQLClient()
client.connect()
client.disconnect()

# Context manager (recommended)
with PostgreSQLClient() as client:
    # Automatically connects and disconnects
    pass

# Test connection
is_connected = client.test_connection()
```

### Query Execution

```python
# Simple query
result = client.query("SELECT * FROM users WHERE age > %s", [18])

# Query with options
result = client.query(
    "SELECT * FROM orders",
    options={"limit": 100, "log_query": True}
)

# Multiple queries in transaction
results = client.query_many([
    {"sql": "INSERT INTO logs (action) VALUES (%s)", "params": ["login"]},
    {"sql": "UPDATE users SET last_login = NOW() WHERE id = %s", "params": [user_id]}
])

# Custom transaction
def my_transaction(cursor):
    cursor.execute("SELECT COUNT(*) FROM users")
    return cursor.fetchone()['count']

count = client.transaction(my_transaction)
```

### Natural Language Queries

```python
# Supported patterns
response = client.natural_language_query("show tables")
response = client.natural_language_query("tabloları listele")  # Turkish
response = client.natural_language_query("describe users table")
response = client.natural_language_query("count rows in products")
response = client.natural_language_query("database info")

# Get suggestions
suggestions = client.get_query_suggestions("show")
```

### Schema Inspection

```python
# Get all tables
tables = client.get_all_tables()

# Get tables in specific schema
public_tables = client.get_tables("public")

# Get table columns
columns = client.get_table_columns("users")

# Get comprehensive table info
table_info = client.get_table_info("users")
print(f"Table has {table_info.row_count} rows, size: {table_info.table_size}")

# Check if table exists
exists = client.table_exists("users")

# Get all schemas
schemas = client.get_schemas()

# Get database statistics
stats = client.get_database_stats()
print(f"Database: {stats.database_name}")
print(f"Version: {stats.postgresql_version}")
```

### Result Formatting

```python
result = client.query("SELECT * FROM users LIMIT 5")

# Format as table
formatted = client.format_results(result)
print(formatted)

# Access raw data
for row in result.rows:
    print(f"User: {row['name']}, Email: {row['email']}")

# Metadata
print(f"Query took {result.execution_time_ms:.2f}ms")
print(f"Returned {result.row_count} rows")
print(f"Columns: {result.field_names}")
```

## Examples

### Basic Usage
```python
# See examples/basic_usage.py
from postgresql_py_lib import PostgreSQLClient

with PostgreSQLClient() as client:
    # Simple operations
    result = client.query("SELECT NOW()")
    tables = client.get_all_tables()
    nl_result = client.natural_language_query("show users")
```

### Advanced Operations
```python
# See examples/advanced_usage.py

# Transaction with multiple operations
def complex_operation(cursor):
    cursor.execute("CREATE TEMP TABLE calc (id INT, value INT)")
    cursor.execute("INSERT INTO calc VALUES (1, 100), (2, 200)")
    cursor.execute("SELECT SUM(value) FROM calc")
    return cursor.fetchone()['sum']

with PostgreSQLClient() as client:
    total = client.transaction(complex_operation)
    print(f"Total: {total}")
```

### Error Handling
```python
try:
    with PostgreSQLClient() as client:
        result = client.query("SELECT * FROM users")
except ConnectionError as e:
    print(f"Could not connect to database: {e}")
except QueryExecutionError as e:
    print(f"Query failed: {e}")
except Exception as e:
    print(f"Unexpected error: {e}")
```

## Natural Language Support

### English Patterns
- "show tables"
- "list users" 
- "describe [table] table"
- "count rows in [table]"
- "database info"
- "size of [table]"
- "indexes on [table]"

### Turkish Patterns  
- "tabloları listele"
- "kullanıcıları göster"
- "[tablo] tablosunu açıkla"
- "[tablo] kayıt sayısı"
- "veritabanı bilgileri"
- "[tablo] boyutu"
- "[tablo] indeksleri"

## Best Practices

### 1. Use Context Managers
```python
# ✅ Good - automatic cleanup
with PostgreSQLClient() as client:
    result = client.query("SELECT * FROM users")

# ❌ Avoid - manual cleanup required
client = PostgreSQLClient()
client.connect()
result = client.query("SELECT * FROM users")
client.disconnect()
```

### 2. Use Parameterized Queries
```python
# ✅ Safe - prevents SQL injection
user_id = 123
client.query("SELECT * FROM users WHERE id = %s", [user_id])

# ❌ Dangerous - SQL injection risk
client.query(f"SELECT * FROM users WHERE id = {user_id}")
```

### 3. Handle Errors Properly
```python
try:
    with PostgreSQLClient() as client:
        result = client.query("SELECT * FROM users")
except (ConnectionError, QueryExecutionError) as e:
    logger.error(f"Database error: {e}")
    # Handle error appropriately
```

### 4. Use Transactions for Multiple Operations
```python
# ✅ Atomic operations
queries = [
    {"sql": "INSERT INTO users (name) VALUES (%s)", "params": ["John"]},
    {"sql": "INSERT INTO audit (action) VALUES (%s)", "params": ["user_created"]}
]
client.query_many(queries)
```

## Type Safety

The library includes comprehensive type hints:

```python
from postgresql_py_lib import PostgreSQLClient, QueryResult, TableInfo

client: PostgreSQLClient = PostgreSQLClient()
result: QueryResult = client.query("SELECT * FROM users")
tables: List[TableInfo] = client.get_all_tables()
```

## Logging

Enable query logging:

```python
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)

# Enable query logging
result = client.query(
    "SELECT * FROM users", 
    options={"log_query": True}
)
```

## Requirements

- Python 3.8+
- psycopg2-binary >= 2.9.0
- python-dotenv >= 1.0.0
- typing-extensions >= 4.0.0

## Development

```bash
# Install development dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Type checking
mypy src/

# Code formatting
black src/
isort src/
```

## License

MIT License - see LICENSE file for details.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests pass
5. Submit a pull request

## Support

For issues and questions:
- Check the examples in the `examples/` directory
- Review this README
- Create an issue on GitHub