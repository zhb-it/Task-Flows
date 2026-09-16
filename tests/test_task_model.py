"""TASK-031：Task 模型断言（离线 metadata + DB 约束集成）.

离线部分：列集、枚举值、FK 删除规则、CHECK、索引（含部分索引谓词）、
server_default、__repr__。

DB 集成部分（真实 PostgreSQL 5433）：
- roundtrip（默认 status=TODO / priority=MEDIUM）；
- CHECK 拒非法 status / priority；
- ``project_id`` ON DELETE CASCADE：删项目级联清任务；
- ``creator_id`` ON DELETE CASCADE：删用户级联清其创建的任务（TASK-031 决策）；
- 同名任务（同项目）允许并存。

零残留：teardown 精确删除本运行前缀的行（先项目后用户，级联清任务）。
"""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.crud.project import create_project
from app.crud.team import create_team as create_team_crud
from app.crud.user import create_user
from app.models.project import Project
from app.models.task import Task, TaskPriority, TaskStatus
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
                select(User).where(User.username.like(f"tskmodel_{RUN_TOKEN}%"))
            )
        ).scalars().all()
        for u in users:
            teams = (
                await session.execute(select(Team).where(Team.owner_id == u.id))
            ).scalars().all()
            for t in teams:
                await session.delete(t)  # 级联清项目 → 级联清任务
            await session.flush()
            await session.delete(u)  # 级联清其创建的任务
        await session.commit()


# --- 离线模型断言 ------------------------------------------------------------------


def test_tasks_table_registered_in_metadata():
    assert Task.__tablename__ == "tasks"


def test_tasks_column_set():
    cols = {c.name for c in Task.__table__.columns}
    assert cols == {
        "id",
        "tenant_id",  # TASK-094
        "project_id",
        "title",
        "description",
        "status",
        "priority",
        "creator_id",
        "due_at",
        "created_at",
        "updated_at",
        # TASK-064 新增：DB 端生成的全文检索列（§14 / DB_SCHEMA「PostgreSQL 能力」）。
        "search_vector",
    }


def test_no_assignee_column():
    """多人分配由 task_assignees（TASK-036）承担，tasks 无 assignee 列。"""
    assert "assignee" not in {c.name for c in Task.__table__.columns}


def test_task_status_enum_values():
    assert {s.value for s in TaskStatus} == {
        "TODO",
        "IN_PROGRESS",
        "REVIEW",
        "DONE",
        "CANCELLED",
    }


def test_task_priority_enum_values():
    assert {p.value for p in TaskPriority} == {"LOW", "MEDIUM", "HIGH", "URGENT"}


def test_tasks_fk_rules():
    fks = {fk.parent.name: fk for fk in Task.__table__.foreign_keys}
    assert fks["project_id"].ondelete == "CASCADE"
    assert fks["creator_id"].ondelete == "CASCADE"


def test_tasks_check_constraints_defined():
    names = {c.name for c in Task.__table__.constraints}
    assert "ck_tasks_status_values" in names
    assert "ck_tasks_priority_values" in names


def test_tasks_indexes_per_db_schema():
    """DB_SCHEMA「Task 索引」：(project_id, status)、(creator_id)、due_at 部分索引。"""
    by_name = {i.name: i for i in Task.__table__.indexes}
    assert {tuple(by_name["ix_tasks_project_id_status"].columns.keys())} == {
        ("project_id", "status")
    }
    assert {tuple(by_name["ix_tasks_creator_id"].columns.keys())} == {("creator_id",)}
    partial = by_name["ix_tasks_due_at_open"]
    assert partial.dialect_options["postgresql"]["where"] is not None


def test_tasks_defaults():
    assert Task.__table__.columns["status"].server_default.arg == "TODO"
    assert Task.__table__.columns["priority"].server_default.arg == "MEDIUM"
    assert Task.__table__.columns["due_at"].nullable


def test_tasks_repr():
    t = Task(id=1, project_id=2, title="demo", status="TODO")
    assert "Task" in repr(t) and "demo" in repr(t) and "TODO" in repr(t)


# --- DB 约束集成 -------------------------------------------------------------------


async def _mk_user(tag: str) -> User:
    async with SessionFactory() as session:
        user = await create_user(
            session,
            username=f"tskmodel_{RUN_TOKEN}_{tag}",
            email=f"tskmodel_{RUN_TOKEN}_{tag}@example.com",
            password_hash="h",
        )
        await session.commit()
        await session.refresh(user)
        return user


