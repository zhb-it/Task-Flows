"""TASK-032：Task Schema / CRUD 层测试。

覆盖两项已确认决策与 Schema/CRUD 行为（数据库集成，开发库零残留）：

1. `TaskCreate` 不暴露 `status` —— 新任务一律 TODO 起步，状态流转只能走
   transition API（TASK-038）。
2. CRUD 层仅基础操作 —— `get_task` / `list_tasks_by_project`（id 升序）/
   create / update / delete；过滤/分页/排序留 TASK-035。

Schema 校验为纯 Pydantic 行为（离线断言），持久化行为走真实开发库；
用户/团队/项目按「本次运行唯一前缀」创建，teardown 精确删除。
"""

import uuid
from datetime import datetime, timezone

import pytest
import pydantic
import pytest_asyncio
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.crud.project import create_project
from app.crud.task import (
    create_task,
    delete_task,
    get_task,
    list_tasks_by_project,
    update_task,
)
from app.crud.team import create_team
from app.crud.user import create_user
from app.models.task import Task
from app.models.user import User
from app.schemas.task import TaskCreate, TaskRead, TaskUpdate

TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@127.0.0.1:5433/taskflow"

RUN_TOKEN = uuid.uuid4().hex[:10]
PASSWORD_HASH = "h"

engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
SessionFactory = async_sessionmaker(engine, expire_on_commit=False)


def _username(tag: str) -> str:
    return f"taskcrud_{RUN_TOKEN}_{tag}"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest_asyncio.fixture(autouse=True)
