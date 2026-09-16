"""TASK-022：RBAC Migration / CRUD 的测试。

三组：
1. 种子数据验证（只读）——0de65c197efc 数据迁移在 `upgrade head` 后应保证
   admin / member 角色存在、§6 全部 22 项权限落库、admin 绑定全部权限、
   member 恰好持有「读 + 基础写」10 项（TASK-022 决策）。这也是开发文档
   §56 Phase 4「ADMIN / MEMBER 权限表现不同」验收的数据前提。
2. CRUD 集成测试（flush-only，session 关闭即回滚，开发库零残留）——
   角色/权限的增查、关联表的授予/撤销/绑定/解绑及幂等语义、
   复合 UNIQUE 约束由数据库兜底。
3. 模型链端到端——User → UserRole → Role → RolePermission → Permission
   解析出 `resource:action` 权限名集合（TASK-023 权限依赖的直接输入），
   含多角色去重与用户删除级联清理。

数据库：宿主 5433 的开发库（与 test_user_crud.py 同一套模式）。
"""

import os
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.crud.permission import (
    bind_permission_to_role,
    create_permission,
    get_permission,
    get_permission_by_name,
    get_permissions,
    get_role_permissions,
    get_user_permissions,
    unbind_permission_from_role,
)
from app.crud.role import (
    assign_role_to_user,
    create_role,
    get_role,
    get_role_by_name,
    get_roles,
    get_user_roles,
    revoke_role_from_user,
)
from app.crud.user import create_user
from app.models.permission import Permission
from app.models.role import Role
from app.models.user import User
from app.models.user_role import UserRole

TEST_DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql+asyncpg://postgres:postgres@127.0.0.1:5433/taskflow"
)

RUN_TOKEN = uuid.uuid4().hex[:10]

# TASK-022 决策：member = 读 + 基础写（与种子迁移中的 MEMBER_PERMISSIONS 一致）。
MEMBER_EXPECTED = {
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
}


@pytest_asyncio.fixture(scope="module")
async def engine():
    eng = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session(engine):
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        yield s
    # Closing the session rolls back any uncommitted work.


@pytest_asyncio.fixture(autouse=True)
async def _safety_cleanup(engine):
    """兜底清理：flush-only 模式理论上零残留，此 fixture 防御外部中断残留。"""
    yield
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        await s.execute(
            delete(User).where(User.username.like(f"rbaccrud_{RUN_TOKEN}%"))
        )
        await s.execute(delete(Role).where(Role.name.like(f"rbaccrud_{RUN_TOKEN}%")))
        await s.execute(
            delete(Permission).where(Permission.name.like(f"rbaccrud:{RUN_TOKEN}%"))
        )
        await s.commit()


def _role_name(tag: str) -> str:
    return f"rbaccrud_{RUN_TOKEN}_{tag}"


def _perm_name(tag: str) -> str:
    return f"rbaccrud:{RUN_TOKEN}:{tag}"


def _username(tag: str) -> str:
    return f"rbaccrud_{RUN_TOKEN}_{tag}"


# --- 种子数据验证（只读，不产生任何写入） ------------------------------------


async def test_seed_roles_exist(session):
    admin = await get_role_by_name(session, "admin")
    member = await get_role_by_name(session, "member")
    assert admin is not None
    assert member is not None
    assert admin.id != member.id


async def test_seed_permissions_complete(session):
    perms = await get_permissions(session, skip=0, limit=100)
    names = {p.name for p in perms}
    # §6 的 22 项 + TASK-093 平台管理员权限 tenant:manage
    assert len(names) == 23
    # §6 每个资源域都有代表性权限；格式严格为 resource:action
    for expected in (
        "user:read",
        "user:update",
        "team:invite",
        "project:delete",
        "task:transition",
        "comment:delete",
        "attachment:upload",
        "log:read",
    ):
        assert expected in names
    for name in names:
        assert ":" in name, f"permission {name!r} must be resource:action format"


