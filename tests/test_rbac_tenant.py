"""TASK-096：RBAC 租户化测试（多租户内授权隔离核心）.

四组：

1. **权限目录全局性**——``permissions`` 表不随租户复制，同一份全局对象。
2. **角色/授权租户化**——每租户各持 admin/member（name 租户内唯一），
   ``do_orm_execute`` 自动过滤 + RLS 兜底使跨租户不可见；``seed_tenant_rbac``
   幂等（重放不产生重复角色/绑定）。
3. **用户角色租户化**——``get_user_roles`` 仅在用户所属租户解析；越租户
   授予在作用域/RLS 下不可见。
4. **RLS 实证（SET ROLE taskflow_app）**——运行时角色下漏加条件仍被策略
   过滤；越租户 INSERT 被 WITH CHECK 拒绝。

本文件与 ``test_tenant_isolation`` 一样自建引擎、自行管理租户上下文，故被
conftest 的默认租户上下文夹具跳过（清理在无上下文下以 RLS bypass 执行）。
"""

import uuid

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.rbac_data import ADMIN_ROLE_NAME, MEMBER_ROLE_NAME
from app.core.tenant_context import (
    reset_current_tenant_id,
    set_current_tenant_id,
)
from app.crud.permission import get_permission_by_name
from app.crud.role import (
    assign_role_to_user,
    get_role_by_name,
    get_user_roles,
)
from app.models.role import Role
from app.models.role_permission import RolePermission
from app.models.tenant import Tenant
from app.models.user import User
from app.models.user_role import UserRole
from app.services.rbac_seed import seed_tenant_rbac

TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@127.0.0.1:5433/taskflow"
RUN_TOKEN = uuid.uuid4().hex[:10]
_PREFIX = f"trbac{RUN_TOKEN}"

engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
SessionFactory = async_sessionmaker(engine, expire_on_commit=False)


async def _cleanup():
    """按本运行前缀精确删除：先子后父，最后删租户（FK RESTRICT）。"""
    async with SessionFactory() as s:
        tids = (
            await s.execute(
                select(Tenant.id).where(Tenant.slug.like(f"{_PREFIX}%"))
            )
        ).scalars().all()
        if not tids:
            return
        uids = (
            await s.execute(
                select(User.id).where(User.username.like(f"{_PREFIX}%"))
            )
        ).scalars().all()
        for m in (UserRole, RolePermission, Role):
            await s.execute(delete(m).where(m.tenant_id.in_(tids)))
        await s.execute(delete(UserRole).where(UserRole.user_id.in_(uids)))
        await s.execute(delete(User).where(User.username.like(f"{_PREFIX}%")))
        await s.execute(delete(Tenant).where(Tenant.slug.like(f"{_PREFIX}%")))
        await s.commit()


@pytest_asyncio.fixture(autouse=True)
async def _cleanup_fixture():
    yield
    await _cleanup()


async def _make_tenant(slug_suffix: str) -> int:
    async with SessionFactory() as s:
        t = Tenant(slug=f"{_PREFIX}-{slug_suffix}", name=f"T {slug_suffix} {_PREFIX}")
        s.add(t)
        await s.commit()
        return t.id


async def _seed(tenant_id: int) -> None:
    async with SessionFactory() as s:
        await seed_tenant_rbac(s, tenant_id)
        await s.commit()


def _uname(tag: str) -> str:
    return f"{_PREFIX}_{tag}"


# --- 1. 权限目录全局性 --------------------------------------------------------


async def test_permission_catalog_is_global():
    """权限定义不随租户复制——无论上下文如何，取到的是同一份全局对象。"""
    ta = await _make_tenant("a")
    tb = await _make_tenant("b")
    async with SessionFactory() as s:
        p_none = await get_permission_by_name(s, "task:read")
        tok_a = set_current_tenant_id(ta)
        try:
            p_a = await get_permission_by_name(s, "task:read")
        finally:
            reset_current_tenant_id(tok_a)
        tok_b = set_current_tenant_id(tb)
        try:
            p_b = await get_permission_by_name(s, "task:read")
        finally:
            reset_current_tenant_id(tok_b)
        assert p_none is not None
        assert p_a.id == p_none.id == p_b.id


# --- 2. 角色/授权租户化 -------------------------------------------------------