async def _cleanup():
    yield
    async with SessionFactory() as session:
        from app.models.project import Project
        from app.models.team import Team

        # 依 RESTRICT 链精确拆除：tasks → projects → teams → users
        await session.execute(
            delete(Task).where(Task.title.like(f"taskcrud {RUN_TOKEN}%"))
        )
        await session.execute(
            delete(Project).where(Project.name.like(f"taskcrud proj {RUN_TOKEN}%"))
        )
        await session.execute(
            delete(Team).where(Team.name.like(f"taskcrud team {RUN_TOKEN}%"))
        )
        await session.execute(
            delete(User).where(User.username.like(f"taskcrud_{RUN_TOKEN}%"))
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


async def _make_project(owner: User, name: str):
    """建 team + project（owner 兼任团队 owner 与项目创建者）。"""
    async with SessionFactory() as session:
        team = await create_team(
            session,
            name=f"taskcrud team {RUN_TOKEN}",
            description=None,
            owner_id=owner.id,
        )
        project = await create_project(
            session,
            name=name,
            description=None,
            team_id=team.id,
            owner_id=owner.id,
        )
        await session.commit()
        await session.refresh(project)
        return project


# --- 决策 1：TaskCreate 不暴露 status，强制 TODO 起步 ----------------------------


def test_task_create_schema_has_no_status_field():
    """TaskCreate 不收 status —— 传入直接 422 语义（extra 字段被忽略前先验证字段集）。"""
    fields = set(TaskCreate.model_fields)
    assert "status" not in fields
    assert fields == {"project_id", "title", "description", "priority", "due_at"}


def test_task_update_schema_has_no_status_field():
    """TaskUpdate 同样不含 status（更新走 transition API）与 project_id/creator_id。"""
    fields = set(TaskUpdate.model_fields)
    assert "status" not in fields
    assert "project_id" not in fields
    assert "creator_id" not in fields
    assert fields == {"title", "description", "priority", "due_at"}


def test_task_create_defaults():
    data = TaskCreate(project_id=1, title="t")
    assert data.priority.value == "MEDIUM"
    assert data.description is None
    assert data.due_at is None


def test_task_create_rejects_empty_title():
    with pytest.raises(pydantic.ValidationError):
        TaskCreate(project_id=1, title="")


def test_task_create_rejects_overlong_title():
    with pytest.raises(pydantic.ValidationError):
        TaskCreate(project_id=1, title="x" * 201)


def test_task_create_rejects_invalid_priority():
    with pytest.raises(pydantic.ValidationError):
        TaskCreate(project_id=1, title="t", priority="WHENEVER")


def test_task_create_accepts_all_priority_values():
    for value in ("LOW", "MEDIUM", "HIGH", "URGENT"):
        assert TaskCreate(project_id=1, title="t", priority=value).priority.value == value


def test_task_read_exposes_all_columns():
    model_fields = set(TaskRead.model_fields)
    assert model_fields == {
        "id",
        "project_id",
        "title",
        "description",
        "status",
        "priority",
        "creator_id",
        "due_at",
        "created_at",
        "updated_at",
    }


# --- 决策 2：基础 CRUD（DB 集成）-------------------------------------------------


async def test_create_task_defaults_to_todo():
    owner = await _make_user("creator")
    project = await _make_project(owner, f"taskcrud proj {RUN_TOKEN} todo")
    async with SessionFactory() as session:
        task = await create_task(
            session,
            project_id=project.id,
            title=f"taskcrud {RUN_TOKEN} todo",
            description=None,
            priority="HIGH",
            creator_id=owner.id,
        )
        await session.commit()
        assert task.status == "TODO"
        assert task.priority == "HIGH"
        assert task.id is not None


async def test_get_task_roundtrip_and_missing():
    owner = await _make_user("getter")
    project = await _make_project(owner, f"taskcrud proj {RUN_TOKEN} get")
    due = datetime(2026, 10, 1, 8, 30, tzinfo=timezone.utc)
    async with SessionFactory() as session:
        task = await create_task(
            session,
            project_id=project.id,
            title=f"taskcrud {RUN_TOKEN} get",
            description="d",
            priority="LOW",
            creator_id=owner.id,
            due_at=due,
        )
        await session.commit()
        fetched = await get_task(session, task.id)
        assert fetched is not None
        assert fetched.due_at == due
        assert fetched.title == f"taskcrud {RUN_TOKEN} get"
        assert await get_task(session, 999999999) is None


async def test_list_tasks_by_project_ordered_and_isolated():
    owner = await _make_user("lister")
    p1 = await _make_project(owner, f"taskcrud proj {RUN_TOKEN} l1")
    p2 = await _make_project(owner, f"taskcrud proj {RUN_TOKEN} l2")
    async with SessionFactory() as session:
        ids = []
        for i in (3, 1, 2):
            t = await create_task(
                session,
                project_id=p1.id,
                title=f"taskcrud {RUN_TOKEN} l{i}",
                description=None,
                priority="MEDIUM",
                creator_id=owner.id,
            )
            ids.append(t.id)
        # p2 一条，验证项目隔离
        await create_task(
            session,
            project_id=p2.id,
            title=f"taskcrud {RUN_TOKEN} other",
            description=None,
            priority="MEDIUM",
            creator_id=owner.id,
        )
        await session.commit()
        got = await list_tasks_by_project(session, p1.id)
        assert [t.id for t in got] == sorted(ids)
        assert all(t.project_id == p1.id for t in got)
        assert len(await list_tasks_by_project(session, p2.id)) == 1


async def test_update_task_partial_fields():
    owner = await _make_user("updater")
    project = await _make_project(owner, f"taskcrud proj {RUN_TOKEN} upd")
    async with SessionFactory() as session:
        task = await create_task(
            session,
            project_id=project.id,
            title=f"taskcrud {RUN_TOKEN} upd",
            description="before",
            priority="LOW",
            creator_id=owner.id,
        )
        await session.commit()

    payload = TaskUpdate(priority="URGENT", description=None)
    fields = payload.model_dump(exclude_unset=True)
    async with SessionFactory() as session:
        task_ref = await get_task(session, task.id)
        for key, value in fields.items():
            setattr(task_ref, key, value)
        await update_task(session, task_ref)
        await session.commit()
        refreshed = await get_task(session, task.id)
        # 只应用显式传入的字段；title 未传保持不变
        assert refreshed.priority == "URGENT"
        assert refreshed.description is None
        assert refreshed.title == f"taskcrud {RUN_TOKEN} upd"
        # status 不受 update 影响
        assert refreshed.status == "TODO"


async def test_delete_task():
    owner = await _make_user("deleter")
    project = await _make_project(owner, f"taskcrud proj {RUN_TOKEN} del")
    async with SessionFactory() as session:
        task = await create_task(
            session,
            project_id=project.id,
            title=f"taskcrud {RUN_TOKEN} del",
            description=None,
            priority="MEDIUM",
            creator_id=owner.id,
        )
        await session.commit()
        task_ref = await get_task(session, task.id)
        await delete_task(session, task_ref)
        await session.commit()
        assert await get_task(session, task.id) is None
