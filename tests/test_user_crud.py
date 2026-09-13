"""Tests for User schemas and CRUD.

Offline tests validate the schema contract (no `password_hash` leakage).
Integration tests use a *separate* async engine pointed at the running
PostgreSQL (host port 5433) so the app's container-named engine is untouched.
Write operations only `flush` (never `commit`); the session fixture closes the
session on teardown, rolling back all work, so the dev DB stays clean even if a
run is interrupted.
"""

import os

import pytest
import pytest_asyncio
from datetime import datetime, timezone
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.crud.user import (
    create_user,
    get_user,
    get_user_by_email,
    get_user_by_username,
    get_users,
)
from app.models.user import User
from app.schemas.user import UserCreate, UserRead

TEST_DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql+asyncpg://postgres:postgres@127.0.0.1:5433/taskflow"
)


@pytest_asyncio.fixture(scope="module")
async def engine():
    eng = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session(engine):
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        yield s
    # Closing the session rolls back any uncommitted work.


# --- Offline schema contract tests ----------------------------------------


def test_user_read_excludes_password_hash():
    user = User(
        id=1,
        username="alice",
        email="alice@example.com",
        password_hash="super-secret",
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    read = UserRead.model_validate(user)
    assert read.username == "alice"
    # The hash must never round-trip through the public schema.
    assert "password_hash" not in read.model_dump()


def test_user_create_carries_plain_password():
    create = UserCreate(username="bob", email="bob@example.com", password="plain123")
    assert create.password == "plain123"
    assert "password" in create.model_dump()


# --- Integration tests against real PostgreSQL (flush-only, no commit) -----


async def test_create_and_read_back(session):
    user = await create_user(
        session, username="crud_t_a", email="crud_t_a@example.com", password_hash="h"
    )
    await session.flush()
    got = await get_user(session, user.id)
    assert got is not None
    assert got.username == "crud_t_a"
    assert got.email == "crud_t_a@example.com"
    assert got.is_active is True
    assert got.created_at is not None
    assert got.updated_at is not None


async def test_lookup_by_username_and_email(session):
    await create_user(
        session, username="crud_t_b", email="crud_t_b@example.com", password_hash="h"
    )
    await session.flush()
    assert (await get_user_by_username(session, "crud_t_b")) is not None
    assert (await get_user_by_email(session, "crud_t_b@example.com")) is not None
    assert (await get_user_by_username(session, "missing")) is None
    assert (await get_user_by_email(session, "missing@example.com")) is None
    assert (await get_user(session, 9_999_999)) is None


async def test_unique_username_enforced(session):
    # create_user flushes internally, so the duplicate INSERT raises there.
    await create_user(session, username="dup_u", email="dup1@example.com", password_hash="h")
    with pytest.raises(IntegrityError):
        await create_user(session, username="dup_u", email="dup2@example.com", password_hash="h")
    await session.rollback()


async def test_unique_email_enforced(session):
    await create_user(session, username="dup_e1", email="dup_e@example.com", password_hash="h")
    with pytest.raises(IntegrityError):
        await create_user(session, username="dup_e2", email="dup_e@example.com", password_hash="h")
    await session.rollback()


async def test_pagination(session):
    for i in range(3):
        await create_user(
            session, username=f"page_{i}", email=f"page_{i}@example.com", password_hash="h"
        )
    await session.flush()
    all_users = await get_users(session, skip=0, limit=100)
    assert len(all_users) >= 3
    single = await get_users(session, skip=1, limit=1)
    assert len(single) == 1


async def test_username_too_long_rejected_by_db(session):
    # The oversized value is rejected on flush inside create_user.
    with pytest.raises(DBAPIError):
        await create_user(
            session, username="x" * 200, email="long@example.com", password_hash="h"
        )
    await session.rollback()
