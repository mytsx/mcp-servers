"""PostgreSQL connection management with modern Python features."""

import os
import logging
from contextlib import contextmanager
from typing import Generator, Optional, Dict, Any, Union
import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

from .types import PostgreSQLConfig, ConnectionPoolStats

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Modern PostgreSQL connection manager with pooling and context management."""
    
    def __init__(self, config: Optional[PostgreSQLConfig] = None) -> None:
        """Initialize connection manager with optional config override."""
        # Load environment variables
        load_dotenv()
        
        # Set up configuration
        self.config = config or self._load_config_from_env()
        self._pool: Optional[pool.SimpleConnectionPool] = None
        self._is_connected = False
        
    def _load_config_from_env(self) -> PostgreSQLConfig:
        """Load configuration from environment variables."""
        return PostgreSQLConfig(
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", "5432")),
            database=os.getenv("DB_NAME", "postgres"),
            user=os.getenv("DB_USER", "postgres"),
            password=os.getenv("DB_PASSWORD", ""),
            ssl=self._parse_ssl_config(),
            max_connections=int(os.getenv("DB_MAX_CONNECTIONS", "20")),
            idle_timeout=int(os.getenv("DB_IDLE_TIMEOUT", "30000")),
            connection_timeout=int(os.getenv("DB_CONNECTION_TIMEOUT", "2000")),
        )
        
    def _parse_ssl_config(self) -> Union[Dict[str, Any], bool]:
        """Parse SSL configuration from environment."""
        ssl_enabled = os.getenv("DB_SSL", "false").lower() == "true"
        if not ssl_enabled:
            return False
            
        return {
            "sslmode": os.getenv("DB_SSL_MODE", "require"),
            "sslcert": os.getenv("DB_SSL_CERT"),
            "sslkey": os.getenv("DB_SSL_KEY"),
            "sslrootcert": os.getenv("DB_SSL_ROOT_CERT"),
        }
    
    def connect(self) -> None:
        """Establish connection pool."""
        if self._is_connected:
            return
            
        try:
            # Build connection arguments
            conn_kwargs = {
                "minconn": 1,
                "maxconn": self.config.max_connections,
                "host": self.config.host,
                "port": self.config.port,
                "database": self.config.database,
                "user": self.config.user,
                "password": self.config.password,
                "connect_timeout": self.config.connection_timeout // 1000  # Convert to seconds
            }
            
            # Add SSL parameters if configured
            if isinstance(self.config.ssl, dict):
                conn_kwargs.update(self.config.ssl)
            elif self.config.ssl is False:
                conn_kwargs["sslmode"] = "disable"

            self._pool = pool.SimpleConnectionPool(**conn_kwargs)
            
            # Test connection directly from pool
            test_conn = self._pool.getconn()
            try:
                with test_conn.cursor() as cursor:
                    cursor.execute("SELECT 1")
            finally:
                self._pool.putconn(test_conn)
                    
            self._is_connected = True
            logger.info(f"Connected to PostgreSQL database: {self.config.database}")
            
        except Exception as e:
            logger.error(f"Failed to connect to PostgreSQL: {e}")
            raise ConnectionError(f"Database connection failed: {e}")
    
    def disconnect(self) -> None:
        """Close all connections in the pool."""
        if self._pool:
            self._pool.closeall()
            self._pool = None
            self._is_connected = False
            logger.info("Disconnected from PostgreSQL")
    
    @contextmanager
    def get_connection(self) -> Generator[psycopg2.extensions.connection, None, None]:
        """Get a connection from the pool with context management."""
        if not self._is_connected or not self._pool:
            raise ConnectionError("Not connected to database. Call connect() first.")
            
        conn = None
        try:
            conn = self._pool.getconn()
            conn.autocommit = True
            yield conn
        finally:
            if conn:
                self._pool.putconn(conn)
    
    @contextmanager
    def get_cursor(
        self, 
        connection: Optional[psycopg2.extensions.connection] = None,
        dict_cursor: bool = True
    ) -> Generator[psycopg2.extensions.cursor, None, None]:
        """Get a cursor with context management."""
        if connection:
            # Use provided connection
            cursor_factory = RealDictCursor if dict_cursor else None
            cursor = connection.cursor(cursor_factory=cursor_factory)
            try:
                yield cursor
            finally:
                cursor.close()
        else:
            # Get connection from pool
            with self.get_connection() as conn:
                cursor_factory = RealDictCursor if dict_cursor else None
                cursor = conn.cursor(cursor_factory=cursor_factory)
                try:
                    yield cursor
                finally:
                    cursor.close()
    
    def test_connection(self) -> bool:
        """Test if the database connection is working."""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT 1")
                    return True
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return False
    
    def get_pool_stats(self) -> ConnectionPoolStats:
        """Get connection pool statistics."""
        if not self._pool:
            return ConnectionPoolStats(
                total_connections=0,
                idle_connections=0,
                active_connections=0,
                waiting_connections=0
            )
            
        # Note: psycopg2's SimpleConnectionPool doesn't expose detailed stats
        # This is a simplified implementation
        return ConnectionPoolStats(
            total_connections=self.config.max_connections,
            idle_connections=0,  # Not available in SimpleConnectionPool
            active_connections=0,  # Not available in SimpleConnectionPool
            waiting_connections=0   # Not available in SimpleConnectionPool
        )
    
    def __enter__(self) -> "ConnectionManager":
        """Context manager entry."""
        self.connect()
        return self
    
    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit."""
        self.disconnect()
    
    @property
    def is_connected(self) -> bool:
        """Check if connection manager is connected."""
        return self._is_connected