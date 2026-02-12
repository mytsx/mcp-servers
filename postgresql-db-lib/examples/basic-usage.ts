import { PostgreSQLClient } from '../src';

// Example 1: Basic connection and query
async function basicExample() {
  // Create client - will use .env file from your project
  const db = new PostgreSQLClient();
  
  try {
    // Connect to database
    await db.connect();
    console.log('Connected to database!');
    
    // Execute a simple query
    const result = await db.query('SELECT NOW() as current_time');
    console.log('Current time:', result.rows[0].current_time);
    
    // Disconnect
    await db.disconnect();
  } catch (error) {
    console.error('Error:', error);
  }
}

// Example 2: Using custom configuration
async function customConfigExample() {
  // Override specific config values
  const db = new PostgreSQLClient({
    host: 'custom-host.com',
    database: 'myapp_db',
    // Other values will still come from .env
  });
  
  await db.connect();
  const connected = await db.testConnection();
  console.log('Connection test:', connected);
  await db.disconnect();
}

// Example 3: Working with tables
async function tableOperations() {
  const db = new PostgreSQLClient();
  await db.connect();
  
  // Get all tables
  const tables = await db.getTables();
  console.log('Tables in database:');
  tables.forEach(table => {
    console.log(`- ${table.schemaname}.${table.tablename}`);
  });
  
  // Check if a table exists
  const exists = await db.tableExists('users');
  console.log('Users table exists:', exists);
  
  if (exists) {
    // Get table information
    const tableInfo = await db.getTableInfo('users');
    console.log('Users table info:');
    console.log('- Columns:', tableInfo.columns.length);
    console.log('- Row count:', tableInfo.rowCount);
    console.log('- Size:', tableInfo.size);
    
    // Get column details
    tableInfo.columns.forEach(col => {
      console.log(`  ${col.column_name}: ${col.data_type}`);
    });
  }
  
  await db.disconnect();
}

// Example 4: Natural language queries
async function naturalLanguageExample() {
  const db = new PostgreSQLClient();
  await db.connect();
  
  const queries = [
    'show tables',
    'database info',
    'list users',
    'describe users table'
  ];
  
  for (const query of queries) {
    console.log(`\nNatural language query: "${query}"`);
    const result = await db.naturalLanguageQuery(query);
    
    if (result.sql) {
      console.log('Generated SQL:', result.sql);
    }
    
    if (result.result) {
      console.log('Results:', db.formatResults(result.result));
    } else if (result.message) {
      console.log('Message:', result.message);
    }
  }
  
  await db.disconnect();
}

// Example 5: Parameterized queries
async function parameterizedQueries() {
  const db = new PostgreSQLClient();
  await db.connect();
  
  // Safe parameterized query
  const userId = 123;
  const result = await db.query(
    'SELECT * FROM users WHERE id = $1',
    [userId],
    { limit: 1 }
  );
  
  if (result.rows.length > 0) {
    console.log('User found:', result.rows[0]);
  }
  
  await db.disconnect();
}

// Run examples
if (require.main === module) {
  (async () => {
    console.log('=== Basic Example ===');
    await basicExample();
    
    console.log('\n=== Table Operations ===');
    await tableOperations();
    
    console.log('\n=== Natural Language Example ===');
    await naturalLanguageExample();
  })();
}