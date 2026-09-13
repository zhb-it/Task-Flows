"""TASK-020：Auth 端到端验收链路测试。

开发文档 §35「Auth 重点测试」八项（注册成功 / 重复用户名 / 重复邮箱 / 错误密码 /
登录成功 / Refresh 成功 / Refresh Token 撤销 / Logout）已由专项模块各自覆盖
（test_register / test_login / test_refresh / test_logout）；本模块补上此前缺失的
**验收链路**——把 §56 Phase 2 与 Phase 3 的验收流程完整走一遍，证明各环节
组合在一起时行为正确：

- Phase 2 验收：注册 → 登录 → 获取 Access Token → 访问 /users/me
- Phase 3 验收：Access Token / Refresh Token / Logout / Refresh 失败
- §57 功能验收：用户注册 / 用户登录 / Access Token / Refresh Token / Logout

沿用「本次运行唯一前缀 + teardown 精确删除」保证开发库零残留；
删除 `users` 行时由 `ON DELETE CASCADE` 带走其 `refresh_tokens` 记录。
"""

import base64
import json
import os
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.security import decode_access_token, decode_refresh_token
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
    return f"authflow_{RUN_TOKEN}_{tag}"


def _email(tag: str) -> str:
    return f"authflow_{RUN_TOKEN}_{tag}@example.com"


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
            delete(User).where(User.username.like(f"authflow_{RUN_TOKEN}%"))
        )
        await session.commit()


def _claims(token: str) -> dict:
    """解码 JWT 的 payload 段（不验签，仅用于断言 claims 契约）。"""
    mid = token.split(".")[1]
    mid += "=" * (-len(mid) % 4)
    return json.loads(base64.urlsafe_b64decode(mid))


# --- Phase 2 验收链路 -------------------------------------------------------


async def test_phase2_acceptance_chain(client) -> None:
    """§56 Phase 2：注册 → 登录 → 获取 Access Token → 访问 /users/me。"""
    # 注册
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "username": _username("p2"),
            "email": _email("p2"),
            "password": PASSWORD,
        },
    )
    assert resp.status_code == 201, resp.text
    registered = resp.json()["data"]
    assert registered["username"] == _username("p2")

    # 登录 → 获取 Access Token
    resp = await client.post(
        "/api/v1/auth/login",
        json={"username": _username("p2"), "password": PASSWORD},
    )
    assert resp.status_code == 200, resp.text
    tokens = resp.json()["data"]
    assert tokens["token_type"] == "bearer"
    access_token = tokens["access_token"]
    assert _claims(access_token)["type"] == "access"

    # 访问 /users/me
    resp = await client.get(
        "/api/v1/users/me", headers={"Authorization": f"Bearer {access_token}"}
    )
    assert resp.status_code == 200, resp.text
    me = resp.json()["data"]
    assert me["id"] == registered["id"]
    assert me["username"] == _username("p2")
    assert me["email"] == _email("p2")
    assert "password_hash" not in me


# --- Phase 3 验收链路 -------------------------------------------------------


async def test_phase3_acceptance_chain(client) -> None:
    """§56 Phase 3：Access Token / Refresh Token / Logout / Refresh 失败。"""
    await client.post(
        "/api/v1/auth/register",
        json={
            "username": _username("p3"),
            "email": _email("p3"),
            "password": PASSWORD,
        },
    )
    resp = await client.post(
        "/api/v1/auth/login",
        json={"username": _username("p3"), "password": PASSWORD},
    )
    tokens = resp.json()["data"]

    # Access Token 与 Refresh Token 的 claims 契约
    access_claims = _claims(tokens["access_token"])
    refresh_claims = _claims(tokens["refresh_token"])
    assert access_claims["type"] == "access"
    assert refresh_claims["type"] == "refresh"
    assert refresh_claims["jti"]  # UUID 字符串
    assert refresh_claims["exp"] > refresh_claims["iat"]
    assert access_claims["exp"] - access_claims["iat"] < (
        refresh_claims["exp"] - refresh_claims["iat"]
    )  # Access 短时效、Refresh 长时效

    # Refresh 成功 → 全新 Token 对
    resp = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert resp.status_code == 200, resp.text
    rotated = resp.json()["data"]
    assert rotated["refresh_token"] != tokens["refresh_token"]

    # 新 Access Token 可用（轮换后的会话连续性）
    resp = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {rotated['access_token']}"},
    )
    assert resp.status_code == 200, resp.text

    # Logout
    resp = await client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": rotated["refresh_token"]},
        headers={"Authorization": f"Bearer {rotated['access_token']}"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"] is None

    # Refresh 失败（被撤销的 jti）
    resp = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": rotated["refresh_token"]}
    )
    assert resp.status_code == 401, resp.text


