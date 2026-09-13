"""TASK-023：权限依赖 `require_permission` 的测试。

四组：
1. 工厂校验（离线）——空权限列表 / 非 `resource:action` 格式的权限名在
   创建时即抛 ValueError（启动期快速失败，而非首个请求才暴露）。
2. 授权判定（HTTP 级，真实数据库 + 种子角色）——member 访问 `task:read`
   端点 200、访问 `task:delete` 端点 403 且文案列出缺失权限；admin 全部
   200（§35「不同角色权限差异」）。
3. AND 语义——同时要求两个权限：全持有 → 200，缺一个 → 403。
4. 认证链顺序——认证失败（401）先于授权判定；禁用账号 403 来自
   `load_current_user` 而非权限依赖。

验证方式（TASK-023 决策）：不向产品 API 添加任何端点；在测试内构造一个
独立的 FastAPI 应用挂载探针路由，走完整的 HTTP → 认证 → 授权依赖链。
探针路由使用产品依赖 `require_permission`，与未来真实资源端点的用法
完全一致。写入采用「本次运行唯一前缀 + teardown 精确删除」保证开发库
零残留。
"""

import uuid

import pytest
import pytest_asyncio
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.deps import require_permission
from app.core.exceptions import AppError, app_error_handler
from app.core.security import create_access_token
from app.crud.role import assign_role_to_user, get_role_by_name
from app.crud.user import create_user
from app.db.session import get_db
from app.models.user import User
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@127.0.0.1:5433/taskflow"

RUN_TOKEN = uuid.uuid4().hex[:10]
PASSWORD_HASH = "h"

engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
SessionFactory = async_sessionmaker(engine, expire_on_commit=False)


async def _override_get_db():
    async with SessionFactory() as session:
        yield session


def _username(tag: str) -> str:
    return f"permdep_{RUN_TOKEN}_{tag}"


# --- 测试专用探针应用：路由即「未来真实资源端点」的标准用法 -------------------

probe_app = FastAPI()
# 产品 app.main 注册的同一个 AppError 渲染器，保证 401/403 表现与真实端点一致
probe_app.add_exception_handler(AppError, app_error_handler)


@probe_app.get("/probe/read")
async def probe_read(
    user: User = Depends(require_permission("task:read")),
):
    return {"user_id": user.id}


@probe_app.get("/probe/delete")
async def probe_delete(
    user: User = Depends(require_permission("task:delete")),
):
    return {"user_id": user.id}


@probe_app.get("/probe/and-ok")
async def probe_and_ok(
    user: User = Depends(require_permission("task:read", "task:update")),
):
    return {"user_id": user.id}


@probe_app.get("/probe/and-missing")
async def probe_and_missing(
    user: User = Depends(require_permission("task:read", "task:delete")),
):
    return {"user_id": user.id}


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest_asyncio.fixture
async def client():
    probe_app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=probe_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c
    probe_app.dependency_overrides.pop(get_db, None)


@pytest_asyncio.fixture(autouse=True)
async def _cleanup():
    yield
    async with SessionFactory() as session:
        await session.execute(
            delete(User).where(User.username.like(f"permdep_{RUN_TOKEN}%"))
        )
        await session.commit()


async def _user_with_role(tag: str, role_name: str | None) -> User:
    """创建用户并（可选）授予种子角色；提交后对 HTTP 请求可见。"""
    async with SessionFactory() as session:
        user = await create_user(
            session,
            username=_username(tag),
            email=f"{_username(tag)}@example.com",
            password_hash=PASSWORD_HASH,
        )
        if role_name is not None:
            role = await get_role_by_name(session, role_name)
            assert role is not None, f"seed role {role_name!r} missing"
            await assign_role_to_user(session, user_id=user.id, role_id=role.id)
        await session.commit()
        await session.refresh(user)
        return user


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# --- 1. 工厂校验（离线） ------------------------------------------------------


@pytest.mark.parametrize(
    "bad_name",
    ["taskread", "", ":", ":read", "task:", "a:b:c", "TASK READ"],
)
def test_factory_rejects_malformed_permission_names(bad_name):
    with pytest.raises(ValueError, match="resource:action"):
        require_permission(bad_name)


