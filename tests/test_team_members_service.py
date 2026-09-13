"""TASK-028：成员管理 Service 层测试（数据库集成，零残留）。

覆盖 TASK-028 四项决策：

1. 双层判定——本文件直接调 Service（功能级 403 在 Router 依赖层，此处只验
   资源级）：团队角色不足（plain MEMBER 调用者）→ 403。
2. 邀请 user_id + role（admin/member），owner 不可邀请；重复邀请 409；
   目标用户不存在 404。
3. 移除层级 OWNER > ADMIN > MEMBER；owner 不可被移除。
4. 成员列表团队成员可见。

零残留：用户/团队按「本次运行唯一前缀」创建，teardown 先删团队再删用户。
"""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.exceptions import ConflictError, ForbiddenError, ResourceNotFoundError
from app.crud.team import (
    add_team_member,
    get_team_member,
    list_team_members,
)
from app.crud.user import create_user
from app.models.team import Team
from app.models.team_member import TeamRole
from app.models.user import User
from app.schemas.team import TeamCreate, TeamMemberInvite
from app.services.team import (
    create_team,
    invite_member,
    list_members,
    remove_member,
    team_membership,
)

TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@127.0.0.1:5433/taskflow"

RUN_TOKEN = uuid.uuid4().hex[:10]
PASSWORD_HASH = "h"

engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
SessionFactory = async_sessionmaker(engine, expire_on_commit=False)


def _username(tag: str) -> str:
    return f"tmemsvc_{RUN_TOKEN}_{tag}"


def _team_name(tag: str) -> str:
    return f"tmemsvc {RUN_TOKEN} {tag}"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest_asyncio.fixture(autouse=True)
async def _cleanup():
    yield
    async with SessionFactory() as session:
        await session.execute(
            delete(Team).where(Team.name.like(f"tmemsvc {RUN_TOKEN}%"))
        )
        await session.execute(
            delete(User).where(User.username.like(f"tmemsvc_{RUN_TOKEN}%"))
        )
        await session.commit()


async def _make_user(tag: str) -> User:
    async with SessionFactory() as session:
        user = await create_user(
            session,
            username=_username(tag),
            email=f"{_username(tag)}@example.com",
            password_hash=PASSWORD_HASH,
        )
        await session.commit()
        await session.refresh(user)
        return user


async def _make_team(owner: User, tag: str) -> int:
    async with SessionFactory() as session:
        team = await create_team(session, owner, TeamCreate(name=_team_name(tag)))
        await session.commit()
        return team.id


# --- 决策 1/2：邀请 ---------------------------------------------------------------


async def test_invite_member_by_owner_default_role():
    owner = await _make_user("owner")
    target = await _make_user("target")
    team_id = await _make_team(owner, "invite")

    async with SessionFactory() as session:
        member = await invite_member(
            session, owner, team_id, TeamMemberInvite(user_id=target.id)
        )
        await session.commit()
        assert member.role == "member"
        assert member.username == target.username
        assert (await team_membership(session, team_id, target.id)) is TeamRole.MEMBER


async def test_invite_member_with_admin_role():
    owner = await _make_user("owner2")
    target = await _make_user("target2")
    team_id = await _make_team(owner, "invite2")

    async with SessionFactory() as session:
        member = await invite_member(
            session,
            owner,
            team_id,
            TeamMemberInvite(user_id=target.id, role="admin"),
        )
        await session.commit()
        assert member.role == "admin"


async def test_invite_duplicate_409():
    owner = await _make_user("owner3")
    target = await _make_user("target3")
    team_id = await _make_team(owner, "invite3")

    async with SessionFactory() as session:
        await invite_member(
            session, owner, team_id, TeamMemberInvite(user_id=target.id)
        )
        await session.commit()
        with pytest.raises(ConflictError, match="already a team member"):
            await invite_member(
                session, owner, team_id, TeamMemberInvite(user_id=target.id)
            )


async def test_invite_missing_user_404():
    owner = await _make_user("owner4")
    team_id = await _make_team(owner, "invite4")

    async with SessionFactory() as session:
        with pytest.raises(ResourceNotFoundError, match="User not found"):
            await invite_member(
                session, owner, team_id, TeamMemberInvite(user_id=999_999_999)
            )


async def test_invite_by_plain_member_403():
    owner = await _make_user("owner5")
    plain = await _make_user("plain5")
    target = await _make_user("target5")
    team_id = await _make_team(owner, "invite5")

    async with SessionFactory() as session:
        await add_team_member(
            session,
            team_id=team_id,
            user_id=plain.id,
            role_id=TeamRole.MEMBER.value,
        )
        await session.commit()

    async with SessionFactory() as session:
        with pytest.raises(ForbiddenError, match="owner or admin"):
            await invite_member(
                session, plain, team_id, TeamMemberInvite(user_id=target.id)
            )


