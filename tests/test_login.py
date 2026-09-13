"""TASK-016：登录与 Access Token 的测试。

两部分：

1. JWT 单元测试——不依赖数据库，直接验证 `core/security.py` 的签发/校验契约
   （含篡改、过期、类别不符三类拒绝路径）。
2. 集成测试——通过依赖覆盖把 `get_db` 指向宿主机上的真实 PostgreSQL（宿主
   端口 5433），请求走完整 ASGI 链路。

`/register` 会提交事务，故沿用「本次运行唯一前缀 + teardown 精确删除」，
保证开发库零残留。
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
from app.core.exceptions import UnauthorizedError
from app.core.security import ACCESS_TOKEN_TYPE, create_access_token, decode_access_token
from app.db.session import get_db
from app.main import app
from app.models.user import User

TEST_DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql+asyncpg://postgres:postgres@127.0.0.1:5433/taskflow"
)

RUN_TOKEN = uuid.uuid4().hex[:10]
PASSWORD = "S3cret-Passw0rd!"

engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
SessionFactory = async_sessionmaker(engine, expire_on_commit=False)


async def _override_get_db():
    async with SessionFactory() as session:
        yield session


def _username(tag: str) -> str:
    return f"login_{RUN_TOKEN}_{tag}"


def _email(tag: str) -> str:
    return f"login_{RUN_TOKEN}_{tag}@example.com"


def _register_payload(tag: str) -> dict:
    return {"username": _username(tag), "email": _email(tag), "password": PASSWORD}


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
            delete(User).where(User.username.like(f"login_{RUN_TOKEN}%"))
        )
        await session.commit()


async def _register(client, tag: str) -> int:
    """注册一个可用账号，返回其 id。"""
    resp = await client.post("/api/v1/auth/register", json=_register_payload(tag))
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]["id"]


async def _set_active(user_id: int, active: bool) -> None:
    async with SessionFactory() as session:
        await session.execute(
            update(User).where(User.id == user_id).values(is_active=active)
        )
        await session.commit()


# --- JWT 单元测试 ---------------------------------------------------------


def test_access_token_round_trip() -> None:
    token = create_access_token(42)
    payload = decode_access_token(token)
    assert payload["sub"] == "42"
    assert payload["type"] == ACCESS_TOKEN_TYPE
    assert "exp" in payload and "iat" in payload


def test_access_token_expires_in_configured_window() -> None:
    settings = get_settings()
    payload = decode_access_token(create_access_token(1))
    ttl = payload["exp"] - payload["iat"]
    assert ttl == settings.access_token_expire_minutes * 60


def test_token_signed_with_other_secret_is_rejected() -> None:
    forged = jwt.encode(
        {"sub": "1", "type": ACCESS_TOKEN_TYPE},
        "attacker-secret-" * 3,  # >= 32 bytes, only the wrong key matters here
        algorithm="HS256",
    )
    with pytest.raises(UnauthorizedError):
        decode_access_token(forged)


def test_expired_token_is_rejected() -> None:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    expired = jwt.encode(
        {
            "sub": "1",
            "type": ACCESS_TOKEN_TYPE,
            "iat": now - timedelta(hours=2),
            "exp": now - timedelta(hours=1),
        },
        settings.jwt_secret_key,
        algorithm="HS256",
    )
    with pytest.raises(UnauthorizedError):
        decode_access_token(expired)


def test_non_access_token_type_is_rejected() -> None:
    """TASK-018 的 refresh token 不能当作 access token 使用。"""
    settings = get_settings()
    now = datetime.now(timezone.utc)
    refresh_like = jwt.encode(
        {
            "sub": "1",
            "type": "refresh",
            "iat": now,
            "exp": now + timedelta(days=7),
        },
        settings.jwt_secret_key,
        algorithm="HS256",
    )
    with pytest.raises(UnauthorizedError):
        decode_access_token(refresh_like)


# --- 成功路径 -------------------------------------------------------------


async def test_login_returns_200_with_access_token(client) -> None:
    user_id = await _register(client, "ok")

    resp = await client.post(
        "/api/v1/auth/login",
        json={"username": _username("ok"), "password": PASSWORD},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["message"] == "success"
    assert body["data"]["token_type"] == "bearer"

    payload = decode_access_token(body["data"]["access_token"])
    assert payload["sub"] == str(user_id)


async def test_login_response_never_exposes_password(client) -> None:
    await _register(client, "noleak")

    resp = await client.post(
        "/api/v1/auth/login",
        json={"username": _username("noleak"), "password": PASSWORD},
    )
    assert resp.status_code == 200, resp.text
    raw = resp.text
    assert PASSWORD not in raw
    assert "password_hash" not in raw


async def test_login_does_not_mutate_user(client) -> None:
    user_id = await _register(client, "nomutate")

    assert (
        await client.post(
            "/api/v1/auth/login",
            json={"username": _username("nomutate"), "password": PASSWORD},
        )
    ).status_code == 200

    async with SessionFactory() as session:
        user = (
            await session.execute(select(User).where(User.id == user_id))
        ).scalar_one()

    assert user.password_hash.startswith("$argon2id$")
    assert user.is_active is True


# --- 失败路径 -------------------------------------------------------------


async def test_wrong_password_returns_401(client) -> None:
    await _register(client, "badpw")

    resp = await client.post(
        "/api/v1/auth/login",
        json={"username": _username("badpw"), "password": "definitely-wrong"},
    )
    assert resp.status_code == 401, resp.text
    assert "detail" in resp.json()
    assert resp.headers.get("www-authenticate") == "Bearer"


async def test_unknown_user_returns_same_401_as_wrong_password(client) -> None:
    """两种失败返回同一文案，避免用户名枚举。"""
    await _register(client, "known")

    unknown = await client.post(
        "/api/v1/auth/login",
        json={"username": _username("ghost"), "password": PASSWORD},
    )
    wrong_pw = await client.post(
        "/api/v1/auth/login",
        json={"username": _username("known"), "password": "definitely-wrong"},
    )

    assert unknown.status_code == wrong_pw.status_code == 401
    assert unknown.json()["detail"] == wrong_pw.json()["detail"]


async def test_disabled_account_returns_403(client) -> None:
    user_id = await _register(client, "disabled")
    await _set_active(user_id, False)

    resp = await client.post(
        "/api/v1/auth/login",
        json={"username": _username("disabled"), "password": PASSWORD},
    )
    assert resp.status_code == 403, resp.text
    assert "detail" in resp.json()


async def test_disabled_account_with_wrong_password_still_401(client) -> None:
    """密码错误时先返回 401，不泄露账号是否被禁用。"""
    user_id = await _register(client, "disabled2")
    await _set_active(user_id, False)

    resp = await client.post(
        "/api/v1/auth/login",
        json={"username": _username("disabled2"), "password": "definitely-wrong"},
    )
    assert resp.status_code == 401, resp.text


@pytest.mark.parametrize("drop", ["username", "password"])
async def test_missing_required_field_returns_422(client, drop: str) -> None:
    payload = {"username": _username("missing"), "password": PASSWORD}
    payload.pop(drop)
    resp = await client.post("/api/v1/auth/login", json=payload)
    assert resp.status_code == 422, resp.text
