"""TASK-093：Tenant 模型、生命周期与平台管理端点测试。

三组：
1. 离线模型测试——只检查映射的列与约束，不需要 PostgreSQL（沿用
   TASK-021/026 模式）。列定稿 docs/DB_SCHEMA.md「tenants（TASK-093）」，
   决策登记 docs/DECISIONS.md 065：slug 全局 UNIQUE + 格式 CHECK 且不可变、
   status 值域 CHECK（转换白名单 Service 执行）、配额列可空（NULL = 不限）、
   name 不加 UNIQUE。
2. 数据库约束集成测试——真实 PostgreSQL 上验证 DB 级兜底：slug UNIQUE、
   CHECK 拒绝非法状态/非法 slug/非法配额。写入采用「本次运行唯一前缀 +
   teardown 精确删除」。
3. 平台管理端点端到端——真实 ``require_permission("tenant:manage")`` +
   真实认证链（种子迁移已把 tenant:manage 授予 admin），仅覆盖 get_db：
   平台管理员创建/停用/恢复/删除租户、slug 冲突 409、非法状态转换 409、
   deleted 终态不可再改 409、member 无权限 403、404、分页 total。

级联行为说明（TASKS 验收项）：本 TASK 不接业务表（tenant_id 归属属
TASK-094），tenants 暂无被引用关系，级联行为集合为空——TASK-094 落表后
由其测试补级联断言。
"""

import uuid

import pytest
import pytest_asyncio
from fastapi import status
from httpx import ASGITransport, AsyncClient
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    String,
    UniqueConstraint,
    delete,
    select,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.security import create_access_token
from app.crud.role import assign_role_to_user, get_role_by_name
from app.crud.user import create_user
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import Role, RolePermission, Tenant, User, UserRole
from app.models.tenant import ALLOWED_TENANT_TRANSITIONS, TENANT_SLUG_PATTERN
from app.schemas.tenant import TenantUpdate

TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@127.0.0.1:5433/taskflow"

RUN_TOKEN = uuid.uuid4().hex[:10]
PASSWORD_HASH = "h"

engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
SessionFactory = async_sessionmaker(engine, expire_on_commit=False)


async def _override_get_db():
    async with SessionFactory() as session:
        yield session


def _slug(tag: str) -> str:
    return f"t{RUN_TOKEN}{tag}"


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
        # TASK-096：create_tenant_with_checks 现在会为租户播种 RBAC（roles /
        # role_permissions / user_roles 均带 tenant_id 且 RESTRICT 引用 tenants）。
        # 直接删 Tenant 会被新加的外键拦截，故先按 slug 锁定租户 id，再按
        # tenant_id 精确清理 RBAC 三表，最后删用户与租户本身。连接角色为
        # postgres 超级用户，RLS 自动绕过，批量删除不受行级策略影响。
        result = await session.execute(
            select(Tenant.id).where(Tenant.slug.like(f"t{RUN_TOKEN}%"))
        )
        tenant_ids = [row[0] for row in result]
        if tenant_ids:
            await session.execute(
                delete(RolePermission).where(
                    RolePermission.tenant_id.in_(tenant_ids)
                )
            )
            await session.execute(
                delete(UserRole).where(UserRole.tenant_id.in_(tenant_ids))
            )
            await session.execute(
                delete(Role).where(Role.tenant_id.in_(tenant_ids))
            )
        await session.execute(
            delete(User).where(User.username.like(f"tenant93_{RUN_TOKEN}%"))
        )
        await session.execute(
            delete(Tenant).where(Tenant.slug.like(f"t{RUN_TOKEN}%"))
        )
        await session.commit()


# --- 1. 离线模型测试 -----------------------------------------------------------


def test_tenants_registered_on_metadata():
    assert "tenants" in Base.metadata.tables


def test_tenant_tablename():
    assert Tenant.__tablename__ == "tenants"


