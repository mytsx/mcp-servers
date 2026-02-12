import { Pool, PoolConfig, Client } from 'pg';
import { config } from 'dotenv';
import { PostgreSQLConfig } from './types';

// Load environment variables from the project using this library
config();

export class ConnectionManager {
  private pool: Pool | null = null;
  private config: PostgreSQLConfig;

  constructor(userConfig?: PostgreSQLConfig) {
    // Merge user config with environment variables
    this.config = {
      host: userConfig?.host || process.env.DB_HOST || 'localhost',
      port: userConfig?.port || process.env.DB_PORT || 5432,
      database: userConfig?.database || process.env.DB_NAME || 'postgres',
      user: userConfig?.user || process.env.DB_USER || 'postgres',
      password: userConfig?.password || process.env.DB_PASSWORD || '',
      max: userConfig?.max || 20,
      idleTimeoutMillis: userConfig?.idleTimeoutMillis || 30000,
      connectionTimeoutMillis: userConfig?.connectionTimeoutMillis || 2000,
      ssl: userConfig?.ssl || (process.env.DB_SSL === 'true' ? { rejectUnauthorized: false } : false)
    };
  }

  async connect(): Promise<void> {
    if (this.pool) {
      return;
    }

    const poolConfig: PoolConfig = {
      host: this.config.host,
      port: typeof this.config.port === 'string' ? parseInt(this.config.port) : this.config.port,
      database: this.config.database,
      user: this.config.user,
      password: this.config.password,
      max: this.config.max,
      idleTimeoutMillis: this.config.idleTimeoutMillis,
      connectionTimeoutMillis: this.config.connectionTimeoutMillis,
      ssl: this.config.ssl
    };

    this.pool = new Pool(poolConfig);

    // Test connection
    try {
      const client = await this.pool.connect();
      await client.query('SELECT 1');
      client.release();
      console.log(`Connected to PostgreSQL database: ${this.config.database}`);
    } catch (error) {
      this.pool = null;
      throw new Error(`Failed to connect to PostgreSQL: ${error}`);
    }
  }

  async disconnect(): Promise<void> {
    if (this.pool) {
      await this.pool.end();
      this.pool = null;
    }
  }

  getPool(): Pool {
    if (!this.pool) {
      throw new Error('Database connection not established. Call connect() first.');
    }
    return this.pool;
  }

  async getClient(): Promise<any> {
    const pool = this.getPool();
    return await pool.connect();
  }

  async testConnection(): Promise<boolean> {
    try {
      const client = await this.getClient();
      await client.query('SELECT 1');
      client.release();
      return true;
    } catch (error) {
      return false;
    }
  }

  getConfig(): PostgreSQLConfig {
    return { ...this.config };
  }
}