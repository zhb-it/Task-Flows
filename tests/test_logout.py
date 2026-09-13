"""TASK-019：Logout / Token revoke 的测试。

五组：
1. 成功路径——200 信封、jti 置 revoked、Logout 后 Refresh 失败（开发文档 §56
   Phase 3 验收「Logout → Refresh 失败」）。
2. 幂等语义（TASK-019 决策）——签名/过期/类别不合法、jti 未知、已撤销等
   「Token 本来就不可用」的情形一律静默 200，无副作用。
3. 归属校验——出示他人的 Refresh Token → 403，且对方的 Token 不受影响。
4. Access Token 认证失败路径——与 /users/me 同一套 401 / 403 规则。
5. OpenAPI 登记。

沿用「本次运行唯一前缀 + teardown 精确删除」保证开发库零残留；
删除 `users` 行时由 `ON DELETE CASCADE` 带走其 `refresh_tokens` 记录。
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
from app.core.security import (
    REFRESH_TOKEN_TYPE,
    create_access_token,
    decode_refresh_token,
)
from app.db.session import get_db
from app.main import app
from app.models.refresh_token import RefreshToken
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
    return f"logout_{RUN_TOKEN}_{tag}"


def _email(tag: str) -> str:
    return f"logout_{RUN_TOKEN}_{tag}@example.com"


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
    yield
    async with SessionFactory() as session:
        await session.execute(
            delete(User).where(User.username.like(f"logout_{RUN_TOKEN}%"))
        )
        await session.commit()


async def _register(client, tag: str) -> dict:
    resp = await client.post(
        "/api/v1/auth/register",
        json={"username": _username(tag), "email": _email(tag), "password": PASSWORD},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


async def _login(client, tag: str) -> dict:
    """注册并登录，返回 ``data``（含 access_token / refresh_token）。"""
    await _register(client, tag)
    resp = await client.post(
        "/api/v1/auth/login",
        json={"username": _username(tag), "password": PASSWORD},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def _post_logout(client, refresh_token: str, access_token: str | None = None):
    headers = (
        {"Authorization": f"Bearer {access_token}"} if access_token is not None else {}
    )
    return client.post(
        "/api/v1/auth/logout", json={"refresh_token": refresh_token}, headers=headers
    )


async def _stored_token(jti: str) -> RefreshToken | None:
    async with SessionFactory() as session:
        return (
            await session.execute(
                select(RefreshToken).where(RefreshToken.jti == jti)
            )
        ).scalar_one_or_none()


async def _set_active(user_id: int, active: bool) -> None:
    async with SessionFactory() as session:
        await session.execute(
            update(User).where(User.id == user_id).values(is_active=active)
        )
        await session.commit()


async def _delete_user(user_id: int) -> None:
    async with SessionFactory() as session:
        await session.execute(delete(User).where(User.id == user_id))
        await session.commit()


def _signed(payload: dict, *, secret: str | None = None) -> str:
    settings = get_settings()
    return jwt.encode(
        payload,
        secret if secret is not None else settings.jwt_secret_key,
        algorithm="HS256",
    )


def _refresh_payload(**overrides) -> dict:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": "1",
        "type": REFRESH_TOKEN_TYPE,
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": now + timedelta(days=1),
    }
    payload.update(overrides)
    return payload


# --- 成功路径 --------------------------------------------------------------


async def test_logout_returns_success_envelope(client) -> None:
    data = await _login(client, "envelope")

    resp = await _post_logout(client, data["refresh_token"], data["access_token"])

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["message"] == "success"
    assert body["data"] is None


async def test_logout_revokes_token_and_refresh_then_fails(client) -> None:
    """开发文档 §56 Phase 3 验收：Logout → Refresh 失败。"""
    data = await _login(client, "accept")

    resp = await _post_logout(client, data["refresh_token"], data["access_token"])
    assert resp.status_code == 200, resp.text

    resp = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": data["refresh_token"]}
    )
    assert resp.status_code == 401, resp.text


async def test_logout_marks_jti_revoked_in_db(client) -> None:
    data = await _login(client, "dbstate")
    jti = decode_refresh_token(data["refresh_token"])["jti"]

    resp = await _post_logout(client, data["refresh_token"], data["access_token"])
    assert resp.status_code == 200, resp.text

    stored = await _stored_token(jti)
    assert stored is not None
    assert stored.revoked is True


async def test_logout_only_revokes_the_submitted_token(client) -> None:
    """同一用户两次登录（两个会话）：登出会话 A 不影响会话 B。"""
    await _register(client, "multi")
    session_a = (
        await client.post(
            "/api/v1/auth/login",
            json={"username": _username("multi"), "password": PASSWORD},
        )
    ).json()["data"]
    session_b = (
        await client.post(
            "/api/v1/auth/login",
            json={"username": _username("multi"), "password": PASSWORD},
        )
    ).json()["data"]

    resp = await _post_logout(
        client, session_a["refresh_token"], session_a["access_token"]
    )
    assert resp.status_code == 200, resp.text

    resp = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": session_a["refresh_token"]}
    )
    assert resp.status_code == 401, resp.text

    resp = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": session_b["refresh_token"]}
    )
    assert resp.status_code == 200, resp.text


# --- 幂等语义：不可用的 Token 静默 200 --------------------------------------


async def test_logout_is_idempotent(client) -> None:
    data = await _login(client, "idem")

    first = await _post_logout(client, data["refresh_token"], data["access_token"])
    second = await _post_logout(client, data["refresh_token"], data["access_token"])

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    jti = decode_refresh_token(data["refresh_token"])["jti"]
    assert (await _stored_token(jti)).revoked is True


async def test_logout_with_forged_signature_returns_200(client) -> None:
    data = await _login(client, "forge")
    forged = jwt.encode(
        _refresh_payload(sub=str(data and 1)),
        "attacker-secret-" * 3,
        algorithm="HS256",
    )

    resp = await _post_logout(client, forged, data["access_token"])

    assert resp.status_code == 200, resp.text


async def test_logout_with_access_token_as_refresh_token_returns_200(client) -> None:
    """类别不符的 Token 本来就不可用：静默成功，不撤销任何 jti。"""
    data = await _login(client, "wrongtype")

    resp = await _post_logout(client, data["access_token"], data["access_token"])

    assert resp.status_code == 200, resp.text


async def test_logout_with_garbage_token_returns_200(client) -> None:
    data = await _login(client, "garbage")

    resp = await _post_logout(client, "not-a-jwt", data["access_token"])

    assert resp.status_code == 200, resp.text


async def test_logout_with_unknown_jti_returns_200(client) -> None:
    """签名有效但 jti 未登记：幂等成功，且不产生任何落库副作用。"""
    data = await _login(client, "unknown")
    before = decode_refresh_token(data["refresh_token"])["jti"]

    outsider = _signed(_refresh_payload(sub="1", jti=str(uuid.uuid4())))
    resp = await _post_logout(client, outsider, data["access_token"])

    assert resp.status_code == 200, resp.text
    stored = await _stored_token(before)
    assert stored is not None
    assert stored.revoked is False


async def test_logout_with_expired_refresh_token_returns_200(client) -> None:
    data = await _login(client, "expired")
    now = datetime.now(timezone.utc)
    expired = _signed(
        _refresh_payload(sub="1", iat=now - timedelta(days=9), exp=now - timedelta(days=1))
    )

    resp = await _post_logout(client, expired, data["access_token"])

    assert resp.status_code == 200, resp.text


# --- 归属校验 ---------------------------------------------------------------


async def test_logout_rejects_other_users_token(client) -> None:
    """A 的 Access Token + B 的 Refresh Token → 403，且 B 的 Token 不受影响。"""
    user_a = await _login(client, "owner")
    user_b = await _login(client, "victim")
    b_jti = decode_refresh_token(user_b["refresh_token"])["jti"]

    resp = await _post_logout(
        client, user_b["refresh_token"], user_a["access_token"]
    )

    assert resp.status_code == 403, resp.text
    assert resp.json() == {"detail": "Refresh token does not belong to current user"}

    stored = await _stored_token(b_jti)
    assert stored is not None
    assert stored.revoked is False

    resp = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": user_b["refresh_token"]}
    )
    assert resp.status_code == 200, resp.text


# --- Access Token 认证失败路径 ----------------------------------------------


async def test_logout_without_authorization_header(client) -> None:
    data = await _login(client, "noheader")

    resp = await _post_logout(client, data["refresh_token"])

    assert resp.status_code == 401, resp.text
    assert resp.headers["www-authenticate"] == "Bearer"


async def test_logout_with_non_bearer_scheme(client) -> None:
    data = await _login(client, "scheme")

    resp = await client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": data["refresh_token"]},
        headers={"Authorization": f"Basic {data['access_token']}"},
    )

    assert resp.status_code == 401, resp.text
    assert resp.headers["www-authenticate"] == "Bearer"


async def test_logout_with_forged_access_token(client) -> None:
    data = await _login(client, "forged")
    forged_access = _signed({"sub": "1", "type": "access", "iat": 0, "exp": 0})

    resp = await _post_logout(client, data["refresh_token"], forged_access)

    assert resp.status_code == 401, resp.text


async def test_logout_with_expired_access_token(client) -> None:
    data = await _login(client, "accessexp")
    now = datetime.now(timezone.utc)
    expired_access = _signed(
        {
            "sub": "1",
            "type": "access",
            "iat": now - timedelta(hours=2),
            "exp": now - timedelta(hours=1),
        }
    )

    resp = await _post_logout(client, data["refresh_token"], expired_access)

    assert resp.status_code == 401, resp.text


async def test_logout_with_refresh_type_access_token(client) -> None:
    """Refresh Token 冒充 Access Token → 401。"""
    data = await _login(client, "typemix")

    resp = await _post_logout(client, data["refresh_token"], data["refresh_token"])

    assert resp.status_code == 401, resp.text


async def test_logout_with_disabled_account(client) -> None:
    """禁用账号 → 403（与 /users/me 一致），且其 Token 不被撤销。"""
    data = await _login(client, "disabled")
    user_id = int(decode_refresh_token(data["refresh_token"])["sub"])
    jti = decode_refresh_token(data["refresh_token"])["jti"]
    await _set_active(user_id, False)

    resp = await _post_logout(client, data["refresh_token"], data["access_token"])

    assert resp.status_code == 403, resp.text
    stored = await _stored_token(jti)
    assert stored is not None
    assert stored.revoked is False


async def test_logout_with_deleted_user(client) -> None:
    """Token 签名有效但用户已不存在 → 401，不进入 Service。"""
    data = await _login(client, "deleted")
    user_id = int(decode_refresh_token(data["refresh_token"])["sub"])
    await _delete_user(user_id)
    access_token = create_access_token(user_id)

    resp = await _post_logout(client, data["refresh_token"], access_token)

    assert resp.status_code == 401, resp.text


# --- 请求校验与 OpenAPI ------------------------------------------------------


async def test_logout_missing_body_field(client) -> None:
    data = await _login(client, "nofield")

    resp = await client.post(
        "/api/v1/auth/logout",
        json={},
        headers={"Authorization": f"Bearer {data['access_token']}"},
    )

    assert resp.status_code == 422, resp.text


async def test_logout_is_registered_in_openapi(client) -> None:
    resp = await client.get("/openapi.json")

    assert resp.status_code == 200, resp.text
    assert "/api/v1/auth/logout" in resp.json()["paths"]
