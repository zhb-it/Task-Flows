"""Async SQLAlchemy engine, session factory and FastAPI dependency.

No connection is opened at import time — the engine connects lazily on the
first query. This keeps the module importable (and testable) without a
running PostgreSQL instance.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    pool_pre_ping=True,
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield one :class:`AsyncSession` per request and close it afterwards."""
    async with async_session_factory() as session:
        yield session