def test_factory_rejects_empty_permissions():
    with pytest.raises(ValueError, match="at least one"):
        require_permission()


def test_factory_accepts_valid_names_and_returns_callable():
    checker = require_permission("task:read", "task:update")
    assert callable(checker)


# --- 2. 授权判定（HTTP 级） ---------------------------------------------------


async def test_member_passes_task_read(client):
    user = await _user_with_role("member_r", "member")
    resp = await client.get("/probe/read", headers=_bearer(create_access_token(user.id)))
    assert resp.status_code == 200, resp.text
    assert resp.json()["user_id"] == user.id


async def test_member_denied_task_delete_with_missing_permission_in_detail(client):
    user = await _user_with_role("member_d", "member")
    resp = await client.get("/probe/delete", headers=_bearer(create_access_token(user.id)))
    assert resp.status_code == 403, resp.text
    assert "task:delete" in resp.json()["detail"]


async def test_admin_passes_task_delete(client):
    user = await _user_with_role("admin_d", "admin")
    resp = await client.get("/probe/delete", headers=_bearer(create_access_token(user.id)))
    assert resp.status_code == 200, resp.text
    assert resp.json()["user_id"] == user.id


async def test_roles_differ_on_same_endpoint(client):
    """§35「不同角色权限差异」：同一端点，member 403 / admin 200。"""
    member = await _user_with_role("diff_m", "member")
    admin = await _user_with_role("diff_a", "admin")
    token_m = create_access_token(member.id)
    token_a = create_access_token(admin.id)
    assert (
        await client.get("/probe/delete", headers=_bearer(token_m))
    ).status_code == 403
    assert (
        await client.get("/probe/delete", headers=_bearer(token_a))
    ).status_code == 200


async def test_roleless_user_denied_even_read(client):
    user = await _user_with_role("roleless", None)
    resp = await client.get("/probe/read", headers=_bearer(create_access_token(user.id)))
    assert resp.status_code == 403, resp.text
    assert "task:read" in resp.json()["detail"]


# --- 3. AND 语义 --------------------------------------------------------------


async def test_and_all_held_passes(client):
    user = await _user_with_role("and_ok", "member")
    resp = await client.get("/probe/and-ok", headers=_bearer(create_access_token(user.id)))
    assert resp.status_code == 200, resp.text
    assert resp.json()["user_id"] == user.id


async def test_and_missing_one_fails_and_lists_it(client):
    user = await _user_with_role("and_miss", "member")
    resp = await client.get(
        "/probe/and-missing", headers=_bearer(create_access_token(user.id))
    )
    assert resp.status_code == 403, resp.text
    detail = resp.json()["detail"]
    assert "task:delete" in detail  # 缺失的那个被点名
    assert "task:read" not in detail  # 已持有的不被误报


# --- 4. 认证链顺序 ------------------------------------------------------------


async def test_missing_token_is_401_before_permission_check(client):
    resp = await client.get("/probe/read")
    assert resp.status_code == 401, resp.text
    assert resp.headers.get("www-authenticate") == "Bearer"


async def test_garbage_token_is_401(client):
    resp = await client.get("/probe/read", headers=_bearer("not-a-jwt"))
    assert resp.status_code == 401, resp.text


async def test_disabled_account_is_403_from_auth_chain(client):
    """禁用账号的 403 文案来自 load_current_user，而非权限依赖。"""
    user = await _user_with_role("disabled", "member")
    async with SessionFactory() as session:
        row = await session.get(User, user.id)
        row.is_active = False
        await session.commit()
    resp = await client.get("/probe/read", headers=_bearer(create_access_token(user.id)))
    assert resp.status_code == 403, resp.text
    assert resp.json()["detail"] == "User account is disabled"
    # 恢复启用后同一 Token 可通过权限判定
    async with SessionFactory() as session:
        row = await session.get(User, user.id)
        row.is_active = True
        await session.commit()
    resp = await client.get("/probe/read", headers=_bearer(create_access_token(user.id)))
    assert resp.status_code == 200, resp.text
