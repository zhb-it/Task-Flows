"""TASK-026：Team / TeamMember 模型与表结构测试。

两组：
1. 离线模型测试——只检查映射的列与约束，不需要 PostgreSQL（沿用
   TASK-021 模式）。列集依据开发文档 §7，决策已登记 docs/DB_SCHEMA.md：
   teams.owner_id FK RESTRICT、name 不加 UNIQUE；team_members.role_id
   SmallInt + CHECK 枚举（OWNER/ADMIN/MEMBER）、双 FK CASCADE、
   复合 UNIQUE (team_id, user_id)。
2. 数据库约束集成测试——真实 PostgreSQL 上验证 DB 级兜底行为：
   复合 UNIQUE 拒绝重复加入、CHECK 拒绝非法团队角色、RESTRICT 拒绝
   删除拥有团队的用户、CASCADE 清理成员行。写入采用「本次运行唯一
   前缀 + teardown 精确删除」，删除顺序必须先团队后用户（RESTRICT）。
"""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, SmallInteger, String, UniqueConstraint, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.db.base import Base
from app.models import Team, TeamMember, User
from app.models.team_member import TeamRole

TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@127.0.0.1:5433/taskflow"

RUN_TOKEN = uuid.uuid4().hex[:10]

engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
SessionFactory = async_sessionmaker(engine, expire_on_commit=False)


# --- 1. 离线模型测试 -----------------------------------------------------------


def test_team_tables_registered_on_metadata():
    for table in ("teams", "team_members"):
        assert table in Base.metadata.tables, table


def test_team_tablename():
    assert Team.__tablename__ == "teams"


def test_team_columns():
    assert set(Team.__table__.columns.keys()) == {
        "id",
        "name",
        "description",
        "owner_id",
        "created_at",
        "updated_at",
    }


def test_team_id_is_bigint_primary_key():
    col = Team.__table__.columns["id"]
    assert col.primary_key is True
    assert isinstance(col.type, BigInteger)


def test_team_name_not_nullable_and_not_unique():
    """§7 未定义 name 唯一（TASK-026 决策：不加 UNIQUE，同名团队靠 id 区分）。"""
    col = Team.__table__.columns["name"]
    assert col.nullable is False
    assert col.unique is not True
    assert isinstance(col.type, String)


def test_team_description_nullable():
    assert Team.__table__.columns["description"].nullable is True


def test_team_owner_id_fk_restrict_with_index():
    col = Team.__table__.columns["owner_id"]
    assert col.nullable is False
    fk = next(f for f in Team.__table__.foreign_keys if f.parent is col)
    assert fk.column.table.name == "users"
    assert fk.ondelete == "RESTRICT"
    assert any(ix.columns[0].name == "owner_id" for ix in Team.__table__.indexes)


def test_team_timestamps_timezone_aware():
    for name in ("created_at", "updated_at"):
        col = Team.__table__.columns[name]
        assert isinstance(col.type, DateTime)
        assert col.type.timezone is True
        assert col.nullable is False
        assert col.server_default is not None


def test_team_member_tablename_and_columns():
    assert TeamMember.__tablename__ == "team_members"
    assert set(TeamMember.__table__.columns.keys()) == {
        "id",
        "team_id",
        "user_id",
        "role_id",
        "joined_at",
    }


def test_team_member_role_id_smallint_with_check():
    col = TeamMember.__table__.columns["role_id"]
    assert isinstance(col.type, SmallInteger)
    assert col.nullable is False
    checks = [c for c in TeamMember.__table__.constraints if isinstance(c, CheckConstraint)]
    assert any("ck_team_members_role_id" == c.name for c in checks)
    assert any("role_id IN (1, 2, 3)" in str(c.sqltext) for c in checks)


def test_team_member_role_enum_values():
    assert TeamRole.OWNER == 1
    assert TeamRole.ADMIN == 2
    assert TeamRole.MEMBER == 3
    assert TeamRole(2) is TeamRole.ADMIN


def test_team_member_fk_cascade_with_indexes():
    fks = {fk.parent.name: fk for fk in TeamMember.__table__.foreign_keys}
    assert fks["team_id"].column.table.name == "teams"
    assert fks["team_id"].ondelete == "CASCADE"
    assert fks["user_id"].column.table.name == "users"
    assert fks["user_id"].ondelete == "CASCADE"
    indexed = {ix.columns[0].name for ix in TeamMember.__table__.indexes}
    assert {"team_id", "user_id"} <= indexed


def test_team_member_composite_unique():
    uqs = [
        c for c in TeamMember.__table__.constraints if isinstance(c, UniqueConstraint)
    ]
    assert any(
        c.name == "uq_team_members_team_user"
        and [col.name for col in c.columns] == ["team_id", "user_id"]
        for c in uqs
    )