async def test_invite_by_team_admin_allowed():
    """团队 ADMIN（无全局角色）在 Service 层可邀请（功能级 403 归 Router）。"""
    owner = await _make_user("owner6")
    team_admin = await _make_user("tadmin6")
    target = await _make_user("target6")
    team_id = await _make_team(owner, "invite6")

    async with SessionFactory() as session:
        await add_team_member(
            session,
            team_id=team_id,
            user_id=team_admin.id,
            role_id=TeamRole.ADMIN.value,
        )
        await session.commit()

    async with SessionFactory() as session:
        await invite_member(
            session, team_admin, team_id, TeamMemberInvite(user_id=target.id)
        )
        await session.commit()
        assert (await team_membership(session, team_id, target.id)) is TeamRole.MEMBER


async def test_invite_to_invisible_team_404():
    owner = await _make_user("owner7")
    outsider = await _make_user("out7")
    target = await _make_user("target7")
    team_id = await _make_team(owner, "invite7")

    async with SessionFactory() as session:
        with pytest.raises(ResourceNotFoundError, match="Team not found"):
            await invite_member(
                session, outsider, team_id, TeamMemberInvite(user_id=target.id)
            )


# --- 决策 4：成员列表 --------------------------------------------------------------


async def test_list_members_ordered_with_roles():
    owner = await _make_user("owner8")
    admin = await _make_user("admin8")
    member = await _make_user("member8")
    team_id = await _make_team(owner, "list8")

    async with SessionFactory() as session:
        await add_team_member(
            session, team_id=team_id, user_id=admin.id, role_id=TeamRole.ADMIN.value
        )
        await add_team_member(
            session, team_id=team_id, user_id=member.id, role_id=TeamRole.MEMBER.value
        )
        await session.commit()

        members = await list_members(session, owner, team_id)

    assert [m.username for m in members] == [
        owner.username, admin.username, member.username
    ]
    assert [m.role for m in members] == ["owner", "admin", "member"]


async def test_list_members_outsider_404():
    owner = await _make_user("owner9")
    outsider = await _make_user("out9")
    team_id = await _make_team(owner, "list9")

    async with SessionFactory() as session:
        with pytest.raises(ResourceNotFoundError, match="Team not found"):
            await list_members(session, outsider, team_id)


# --- 决策 3：移除层级 --------------------------------------------------------------


async def test_owner_removes_admin_and_member():
    owner = await _make_user("owner10")
    admin = await _make_user("admin10")
    member = await _make_user("member10")
    team_id = await _make_team(owner, "rm10")

    async with SessionFactory() as session:
        await add_team_member(
            session, team_id=team_id, user_id=admin.id, role_id=TeamRole.ADMIN.value
        )
        await add_team_member(
            session, team_id=team_id, user_id=member.id, role_id=TeamRole.MEMBER.value
        )
        await session.commit()

        await remove_member(session, owner, team_id, admin.id)
        await remove_member(session, owner, team_id, member.id)
        await session.commit()

        remaining = await list_team_members(session, team_id)
        assert [m.user_id for m in remaining] == [owner.id]


async def test_admin_removes_member_but_not_admin():
    owner = await _make_user("owner11")
    team_admin = await _make_user("tadmin11")
    other_admin = await _make_user("tadmin11b")
    plain = await _make_user("plain11")
    team_id = await _make_team(owner, "rm11")

    async with SessionFactory() as session:
        for uid, role in (
            (team_admin.id, TeamRole.ADMIN),
            (other_admin.id, TeamRole.ADMIN),
            (plain.id, TeamRole.MEMBER),
        ):
            await add_team_member(
                session, team_id=team_id, user_id=uid, role_id=role.value
            )
        await session.commit()

        # ADMIN 可移除 MEMBER
        await remove_member(session, team_admin, team_id, plain.id)
        await session.commit()
        assert await get_team_member(session, team_id=team_id, user_id=plain.id) is None

        # ADMIN 不可移除另一 ADMIN / OWNER
        with pytest.raises(ForbiddenError, match="only remove members"):
            await remove_member(session, team_admin, team_id, other_admin.id)
        with pytest.raises(ForbiddenError, match="cannot be removed"):
            await remove_member(session, team_admin, team_id, owner.id)


async def test_owner_cannot_be_removed_even_by_self():
    owner = await _make_user("owner12")
    team_id = await _make_team(owner, "rm12")

    async with SessionFactory() as session:
        with pytest.raises(ForbiddenError, match="cannot be removed"):
            await remove_member(session, owner, team_id, owner.id)
        assert await get_team_member(session, team_id=team_id, user_id=owner.id)


async def test_remove_missing_member_404():
    owner = await _make_user("owner13")
    team_id = await _make_team(owner, "rm13")

    async with SessionFactory() as session:
        with pytest.raises(ResourceNotFoundError, match="Team member not found"):
            await remove_member(session, owner, team_id, 999_999_999)


async def test_removed_user_can_be_reinvited():
    owner = await _make_user("owner14")
    target = await _make_user("target14")
    team_id = await _make_team(owner, "rm14")

    async with SessionFactory() as session:
        await invite_member(
            session, owner, team_id, TeamMemberInvite(user_id=target.id)
        )
        await session.commit()
        await remove_member(session, owner, team_id, target.id)
        await session.commit()

        again = await invite_member(
            session, owner, team_id, TeamMemberInvite(user_id=target.id)
        )
        await session.commit()
        assert again.user_id == target.id
