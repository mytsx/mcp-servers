export interface PostgreSQLConfig {
  host?: string;
  port?: number | string;
  database?: string;
  user?: string;
  password?: string;
  ssl?: boolean | any;
  max?: number; // connection pool size
  idleTimeoutMillis?: number;
  connectionTimeoutMillis?: number;
}

export interface QueryResult<T = any> {
  rows: T[];
  rowCount: number;
  fields: Array<{
    name: string;
    dataTypeID: number;
    dataTypeSize: number;
    dataTypeModifier: number;
    format: string;
  }>;
}

export interface TableColumn {
  column_name: string;
  data_type: string;
  character_maximum_length?: number;
  is_nullable: string;
  column_default?: string;
  ordinal_position: number;
}

export interface TableInfo {
  schemaname: string;
  tablename: string;
  tableowner: string;
  hasindexes: boolean;
  hasrules: boolean;
  hastriggers: boolean;
}

export interface DatabaseStats {
  database_name: string;
  current_user: string;
  postgresql_version: string;
  schema_stats: Array<{
    schemaname: string;
    table_count: number;
  }>;
}

export interface NaturalLanguageQuery {
  query: string;
  generatedSQL?: string;
  confidence?: number;
}

export interface QueryOptions {
  limit?: number;
  timeout?: number;
  logQuery?: boolean;
}