async def _mk_project(owner: User, name: str) -> Project:
    async with SessionFactory() as session:
        owner_ref = await session.merge(owner)
        team = await create_team_crud(
            session, name=f"{name} team", description=None, owner_id=owner_ref.id
        )
        project = await create_project(
            session, name=name, description=None, team_id=team.id, owner_id=owner_ref.id
        )
        await session.commit()
        await session.refresh(project)
        return project


def _mk_task(session, project: Project, creator: User, name: str, **kw) -> Task:
    task = Task(
        project_id=project.id,
        title=name,
        description=None,
        creator_id=creator.id,
        **kw,
    )
    session.add(task)
    return task


async def test_task_roundtrip_with_defaults(anyio_backend):
    creator = await _mk_user("rt")
    project = await _mk_project(creator, f"tskmodel rt {RUN_TOKEN}")

    async with SessionFactory() as session:
        project_ref = await session.get(Project, project.id)
        creator_ref = await session.get(User, creator.id)
        task = _mk_task(session, project_ref, creator_ref, f"rt task {RUN_TOKEN}")
        session.add(task)
        await session.commit()
        tid = task.id

    async with SessionFactory() as session:
        loaded = await session.get(Task, tid)
        assert loaded is not None
        assert loaded.status == "TODO"  # server_default
        assert loaded.priority == "MEDIUM"
        assert loaded.project_id == project.id
        assert loaded.creator_id == creator.id


async def test_check_rejects_invalid_status_and_priority(anyio_backend):
    from sqlalchemy.exc import IntegrityError

    creator = await _mk_user("ck")
    project = await _mk_project(creator, f"tskmodel ck {RUN_TOKEN}")

    for bad in ({"status": "DONE_X"}, {"priority": "CRITICAL"}):
        async with SessionFactory() as session:
            project_ref = await session.get(Project, project.id)
            creator_ref = await session.get(User, creator.id)
            session.add(
                Task(
                    project_id=project_ref.id,
                    title=f"bad {RUN_TOKEN}",
                    creator_id=creator_ref.id,
                    **bad,
                )
            )
            with pytest.raises(IntegrityError):
                await session.commit()
            await session.rollback()


async def test_delete_project_cascades_tasks(anyio_backend):
    creator = await _mk_user("cas")
    project = await _mk_project(creator, f"tskmodel cas {RUN_TOKEN}")

    async with SessionFactory() as session:
        project_ref = await session.get(Project, project.id)
        creator_ref = await session.get(User, creator.id)
        session.add(
            Task(
                project_id=project_ref.id,
                title=f"cas task {RUN_TOKEN}",
                creator_id=creator_ref.id,
            )
        )
        await session.commit()

    async with SessionFactory() as session:
        project_ref = await session.get(Project, project.id)
        await session.delete(project_ref)
        await session.commit()

    async with SessionFactory() as session:
        remaining = (
            await session.execute(
                select(Task).where(Task.title == f"cas task {RUN_TOKEN}")
            )
        ).scalar_one_or_none()
    assert remaining is None


async def test_delete_creator_cascades_tasks(anyio_backend):
    """TASK-031 决策：creator_id CASCADE，删用户级联清其创建的任务。

    团队/项目归属另一个用户（owner），creator 仅创建任务——避免
    teams.owner_id RESTRICT 干扰，真正验证 creator 级联。
    """
    team_owner = await _mk_user("ccas_owner")
    creator = await _mk_user("ccas_creator")
    project = await _mk_project(team_owner, f"tskmodel ccas {RUN_TOKEN}")

    async with SessionFactory() as session:
        project_ref = await session.get(Project, project.id)
        creator_ref = await session.get(User, creator.id)
        session.add(
            Task(
                project_id=project_ref.id,
                title=f"ccas task {RUN_TOKEN}",
                creator_id=creator_ref.id,
            )
        )
        await session.commit()

    async with SessionFactory() as session:
        user_ref = await session.get(User, creator.id)
        await session.delete(user_ref)
        await session.commit()

    async with SessionFactory() as session:
        remaining = (
            await session.execute(
                select(Task).where(Task.title == f"ccas task {RUN_TOKEN}")
            )
        ).scalar_one_or_none()
    assert remaining is None


async def test_same_title_tasks_coexist(anyio_backend):
    creator = await _mk_user("dup")
    project = await _mk_project(creator, f"tskmodel dup {RUN_TOKEN}")

    async with SessionFactory() as session:
        project_ref = await session.get(Project, project.id)
        creator_ref = await session.get(User, creator.id)
        t1 = _mk_task(session, project_ref, creator_ref, f"dup task {RUN_TOKEN}")
        t2 = _mk_task(session, project_ref, creator_ref, f"dup task {RUN_TOKEN}")
        await session.flush()
        assert t1.id != t2.id
        await session.commit()