def test_tenant_columns():
    assert set(Tenant.__table__.columns.keys()) == {
        "id",
        "name",
        "slug",
        "status",
        "member_limit",
        "storage_limit_bytes",
        "created_at",
        "updated_at",
    }


def test_tenant_id_is_bigint_primary_key():
    col = Tenant.__table__.columns["id"]
    assert col.primary_key is True
    assert isinstance(col.type, BigInteger)


def test_tenant_slug_unique_and_not_nullable():
    col = Tenant.__table__.columns["slug"]
    assert col.nullable is False
    assert col.unique is True
    assert isinstance(col.type, String)
    assert col.type.length == 63
    uqs = [c for c in Tenant.__table__.constraints if isinstance(c, UniqueConstraint)]
    assert any(c.name == "uq_tenants_slug" for c in uqs)


def test_tenant_name_not_unique():
    """§61.3 未定义租户名唯一（DECISIONS 065：与 teams.name 同口径）。"""
    col = Tenant.__table__.columns["name"]
    assert col.nullable is False
    assert col.unique is not True
    assert col.type.length == 150


def test_tenant_status_check_and_default():
    col = Tenant.__table__.columns["status"]
    assert col.nullable is False
    assert col.server_default is not None
    checks = [c for c in Tenant.__table__.constraints if isinstance(c, CheckConstraint)]
    assert any(
        c.name == "ck_tenants_status"
        and "active" in str(c.sqltext)
        and "suspended" in str(c.sqltext)
        and "deleted" in str(c.sqltext)
        for c in checks
    )


def test_tenant_slug_format_check():
    checks = [c for c in Tenant.__table__.constraints if isinstance(c, CheckConstraint)]
    assert any(
        c.name == "ck_tenants_slug_format" and "~" in str(c.sqltext) for c in checks
    )


def test_tenant_quota_checks():
    checks = [c for c in Tenant.__table__.constraints if isinstance(c, CheckConstraint)]
    by_name = {c.name: c for c in checks}
    assert "member_limit IS NULL OR member_limit > 0" in str(
        by_name["ck_tenants_member_limit"].sqltext
    )
    assert "storage_limit_bytes IS NULL OR storage_limit_bytes >= 0" in str(
        by_name["ck_tenants_storage_limit"].sqltext
    )


def test_tenant_quota_columns_nullable():
    assert Tenant.__table__.columns["member_limit"].nullable is True
    assert Tenant.__table__.columns["storage_limit_bytes"].nullable is True


def test_tenant_timestamps_timezone_aware():
    for name in ("created_at", "updated_at"):
        col = Tenant.__table__.columns[name]
        assert isinstance(col.type, DateTime)
        assert col.type.timezone is True
        assert col.nullable is False
        assert col.server_default is not None


def test_status_transition_whitelist():
    """active ↔ suspended 双向、二者均可 → deleted、deleted 无出边（终态）。"""
    assert ALLOWED_TENANT_TRANSITIONS["active"] == frozenset({"suspended", "deleted"})
    assert ALLOWED_TENANT_TRANSITIONS["suspended"] == frozenset({"active", "deleted"})
    assert ALLOWED_TENANT_TRANSITIONS["deleted"] == frozenset()


def test_slug_pattern_shape():
    import re

    pattern = re.compile(TENANT_SLUG_PATTERN)
    assert pattern.fullmatch("acme")
    assert pattern.fullmatch("acme-corp-2")
    assert pattern.fullmatch("a")
    assert not pattern.fullmatch("-acme")
    assert not pattern.fullmatch("acme-")
    assert not pattern.fullmatch("Acme")
    assert not pattern.fullmatch("acme_corp")


def test_repr_contains_identity():
    assert "Tenant" in repr(Tenant(id=1, slug="acme", status="active"))


# --- 2. 数据库约束集成测试 -------------------------------------------------------