# --- 完整生命周期（§57 功能验收） -------------------------------------------


async def test_full_auth_lifecycle(client) -> None:
    """注册 → 登录 → me → refresh → me → logout → refresh 401 → 重新登录恢复。"""
    creds = {"username": _username("life"), "password": PASSWORD}
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "username": creds["username"],
            "email": _email("life"),
            "password": creds["password"],
        },
    )
    assert resp.status_code == 201, resp.text

    resp = await client.post("/api/v1/auth/login", json=creds)
    first = resp.json()["data"]

    resp = await client.get(
        "/api/v1/users/me", headers={"Authorization": f"Bearer {first['access_token']}"}
    )
    assert resp.status_code == 200, resp.text

    resp = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": first["refresh_token"]}
    )
    second = resp.json()["data"]

    resp = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {second['access_token']}"},
    )
    assert resp.status_code == 200, resp.text

    resp = await client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": second["refresh_token"]},
        headers={"Authorization": f"Bearer {second['access_token']}"},
    )
    assert resp.status_code == 200, resp.text

    resp = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": second["refresh_token"]}
    )
    assert resp.status_code == 401, resp.text

    # 旧 Access Token 在剩余有效期内仍可用（API_CONTRACT 登记的已知行为，
    # 本阶段不引入 Redis 黑名单的既定决策）
    resp = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {second['access_token']}"},
    )
    assert resp.status_code == 200, resp.text

    # 重新登录恢复会话
    resp = await client.post("/api/v1/auth/login", json=creds)
    assert resp.status_code == 200, resp.text
    third = resp.json()["data"]
    resp = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": third["refresh_token"]}
    )
    assert resp.status_code == 200, resp.text


async def test_repeated_register_login_refresh_logout_cycle(client) -> None:
    """同一账号三轮「登录 → refresh → logout」独立会话互不干扰。"""
    creds = {"username": _username("cycle"), "password": PASSWORD}
    await client.post(
        "/api/v1/auth/register",
        json={
            "username": creds["username"],
            "email": _email("cycle"),
            "password": creds["password"],
        },
    )

    sessions = []
    for _ in range(3):
        resp = await client.post("/api/v1/auth/login", json=creds)
        assert resp.status_code == 200, resp.text
        sessions.append(resp.json()["data"])

    for tokens in sessions:
        resp = await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        )
        assert resp.status_code == 200, resp.text

    for tokens in sessions:
        resp = await client.post(
            "/api/v1/auth/logout",
            json={"refresh_token": tokens["refresh_token"]},
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        assert resp.status_code == 200, resp.text

    for tokens in sessions:
        resp = await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        )
        assert resp.status_code == 401, resp.text


# --- OpenAPI 验收面 ---------------------------------------------------------


async def test_auth_surface_is_registered_in_openapi(client) -> None:
    """§25.1 Auth 端点与 §25.2 /users/me 均已登记。"""
    resp = await client.get("/openapi.json")
    assert resp.status_code == 200, resp.text
    paths = resp.json()["paths"]
    for path in (
        "/api/v1/auth/register",
        "/api/v1/auth/login",
        "/api/v1/auth/refresh",
        "/api/v1/auth/logout",
        "/api/v1/users/me",
    ):
        assert path in paths, path
