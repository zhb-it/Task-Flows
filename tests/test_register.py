"""TASK-015：注册接口的集成测试。

通过依赖覆盖把 `get_db` 指向宿主机上的真实 PostgreSQL（宿主端口 5433），
不动应用默认的容器名 engine。请求走完整 ASGI 链路（httpx ASGITransport），
测试与 fixture 处于同一事件循环。

`/register` 会提交事务，故不能用回滚清理；改用「本次运行唯一 token 前缀 +
teardown 精确删除」保证开发库零残留。
"""

import os
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.security import verify_password
from app.db.session import get_db
from app.main import app
from app.models.user import User

TEST_DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql+asyncpg://postgres:postgres@127.0.0.1:5433/taskflow"
)

# 本次运行唯一前缀：既避开与既有数据冲突，也让 teardown 能精确删除自己造的行。
RUN_TOKEN = uuid.uuid4().hex[:10]
PASSWORD = "S3cret-Passw0rd!"

engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
SessionFactory = async_sessionmaker(engine, expire_on_commit=False)


async def _override_get_db():
    async with SessionFactory() as session:
        yield session


def _username(tag: str) -> str:
    return f"reg_{RUN_TOKEN}_{tag}"


def _email(tag: str) -> str:
    return f"reg_{RUN_TOKEN}_{tag}@example.com"


def _payload(tag: str, **overrides) -> dict:
    data = {"username": _username(tag), "email": _email(tag), "password": PASSWORD}
    data.update(overrides)
    return data


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest_asyncio.fixture
async def client():
    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c
    app.dependency_overrides.pop(get_db, None)


@pytest_asyncio.fixture(autouse=True)
async def _cleanup():
    """删除本次运行前缀的所有行，保证开发库零残留。"""
    yield
    async with SessionFactory() as session:
        await session.execute(
            delete(User).where(User.username.like(f"reg_{RUN_TOKEN}%"))
        )
        await session.commit()


# --- 成功路径 -------------------------------------------------------------


async def test_register_returns_201_with_envelope(client) -> None:
    resp = await client.post("/api/v1/auth/register", json=_payload("ok"))
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["message"] == "success"
    data = body["data"]
    assert data["username"] == _username("ok")
    assert data["email"] == _email("ok")
    assert data["is_active"] is True
    assert isinstance(data["id"], int)
    assert "created_at" in data and "updated_at" in data


async def test_register_response_never_exposes_password(client) -> None:
    resp = await client.post("/api/v1/auth/register", json=_payload("noleak"))
    assert resp.status_code == 201, resp.text
    raw = resp.text
    assert "password_hash" not in raw
    assert PASSWORD not in raw
    assert "password" not in resp.json()["data"]


async def test_register_persists_argon2_hash(client) -> None:
    resp = await client.post("/api/v1/auth/register", json=_payload("stored"))
    assert resp.status_code == 201, resp.text
    user_id = resp.json()["data"]["id"]

    async with SessionFactory() as session:
        row = (
            await session.execute(select(User).where(User.id == user_id))
        ).scalar_one()

    assert row.password_hash != PASSWORD
    assert row.password_hash.startswith("$argon2id$")
    assert verify_password(PASSWORD, row.password_hash) is True
    assert verify_password("wrong-password", row.password_hash) is False


# --- 冲突路径 -------------------------------------------------------------


async def test_duplicate_username_returns_409(client) -> None:
    assert (
        await client.post("/api/v1/auth/register", json=_payload("dupuser"))
    ).status_code == 201

    resp = await client.post(
        "/api/v1/auth/register",
        json=_payload("dupuser2", username=_username("dupuser")),
    )
    assert resp.status_code == 409, resp.text
    assert "detail" in resp.json()


async def test_duplicate_email_returns_409(client) -> None:
    assert (
        await client.post("/api/v1/auth/register", json=_payload("dupemail"))
    ).status_code == 201

    resp = await client.post(
        "/api/v1/auth/register",
        json=_payload("dupemail2", email=_email("dupemail")),
    )
    assert resp.status_code == 409, resp.text
    assert "detail" in resp.json()


async def test_conflict_does_not_create_second_row(client) -> None:
    await client.post("/api/v1/auth/register", json=_payload("norow"))
    await client.post(
        "/api/v1/auth/register",
        json=_payload("norow2", username=_username("norow")),
    )

    async with SessionFactory() as session:
        rows = (
            await session.execute(
                select(User).where(User.username.like(f"reg_{RUN_TOKEN}_norow%"))
            )
        ).scalars().all()

    assert len(rows) == 1


# --- 参数校验 -------------------------------------------------------------


@pytest.mark.parametrize(
    "drop",
    ["username", "email", "password"],
)
async def test_missing_required_field_returns_422(client, drop: str) -> None:
    payload = _payload(f"missing_{drop}")
    payload.pop(drop)
    resp = await client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 422, resp.text