async def _make_tenant_row(tag: str, **overrides) -> Tenant:
    async with SessionFactory() as session:
        tenant = Tenant(
            name=f"tenant93 {RUN_TOKEN} {tag}",
            slug=_slug(tag),
            **overrides,
        )
        session.add(tenant)
        await session.commit()
        await session.refresh(tenant)
        return tenant


async def test_insert_tenant_roundtrip():
    tenant = await _make_tenant_row("rt", member_limit=10, storage_limit_bytes=1024)
    async with SessionFactory() as session:
        loaded = await session.get(Tenant, tenant.id)
        assert loaded.status == "active"
        assert loaded.member_limit == 10
        assert loaded.storage_limit_bytes == 1024
        assert loaded.created_at is not None


async def test_duplicate_slug_rejected_by_unique():
    await _make_tenant_row("dup")
    async with SessionFactory() as session:
        session.add(Tenant(name="another", slug=_slug("dup")))
        with pytest.raises(IntegrityError):
            await session.flush()


async def test_invalid_status_rejected_by_check():
    async with SessionFactory() as session:
        session.add(Tenant(name="bad", slug=_slug("ckstatus"), status="archived"))
        with pytest.raises(IntegrityError):
            await session.flush()


async def test_invalid_slug_format_rejected_by_check():
    async with SessionFactory() as session:
        session.add(Tenant(name="bad", slug=f"T{RUN_TOKEN}upper"))
        with pytest.raises(IntegrityError):
            await session.flush()


async def test_nonpositive_member_limit_rejected_by_check():
    async with SessionFactory() as session:
        session.add(Tenant(name="bad", slug=_slug("ckml"), member_limit=0))
        with pytest.raises(IntegrityError):
            await session.flush()


async def test_negative_storage_limit_rejected_by_check():
    async with SessionFactory() as session:
        session.add(Tenant(name="bad", slug=_slug("cksl"), storage_limit_bytes=-1))
        with pytest.raises(IntegrityError):
            await session.flush()


# --- 3. 平台管理端点端到端 -------------------------------------------------------


async def _make_user(tag: str, role_names: list[str] | None = None) -> User:
    """创建用户并授予种子角色（只读种子，只写 user_roles 关联）。"""
    async with SessionFactory() as session:
        user = await create_user(
            session,
            username=f"tenant93_{RUN_TOKEN}_{tag}",
            email=f"tenant93_{RUN_TOKEN}_{tag}@example.com",
            password_hash=PASSWORD_HASH,
        )
        for role_name in role_names or []:
            role = await get_role_by_name(session, role_name)
            assert role is not None, f"seed role {role_name!r} missing"
            await assign_role_to_user(session, user_id=user.id, role_id=role.id)
        await session.commit()
        await session.refresh(user)
        return user


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def test_create_tenant_as_platform_admin(client):
    admin = await _make_user("admin", ["admin"])
    resp = await client.post(
        "/api/v1/tenants",
        json={"name": "Acme Inc", "slug": _slug("create"), "member_limit": 25},
        headers=_bearer(create_access_token(admin.id)),
    )
    assert resp.status_code == status.HTTP_201_CREATED, resp.text
    body = resp.json()
    assert body["message"] == "success"
    assert body["data"]["slug"] == _slug("create")
    assert body["data"]["status"] == "active"
    assert body["data"]["member_limit"] == 25
    assert body["data"]["storage_limit_bytes"] is None


