"""TASK-025：RBAC 端到端验收链路测试（Phase 3 收尾）。

§35「RBAC 重点测试」三项要求（有权限访问 / 无权限访问 / 不同角色权限差异）
已由 TASK-022/023/024 的专项模块覆盖；本文件补上此前缺失的验收链路：

1. §56 Phase 4 验收——ADMIN 与 MEMBER 在同一端点集合上「权限表现不同」。
2. 角色生命周期——无角色 403 → 授予角色立即生效 → 撤销立即失效
   （授权判定每次请求实时解析，无缓存）。
3. 多角色并集聚合——多个角色的权限取并集（去重），撤销其一保留其余。
4. 权限绑定即时生效——给角色绑定/解绑权限，其既有持有者立刻获得/失去。
5. 依赖 ⇄ 守卫两层判定一致性——同一用户同一权限，HTTP 依赖链与 Service
   守卫结论必须相同（§49「认证 ≠ 授权」的两层执行不得有分叉）。
6. 种子健全性——admin 权限集 ⊇ member 权限集（只读）。

验证方式（沿用 TASK-023 决策）：不向产品 API 添加任何端点；测试内探针
应用走完整 HTTP 链路。自定义角色/权限使用「本次运行唯一前缀」，teardown
精确删除，种子角色与种子权限只读不写，保证开发库零残留。
"""

import uuid

import pytest
import pytest_asyncio
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.core.deps import require_permission
from app.core.exceptions import AppError, ForbiddenError, app_error_handler
from app.core.security import create_access_token
from app.crud.permission import (
    bind_permission_to_role,
    create_permission,
    get_user_permissions,
    unbind_permission_from_role,
)
from app.crud.role import (
    assign_role_to_user,
    create_role,
    get_role_by_name,
    revoke_role_from_user,
)
from app.crud.user import create_user
from app.db.session import get_db
from app.models.permission import Permission
from app.models.role import Role
from app.models.user import User
from app.services.authorization import ensure_permission
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
    return f"rbacflow_{RUN_TOKEN}_{tag}"


def _role_name(tag: str) -> str:
    return f"rbacflow_{RUN_TOKEN}_{tag}"


def _perm_name(tag: str) -> str:
    return f"rbacflow_{RUN_TOKEN}:{tag}"


# --- 测试专用探针应用（与 TASK-023/024 同模式） --------------------------------

probe_app = FastAPI()
probe_app.add_exception_handler(AppError, app_error_handler)


@probe_app.get("/probe/read")
async def probe_read(user: User = Depends(require_permission("task:read"))):
    return {"user_id": user.id}


@probe_app.get("/probe/delete")
async def probe_delete(user: User = Depends(require_permission("task:delete"))):
    return {"user_id": user.id}


@probe_app.get("/probe/invite")
async def probe_invite(user: User = Depends(require_permission("team:invite"))):
    return {"user_id": user.id}


@probe_app.get("/probe/guard-delete")
async def probe_guard_delete(
    user: User = Depends(require_permission("task:read")),
    db=Depends(get_db),
):
    """依赖放行后由 Service 守卫二次判定的标准组合。"""
    await ensure_permission(db, user, "task:delete")
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
        # 自定义角色/权限按唯一前缀删除（级联清理关联表）；种子数据只读未动
        await session.execute(
            delete(User).where(User.username.like(f"rbacflow_{RUN_TOKEN}%"))
        )
        await session.execute(
            delete(Role).where(Role.name.like(f"rbacflow_{RUN_TOKEN}%"))
        )
        await session.execute(
            delete(Permission).where(Permission.name.like(f"rbacflow_{RUN_TOKEN}%"))
        )
        await session.commit()


async def _make_user(tag: str, role_names: list[str] | None = None) -> User:
    """创建用户并授予若干角色（种子角色按 name 查找，自定义角色现场创建）。"""
    async with SessionFactory() as session:
        user = await create_user(
            session,
            username=_username(tag),
            email=f"{_username(tag)}@example.com",
            password_hash=PASSWORD_HASH,
        )
        for role_name in role_names or []:
            if role_name in ("admin", "member"):
                role = await get_role_by_name(session, role_name)
                assert role is not None, f"seed role {role_name!r} missing"
            else:
                role = await create_role(session, name=role_name)
            await assign_role_to_user(session, user_id=user.id, role_id=role.id)
        await session.commit()
        await session.refresh(user)
        return user


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# --- 1. §56 Phase 4 验收：ADMIN / MEMBER 权限表现不同 --------------------------


