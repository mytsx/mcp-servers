"""Type definitions for PostgreSQL library."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union, TypedDict
from typing_extensions import NotRequired


@dataclass
class PostgreSQLConfig:
    """PostgreSQL connection configuration."""
    
    host: str = "localhost"
    port: int = 5432
    database: str = "postgres"
    user: str = "postgres"
    password: str = ""
    ssl: Union[bool, Dict[str, Any]] = False
    max_connections: int = 20
    idle_timeout: int = 30000
    connection_timeout: int = 2000


@dataclass
class QueryResult:
    """Result of a SQL query execution."""
    
    rows: List[Dict[str, Any]]
    row_count: int
    field_names: List[str]
    execution_time_ms: Optional[float] = None


@dataclass
class TableColumn:
    """Information about a database table column."""
    
    column_name: str
    data_type: str
    is_nullable: bool
    column_default: Optional[str] = None
    character_maximum_length: Optional[int] = None
    ordinal_position: int = 0


@dataclass
class TableInfo:
    """Information about a database table."""
    
    schema_name: str
    table_name: str
    table_owner: str
    has_indexes: bool = False
    has_rules: bool = False
    has_triggers: bool = False
    row_count: Optional[int] = None
    table_size: Optional[str] = None


@dataclass
class DatabaseStats:
    """Database statistics and information."""
    
    database_name: str
    current_user: str
    postgresql_version: str
    schema_stats: List[Dict[str, Union[str, int]]] = field(default_factory=list)


@dataclass
class NaturalLanguageQuery:
    """Natural language query with generated SQL."""
    
    original_query: str
    generated_sql: Optional[str] = None
    confidence: float = 0.0
    pattern_matched: Optional[str] = None


class QueryOptions(TypedDict, total=False):
    """Options for query execution."""
    
    limit: NotRequired[int]
    timeout: NotRequired[int]
    log_query: NotRequired[bool]
    
    
class ConnectionPoolStats(TypedDict):
    """Connection pool statistics."""
    
    total_connections: int
    idle_connections: int
    active_connections: int
    waiting_connections: int