"""Database session and engine configuration.

This module provides async SQLAlchemy engine and session management
for PostgreSQL with asyncpg driver.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from backend.core.config import get_settings

settings = get_settings()

engine_kwargs = {
    "echo": settings.debug,
}

if "sqlite" in settings.database_url:
    engine_kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
elif settings.resolved_db_pool_mode == "null":
    engine_kwargs["poolclass"] = NullPool
else:
    engine_kwargs.update(
        {
            "pool_pre_ping": True,
            "pool_size": settings.db_pool_size,
            "max_overflow": settings.db_max_overflow,
            "pool_timeout": settings.db_pool_timeout_seconds,
            "pool_recycle": settings.db_pool_recycle_seconds,
        }
    )

engine = create_async_engine(
    settings.database_url,
    **engine_kwargs,
)

if "sqlite" in settings.database_url:
    from sqlalchemy import event
    
    @event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()

async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Get an async database session.

    Yields
    ------
    AsyncSession
        An async SQLAlchemy session.
    """
    async with async_session_maker() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
