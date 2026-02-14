"""Database session and engine configuration.

This module provides async SQLAlchemy engine and session management
for PostgreSQL with asyncpg driver.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.core.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    pool_pre_ping=True,
    # Increase pool size to handle background worker + API requests
    pool_size=20,
    max_overflow=10,
    connect_args={"check_same_thread": False, "timeout": 30} if "sqlite" in settings.database_url else {},
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
            await session.commit()
        except Exception:
            await session.rollback()
            raise
