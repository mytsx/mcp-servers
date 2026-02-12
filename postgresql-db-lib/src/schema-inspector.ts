import { QueryExecutor } from './query-executor';
import { TableInfo, TableColumn, DatabaseStats } from './types';

export class SchemaInspector {
  constructor(private queryExecutor: QueryExecutor) {}

  async getTables(schema: string = 'public'): Promise<TableInfo[]> {
    const sql = `
      SELECT 
        schemaname,
        tablename,
        tableowner,
        hasindexes,
        hasrules,
        hastriggers
      FROM pg_tables 
      WHERE schemaname = $1
      ORDER BY tablename
    `;
    
    const result = await this.queryExecutor.execute<TableInfo>(sql, [schema]);
    return result.rows;
  }

  async getAllTables(): Promise<TableInfo[]> {
    const sql = `
      SELECT 
        schemaname,
        tablename,
        tableowner,
        hasindexes,
        hasrules,
        hastriggers
      FROM pg_tables 
      WHERE schemaname NOT IN ('information_schema', 'pg_catalog')
      ORDER BY schemaname, tablename
    `;
    
    const result = await this.queryExecutor.execute<TableInfo>(sql);
    return result.rows;
  }

  async getTableColumns(tableName: string, schema: string = 'public'): Promise<TableColumn[]> {
    const sql = `
      SELECT 
        column_name,
        data_type,
        character_maximum_length,
        is_nullable,
        column_default,
        ordinal_position
      FROM information_schema.columns 
      WHERE table_schema = $1 AND table_name = $2
      ORDER BY ordinal_position
    `;
    
    const result = await this.queryExecutor.execute<TableColumn>(sql, [schema, tableName]);
    return result.rows;
  }

  async getTableInfo(tableName: string, schema: string = 'public'): Promise<{
    columns: TableColumn[];
    rowCount: number;
    size: string;
  }> {
    const columns = await this.getTableColumns(tableName, schema);
    
    // Get row count
    const countResult = await this.queryExecutor.execute<{ count: string }>(
      `SELECT COUNT(*) as count FROM "${schema}"."${tableName}"`
    );
    
    // Get table size
    const sizeResult = await this.queryExecutor.execute<{ size: string }>(
      `SELECT pg_size_pretty(pg_total_relation_size($1)) as size`,
      [`"${schema}"."${tableName}"`]
    );
    
    return {
      columns,
      rowCount: parseInt(countResult.rows[0].count),
      size: sizeResult.rows[0].size
    };
  }

  async getDatabaseStats(): Promise<DatabaseStats> {
    // Get basic database info
    const infoResult = await this.queryExecutor.execute<{
      database_name: string;
      current_user: string;
      postgresql_version: string;
    }>(`
      SELECT 
        current_database() as database_name,
        current_user as current_user,
        version() as postgresql_version
    `);
    
    // Get schema statistics
    const schemaResult = await this.queryExecutor.execute<{
      schemaname: string;
      table_count: number;
    }>(`
      SELECT 
        schemaname,
        COUNT(*) as table_count
      FROM pg_tables 
      WHERE schemaname NOT IN ('information_schema', 'pg_catalog')
      GROUP BY schemaname
      ORDER BY table_count DESC
    `);
    
    return {
      ...infoResult.rows[0],
      schema_stats: schemaResult.rows
    };
  }

  async getSchemas(): Promise<string[]> {
    const result = await this.queryExecutor.execute<{ schema_name: string }>(`
      SELECT schema_name 
      FROM information_schema.schemata 
      WHERE schema_name NOT IN ('information_schema', 'pg_catalog', 'pg_toast')
      ORDER BY schema_name
    `);
    
    return result.rows.map(row => row.schema_name);
  }

  async tableExists(tableName: string, schema: string = 'public'): Promise<boolean> {
    const result = await this.queryExecutor.execute<{ exists: boolean }>(`
      SELECT EXISTS (
        SELECT 1 
        FROM information_schema.tables 
        WHERE table_schema = $1 AND table_name = $2
      ) as exists
    `, [schema, tableName]);
    
    return result.rows[0].exists;
  }
}