async def test_create_tenant_requires_platform_permission(client):
    member = await _make_user("member", ["member"])
    resp = await client.post(
        "/api/v1/tenants",
        json={"name": "Nope", "slug": _slug("noperm")},
        headers=_bearer(create_access_token(member.id)),
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN
    assert "tenant:manage" in resp.json()["detail"]


async def test_create_tenant_requires_auth(client):
    resp = await client.post(
        "/api/v1/tenants", json={"name": "Anon", "slug": _slug("anon")}
    )
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED


async def test_slug_conflict_returns_409(client):
    admin = await _make_user("admin2", ["admin"])
    headers = _bearer(create_access_token(admin.id))
    first = await client.post(
        "/api/v1/tenants",
        json={"name": "First", "slug": _slug("conflict")},
        headers=headers,
    )
    assert first.status_code == status.HTTP_201_CREATED
    second = await client.post(
        "/api/v1/tenants",
        json={"name": "Second", "slug": _slug("conflict")},
        headers=headers,
    )
    assert second.status_code == status.HTTP_409_CONFLICT
    assert second.json()["detail"] == "Tenant slug already exists"


async def test_slug_validation_rejects_bad_format(client):
    admin = await _make_user("admin3", ["admin"])
    resp = await client.post(
        "/api/v1/tenants",
        json={"name": "Bad", "slug": f"-{RUN_TOKEN}bad-"},
        headers=_bearer(create_access_token(admin.id)),
    )
    assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


async def test_status_lifecycle_whitelist(client):
    admin = await _make_user("admin4", ["admin"])
    headers = _bearer(create_access_token(admin.id))
    created = await client.post(
        "/api/v1/tenants",
        json={"name": "Lifecycle", "slug": _slug("life")},
        headers=headers,
    )
    tenant_id = created.json()["data"]["id"]

    # active -> suspended -> active（双向白名单）
    suspended = await client.patch(
        f"/api/v1/tenants/{tenant_id}/status",
        json={"status": "suspended"},
        headers=headers,
    )
    assert suspended.status_code == status.HTTP_200_OK
    assert suspended.json()["data"]["status"] == "suspended"
    reactivated = await client.patch(
        f"/api/v1/tenants/{tenant_id}/status",
        json={"status": "active"},
        headers=headers,
    )
    assert reactivated.json()["data"]["status"] == "active"

    # 同状态重复请求幂等放行
    again = await client.patch(
        f"/api/v1/tenants/{tenant_id}/status",
        json={"status": "active"},
        headers=headers,
    )
    assert again.status_code == status.HTTP_200_OK

    # active -> active 之外都非法的转换：deleted -> active 不可能，先验证非法路径
    illegal = await client.patch(
        f"/api/v1/tenants/{tenant_id}/status",
        json={"status": "deleted"},
        headers=headers,
    )
    assert illegal.status_code == status.HTTP_200_OK  # active -> deleted 合法
    terminal = await client.patch(
        f"/api/v1/tenants/{tenant_id}/status",
        json={"status": "active"},
        headers=headers,
    )
    assert terminal.status_code == status.HTTP_409_CONFLICT
    assert "deleted -> active" in terminal.json()["detail"]


async def test_deleted_tenant_is_terminal_for_updates(client):
    admin = await _make_user("admin5", ["admin"])
    headers = _bearer(create_access_token(admin.id))
    created = await client.post(
        "/api/v1/tenants",
        json={"name": "Terminal", "slug": _slug("term")},
        headers=headers,
    )
    tenant_id = created.json()["data"]["id"]
    deleted = await client.patch(
        f"/api/v1/tenants/{tenant_id}/status",
        json={"status": "deleted"},
        headers=headers,
    )
    assert deleted.json()["data"]["status"] == "deleted"

    update = await client.patch(
        f"/api/v1/tenants/{tenant_id}",
        json={"name": "Renamed"},
        headers=headers,
    )
    assert update.status_code == status.HTTP_409_CONFLICT
    assert update.json()["detail"] == "Tenant is deleted"


async def test_update_name_and_quotas_partial(client):
    admin = await _make_user("admin6", ["admin"])
    headers = _bearer(create_access_token(admin.id))
    created = await client.post(
        "/api/v1/tenants",
        json={"name": "Before", "slug": _slug("upd"), "member_limit": 10},
        headers=headers,
    )
    tenant_id = created.json()["data"]["id"]
    updated = await client.patch(
        f"/api/v1/tenants/{tenant_id}",
        json={"name": "After", "storage_limit_bytes": 0},
        headers=headers,
    )
    assert updated.status_code == status.HTTP_200_OK
    data = updated.json()["data"]
    assert data["name"] == "After"
    assert data["member_limit"] == 10  # 未提供的字段保持不变
    assert data["storage_limit_bytes"] == 0  # 显式 0 = 允许但为 0 的配额


async def test_update_rejects_slug_and_invalid_quota(client):
    admin = await _make_user("admin7", ["admin"])
    headers = _bearer(create_access_token(admin.id))
    created = await client.post(
        "/api/v1/tenants",
        json={"name": "Immutable", "slug": _slug("noslug")},
        headers=headers,
    )
    tenant_id = created.json()["data"]["id"]

    # slug 不在更新契约中：即使塞进 payload 也会被 422 挡住（extra 字段默认禁止?）
    # pydantic v2 默认 ignore extra —— 因此显式断言 slug 未被改动的行为契约。
    assert "slug" not in TenantUpdate.model_fields
    resp = await client.patch(
        f"/api/v1/tenants/{tenant_id}",
        json={"member_limit": -5},
        headers=headers,
    )
    assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


async def test_get_tenant_404_and_list_pagination(client):
    admin = await _make_user("admin8", ["admin"])
    headers = _bearer(create_access_token(admin.id))

    missing = await client.get("/api/v1/tenants/999999999", headers=headers)
    assert missing.status_code == status.HTTP_404_NOT_FOUND
    assert missing.json()["detail"] == "Tenant not found"

    for tag in ("l1", "l2", "l3"):
        await client.post(
            "/api/v1/tenants",
            json={"name": f"List {tag}", "slug": _slug(tag)},
            headers=headers,
        )

    page = await client.get(
        "/api/v1/tenants", params={"skip": 0, "limit": 2}, headers=headers
    )
    assert page.status_code == status.HTTP_200_OK
    data = page.json()["data"]
    assert data["total"] >= 3
    assert len(data["items"]) == 2

    page2 = await client.get(
        "/api/v1/tenants", params={"skip": 2, "limit": 2}, headers=headers
    )
    assert len(page2.json()["data"]["items"]) >= 1

    # 无权限者连列表都不可见（member 403）
    member = await _make_user("member8", ["member"])
    denied = await client.get(
        "/api/v1/tenants", headers=_bearer(create_access_token(member.id))
    )
    assert denied.status_code == status.HTTP_403_FORBIDDEN


async def test_get_tenant_detail(client):
    """GET /tenants/{id} 返回租户详情（含配额与时间戳）。"""
    admin = await _make_user("admin10", ["admin"])
    headers = _bearer(create_access_token(admin.id))
    created = await client.post(
        "/api/v1/tenants",
        json={"name": "Detail", "slug": _slug("detail"), "member_limit": 5},
        headers=headers,
    )
    tenant_id = created.json()["data"]["id"]
    resp = await client.get(f"/api/v1/tenants/{tenant_id}", headers=headers)
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()["data"]
    assert data["name"] == "Detail"
    assert data["slug"] == _slug("detail")
    assert data["member_limit"] == 5
    assert data["created_at"]


async def test_slug_of_deleted_tenant_still_taken(client):
    """deleted 是状态而非物理删除：slug 依旧占用（DECISIONS 065）。"""
    admin = await _make_user("admin9", ["admin"])
    headers = _bearer(create_access_token(admin.id))
    created = await client.post(
        "/api/v1/tenants",
        json={"name": "Gone", "slug": _slug("gone")},
        headers=headers,
    )
    tenant_id = created.json()["data"]["id"]
    await client.patch(
        f"/api/v1/tenants/{tenant_id}/status",
        json={"status": "deleted"},
        headers=headers,
    )
    conflict = await client.post(
        "/api/v1/tenants",
        json={"name": "Reuse", "slug": _slug("gone")},
        headers=headers,
    )
    assert conflict.status_code == status.HTTP_409_CONFLICT