async def test_seed_admin_has_all_permissions(session):
    admin = await get_role_by_name(session, "admin")
    perms = await get_role_permissions(session, admin.id)
    assert len(perms) == 23  # 含 TASK-093 的 tenant:manage


async def test_seed_member_has_exactly_decided_set(session):
    member = await get_role_by_name(session, "member")
    perms = await get_role_permissions(session, member.id)
    assert {p.name for p in perms} == MEMBER_EXPECTED


async def test_seed_admin_and_member_sets_differ(session):
    """Phase 4 验收「ADMIN / MEMBER 权限表现不同」的数据前提。"""
    admin = await get_role_by_name(session, "admin")
    member = await get_role_by_name(session, "member")
    admin_names = {p.name for p in await get_role_permissions(session, admin.id)}
    member_names = {p.name for p in await get_role_permissions(session, member.id)}
    assert admin_names != member_names
    assert admin_names - member_names  # admin 严格多于 member


# --- Role CRUD --------------------------------------------------------------


async def test_create_role_and_read_back(session):
    role = await create_role(session, name=_role_name("viewer"), description="read only")
    got = await get_role(session, role.id)
    assert got is not None
    assert got.name == _role_name("viewer")
    assert got.description == "read only"
    assert got.created_at is not None
    assert got.updated_at is not None
    assert (await get_role_by_name(session, _role_name("viewer"))) is not None
    assert (await get_role(session, 9_999_999)) is None
    assert (await get_role_by_name(session, "no-such-role")) is None


async def test_duplicate_role_name_rejected(session):
    # 种子角色 admin 已存在 —— 数据库 UNIQUE 兜底
    with pytest.raises(IntegrityError):
        await create_role(session, name="admin")
    await session.rollback()


async def test_role_pagination(session):
    for i in range(3):
        await create_role(session, name=_role_name(f"page_{i}"))
    roles = await get_roles(session, skip=0, limit=100)
    assert len(roles) >= 3
    single = await get_roles(session, skip=1, limit=1)
    assert len(single) == 1


# --- Permission CRUD --------------------------------------------------------


async def test_create_permission_and_read_back(session):
    perm = await create_permission(session, name=_perm_name("export"))
    got = await get_permission(session, perm.id)
    assert got is not None
    assert got.name == _perm_name("export")
    assert (await get_permission_by_name(session, _perm_name("export"))) is not None
    assert (await get_permission(session, 9_999_999)) is None
    assert (await get_permission_by_name(session, "bogus:action")) is None


async def test_duplicate_permission_name_rejected(session):
    with pytest.raises(IntegrityError):
        await create_permission(session, name="user:read")  # 种子已有
    await session.rollback()


# --- 关联表：授予 / 绑定 / 撤销 / 解绑 ----------------------------------------


async def _make_role(session, tag: str):
    return await create_role(session, name=_role_name(tag))


async def _make_permission(session, tag: str):
    return await create_permission(session, name=_perm_name(tag))


async def _make_user(session, tag: str):
    return await create_user(
        session,
        username=_username(tag),
        email=f"{_username(tag)}@example.com",
        password_hash="h",
    )


async def test_assign_and_get_user_roles(session):
    user = await _make_user(session, "assignee")
    role = await _make_role(session, "editor")
    grant = await assign_role_to_user(session, user_id=user.id, role_id=role.id)
    assert grant.user_id == user.id
    assert grant.role_id == role.id
    roles = await get_user_roles(session, user.id)
    assert [r.id for r in roles] == [role.id]
    # 未授权用户 → 空列表
    other = await _make_user(session, "plain")
    assert await get_user_roles(session, other.id) == []


async def test_duplicate_assignment_rejected(session):
    user = await _make_user(session, "dup_assign")
    role = await _make_role(session, "dup_role")
    await assign_role_to_user(session, user_id=user.id, role_id=role.id)
    with pytest.raises(IntegrityError):
        await assign_role_to_user(session, user_id=user.id, role_id=role.id)
    await session.rollback()


