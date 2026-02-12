import { ConnectionManager } from './connection';
import { QueryExecutor } from './query-executor';
import { SchemaInspector } from './schema-inspector';
import { NaturalLanguageProcessor } from './natural-language';
import { 
  PostgreSQLConfig, 
  QueryResult, 
  QueryOptions,
  TableInfo,
  TableColumn,
  DatabaseStats
} from './types';

export * from './types';

export class PostgreSQLClient {
  private connectionManager: ConnectionManager;
  private queryExecutor: QueryExecutor;
  private schemaInspector: SchemaInspector;
  private naturalLanguageProcessor: NaturalLanguageProcessor;

  constructor(config?: PostgreSQLConfig) {
    this.connectionManager = new ConnectionManager(config);
    this.queryExecutor = new QueryExecutor(this.connectionManager);
    this.schemaInspector = new SchemaInspector(this.queryExecutor);
    this.naturalLanguageProcessor = new NaturalLanguageProcessor(
      this.queryExecutor,
      this.schemaInspector
    );
  }

  /**
   * Connect to the PostgreSQL database
   */
  async connect(): Promise<void> {
    await this.connectionManager.connect();
  }

  /**
   * Disconnect from the PostgreSQL database
   */
  async disconnect(): Promise<void> {
    await this.connectionManager.disconnect();
  }

  /**
   * Execute a SQL query
   */
  async query<T = any>(sql: string, params?: any[], options?: QueryOptions): Promise<QueryResult<T>> {
    return await this.queryExecutor.execute<T>(sql, params, options);
  }

  /**
   * Execute multiple queries in a transaction
   */
  async queryMany<T = any>(queries: Array<{ sql: string; params?: any[] }>, options?: QueryOptions): Promise<QueryResult<T>[]> {
    return await this.queryExecutor.executeMany<T>(queries, options);
  }

  /**
   * Execute queries within a transaction
   */
  async transaction<T>(callback: (client: any) => Promise<T>): Promise<T> {
    return await this.queryExecutor.transaction(callback);
  }

  /**
   * Process a natural language query
   */
  async naturalLanguageQuery(query: string): Promise<{
    sql?: string;
    result?: QueryResult;
    message?: string;
  }> {
    const response = await this.naturalLanguageProcessor.processQuery(query);
    return {
      sql: response.query.generatedSQL,
      result: response.result || undefined,
      message: response.message
    };
  }

  /**
   * Get all tables in the database
   */
  async getTables(schema?: string): Promise<TableInfo[]> {
    return schema 
      ? await this.schemaInspector.getTables(schema)
      : await this.schemaInspector.getAllTables();
  }

  /**
   * Get columns for a specific table
   */
  async getTableColumns(tableName: string, schema: string = 'public'): Promise<TableColumn[]> {
    return await this.schemaInspector.getTableColumns(tableName, schema);
  }

  /**
   * Get detailed information about a table
   */
  async getTableInfo(tableName: string, schema: string = 'public'): Promise<{
    columns: TableColumn[];
    rowCount: number;
    size: string;
  }> {
    return await this.schemaInspector.getTableInfo(tableName, schema);
  }

  /**
   * Get database statistics
   */
  async getDatabaseStats(): Promise<DatabaseStats> {
    return await this.schemaInspector.getDatabaseStats();
  }

  /**
   * Get all schemas in the database
   */
  async getSchemas(): Promise<string[]> {
    return await this.schemaInspector.getSchemas();
  }

  /**
   * Check if a table exists
   */
  async tableExists(tableName: string, schema: string = 'public'): Promise<boolean> {
    return await this.schemaInspector.tableExists(tableName, schema);
  }

  /**
   * Format query results as a string table
   */
  formatResults(result: QueryResult): string {
    return this.queryExecutor.formatResults(result);
  }

  /**
   * Test database connection
   */
  async testConnection(): Promise<boolean> {
    return await this.connectionManager.testConnection();
  }

  /**
   * Get current connection configuration
   */
  getConfig(): PostgreSQLConfig {
    return this.connectionManager.getConfig();
  }
}

// Default export
export default PostgreSQLClient;