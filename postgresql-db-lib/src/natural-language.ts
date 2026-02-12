import { QueryExecutor } from './query-executor';
import { SchemaInspector } from './schema-inspector';
import { NaturalLanguageQuery, QueryResult } from './types';

export class NaturalLanguageProcessor {
  constructor(
    private queryExecutor: QueryExecutor,
    private schemaInspector: SchemaInspector
  ) {}

  async processQuery(query: string): Promise<{
    query: NaturalLanguageQuery;
    result: QueryResult | null;
    message?: string;
  }> {
    const queryLower = query.toLowerCase();
    
    // Pattern matching for common queries
    const patterns = [
      {
        regex: /(?:show|list|göster|listele).*(?:table|tablo)/i,
        handler: () => this.listTables()
      },
      {
        regex: /(?:show|list|göster|listele).*(?:user|kullanıcı)/i,
        handler: () => this.listUsers()
      },
      {
        regex: /(?:show|list|göster|listele).*(?:schema|şema)/i,
        handler: () => this.listSchemas()
      },
      {
        regex: /(?:database|veritabanı).*(?:info|bilgi|stats|istatistik)/i,
        handler: () => this.getDatabaseInfo()
      },
      {
        regex: /(?:describe|açıkla|tanımla)\s+(?:table\s+)?(\w+)/i,
        handler: (match: RegExpMatchArray) => this.describeTable(match[1])
      },
      {
        regex: /(?:count|say)\s+(?:rows?|kayıt|satır).*(?:in|from)\s+(\w+)/i,
        handler: (match: RegExpMatchArray) => this.countRows(match[1])
      }
    ];

    // Try to match patterns
    for (const pattern of patterns) {
      const match = query.match(pattern.regex);
      if (match) {
        try {
          const { sql, result } = await pattern.handler(match);
          return {
            query: { query, generatedSQL: sql, confidence: 0.9 },
            result
          };
        } catch (error) {
          return {
            query: { query, generatedSQL: '', confidence: 0 },
            result: null,
            message: `Error: ${error}`
          };
        }
      }
    }

    // No pattern matched
    return {
      query: { query, confidence: 0 },
      result: null,
      message: this.getHelpMessage()
    };
  }

  private async listTables(): Promise<{ sql: string; result: QueryResult }> {
    const sql = `
      SELECT schemaname, tablename, tableowner 
      FROM pg_tables 
      WHERE schemaname NOT IN ('information_schema', 'pg_catalog')
      ORDER BY schemaname, tablename
    `;
    const result = await this.queryExecutor.execute(sql);
    return { sql: sql.trim(), result };
  }

  private async listUsers(): Promise<{ sql: string; result: QueryResult }> {
    const sql = `
      SELECT usename as username, usesuper as is_superuser, usecreatedb as can_create_db
      FROM pg_user 
      ORDER BY usename
    `;
    const result = await this.queryExecutor.execute(sql);
    return { sql: sql.trim(), result };
  }

  private async listSchemas(): Promise<{ sql: string; result: QueryResult }> {
    const sql = `
      SELECT schema_name, schema_owner 
      FROM information_schema.schemata 
      WHERE schema_name NOT IN ('information_schema', 'pg_catalog', 'pg_toast')
      ORDER BY schema_name
    `;
    const result = await this.queryExecutor.execute(sql);
    return { sql: sql.trim(), result };
  }

  private async getDatabaseInfo(): Promise<{ sql: string; result: QueryResult }> {
    const sql = `
      SELECT 
        current_database() as database,
        current_user as user,
        version() as postgresql_version
    `;
    const result = await this.queryExecutor.execute(sql);
    return { sql: sql.trim(), result };
  }

  private async describeTable(tableName: string): Promise<{ sql: string; result: QueryResult }> {
    const sql = `
      SELECT 
        column_name,
        data_type,
        character_maximum_length,
        is_nullable,
        column_default
      FROM information_schema.columns 
      WHERE table_name = '${tableName}'
      ORDER BY ordinal_position
    `;
    const result = await this.queryExecutor.execute(sql);
    return { sql: sql.trim(), result };
  }

  private async countRows(tableName: string): Promise<{ sql: string; result: QueryResult }> {
    const sql = `SELECT COUNT(*) as count FROM ${tableName}`;
    const result = await this.queryExecutor.execute(sql);
    return { sql, result };
  }

  private getHelpMessage(): string {
    return `Supported natural language queries:
• "show tables" / "tabloları listele"
• "show users" / "kullanıcıları göster"
• "show schemas" / "şemaları listele"
• "database info" / "veritabanı bilgileri"
• "describe [table_name]" / "tablo_adı açıkla"
• "count rows in [table_name]" / "tablo_adı içindeki kayıtları say"

For complex queries, use the SQL query method directly.`;
  }
}