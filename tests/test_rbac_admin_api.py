"""TASK-082/083：RBAC 管理端点集成测试（/users 列表、用户角色、权限矩阵）。

沿用本项目集成测试惯例：宿主 PG 5433 + 本次运行唯一前缀 + teardown 精确删除
（users 行级联带走 user_roles）。注册即 member（TASK-081），管理员由
「注册 + 事务内补授 admin 角色」构造，不走任何生产数据。
"""

import os
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.crud.role import assign_role_to_user, get_role_by_name
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

# member 的种子权限（0de65c197efc，与 migrate 内清单一致；sorted 输出）。
MEMBER_PERMISSIONS = sorted(
    [
        "user:read",
        "team:read",
        "project:read",
        "task:read",
        "log:read",
        "task:create",
        "task:update",
        "comment:create",
        "attachment:upload",
        "attachment:download",
    ]
)


async def _override_get_db():
    async with SessionFactory() as session:
        yield session


def _username(tag: str) -> str:
    return f"rbacadm_{RUN_TOKEN}_{tag}"


def _email(tag: str) -> str:
    return f"rbacadm_{RUN_TOKEN}_{tag}@example.com"


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
            delete(User).where(User.username.like(f"rbacadm_{RUN_TOKEN}%"))
        )
        await session.commit()


async def _register(client, tag: str) -> int:
    resp = await client.post(
        "/api/v1/auth/register",
        json={"username": _username(tag), "email": _email(tag), "password": PASSWORD},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]["id"]


async def _grant_admin(user_id: int) -> None:
    async with SessionFactory() as session:
        role = await get_role_by_name(session, "admin")
        assert role is not None
        await assign_role_to_user(session, user_id=user_id, role_id=role.id)
        await session.commit()


async def _login(client, tag: str) -> str:
    resp = await client.post(
        "/api/v1/auth/login",
        json={"username": _username(tag), "password": PASSWORD},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# --- GET /users/me/permissions（TASK-083）----------------------------------


async def test_me_permissions_returns_member_seed_set(client) -> None:
    """注册即 member：me/permissions 必须等于 member 种子权限（去重有序）。"""
    await _register(client, "me")
    token = await _login(client, "me")

    resp = await client.get("/api/v1/users/me/permissions", headers=_auth(token))
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["permissions"] == MEMBER_PERMISSIONS


async def test_me_permissions_requires_auth(client) -> None:
    resp = await client.get("/api/v1/users/me/permissions")
    assert resp.status_code == 401


async def test_me_permissions_reflects_role_change(client) -> None:
    """角色变更后 me/permissions 跟随变化——与 require_permission 同一数据源。"""
    uid = await _register(client, "promo")
    await _grant_admin(uid)
    token = await _login(client, "promo")

    resp = await client.get("/api/v1/users/me/permissions", headers=_auth(token))
    perms = resp.json()["data"]["permissions"]
    assert "user:update" in perms and "team:delete" in perms  # admin 独有项


# --- GET /permissions 权限矩阵（TASK-083）----------------------------------


async def test_permission_matrix_forbidden_for_member(client) -> None:
    await _register(client, "mview")
    token = await _login(client, "mview")

    resp = await client.get("/api/v1/permissions", headers=_auth(token))
    assert resp.status_code == 403, resp.text


async def test_permission_matrix_for_admin(client) -> None:
    uid = await _register(client, "aview")
    await _grant_admin(uid)
    token = await _login(client, "aview")

    resp = await client.get("/api/v1/permissions", headers=_auth(token))
    assert resp.status_code == 200, resp.text
    matrix = {r["name"]: r for r in resp.json()["data"]}
    assert set(matrix) == {"admin", "member"}
    assert len(matrix["admin"]["permissions"]) == 22  # 种子全量
    assert matrix["member"]["permissions"] == MEMBER_PERMISSIONS


# --- GET /users + GET/PUT /users/{id}/roles（TASK-082）---------------------


async def test_list_users_includes_roles(client) -> None:
    await _register(client, "lister")
    token = await _login(client, "lister")

    resp = await client.get("/api/v1/users", headers=_auth(token))
    assert resp.status_code == 200, resp.text
    items = resp.json()["data"]
    me = next(i for i in items if i["username"] == _username("lister"))
    assert me["roles"] == ["member"]
    assert "password_hash" not in me


async def test_member_cannot_modify_roles(client) -> None:
    target = await _register(client, "victim")
    await _register(client, "attacker")
    token = await _login(client, "attacker")

    resp = await client.put(
        f"/api/v1/users/{target}/roles",
        headers=_auth(token),
        json={"roles": ["admin"]},
    )
    assert resp.status_code == 403, resp.text


async def test_admin_replaces_user_roles(client) -> None:
    admin_id = await _register(client, "boss")
    await _grant_admin(admin_id)
    admin_token = await _login(client, "boss")
    target = await _register(client, "target")

    # member → admin：全量替换语义
    resp = await client.put(
        f"/api/v1/users/{target}/roles",
        headers=_auth(admin_token),
        json={"roles": ["admin"]},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["roles"] == ["admin"]

    # 再换回 member + admin 混合，验证撤销 + 补授双向生效
    resp = await client.put(
        f"/api/v1/users/{target}/roles",
        headers=_auth(admin_token),
        json={"roles": ["member", "admin"]},
    )
    assert resp.json()["data"]["roles"] == ["admin", "member"]  # 按 Role.id 排序

    # GET 与 PUT 视角一致
    resp = await client.get(
        f"/api/v1/users/{target}/roles", headers=_auth(admin_token)
    )
    assert resp.json()["data"]["roles"] == ["admin", "member"]


async def test_replace_roles_rejects_unknown_role_and_user(client) -> None:
    admin_id = await _register(client, "boss2")
    await _grant_admin(admin_id)
    token = await _login(client, "boss2")
    target = await _register(client, "target2")

    resp = await client.put(
        f"/api/v1/users/{target}/roles",
        headers=_auth(token),
        json={"roles": ["superadmin"]},
    )
    assert resp.status_code == 404, resp.text
    assert "superadmin" in resp.json()["detail"]

    resp = await client.put(
        "/api/v1/users/999999999/roles",
        headers=_auth(token),
        json={"roles": ["member"]},
    )
    assert resp.status_code == 404, resp.text


async def test_admin_cannot_modify_own_roles(client) -> None:
    admin_id = await _register(client, "self")
    await _grant_admin(admin_id)
    token = await _login(client, "self")

    resp = await client.put(
        f"/api/v1/users/{admin_id}/roles",
        headers=_auth(token),
        json={"roles": ["member"]},
    )
    assert resp.status_code == 403, resp.text
    assert "own roles" in resp.json()["detail"]
