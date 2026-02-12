from datetime import datetime, timezone
from typing import Optional
from sqlmodel import Field, SQLModel, create_engine, Session
from pathlib import Path
import os


class GitLog(SQLModel, table=True):
    """Model for storing Git command execution logs"""
    id: Optional[int] = Field(default=None, primary_key=True)
    command: str = Field(description="Git command/function name")
    arguments: str = Field(description="JSON string of arguments")
    output: Optional[str] = Field(default=None, description="Command output")
    error: Optional[str] = Field(default=None, description="Error message if any")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Execution timestamp")
    duration: float = Field(description="Execution duration in seconds")
    status: str = Field(description="success or error")
    repo_path: Optional[str] = Field(default=None, description="Repository path if applicable")


# Database setup
def get_db_path() -> str:
    """Get the database file path from environment variable or default location"""
    # Check for environment variable first
    db_path = os.getenv('MCP_GIT_LOG_DB_PATH')
    if db_path:
        # Ensure directory exists
        db_dir = Path(db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)
        return db_path
    
    # Default location
    db_dir = Path.home() / ".mcp-git-extended"
    db_dir.mkdir(exist_ok=True)
    return str(db_dir / "logs.db")


# Create engine with connection pooling
engine = create_engine(
    f"sqlite:///{get_db_path()}", 
    connect_args={"check_same_thread": False},
    pool_pre_ping=True,  # Verify connections before using
    pool_size=5,  # Connection pool size
    max_overflow=10  # Maximum overflow connections
)


def create_db_and_tables():
    """Create database tables"""
    SQLModel.metadata.create_all(engine)