async def test_revoke_role_idempotent(session):
    user = await _make_user(session, "revoker")
    role = await _make_role(session, "revoked")
    await assign_role_to_user(session, user_id=user.id, role_id=role.id)
    assert await revoke_role_from_user(session, user_id=user.id, role_id=role.id) is True
    # 幂等：再次撤销返回 False 而非报错
    assert await revoke_role_from_user(session, user_id=user.id, role_id=role.id) is False
    assert await get_user_roles(session, user.id) == []


async def test_bind_and_get_role_permissions(session):
    role = await _make_role(session, "binder")
    p1 = await _make_permission(session, "alpha")
    p2 = await _make_permission(session, "beta")
    await bind_permission_to_role(session, role_id=role.id, permission_id=p1.id)
    await bind_permission_to_role(session, role_id=role.id, permission_id=p2.id)
    perms = await get_role_permissions(session, role.id)
    assert {p.name for p in perms} == {_perm_name("alpha"), _perm_name("beta")}


async def test_duplicate_binding_rejected(session):
    role = await _make_role(session, "dup_bind")
    perm = await _make_permission(session, "dup_perm")
    await bind_permission_to_role(session, role_id=role.id, permission_id=perm.id)
    with pytest.raises(IntegrityError):
        await bind_permission_to_role(session, role_id=role.id, permission_id=perm.id)
    await session.rollback()


async def test_unbind_permission_idempotent(session):
    role = await _make_role(session, "unbinder")
    perm = await _make_permission(session, "unbound")
    await bind_permission_to_role(session, role_id=role.id, permission_id=perm.id)
    assert (
        await unbind_permission_from_role(session, role_id=role.id, permission_id=perm.id)
        is True
    )
    assert (
        await unbind_permission_from_role(session, role_id=role.id, permission_id=perm.id)
        is False
    )
    assert await get_role_permissions(session, role.id) == []


# --- 模型链端到端（TASK-023 权限依赖的直接输入） ------------------------------


async def test_user_permissions_via_seed_member_role(session):
    """真实种子角色：用户授 member → 恰好解析出 10 项决策权限。"""
    user = await _make_user(session, "member_u")
    member = await get_role_by_name(session, "member")
    await assign_role_to_user(session, user_id=user.id, role_id=member.id)
    perms = await get_user_permissions(session, user.id)
    assert set(perms) == MEMBER_EXPECTED
    assert len(perms) == len(set(perms))


async def test_user_permissions_multi_role_dedup(session):
    """同时持 admin+member：admin 超集覆盖 member，去重后 22 项。"""
    user = await _make_user(session, "hybrid_u")
    admin = await get_role_by_name(session, "admin")
    member = await get_role_by_name(session, "member")
    await assign_role_to_user(session, user_id=user.id, role_id=admin.id)
    await assign_role_to_user(session, user_id=user.id, role_id=member.id)
    perms = await get_user_permissions(session, user.id)
    assert len(perms) == 23  # distinct，同一权限不因双角色重复出现（含 tenant:manage）
    assert set(perms) >= MEMBER_EXPECTED


async def test_user_permissions_empty_without_roles(session):
    user = await _make_user(session, "roleless")
    assert await get_user_permissions(session, user.id) == []


async def test_user_permissions_revoke_takes_effect(session):
    user = await _make_user(session, "revoked_u")
    member = await get_role_by_name(session, "member")
    await assign_role_to_user(session, user_id=user.id, role_id=member.id)
    assert len(await get_user_permissions(session, user.id)) == 10
    await revoke_role_from_user(session, user_id=user.id, role_id=member.id)
    assert await get_user_permissions(session, user.id) == []


async def test_delete_user_cascades_role_grant(session):
    user = await _make_user(session, "cascade_u")
    member = await get_role_by_name(session, "member")
    await assign_role_to_user(session, user_id=user.id, role_id=member.id)
    await session.delete(user)
    await session.flush()
    # grant 行已被 DB 级联删除 —— flush-only 事务内即可观测
    from sqlalchemy import func as sa_func

    count = await session.scalar(
        select(sa_func.count())
        .select_from(UserRole)
        .where(UserRole.user_id == user.id)
    )
    assert count == 0
