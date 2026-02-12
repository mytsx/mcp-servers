"""Async database operations for Git logs"""
import logging

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select, desc
from sqlmodel import SQLModel

from .models import GitLog, get_db_path

logger = logging.getLogger(__name__)

# Create async engine
async_engine = create_async_engine(
    f"sqlite+aiosqlite:///{get_db_path()}",
    echo=False,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10
)

# Create async session factory
async_session = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False
)


async def create_db_and_tables_async():
    """Create database tables asynchronously"""
    async with async_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


async def save_log_async(log_entry: GitLog):
    """Save a log entry asynchronously"""
    try:
        async with async_session() as session:
            session.add(log_entry)
            await session.commit()
    except Exception as e:
        logger.error(f"Failed to save log entry async: {e}")
        raise


async def get_logs_async(skip: int = 0, limit: int = 100, command: str = None, status: str = None):
    """Get logs asynchronously with filtering"""
    async with async_session() as session:
        query = select(GitLog).order_by(desc(GitLog.timestamp))
        
        if command:
            query = query.where(GitLog.command.contains(command))
        if status:
            query = query.where(GitLog.status == status)
        
        query = query.offset(skip).limit(limit)
        
        result = await session.execute(query)
        return result.scalars().all()