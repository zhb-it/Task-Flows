"""TASK-027：团队 CRUD 的 Service / CRUD 层测试。

覆盖三个已确认决策与 CRUD 行为（数据库集成，开发库零残留）：

1. 创建团队自动写 `team_members` OWNER 行（同事务）。
2. PATCH / DELETE 资源级仅 owner——非 owner 一律 404（与不存在不可区分）。
3. 可见范围 = 我参与的团队（owner 或成员）。

验证方式：用户/团队按「本次运行唯一前缀」创建，teardown 精确删除（先团队
后用户——teams.owner_id RESTRICT 要求先删团队再删用户），种子数据只读。
"""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.exceptions import ResourceNotFoundError
from app.crud.team import add_team_member, get_team, get_team_member
from app.crud.user import create_user
from app.models.team import Team
from app.models.team_member import TeamRole
from app.models.user import User
from app.schemas.team import TeamCreate, TeamUpdate
from app.services.team import (
    create_team,
    delete_team,
    get_team_for_user,
    list_teams,
    team_membership,
    update_team,
)

TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@127.0.0.1:5433/taskflow"

RUN_TOKEN = uuid.uuid4().hex[:10]
PASSWORD_HASH = "h"

engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
SessionFactory = async_sessionmaker(engine, expire_on_commit=False)


def _username(tag: str) -> str:
    return f"teamsvc_{RUN_TOKEN}_{tag}"


def _team_name(tag: str) -> str:
    return f"teamsvc {RUN_TOKEN} {tag}"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest_asyncio.fixture(autouse=True)
