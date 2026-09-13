"""TASK-017：`GET /users/me` 的测试。

覆盖三组行为：

1. 凭证缺失/方案不对 → 401，且带 `WWW-Authenticate: Bearer`。
2. Token 本身不可用（伪造签名、已过期、类别不符、subject 非法）→ 401。
3. 账号状态规则：账号不存在 → 401；账号被禁用 → 403；正常 → 200。

集成测试沿用「本次运行唯一前缀 + teardown 精确删除」，
保证开发库零残留（TASK-015/016 的既有做法）。
"""

import os
import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.core.security import ACCESS_TOKEN_TYPE, create_access_token
from app.db.session import get_db
from app.main import app
from app.models.user import User

TEST_DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql+asyncpg://postgres:postgres@127.0.0.1:5433/taskflow"
)

RUN_TOKEN = uuid.uuid4().hex[:10]
PASSWORD = "S3cret-Passw0rd!"
# 远大于 users.id 自增序列，保证对应不到任何真实用户。
UNKNOWN_USER_ID = 9_000_000_000

engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
SessionFactory = async_sessionmaker(engine, expire_on_commit=False)


async def _override_get_db():
    async with SessionFactory() as session:
        yield session


def _username(tag: str) -> str:
    return f"usersme_{RUN_TOKEN}_{tag}"


def _email(tag: str) -> str:
    return f"usersme_{RUN_TOKEN}_{tag}@example.com"


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
            delete(User).where(User.username.like(f"usersme_{RUN_TOKEN}%"))
        )
        await session.commit()