async def test_roles_are_tenant_scoped_and_name_unique_per_tenant():
    """两租户各持独立 admin/member；同 name 在不同租户不冲突。"""
    ta = await _make_tenant("a")
    tb = await _make_tenant("b")
    await _seed(ta)
    await _seed(tb)

    async with SessionFactory() as s:
        tok_a = set_current_tenant_id(ta)
        try:
            admin_a = await get_role_by_name(s, ADMIN_ROLE_NAME)
            roles_a = (await s.execute(select(Role))).scalars().all()
        finally:
            reset_current_tenant_id(tok_a)
        assert admin_a is not None
        assert {r.name for r in roles_a} == {ADMIN_ROLE_NAME, MEMBER_ROLE_NAME}
        assert all(r.tenant_id == ta for r in roles_a)
        admin_a_id = admin_a.id

    async with SessionFactory() as s:
        tok_b = set_current_tenant_id(tb)
        try:
            admin_b = await get_role_by_name(s, ADMIN_ROLE_NAME)
        finally:
            reset_current_tenant_id(tok_b)
        assert admin_b is not None
        assert admin_b.id != admin_a_id  # 两租户各自独立 admin 角色


async def test_seed_tenant_rbac_is_idempotent():
    """重放 seed_tenant_rbac 不产生重复角色/绑定。

    每租户 admin=22（不含平台权限 tenant:manage）+ member=10 = 32 条授权。
    """
    ta = await _make_tenant("a")
    await _seed(ta)
    await _seed(ta)  # 重放

    async with SessionFactory() as s:
        tok = set_current_tenant_id(ta)
        try:
            roles = (
                await s.execute(select(Role).where(Role.tenant_id == ta))
            ).scalars().all()
            bindings = (
                await s.execute(
                    select(RolePermission).where(RolePermission.tenant_id == ta)
                )
            ).scalars().all()
        finally:
            reset_current_tenant_id(tok)
        assert len(roles) == 2
        assert len(bindings) == 32


# --- 3. 用户角色租户化 -------------------------------------------------------


async def test_user_roles_resolve_within_tenant():
    """get_user_roles 仅在用户所属租户解析；越租户授予不可见。"""
    ta = await _make_tenant("a")
    tb = await _make_tenant("b")
    await _seed(ta)
    await _seed(tb)

    async with SessionFactory() as s:
        ua = User(
            username=_uname("ua"),
            email=f"{_uname('ua')}@example.com",
            password_hash="h",
            tenant_id=ta,
        )
        s.add(ua)
        await s.flush()
        tok_a = set_current_tenant_id(ta)
        try:
            admin_a = await get_role_by_name(s, ADMIN_ROLE_NAME)
            await assign_role_to_user(s, user_id=ua.id, role_id=admin_a.id)
        finally:
            reset_current_tenant_id(tok_a)
        await s.commit()
        ua_id = ua.id

    async with SessionFactory() as s:
        tok_a = set_current_tenant_id(ta)
        try:
            roles_a = await get_user_roles(s, ua_id)
        finally:
            reset_current_tenant_id(tok_a)
        assert [r.name for r in roles_a] == [ADMIN_ROLE_NAME]

    async with SessionFactory() as s:
        tok_b = set_current_tenant_id(tb)
        try:
            # 在 tb 上下文解析属 ta 的用户 → 看不到任何 tb 角色
            roles_b = await get_user_roles(s, ua_id)
        finally:
            reset_current_tenant_id(tok_b)
        assert roles_b == []


# --- 4. RLS 实证（SET ROLE taskflow_app） ------------------------------------


async def test_rls_isolates_roles_between_tenants():
    """运行时角色下：漏加条件仍只返回本租户角色；越租户 INSERT 被 WITH CHECK 拒。"""
    ta = await _make_tenant("a")
    tb = await _make_tenant("b")
    await _seed(ta)
    await _seed(tb)
    conn = await engine.connect()
    await conn.execute(sa.text("SET ROLE taskflow_app"))
    await conn.execute(sa.text(f"SET LOCAL app.tenant_id = '{ta}'"))
    rows = (await conn.execute(sa.text("SELECT tenant_id FROM roles"))).all()
    assert rows, "expected at least the seeded tenant A roles"
    assert all(r[0] == ta for r in rows)  # 只返回 ta 角色
    with pytest.raises(sa.exc.DBAPIError) as excinfo:
        await conn.execute(
            sa.text("INSERT INTO roles (name, tenant_id) VALUES ('evil', :tid)"),
            {"tid": tb},
        )
    assert "row-level security policy" in str(excinfo.value)
    await conn.rollback()
    await conn.close()
