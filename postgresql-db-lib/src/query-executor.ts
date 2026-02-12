import { QueryResult, QueryOptions } from './types';
import { ConnectionManager } from './connection';

export class QueryExecutor {
  constructor(private connectionManager: ConnectionManager) {}

  async execute<T = any>(sql: string, params?: any[], options?: QueryOptions): Promise<QueryResult<T>> {
    const client = await this.connectionManager.getClient();
    
    try {
      // Add LIMIT if it's a SELECT query and doesn't have one
      let finalSQL = sql;
      if (options?.limit && sql.trim().toUpperCase().startsWith('SELECT') && !sql.toUpperCase().includes('LIMIT')) {
        finalSQL = `${sql} LIMIT ${options.limit}`;
      }

      const startTime = Date.now();
      const result = await client.query(finalSQL, params);
      const executionTime = Date.now() - startTime;

      if (options?.logQuery) {
        console.log(`Query executed in ${executionTime}ms: ${finalSQL}`);
      }

      return {
        rows: result.rows,
        rowCount: result.rowCount,
        fields: result.fields
      };
    } catch (error) {
      throw new Error(`Query execution failed: ${error}`);
    } finally {
      client.release();
    }
  }

  async executeMany<T = any>(queries: Array<{ sql: string; params?: any[] }>, options?: QueryOptions): Promise<QueryResult<T>[]> {
    const client = await this.connectionManager.getClient();
    const results: QueryResult<T>[] = [];

    try {
      await client.query('BEGIN');

      for (const query of queries) {
        const result = await client.query(query.sql, query.params);
        results.push({
          rows: result.rows,
          rowCount: result.rowCount,
          fields: result.fields
        });
      }

      await client.query('COMMIT');
      return results;
    } catch (error) {
      await client.query('ROLLBACK');
      throw new Error(`Transaction failed: ${error}`);
    } finally {
      client.release();
    }
  }

  async transaction<T>(callback: (client: any) => Promise<T>): Promise<T> {
    const client = await this.connectionManager.getClient();

    try {
      await client.query('BEGIN');
      const result = await callback(client);
      await client.query('COMMIT');
      return result;
    } catch (error) {
      await client.query('ROLLBACK');
      throw error;
    } finally {
      client.release();
    }
  }

  formatResults(result: QueryResult): string {
    if (!result.rows || result.rows.length === 0) {
      return 'No results found.';
    }

    const columns = result.fields.map(f => f.name);
    let output = `Results (${result.rowCount} rows):\n`;
    output += '='.repeat(60) + '\n';
    output += columns.join(' | ') + '\n';
    output += '-'.repeat(60) + '\n';

    for (const row of result.rows) {
      const values = columns.map(col => {
        const val = row[col];
        return val !== null && val !== undefined ? String(val) : 'NULL';
      });
      output += values.join(' | ') + '\n';
    }

    return output;
  }
}