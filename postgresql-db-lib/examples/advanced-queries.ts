import { PostgreSQLClient } from '../src';

// Example 1: Transaction handling
async function transactionExample() {
  const db = new PostgreSQLClient();
  await db.connect();
  
  try {
    // Execute multiple queries in a transaction
    const results = await db.queryMany([
      { 
        sql: 'INSERT INTO audit_log (action, timestamp) VALUES ($1, NOW())',
        params: ['user_login']
      },
      {
        sql: 'UPDATE users SET last_login = NOW() WHERE id = $1',
        params: [123]
      }
    ]);
    
    console.log('Transaction completed successfully');
    console.log('Affected rows:', results.map(r => r.rowCount));
    
  } catch (error) {
    console.error('Transaction failed:', error);
  }
  
  await db.disconnect();
}

// Example 2: Custom transaction with client
async function customTransactionExample() {
  const db = new PostgreSQLClient();
  await db.connect();
  
  const result = await db.transaction(async (client) => {
    // Create a temporary table
    await client.query(`
      CREATE TEMP TABLE temp_calculations (
        id SERIAL PRIMARY KEY,
        value NUMERIC,
        calculated_at TIMESTAMP DEFAULT NOW()
      )
    `);
    
    // Insert some data
    await client.query(
      'INSERT INTO temp_calculations (value) VALUES ($1), ($2), ($3)',
      [100, 200, 300]
    );
    
    // Calculate sum
    const sumResult = await client.query(
      'SELECT SUM(value) as total FROM temp_calculations'
    );
    
    return sumResult.rows[0].total;
  });
  
  console.log('Calculated total:', result);
  await db.disconnect();
}

// Example 3: Database statistics and monitoring
async function databaseMonitoring() {
  const db = new PostgreSQLClient();
  await db.connect();
  
  // Get database statistics
  const stats = await db.getDatabaseStats();
  console.log('Database Statistics:');
  console.log('- Database:', stats.database_name);
  console.log('- User:', stats.current_user);
  console.log('- Version:', stats.postgresql_version);
  console.log('\nSchema Statistics:');
  stats.schema_stats.forEach(schema => {
    console.log(`- ${schema.schemaname}: ${schema.table_count} tables`);
  });
  
  // Get all schemas
  const schemas = await db.getSchemas();
  console.log('\nAvailable schemas:', schemas.join(', '));
  
  await db.disconnect();
}

// Example 4: Working with large result sets
async function largeResultSetExample() {
  const db = new PostgreSQLClient();
  await db.connect();
  
  // Query with custom limit
  const result = await db.query(
    'SELECT * FROM large_table WHERE created_at > $1',
    [new Date('2024-01-01')],
    { 
      limit: 1000,
      logQuery: true // Enable query logging
    }
  );
  
  console.log(`Fetched ${result.rowCount} rows`);
  console.log('First row:', result.rows[0]);
  
  // Process results in batches
  const batchSize = 100;
  for (let i = 0; i < result.rows.length; i += batchSize) {
    const batch = result.rows.slice(i, i + batchSize);
    console.log(`Processing batch ${Math.floor(i / batchSize) + 1}: ${batch.length} rows`);
    // Process batch...
  }
  
  await db.disconnect();
}

// Example 5: Schema exploration
async function schemaExploration() {
  const db = new PostgreSQLClient();
  await db.connect();
  
  // Get all tables in public schema
  const publicTables = await db.getTables('public');
  
  // For each table, get column information
  for (const table of publicTables.slice(0, 3)) { // Limit to first 3 tables
    console.log(`\nTable: ${table.tablename}`);
    console.log('- Owner:', table.tableowner);
    console.log('- Has indexes:', table.hasindexes);
    console.log('- Has triggers:', table.hastriggers);
    
    const columns = await db.getTableColumns(table.tablename);
    console.log('- Columns:');
    columns.forEach(col => {
      const nullable = col.is_nullable === 'YES' ? 'NULL' : 'NOT NULL';
      console.log(`  ${col.column_name}: ${col.data_type} ${nullable}`);
    });
  }
  
  await db.disconnect();
}

// Example 6: Error handling
async function errorHandlingExample() {
  const db = new PostgreSQLClient();
  
  try {
    await db.connect();
    
    // Try to query a non-existent table
    try {
      await db.query('SELECT * FROM non_existent_table');
    } catch (error) {
      console.error('Query error:', error.message);
    }
    
    // Try to insert duplicate key
    try {
      await db.queryMany([
        { sql: 'INSERT INTO users (id, email) VALUES (1, "test@example.com")' },
        { sql: 'INSERT INTO users (id, email) VALUES (1, "duplicate@example.com")' }
      ]);
    } catch (error) {
      console.error('Transaction error:', error.message);
    }
    
  } catch (connectionError) {
    console.error('Connection error:', connectionError.message);
  } finally {
    await db.disconnect();
  }
}

// Run examples
if (require.main === module) {
  (async () => {
    console.log('=== Database Monitoring ===');
    await databaseMonitoring();
    
    console.log('\n=== Schema Exploration ===');
    await schemaExploration();
    
    console.log('\n=== Error Handling ===');
    await errorHandlingExample();
  })();
}