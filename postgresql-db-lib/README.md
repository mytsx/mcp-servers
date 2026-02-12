# PostgreSQL Database Library

A TypeScript/JavaScript library for PostgreSQL database operations with natural language query support. This library automatically reads database connection settings from your project's `.env` file.

## Features

- 🔌 **Automatic .env configuration** - Reads DB settings from your project's environment
- 🗣️ **Natural language queries** - Convert plain language to SQL
- 📊 **Schema inspection** - Explore database structure programmatically
- 🔄 **Transaction support** - Execute multiple queries atomically
- 🏊 **Connection pooling** - Efficient connection management
- 📝 **TypeScript support** - Full type definitions included
- 🔍 **Query formatting** - Beautiful result formatting

## Installation

```bash
npm install postgresql-db-lib
```

## Quick Start

### 1. Set up your `.env` file

Add these variables to your project's `.env` file:

```env
DB_HOST=localhost
DB_PORT=5432
DB_NAME=mydatabase
DB_USER=myuser
DB_PASSWORD=mypassword
DB_SSL=false
```

### 2. Basic usage

```typescript
import { PostgreSQLClient } from 'postgresql-db-lib';

// Automatically uses .env configuration
const db = new PostgreSQLClient();

async function main() {
  // Connect to database
  await db.connect();
  
  // Execute a query
  const result = await db.query('SELECT * FROM users LIMIT 10');
  console.log(result.rows);
  
  // Natural language query
  const nlResult = await db.naturalLanguageQuery('show all tables');
  console.log(nlResult.result);
  
  // Disconnect
  await db.disconnect();
}

main();
```

## Configuration

The library automatically reads from environment variables, but you can override specific settings:

```typescript
const db = new PostgreSQLClient({
  host: 'custom-host.com',     // Override host
  port: 5433,                  // Override port
  // Other settings still come from .env
});
```

### Available configuration options:

- `host` - Database host (default: localhost)
- `port` - Database port (default: 5432)
- `database` - Database name
- `user` - Database user
- `password` - Database password
- `ssl` - SSL configuration
- `max` - Maximum pool size (default: 20)
- `idleTimeoutMillis` - Idle timeout (default: 30000)
- `connectionTimeoutMillis` - Connection timeout (default: 2000)

## API Reference

### Connection Management

```typescript
// Connect to database
await db.connect();

// Test connection
const isConnected = await db.testConnection();

// Get current configuration
const config = db.getConfig();

// Disconnect
await db.disconnect();
```

### Query Execution

```typescript
// Simple query
const result = await db.query('SELECT * FROM users WHERE age > $1', [18]);

// Query with options
const result = await db.query(
  'SELECT * FROM orders',
  [],
  { 
    limit: 100,      // Auto-add LIMIT clause
    logQuery: true   // Log query execution time
  }
);

// Multiple queries in transaction
const results = await db.queryMany([
  { sql: 'INSERT INTO logs (action) VALUES ($1)', params: ['login'] },
  { sql: 'UPDATE users SET last_login = NOW() WHERE id = $1', params: [userId] }
]);

// Custom transaction
const result = await db.transaction(async (client) => {
  await client.query('INSERT INTO ...');
  const result = await client.query('SELECT ...');
  return result.rows;
});
```

### Natural Language Queries

```typescript
// Supported patterns
const result = await db.naturalLanguageQuery('show tables');
const result = await db.naturalLanguageQuery('list users');
const result = await db.naturalLanguageQuery('database info');
const result = await db.naturalLanguageQuery('describe products table');
const result = await db.naturalLanguageQuery('count rows in orders');
```

### Schema Inspection

```typescript
// Get all tables
const tables = await db.getTables();

// Get tables in specific schema
const publicTables = await db.getTables('public');

// Get table columns
const columns = await db.getTableColumns('users');

// Get detailed table information
const info = await db.getTableInfo('users');
console.log(info.columns);    // Column definitions
console.log(info.rowCount);   // Number of rows
console.log(info.size);       // Table size

// Check if table exists
const exists = await db.tableExists('users');

// Get all schemas
const schemas = await db.getSchemas();

// Get database statistics
const stats = await db.getDatabaseStats();
```

### Result Formatting

```typescript
const result = await db.query('SELECT * FROM users LIMIT 5');
const formatted = db.formatResults(result);
console.log(formatted);
// Results (5 rows):
// ============================================================
// id | name | email | created_at
// ------------------------------------------------------------
// 1 | John | john@example.com | 2024-01-01
// ...
```

## Examples

See the `examples` directory for more detailed examples:

- `basic-usage.ts` - Simple queries and connections
- `advanced-queries.ts` - Transactions, error handling, and monitoring

## Error Handling

```typescript
try {
  await db.connect();
  const result = await db.query('SELECT * FROM users');
} catch (error) {
  if (error.message.includes('connect')) {
    console.error('Connection failed:', error);
  } else {
    console.error('Query failed:', error);
  }
} finally {
  await db.disconnect();
}
```

## Best Practices

1. **Always disconnect**: Use try/finally to ensure connections are closed
2. **Use parameterized queries**: Prevent SQL injection with `$1, $2` placeholders
3. **Handle errors**: Wrap database operations in try/catch blocks
4. **Use transactions**: Group related queries for consistency
5. **Set appropriate pool size**: Configure `max` based on your application needs

## TypeScript Support

The library includes full TypeScript definitions. You can type your query results:

```typescript
interface User {
  id: number;
  name: string;
  email: string;
}

const result = await db.query<User>('SELECT * FROM users');
result.rows.forEach(user => {
  console.log(user.name); // TypeScript knows this is a string
});
```

## License

MIT