async def _cleanup():
    yield
    async with SessionFactory() as session:
        await session.execute(
            delete(Team).where(Team.name.like(f"teamsvc {RUN_TOKEN}%"))
        )
        await session.execute(
            delete(User).where(User.username.like(f"teamsvc_{RUN_TOKEN}%"))
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


# --- 决策 1：创建团队自动写 OWNER 成员行 ----------------------------------------


async def test_create_team_writes_owner_member_row():
    owner = await _make_user("owner")
    async with SessionFactory() as session:
        team = await create_team(
            session,
            owner,
            TeamCreate(name=_team_name("alpha"), description="d1"),
        )
        await session.commit()

        member = await get_team_member(
            session, team_id=team.id, user_id=owner.id
        )
        assert member is not None
        assert member.role_id == TeamRole.OWNER.value
        # 归属链统一以 team_members 为准
        assert (await team_membership(session, team.id, owner.id)) is TeamRole.OWNER


async def test_create_team_description_optional():
    owner = await _make_user("nodeesc")
    async with SessionFactory() as session:
        team = await create_team(
            session, owner, TeamCreate(name=_team_name("nodesc"))
        )
        await session.commit()
        assert team.description is None


# --- 决策 3：可见范围 = 我参与的团队 ----------------------------------------------


async def test_get_team_for_user_owner_member_outsider():
    owner = await _make_user("o2")
    member = await _make_user("m2")
    outsider = await _make_user("x2")
    async with SessionFactory() as session:
        team = await create_team(
            session, owner, TeamCreate(name=_team_name("vis"))
        )
        await add_team_member(
            session,
            team_id=team.id,
            user_id=member.id,
            role_id=TeamRole.MEMBER.value,
        )
        await session.commit()

        await get_team_for_user(session, owner, team.id)
        await get_team_for_user(session, member, team.id)
        with pytest.raises(ResourceNotFoundError, match="Team not found"):
            await get_team_for_user(session, outsider, team.id)


async def test_get_team_for_user_missing_404_same_contract():
    user = await _make_user("miss")
    async with SessionFactory() as session:
        with pytest.raises(ResourceNotFoundError) as exc_info:
            await get_team_for_user(session, user, 999_999_999)
    assert "Team not found" in str(exc_info.value.detail)


async def test_list_teams_union_owned_and_member_of():
    owner = await _make_user("o3")
    member = await _make_user("m3")
    other_owner = await _make_user("o4")
    async with SessionFactory() as session:
        owned = await create_team(
            session, owner, TeamCreate(name=_team_name("owned"))
        )
        joined = await create_team(
            session, other_owner, TeamCreate(name=_team_name("joined"))
        )
        invisible = await create_team(
            session, other_owner, TeamCreate(name=_team_name("invisible"))
        )
        await add_team_member(
            session,
            team_id=joined.id,
            user_id=member.id,
            role_id=TeamRole.MEMBER.value,
        )
        await session.commit()

    async with SessionFactory() as session:
        owner_teams = await list_teams(session, owner)
        member_teams = await list_teams(session, member)
        other_teams = await list_teams(session, other_owner)

    assert [t.id for t in owner_teams] == [owned.id]
    assert [t.id for t in member_teams] == [joined.id]
    assert [t.id for t in other_teams] == [joined.id, invisible.id]


async def test_list_teams_pagination():
    owner = await _make_user("page")
    async with SessionFactory() as session:
        for i in range(3):
            await create_team(
                session, owner, TeamCreate(name=_team_name(f"pg{i}"))
            )
        await session.commit()

        page1 = await list_teams(session, owner, skip=0, limit=2)
        page2 = await list_teams(session, owner, skip=2, limit=2)

    assert len(page1) == 2
    assert len(page2) == 1
    assert page1[0].id < page1[1].id < page2[0].id


# --- 决策 2：PATCH / DELETE 仅 owner，否则 404 ------------------------------------


async def test_update_team_owner_partial_semantics():
    owner = await _make_user("o5")
    async with SessionFactory() as session:
        team = await create_team(
            session, owner, TeamCreate(name=_team_name("upd"), description="old")
        )
        await session.commit()

        # 只改 name：description 不变（exclude_unset）
        updated = await update_team(
            session, owner, team.id, TeamUpdate(name=_team_name("upd2"))
        )
        assert updated.name == _team_name("upd2")
        assert updated.description == "old"

        # 显式传 null：清空 description
        cleared = await update_team(
            session, owner, team.id, TeamUpdate(description=None)
        )
        assert cleared.description is None
        assert cleared.name == _team_name("upd2")

        # 空请求体：什么都不变
        untouched = await update_team(
            session, owner, team.id, TeamUpdate()
        )
        assert untouched.name == _team_name("upd2")
        assert untouched.description is None


async def test_update_team_non_owner_404():
    owner = await _make_user("o6")
    member = await _make_user("m6")
    async with SessionFactory() as session:
        team = await create_team(
            session, owner, TeamCreate(name=_team_name("deny"))
        )
        await add_team_member(
            session,
            team_id=team.id,
            user_id=member.id,
            role_id=TeamRole.MEMBER.value,
        )
        await session.commit()

    async with SessionFactory() as session:
        with pytest.raises(ResourceNotFoundError, match="Team not found"):
            await update_team(
                session, member, team.id, TeamUpdate(name=_team_name("hacked"))
            )
        assert (await get_team(session, team.id)).name == _team_name("deny")


async def test_delete_team_cascades_member_rows():
    owner = await _make_user("o7")
    member = await _make_user("m7")
    async with SessionFactory() as session:
        team = await create_team(
            session, owner, TeamCreate(name=_team_name("del"))
        )
        await add_team_member(
            session,
            team_id=team.id,
            user_id=member.id,
            role_id=TeamRole.ADMIN.value,
        )
        await session.commit()
        team_id = team.id

    async with SessionFactory() as session:
        await delete_team(session, owner, team_id)
        await session.commit()

    async with SessionFactory() as session:
        assert await get_team(session, team_id) is None
        assert await get_team_member(session, team_id=team_id, user_id=owner.id) is None
        assert await get_team_member(session, team_id=team_id, user_id=member.id) is None


async def test_delete_team_non_owner_404():
    owner = await _make_user("o8")
    outsider = await _make_user("x8")
    async with SessionFactory() as session:
        team = await create_team(
            session, owner, TeamCreate(name=_team_name("keep"))
        )
        await session.commit()

    async with SessionFactory() as session:
        with pytest.raises(ResourceNotFoundError, match="Team not found"):
            await delete_team(session, outsider, team.id)
        assert await get_team(session, team.id) is not None
