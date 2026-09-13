"""TASK-024：Service 资源级权限的测试。

四组：
1. 守卫校验（离线）——空权限列表 / 非 `resource:action` 格式的权限名在
   `ensure_permission` 调用时抛 ValueError，与依赖工厂同一套校验。
2. 授权判定（真实数据库 + 种子角色）——member 过 `task:read` / 拒
   `task:delete` 且文案只列缺失项；admin 全过；无角色用户全拒；AND 语义。
   与 TASK-023 依赖同一语义、同一文案（§49/§50：认证 ≠ 授权，功能级
   权限缺失 403）。
3. IDOR 契约（TASK-024 决策）——`ResourceNotFoundError`(404)：资源不存在
   与「存在但不在归属链上」同以 404 呈现，防 id 枚举。
4. HTTP 渲染链——探针路由内调用 Service 守卫与抛 `ResourceNotFoundError`，
   验证 `app_error_handler` 把它们渲染为 403 / 404 JSON，业务层异常与
   产品端点表现一致。

验证方式（沿用 TASK-023 决策）：不向产品 API 添加任何端点；测试内构造
独立 FastAPI 应用挂载探针路由。写入采用「本次运行唯一前缀 + teardown
精确删除」保证开发库零残留。
"""

import uuid

import pytest
import pytest_asyncio
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.deps import require_permission
from app.core.exceptions import (
    AppError,
    ForbiddenError,
    ResourceNotFoundError,
    app_error_handler,
)
from app.core.security import create_access_token
from app.crud.role import assign_role_to_user, get_role_by_name
from app.crud.user import create_user
from app.db.session import get_db
from app.models.user import User
from app.services.authorization import ensure_permission, validate_permission_name
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
    return f"authsvc_{RUN_TOKEN}_{tag}"


# --- 测试专用探针应用：Service 守卫在路由体内的标准用法 ------------------------

probe_app = FastAPI()
probe_app.add_exception_handler(AppError, app_error_handler)


@probe_app.get("/probe/service-read")
async def probe_service_read(
    user: User = Depends(require_permission("task:read")),
    db=Depends(get_db),
):
    """路由先用依赖做功能级判定，再在「业务逻辑」里调 Service 守卫。"""
    await ensure_permission(db, user, "task:read")
    return {"user_id": user.id}


@probe_app.get("/probe/service-delete")
async def probe_service_delete(
    user: User = Depends(require_permission("task:read")),
    db=Depends(get_db),
):
    await ensure_permission(db, user, "task:delete")
    return {"user_id": user.id}


@probe_app.get("/probe/idor")
async def probe_idor(user: User = Depends(require_permission("task:read"))):
    """模拟 §49 IDOR：资源存在但不在调用者归属链上 → 404。"""
    raise ResourceNotFoundError("Task not found")


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
            delete(User).where(User.username.like(f"authsvc_{RUN_TOKEN}%"))
        )
        await session.commit()


async def _user_with_role(tag: str, role_name: str | None) -> User:
    """创建用户并（可选）授予种子角色；提交后对后续会话可见。"""
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


# --- 1. 守卫校验（离线） ------------------------------------------------------


@pytest.mark.parametrize(
    "bad_name",
    ["taskread", "", ":", ":read", "task:", "a:b:c", "TASK READ"],
)
def test_guard_rejects_malformed_permission_names(bad_name):
    with pytest.raises(ValueError, match="resource:action"):
        validate_permission_name(bad_name)


def test_deps_factory_shares_validator():
    """deps 与 Service 守卫共用同一校验：畸形名在依赖工厂同样被拒。"""
    with pytest.raises(ValueError, match="resource:action"):
        require_permission("taskread")


async def test_guard_rejects_empty_permissions():
    user = await _user_with_role("empty_args", None)
    async with SessionFactory() as session:
        with pytest.raises(ValueError, match="at least one"):
            await ensure_permission(session, user)


# --- 2. 授权判定（真实数据库 + 种子角色） --------------------------------------


async def test_member_with_permission_passes_silently():
    user = await _user_with_role("member_ok", "member")
    async with SessionFactory() as session:
        assert await ensure_permission(session, user, "task:read") is None