async def _register(client, tag: str) -> dict:
    """注册一个可用账号，返回响应中的 `data` 字段。"""
    resp = await client.post(
        "/api/v1/auth/register",
        json={"username": _username(tag), "email": _email(tag), "password": PASSWORD},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _set_active(user_id: int, active: bool) -> None:
    async with SessionFactory() as session:
        await session.execute(
            update(User).where(User.id == user_id).values(is_active=active)
        )
        await session.commit()


async def _read_user(user_id: int) -> User:
    async with SessionFactory() as session:
        return (await session.execute(select(User).where(User.id == user_id))).scalar_one()


def _token_with(payload: dict, *, secret: str | None = None) -> str:
    """构造一个签名可控的 Token，用于测试各类非法输入。"""
    settings = get_settings()
    return jwt.encode(
        payload,
        secret if secret is not None else settings.jwt_secret_key,
        algorithm="HS256",
    )


# --- 成功路径 -------------------------------------------------------------


async def test_returns_current_user_with_valid_token(client) -> None:
    data = await _register(client, "ok")

    resp = await client.get(
        "/api/v1/users/me", headers=_auth(create_access_token(data["id"]))
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["message"] == "success"
    assert body["data"]["id"] == data["id"]
    assert body["data"]["username"] == data["username"]
    assert body["data"]["email"] == data["email"]
    assert body["data"]["is_active"] is True
    assert body["data"]["created_at"] and body["data"]["updated_at"]


async def test_response_never_exposes_password(client) -> None:
    data = await _register(client, "noleak")

    resp = await client.get(
        "/api/v1/users/me", headers=_auth(create_access_token(data["id"]))
    )

    assert resp.status_code == 200, resp.text
    assert PASSWORD not in resp.text
    assert "password_hash" not in resp.text


async def test_me_does_not_mutate_user(client) -> None:
    data = await _register(client, "nomutate")
    before = await _read_user(data["id"])

    resp = await client.get(
        "/api/v1/users/me", headers=_auth(create_access_token(data["id"]))
    )
    assert resp.status_code == 200, resp.text

    after = await _read_user(data["id"])
    assert after.is_active is True
    assert after.password_hash == before.password_hash
    assert after.updated_at == before.updated_at


async def test_endpoint_is_registered_in_openapi(client) -> None:
    resp = await client.get("/openapi.json")

    assert resp.status_code == 200
    schema = resp.json()
    assert "get" in schema["paths"]["/api/v1/users/me"]
    # 该端点必须声明为受保护端点。
    assert "security" in schema["paths"]["/api/v1/users/me"]["get"]


# --- 凭证缺失或方案不对 ---------------------------------------------------


async def test_missing_authorization_header_returns_401(client) -> None:
    resp = await client.get("/api/v1/users/me")

    assert resp.status_code == 401, resp.text
    assert resp.headers.get("www-authenticate") == "Bearer"
    assert "detail" in resp.json()


@pytest.mark.parametrize("header", ["Bearer", "Bearer ", "Basic YWxpY2U6cHc=", "Token x"])
async def test_unsupported_authorization_scheme_returns_401(client, header: str) -> None:
    resp = await client.get("/api/v1/users/me", headers={"Authorization": header})

    assert resp.status_code == 401, resp.text
    assert resp.headers.get("www-authenticate") == "Bearer"


# --- Token 本身不可用 -----------------------------------------------------


async def test_token_signed_with_other_secret_returns_401(client) -> None:
    await _register(client, "forged")
    forged = _token_with(
        {"sub": "1", "type": ACCESS_TOKEN_TYPE},
        secret="attacker-secret-" * 3,  # >= 32 bytes，只有密钥是错的
    )

    resp = await client.get("/api/v1/users/me", headers=_auth(forged))

    assert resp.status_code == 401, resp.text


async def test_expired_token_returns_401(client) -> None:
    data = await _register(client, "expired")
    now = datetime.now(timezone.utc)
    expired = _token_with(
        {
            "sub": str(data["id"]),
            "type": ACCESS_TOKEN_TYPE,
            "iat": now - timedelta(hours=2),
            "exp": now - timedelta(hours=1),
        }
    )

    resp = await client.get("/api/v1/users/me", headers=_auth(expired))

    assert resp.status_code == 401, resp.text


async def test_refresh_token_type_returns_401(client) -> None:
    """TASK-018 的 Refresh Token 不能用于访问受保护资源。"""
    data = await _register(client, "refresh")
    now = datetime.now(timezone.utc)
    refresh_like = _token_with(
        {
            "sub": str(data["id"]),
            "type": "refresh",
            "iat": now,
            "exp": now + timedelta(days=7),
        }
    )

    resp = await client.get("/api/v1/users/me", headers=_auth(refresh_like))

    assert resp.status_code == 401, resp.text


@pytest.mark.parametrize("subject", [None, "not-a-number", "1.5", ""])
async def test_malformed_subject_returns_401(client, subject) -> None:
    now = datetime.now(timezone.utc)
    token = _token_with(
        {
            "sub": subject,
            "type": ACCESS_TOKEN_TYPE,
            "iat": now,
            "exp": now + timedelta(minutes=30),
        }
    )

    resp = await client.get("/api/v1/users/me", headers=_auth(token))

    assert resp.status_code == 401, resp.text


# --- 账号状态规则 ---------------------------------------------------------


async def test_token_for_unknown_user_returns_401(client) -> None:
    """Token 签名有效，但指向一个不存在的账号 → 凭证失效。"""
    resp = await client.get(
        "/api/v1/users/me", headers=_auth(create_access_token(UNKNOWN_USER_ID))
    )

    assert resp.status_code == 401, resp.text
    assert resp.headers.get("www-authenticate") == "Bearer"


async def test_disabled_account_returns_403(client) -> None:
    data = await _register(client, "disabled")
    await _set_active(data["id"], False)

    resp = await client.get(
        "/api/v1/users/me", headers=_auth(create_access_token(data["id"]))
    )

    assert resp.status_code == 403, resp.text
    assert resp.json()["detail"] == "User account is disabled"


async def test_disabled_account_is_not_reported_as_401(client) -> None:
    """禁用账号与凭证无效必须可区分（决策：403，与 login 语义一致）。"""
    data = await _register(client, "disabled2")
    await _set_active(data["id"], False)

    resp = await client.get(
        "/api/v1/users/me", headers=_auth(create_access_token(data["id"]))
    )

    assert resp.status_code != 401
    assert resp.status_code == 403
