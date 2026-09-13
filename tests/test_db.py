"""Tests for the async SQLAlchemy engine, session factory and `get_db` dependency.

These tests do not require a running PostgreSQL: the engine connects lazily,
and a session obtained from the factory only opens a connection when a query
is executed, so `Base`/engine/factory types and the `get_db` contract are
verifiable offline.
"""

import inspect

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.ext.asyncio.engine import AsyncEngine

from app.db.base import Base
from app.db.session import async_session_factory, engine, get_db


def test_base_has_metadata():
    assert Base.metadata is not None


def test_engine_is_async_engine():
    assert isinstance(engine, AsyncEngine)


def test_session_factory_is_async_sessionmaker():
    assert isinstance(async_session_factory, async_sessionmaker)


async def test_session_factory_yields_async_session():
    async with async_session_factory() as session:
        assert isinstance(session, AsyncSession)
        # No transaction is open until the first operation.
        assert session.in_transaction() is False


def test_get_db_is_async_generator():
    assert inspect.isasyncgenfunction(get_db)


async def test_get_db_yields_session_and_closes():
    gen = get_db()
    session = await gen.__anext__()
    try:
        assert isinstance(session, AsyncSession)
    finally:
        # Running cleanup closes the (never-connected) session safely.
        await gen.aclose()