def test_team_member_joined_at_timezone_aware_default():
    col = TeamMember.__table__.columns["joined_at"]
    assert isinstance(col.type, DateTime)
    assert col.type.timezone is True
    assert col.nullable is False
    assert col.server_default is not None


def test_repr_contains_identity():
    assert "Team" in repr(Team(id=1, name="t", owner_id=2))
    assert "TeamMember" in repr(TeamMember(id=1, team_id=2, user_id=3, role_id=1))


# --- 2. 数据库约束集成测试 -------------------------------------------------------


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest_asyncio.fixture(autouse=True)
async def _cleanup():
    yield
    # RESTRICT：必须先删团队（成员行随团队级联），再删用户
    async with SessionFactory() as session:
        teams = await session.scalars(
            select(Team).where(Team.name.like(f"teamflow_{RUN_TOKEN}%"))
        )
        for team in teams:
            await session.delete(team)
        await session.execute(
            User.__table__.delete().where(
                User.username.like(f"teamflow_{RUN_TOKEN}%")
            )
        )
        await session.commit()


async def _make_user(tag: str) -> User:
    async with SessionFactory() as session:
        user = User(
            username=f"teamflow_{RUN_TOKEN}_{tag}",
            email=f"teamflow_{RUN_TOKEN}_{tag}@example.com",
            password_hash="h",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


async def _make_team(tag: str, owner: User) -> Team:
    async with SessionFactory() as session:
        team = Team(name=f"teamflow_{RUN_TOKEN}_{tag}", owner_id=owner.id)
        session.add(team)
        await session.commit()
        await session.refresh(team)
        return team


async def _make_member(team: Team, user: User, role: TeamRole) -> TeamMember:
    async with SessionFactory() as session:
        member = TeamMember(
            team_id=team.id, user_id=user.id, role_id=int(role)
        )
        session.add(member)
        await session.commit()
        await session.refresh(member)
        return member


async def test_insert_team_and_member_roundtrip():
    owner = await _make_user("owner")
    member_user = await _make_user("member")
    team = await _make_team("t1", owner)
    member = await _make_member(team, member_user, TeamRole.MEMBER)

    async with SessionFactory() as session:
        loaded = await session.get(TeamMember, member.id)
        assert loaded.role_id == TeamRole.MEMBER
        assert loaded.joined_at is not None
        team_loaded = await session.get(Team, team.id)
        assert team_loaded.name.endswith("t1")
        assert team_loaded.owner_id == owner.id


async def test_duplicate_membership_rejected_by_composite_unique():
    owner = await _make_user("dup_owner")
    user = await _make_user("dup_user")
    team = await _make_team("dup", owner)
    await _make_member(team, user, TeamRole.MEMBER)

    async with SessionFactory() as session:
        session.add(TeamMember(team_id=team.id, user_id=user.id, role_id=TeamRole.ADMIN))
        with pytest.raises(IntegrityError):
            await session.flush()


async def test_invalid_team_role_rejected_by_check():
    owner = await _make_user("ck_owner")
    user = await _make_user("ck_user")
    team = await _make_team("ck", owner)

    async with SessionFactory() as session:
        session.add(TeamMember(team_id=team.id, user_id=user.id, role_id=9))
        with pytest.raises(IntegrityError):
            await session.flush()


async def test_deleting_owner_with_team_is_restricted():
    """RESTRICT：还有团队的用户不能删（ForeignKeyViolationError）。"""
    owner = await _make_user("restrict_owner")
    team = await _make_team("restrict", owner)

    async with SessionFactory() as session:
        user = await session.get(User, owner.id)
        await session.delete(user)
        with pytest.raises(IntegrityError):
            await session.flush()

    # 团队还在，RESTRICT 生效
    async with SessionFactory() as session:
        assert await session.get(Team, team.id) is not None


async def test_deleting_team_cascades_members():
    owner = await _make_user("cas_owner")
    user = await _make_user("cas_user")
    team = await _make_team("cas", owner)
    await _make_member(team, user, TeamRole.OWNER)

    async with SessionFactory() as session:
        team_row = await session.get(Team, team.id)
        await session.delete(team_row)
        await session.commit()

    async with SessionFactory() as session:
        remaining = await session.scalars(
            select(TeamMember).where(TeamMember.team_id == team.id)
        )
        assert list(remaining) == []
        # 用户不受影响（CASCADE 方向是 team -> members）
        assert await session.get(User, user.id) is not None


async def test_teams_name_allows_duplicates():
    """name 不加 UNIQUE（TASK-026 决策）：同名团队可并存。"""
    owner = await _make_user("dupname_owner")
    team_a = await _make_team("dupname", owner)
    team_b = await _make_team("dupname", owner)
    assert team_a.id != team_b.id
    assert team_a.name == team_b.name