async def test_phase4_admin_and_member_behave_differently(client):
    """同一端点集合：admin 全部通过；member 只过读路径、写路径 403。"""
    admin = await _make_user("admin", ["admin"])
    member = await _make_user("member", ["member"])
    token_a = _bearer(create_access_token(admin.id))
    token_m = _bearer(create_access_token(member.id))

    # member：读路径通过
    resp = await client.get("/probe/read", headers=token_m)
    assert resp.status_code == 200, resp.text
    # member：删除路径 403 且点名缺失权限
    resp = await client.get("/probe/delete", headers=token_m)
    assert resp.status_code == 403, resp.text
    assert "task:delete" in resp.json()["detail"]
    # admin：两条路径都通过
    assert (await client.get("/probe/read", headers=token_a)).status_code == 200
    assert (await client.get("/probe/delete", headers=token_a)).status_code == 200


async def test_phase4_member_with_guard_second_layer(client):
    """member 过了依赖层（task:read）仍会被守卫层（task:delete）拦下：
    两层授权各自独立判定。"""
    member = await _make_user("member2", ["member"])
    resp = await client.get(
        "/probe/guard-delete", headers=_bearer(create_access_token(member.id))
    )
    assert resp.status_code == 403, resp.text
    assert resp.json()["detail"] == "Permission denied: task:delete"


# --- 2. 角色生命周期：授予生效 / 撤销失效 ----------------------------------------


async def test_grant_and_revoke_role_flips_verdict_immediately():
    user = await _make_user("lifecycle")  # 无角色
    async with SessionFactory() as session:
        with pytest.raises(ForbiddenError, match="task:read"):
            await ensure_permission(session, user, "task:read")

        role = await get_role_by_name(session, "member")
        await assign_role_to_user(session, user_id=user.id, role_id=role.id)
        await session.commit()

    # 新会话（模拟下一次请求）立即生效——权限解析每次实时查库，无缓存
    async with SessionFactory() as session:
        await ensure_permission(session, user, "task:read")
        await revoke_role_from_user(session, user_id=user.id, role_id=role.id)
        await session.commit()

    async with SessionFactory() as session:
        with pytest.raises(ForbiddenError, match="task:read"):
            await ensure_permission(session, user, "task:read")


# --- 3. 多角色并集聚合 -----------------------------------------------------------


async def test_multi_role_union_is_deduplicated():
    user = await _make_user(
        "union",
        ["member", _role_name("extra_a"), _role_name("extra_b")],
    )
    # 给两个自定义角色分别绑定一个种子权限，与 member 已有权限部分重叠
    async with SessionFactory() as session:
        role_a = await get_role_by_name(session, _role_name("extra_a"))
        role_b = await get_role_by_name(session, _role_name("extra_b"))
        perm_task_read = await create_permission(session, name=_perm_name("dup_read"))
        perm_team_invite = await create_permission(
            session, name=_perm_name("invite")
        )
        await bind_permission_to_role(
            session, role_id=role_a.id, permission_id=perm_task_read.id
        )
        await bind_permission_to_role(
            session, role_id=role_a.id, permission_id=perm_team_invite.id
        )
        await bind_permission_to_role(
            session, role_id=role_b.id, permission_id=perm_task_read.id
        )
        await session.commit()

        perms = await get_user_permissions(session, user.id)

    assert perms.count(_perm_name("dup_read")) == 1  # 两角色持有同一权限只出现一次
    assert _perm_name("invite") in perms
    assert "task:read" in perms  # member 的种子权限仍在并集中


async def test_revoking_one_role_keeps_the_others():
    role_a_name, role_b_name = _role_name("keep_a"), _role_name("keep_b")
    user = await _make_user("multi", [role_a_name, role_b_name])
    async with SessionFactory() as session:
        role_a = await get_role_by_name(session, role_a_name)
        perm_a = await create_permission(session, name=_perm_name("perm_a"))
        perm_b = await create_permission(session, name=_perm_name("perm_b"))
        role_b = await get_role_by_name(session, role_b_name)
        await bind_permission_to_role(
            session, role_id=role_a.id, permission_id=perm_a.id
        )
        await bind_permission_to_role(
            session, role_id=role_b.id, permission_id=perm_b.id
        )
        await session.commit()

        await revoke_role_from_user(session, user_id=user.id, role_id=role_a.id)
        await session.commit()

        perms = await get_user_permissions(session, user.id)
    assert _perm_name("perm_a") not in perms  # 撤销的角色权限消失
    assert _perm_name("perm_b") in perms  # 保留角色的权限仍在


