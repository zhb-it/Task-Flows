"""TASK-018：Refresh Token / JTI 的测试。

四组：
1. Token 单元测试（不连库）——签发/解析契约、jti、TTL、两类 Token 不可互换。
2. 登录集成测试——返回双 Token，且只有 jti 落库（Token 本体不入库）。
3. Refresh 成功路径——轮换后新 Token 对可用，旧 jti 立即失效。
4. Refresh 失败路径——签名/类型/jti 未知/已撤销/已过期/账号禁用或删除。

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
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.core.exceptions import UnauthorizedError
from app.core.security import (
    REFRESH_TOKEN_TYPE,
    create_access_token,
    create_refresh_token,
    decode_access_token,
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
UNKNOWN_USER_ID = 9_000_000_000

engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
SessionFactory = async_sessionmaker(engine, expire_on_commit=False)


async def _override_get_db():
    async with SessionFactory() as session:
        yield session


def _username(tag: str) -> str:
    return f"refresh_{RUN_TOKEN}_{tag}"


def _email(tag: str) -> str:
    return f"refresh_{RUN_TOKEN}_{tag}@example.com"


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
            delete(User).where(User.username.like(f"refresh_{RUN_TOKEN}%"))
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
    """登录并返回 ``data``（含 access_token / refresh_token）。"""
    await _register(client, tag)
    resp = await client.post(
        "/api/v1/auth/login",
        json={"username": _username(tag), "password": PASSWORD},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def _post_refresh(client, refresh_token: str):
    return client.post(
        "/api/v1/auth/refresh", json={"refresh_token": refresh_token}
    )


async def _stored_token(jti: str) -> RefreshToken | None:
    async with SessionFactory() as session:
        return (
            await session.execute(
                select(RefreshToken).where(RefreshToken.jti == jti)
            )
        ).scalar_one_or_none()


async def _count_tokens(user_id: int) -> int:
    async with SessionFactory() as session:
        return await session.scalar(
            select(func.count()).select_from(RefreshToken).where(
                RefreshToken.user_id == user_id
            )
        )


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


async def _force_expired(jti: str) -> None:
    async with SessionFactory() as session:
        await session.execute(
            update(RefreshToken)
            .where(RefreshToken.jti == jti)
            .values(expires_at=datetime.now(timezone.utc) - timedelta(minutes=1))
        )
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


# --- Token 单元测试 -------------------------------------------------------


def test_refresh_token_round_trip() -> None:
    token, jti, expires_at = create_refresh_token(42)

    payload = decode_refresh_token(token)
    assert payload["sub"] == "42"
    assert payload["type"] == REFRESH_TOKEN_TYPE
    assert payload["jti"] == jti
    assert isinstance(jti, str) and len(jti) == 36


def test_refresh_token_ttl_matches_config() -> None:
    settings = get_settings()
    token, _, _ = create_refresh_token(1)
    payload = decode_refresh_token(token)

    assert (payload["exp"] - payload["iat"]) == (
        settings.refresh_token_expire_days * 24 * 60 * 60
    )


def test_jti_is_unique_per_token() -> None:
    jtis = {create_refresh_token(1)[1] for _ in range(5)}
    assert len(jtis) == 5


def test_refresh_token_is_not_accepted_as_access_token() -> None:
    token, _, _ = create_refresh_token(1)
    with pytest.raises(UnauthorizedError):
        decode_access_token(token)


def test_access_token_is_not_accepted_as_refresh_token() -> None:
    with pytest.raises(UnauthorizedError):
        decode_refresh_token(create_access_token(1))


def test_refresh_token_with_other_secret_is_rejected() -> None:
    forged = _signed(_refresh_payload(), secret="attacker-secret-" * 3)
    with pytest.raises(UnauthorizedError):
        decode_refresh_token(forged)


def test_expired_refresh_token_is_rejected() -> None:
    now = datetime.now(timezone.utc)
    expired = _signed(
        _refresh_payload(iat=now - timedelta(days=9), exp=now - timedelta(days=1))
    )
    with pytest.raises(UnauthorizedError):
        decode_refresh_token(expired)


# --- 登录签发 -------------------------------------------------------------


async def test_login_returns_token_pair(client) -> None:
    data = await _login(client, "pair")

    assert data["token_type"] == "bearer"
    assert data["access_token"] and data["refresh_token"]
    assert decode_refresh_token(data["refresh_token"])["type"] == REFRESH_TOKEN_TYPE


async def test_login_persists_only_the_jti(client) -> None:
    data = await _login(client, "persist")
    payload = decode_refresh_token(data["refresh_token"])

    stored = await _stored_token(payload["jti"])
    assert stored is not None
    assert stored.revoked is False
    assert stored.user_id == int(payload["sub"])

    # Token 本体不落库：库里存的是 jti，不是 JWT 串。
    async with SessionFactory() as session:
        n = await session.scalar(
            select(func.count())
            .select_from(RefreshToken)
            .where(RefreshToken.jti == data["refresh_token"])
        )
    assert n == 0


async def test_login_response_never_exposes_password(client) -> None:
    data = await _login(client, "noleak")

    assert PASSWORD not in str(data)
    assert "password_hash" not in str(data)


# --- Refresh 成功路径 -----------------------------------------------------


async def test_refresh_returns_new_pair(client) -> None:
    data = await _login(client, "rotate")

    resp = await _post_refresh(client, data["refresh_token"])

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["message"] == "success"
    assert body["data"]["token_type"] == "bearer"
    # Refresh Token 的 claims 含唯一 jti，新值必然与旧值不同。
    # Access Token 的 claims 只精确到秒（sub/type/iat/exp），同一秒内签发会得到
    # 完全相同的串，因此这里不断言新旧 access_token 不等，而是由
    # test_new_access_token_works_on_protected_endpoint 验证新 Token 确实可用。
    assert body["data"]["refresh_token"] != data["refresh_token"]
    assert decode_refresh_token(body["data"]["refresh_token"])["jti"] != (
        decode_refresh_token(data["refresh_token"])["jti"]
    )


async def test_new_access_token_works_on_protected_endpoint(client) -> None:
    """refresh 换来的 Access Token 必须真的可用（端到端串联 TASK-017）。"""
    data = await _login(client, "usable")

    rotated = (await _post_refresh(client, data["refresh_token"])).json()["data"]

    resp = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {rotated['access_token']}"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["username"] == _username("usable")


async def test_old_refresh_token_is_revoked_after_rotation(client) -> None:
    data = await _login(client, "oldrev")
    old_jti = decode_refresh_token(data["refresh_token"])["jti"]

    await _post_refresh(client, data["refresh_token"])

    stored = await _stored_token(old_jti)
    assert stored is not None and stored.revoked is True


async def test_reusing_rotated_refresh_token_is_rejected(client) -> None:
    """轮换后旧 Refresh Token 不可复用（防止被复制使用）。"""
    data = await _login(client, "reuse")
    await _post_refresh(client, data["refresh_token"])

    resp = await _post_refresh(client, data["refresh_token"])

    assert resp.status_code == 401, resp.text


async def test_rotation_chain_keeps_working(client) -> None:
    data = await _login(client, "chain")

    first = (await _post_refresh(client, data["refresh_token"])).json()["data"]
    second = (await _post_refresh(client, first["refresh_token"])).json()["data"]

    assert second["refresh_token"] != first["refresh_token"]
    stored = await _stored_token(decode_refresh_token(second["refresh_token"])["jti"])
    assert stored is not None and stored.revoked is False


async def test_each_rotation_registers_a_new_jti(client) -> None:
    data = await _login(client, "count")
    user_id = int(decode_refresh_token(data["refresh_token"])["sub"])
    assert await _count_tokens(user_id) == 1

    await _post_refresh(client, data["refresh_token"])

    assert await _count_tokens(user_id) == 2


async def test_refresh_does_not_rotate_on_rejected_token(client) -> None:
    """校验失败的请求不得产生新记录，也不得影响已有记录。"""
    data = await _login(client, "norecord")
    jti = decode_refresh_token(data["refresh_token"])["jti"]

    resp = await _post_refresh(client, f"{data['refresh_token']}x")
    assert resp.status_code == 401

    stored = await _stored_token(jti)
    assert stored is not None and stored.revoked is False


# --- Refresh 失败路径 -----------------------------------------------------


@pytest.mark.parametrize("garbage", ["", "not-a-jwt", "a.b.c"])
async def test_malformed_refresh_token_returns_401(client, garbage: str) -> None:
    resp = await _post_refresh(client, garbage)

    assert resp.status_code == 401, resp.text
    assert "detail" in resp.json()


async def test_refresh_token_signed_with_other_secret_returns_401(client) -> None:
    forged = _signed(_refresh_payload(), secret="attacker-secret-" * 3)

    resp = await _post_refresh(client, forged)

    assert resp.status_code == 401, resp.text


async def test_access_token_cannot_be_used_to_refresh(client) -> None:
    data = await _login(client, "wrongtype")

    resp = await _post_refresh(client, data["access_token"])

    assert resp.status_code == 401, resp.text


async def test_refresh_token_with_unknown_jti_returns_401(client) -> None:
    """签名合法但 jti 未登记在库（§19「检查数据库 JTI」）。"""
    await _register(client, "unknownjti")
    orphan = _signed(_refresh_payload(sub="1"))

    resp = await _post_refresh(client, orphan)

    assert resp.status_code == 401, resp.text


async def test_revoked_refresh_token_returns_401(client) -> None:
    data = await _login(client, "revoked")
    jti = decode_refresh_token(data["refresh_token"])["jti"]
    async with SessionFactory() as session:
        await session.execute(
            update(RefreshToken).where(RefreshToken.jti == jti).values(revoked=True)
        )
        await session.commit()

    resp = await _post_refresh(client, data["refresh_token"])

    assert resp.status_code == 401, resp.text


async def test_expired_stored_token_returns_401(client) -> None:
    """JWT 的 exp 未到但库中 expires_at 已过期（例如被管理员提前失效）。"""
    data = await _login(client, "dbexpired")
    await _force_expired(decode_refresh_token(data["refresh_token"])["jti"])

    resp = await _post_refresh(client, data["refresh_token"])

    assert resp.status_code == 401, resp.text


@pytest.mark.parametrize("subject", [None, "not-a-number", "1.5", ""])
async def test_malformed_subject_returns_401(client, subject) -> None:
    token = _signed(_refresh_payload(sub=subject))

    resp = await _post_refresh(client, token)

    assert resp.status_code == 401, resp.text


async def test_missing_jti_claim_returns_401(client) -> None:
    payload = _refresh_payload()
    payload.pop("jti")
    token = _signed(payload)

    resp = await _post_refresh(client, token)

    assert resp.status_code == 401, resp.text


async def test_expired_refresh_token_returns_401(client) -> None:
    now = datetime.now(timezone.utc)
    expired = _signed(
        _refresh_payload(iat=now - timedelta(days=9), exp=now - timedelta(days=1))
    )

    resp = await _post_refresh(client, expired)

    assert resp.status_code == 401, resp.text


async def test_disabled_account_cannot_refresh(client) -> None:
    data = await _login(client, "disabled")
    user_id = int(decode_refresh_token(data["refresh_token"])["sub"])
    await _set_active(user_id, False)

    resp = await _post_refresh(client, data["refresh_token"])

    assert resp.status_code == 403, resp.text
    assert resp.json()["detail"] == "User account is disabled"


async def test_deleted_account_cannot_refresh(client) -> None:
    data = await _login(client, "deleted")
    user_id = int(decode_refresh_token(data["refresh_token"])["sub"])

    await _delete_user(user_id)
    resp = await _post_refresh(client, data["refresh_token"])

    assert resp.status_code == 401, resp.text


async def test_deleting_user_cascades_refresh_tokens(client) -> None:
    """DB_SCHEMA 的级联约定：删除用户不留下孤儿 Token 记录。"""
    data = await _login(client, "cascade")
    user_id = int(decode_refresh_token(data["refresh_token"])["sub"])
    assert await _count_tokens(user_id) == 1

    await _delete_user(user_id)

    assert await _count_tokens(user_id) == 0


async def test_missing_field_returns_422(client) -> None:
    resp = await client.post("/api/v1/auth/refresh", json={})

    assert resp.status_code == 422, resp.text
