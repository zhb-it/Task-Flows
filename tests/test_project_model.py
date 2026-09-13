"""TASK-029：Project 模型断言（离线 metadata + DB 约束集成）。

离线部分：列集、类型、FK 删除规则、索引、__repr__。
DB 集成部分（真实 PostgreSQL 5433）：
- roundtrip；
- ``team_id`` ON DELETE CASCADE：删团队级联清项目；
- ``owner_id`` ON DELETE RESTRICT：删有项目的用户抛 ForeignKeyViolation；
- 同名项目（同团队/跨团队）允许并存（name 无 UNIQUE）。

零残留：teardown 精确删除本运行前缀的行（先团队后用户）。
"""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.crud.project import create_project, get_project
from app.crud.team import create_team as create_team_crud
from app.crud.user import create_user
from app.models.project import Project
from app.models.team import Team
from app.models.user import User

TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@127.0.0.1:5433/taskflow"

RUN_TOKEN = uuid.uuid4().hex[:10]

engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
SessionFactory = async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest_asyncio.fixture(autouse=True)
async def _cleanup():
    yield
    async with SessionFactory() as session:
        users = (
            await session.execute(
                select(User).where(User.username.like(f"prjmodel_{RUN_TOKEN}%"))
            )
        ).scalars().all()
        for u in users:
            teams = (
                await session.execute(
                    select(Team).where(Team.owner_id == u.id)
                )
            ).scalars().all()
            for t in teams:
                await session.delete(t)  # 级联清项目
            await session.flush()
            await session.delete(u)
        await session.commit()


# --- 离线模型断言 ------------------------------------------------------------------


def test_projects_table_registered_in_metadata():
    assert Project.__tablename__ == "projects"


def test_projects_column_set():
    cols = {c.name for c in Project.__table__.columns}
    assert cols == {
        "id",
        "name",
        "description",
        "team_id",
        "owner_id",
        "created_at",
        "updated_at",
    }


def test_projects_fk_rules():
    fks = {fk.parent.name: fk for fk in Project.__table__.foreign_keys}
    assert fks["team_id"].ondelete == "CASCADE"
    assert fks["owner_id"].ondelete == "RESTRICT"


def test_projects_indexes():
    idx_cols = {tuple(i.columns.keys()) for i in Project.__table__.indexes}
    assert ("team_id",) in idx_cols
    assert ("owner_id",) in idx_cols


def test_projects_no_unique_on_name():
    name_col = Project.__table__.columns["name"]
    assert not name_col.unique
    assert not name_col.nullable


def test_projects_description_nullable():
    assert Project.__table__.columns["description"].nullable


def test_projects_repr():
    p = Project(id=1, name="demo", team_id=2, owner_id=3)
    assert "Project" in repr(p) and "demo" in repr(p)


# --- DB 约束集成 -------------------------------------------------------------------


async def _mk_user(tag: str) -> User:
    async with SessionFactory() as session:
        user = await create_user(
            session,
            username=f"prjmodel_{RUN_TOKEN}_{tag}",
            email=f"prjmodel_{RUN_TOKEN}_{tag}@example.com",
            password_hash="h",
        )
        await session.commit()
        await session.refresh(user)
        return user


async def _mk_team(owner: User, name: str) -> Team:
    async with SessionFactory() as session:
        owner_in_session = await session.merge(owner)
        team = await create_team_crud(
            session, name=name, description=None, owner_id=owner_in_session.id
        )
        await session.commit()
        await session.refresh(team)
        return team


async def test_project_roundtrip(anyio_backend):
    owner = await _mk_user("rt")
    team = await _mk_team(owner, f"prjmodel rt {RUN_TOKEN}")

    async with SessionFactory() as session:
        team_ref = await session.get(Team, team.id)
        user_ref = await session.get(User, owner.id)
        project = await create_project(
            session,
            name=f"rt project {RUN_TOKEN}",
            description="d",
            team_id=team_ref.id,
            owner_id=user_ref.id,
        )
        await session.commit()
        pid = project.id

    async with SessionFactory() as session:
        loaded = await get_project(session, pid)
        assert loaded is not None
        assert loaded.team_id == team.id
        assert loaded.owner_id == owner.id


async def test_delete_team_cascades_projects(anyio_backend):
    owner = await _mk_user("cas")
    team = await _mk_team(owner, f"prjmodel cas {RUN_TOKEN}")

    async with SessionFactory() as session:
        await create_project(
            session,
            name=f"cas project {RUN_TOKEN}",
            description=None,
            team_id=team.id,
            owner_id=owner.id,
        )
        await session.commit()

    async with SessionFactory() as session:
        team_ref = await session.get(Team, team.id)
        await session.delete(team_ref)
        await session.commit()

    async with SessionFactory() as session:
        remaining = (
            await session.execute(
                select(Project).where(Project.name == f"cas project {RUN_TOKEN}")
            )
        ).scalar_one_or_none()
    assert remaining is None


async def test_delete_user_with_project_restricted(anyio_backend):
    from sqlalchemy.exc import IntegrityError

    owner = await _mk_user("res")
    team = await _mk_team(owner, f"prjmodel res {RUN_TOKEN}")

    async with SessionFactory() as session:
        await create_project(
            session,
            name=f"res project {RUN_TOKEN}",
            description=None,
            team_id=team.id,
            owner_id=owner.id,
        )
        await session.commit()

    # owner_id RESTRICT：先删团队（清项目）才能删用户；直接删会违反 FK。
    async with SessionFactory() as session:
        user_ref = await session.get(User, owner.id)
        with pytest.raises(IntegrityError):
            await session.delete(user_ref)
            await session.commit()
            await session.rollback()


async def test_same_name_projects_coexist(anyio_backend):
    owner = await _mk_user("dup")
    team_a = await _mk_team(owner, f"prjmodel dupa {RUN_TOKEN}")
    team_b = await _mk_team(owner, f"prjmodel dupb {RUN_TOKEN}")

    async with SessionFactory() as session:
        p1 = await create_project(
            session,
            name=f"dup project {RUN_TOKEN}",
            description=None,
            team_id=team_a.id,
            owner_id=owner.id,
        )
        p2 = await create_project(
            session,
            name=f"dup project {RUN_TOKEN}",
            description=None,
            team_id=team_b.id,
            owner_id=owner.id,
        )
        await session.commit()
        assert p1.id != p2.id