# --- 4. 权限绑定对既有持有者即时生效 ----------------------------------------------


async def test_binding_permission_takes_effect_for_existing_holder():
    role_name = _role_name("holder")
    user = await _make_user("holder_u", [role_name])
    async with SessionFactory() as session:
        role = await get_role_by_name(session, role_name)
        perm = await create_permission(session, name=_perm_name("late_perm"))
        await session.commit()

        # 绑定前：不持有
        assert _perm_name("late_perm") not in await get_user_permissions(
            session, user.id
        )
        # 绑定后：既有持有者立即获得
        await bind_permission_to_role(session, role_id=role.id, permission_id=perm.id)
        await session.commit()
        assert _perm_name("late_perm") in await get_user_permissions(session, user.id)

        # 解绑后：立即失去
        await unbind_permission_from_role(
            session, role_id=role.id, permission_id=perm.id
        )
        await session.commit()
        assert _perm_name("late_perm") not in await get_user_permissions(
            session, user.id
        )


# --- 5. 依赖 ⇄ 守卫两层判定一致性 -------------------------------------------------


async def test_dependency_and_guard_agree_on_same_user(client):
    """同一用户同一权限，HTTP 依赖链与 Service 守卫结论一致：允许与拒绝两侧
    都一致（§49 两层执行不分叉）。"""
    member = await _make_user("parity", ["member"])

    # 依赖侧（HTTP）
    resp = await client.get(
        "/probe/read", headers=_bearer(create_access_token(member.id))
    )
    assert resp.status_code == 200, resp.text
    resp = await client.get(
        "/probe/delete", headers=_bearer(create_access_token(member.id))
    )
    assert resp.status_code == 403, resp.text

    # 守卫侧（直接调用）
    async with SessionFactory() as session:
        await ensure_permission(session, member, "task:read")  # 与依赖同样放行
        with pytest.raises(ForbiddenError, match="task:delete"):  # 与依赖同样拒绝
            await ensure_permission(session, member, "task:delete")


async def test_custom_role_permission_visible_at_dependency_layer(client):
    """自定义角色 + 种子权限同样走通依赖层——权限判定只认 resource:action
    字符串，与角色来源无关（种子 team:invite 默认仅 admin 持有）。"""
    extra_role = _role_name("inviter")
    user = await _make_user("inviter_u", [extra_role])
    async with SessionFactory() as session:
        role = await get_role_by_name(session, extra_role)
        from app.crud.permission import get_permission_by_name

        perm = await get_permission_by_name(session, "team:invite")
        assert perm is not None, "seed permission team:invite missing"
        await bind_permission_to_role(
            session, role_id=role.id, permission_id=perm.id
        )
        await session.commit()

    # team:invite 只有 admin 持有（种子），该用户仅凭自定义角色即可通过
    resp = await client.get(
        "/probe/invite", headers=_bearer(create_access_token(user.id))
    )
    assert resp.status_code == 200, resp.text


# --- 6. 种子健全性（只读） --------------------------------------------------------


async def test_admin_permission_set_superset_of_member():
    """Phase 4 验收的数据前提：admin 权限集 ⊇ member 权限集。"""
    async with SessionFactory() as session:
        admin = await get_role_by_name(session, "admin")
        member = await get_role_by_name(session, "member")
        from app.crud.permission import get_role_permissions

        admin_perms = {p.name for p in await get_role_permissions(session, admin.id)}
        member_perms = {
            p.name for p in await get_role_permissions(session, member.id)
        }
    assert member_perms <= admin_perms
    assert member_perms  # member 非空（「读 + 基础写」10 项）


async def test_seed_roles_unaffected_by_test_data():
    """测试自建的角色/权限不污染种子：admin/member 与 22 项种子权限原样。"""
    from sqlalchemy import func as sa_func, select

    async with SessionFactory() as session:
        assert await get_role_by_name(session, "admin") is not None
        assert await get_role_by_name(session, "member") is not None
        seed_count = await session.scalar(
            select(sa_func.count())
            .select_from(Permission)
            .where(Permission.name.notlike(f"rbacflow_{RUN_TOKEN}:%"))
        )
        role_count = await session.scalar(
            select(sa_func.count())
            .select_from(Role)
            .where(Role.name.notlike(f"rbacflow_{RUN_TOKEN}%"))
        )
    assert seed_count == 22
    assert role_count == 2