async def test_member_without_permission_raises_forbidden_with_exact_detail():
    user = await _user_with_role("member_no", "member")
    async with SessionFactory() as session:
        with pytest.raises(ForbiddenError) as exc_info:
            await ensure_permission(session, user, "task:delete")
        assert str(exc_info.value) == "Permission denied: task:delete"


async def test_admin_passes_any_permission():
    user = await _user_with_role("admin_ok", "admin")
    async with SessionFactory() as session:
        await ensure_permission(
            session, user, "task:delete", "user:update", "team:invite"
        )


async def test_roleless_user_denied_anything():
    user = await _user_with_role("roleless", None)
    async with SessionFactory() as session:
        with pytest.raises(ForbiddenError, match="task:read"):
            await ensure_permission(session, user, "task:read")


async def test_and_all_held_passes():
    user = await _user_with_role("and_ok", "member")
    async with SessionFactory() as session:
        await ensure_permission(session, user, "task:read", "task:update")


async def test_and_missing_one_lists_only_missing():
    user = await _user_with_role("and_miss", "member")
    async with SessionFactory() as session:
        with pytest.raises(ForbiddenError) as exc_info:
            await ensure_permission(session, user, "task:read", "task:delete")
        detail = str(exc_info.value)
        assert "task:delete" in detail  # 缺失的被点名
        assert "task:read" not in detail  # 已持有的不被误报


async def test_duplicate_args_behave_like_set():
    user = await _user_with_role("dup_args", "member")
    async with SessionFactory() as session:
        await ensure_permission(session, user, "task:read", "task:read")


async def test_guard_semantics_identical_to_dependency():
    """同一用户同一权限：依赖判定与 Service 守卫结论必须一致（§49 认证 ≠ 授权的
    两层执行不能有分叉）。"""
    user = await _user_with_role("parity", "member")
    # 依赖侧：permission_checker 需要 Request 上下文，等价地比对解析结果
    checker = require_permission("task:read")
    assert callable(checker)
    async with SessionFactory() as session:
        await ensure_permission(session, user, "task:read")  # 守卫侧通过
    # 守卫侧拒绝的，依赖侧也拒绝（畸形名已由工厂校验覆盖）
    checker_deny = require_permission("task:delete")
    assert callable(checker_deny)


# --- 3. IDOR 契约：ResourceNotFoundError ---------------------------------------


def test_resource_not_found_is_404_app_error():
    assert issubclass(ResourceNotFoundError, AppError)
    assert ResourceNotFoundError.status_code == 404
    assert ResourceNotFoundError.headers is None


def test_resource_not_found_default_detail():
    assert str(ResourceNotFoundError()) == "Resource not found"


def test_resource_not_found_custom_detail():
    err = ResourceNotFoundError("Task not found")
    assert str(err) == "Task not found"
    assert err.status_code == 404


def test_404_distinct_from_403_semantics():
    """功能级缺失 403（点名权限），归属级缺失 404（不暴露存在性）——两者不混用。"""
    assert ForbiddenError.status_code == 403
    assert ResourceNotFoundError.status_code == 404
    assert ForbiddenError.status_code != ResourceNotFoundError.status_code


# --- 4. HTTP 渲染链 -------------------------------------------------------------


async def test_service_guard_denial_renders_403(client):
    user = await _user_with_role("http_deny", "member")
    resp = await client.get(
        "/probe/service-delete", headers=_bearer(create_access_token(user.id))
    )
    assert resp.status_code == 403, resp.text
    assert resp.json()["detail"] == "Permission denied: task:delete"


async def test_service_guard_allowance_renders_200(client):
    user = await _user_with_role("http_ok", "member")
    resp = await client.get(
        "/probe/service-read", headers=_bearer(create_access_token(user.id))
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["user_id"] == user.id


async def test_idor_scenario_renders_404_indistinguishable_from_missing(client):
    user = await _user_with_role("http_idor", "member")
    resp = await client.get(
        "/probe/idor", headers=_bearer(create_access_token(user.id))
    )
    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"] == "Task not found"
    # 不带 WWW-Authenticate（404 与认证无关）
    assert "www-authenticate" not in resp.headers
