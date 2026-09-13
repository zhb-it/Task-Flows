"""TASK-033：Task Service 层测试。

覆盖两项已确认决策与 Service 行为（数据库集成，开发库零残留）：

1. 创建授权 = 团队成员即可（task:create 功能级之上）；项目不存在或
   调用者非成员 → 404 "Project not found"（IDOR 防枚举）。
2. 更新 = 团队成员即可；删除 = 团队角色 OWNER/ADMIN（角色不足 403
   "Only team owner or admin can delete tasks"，不在归属链 404）。

可见性按规格 §5「所属团队链路下的资源」：任务 → 项目 → 团队 →
team_members。用户/团队/项目/任务按「本次运行唯一前缀」创建，
teardown 按 RESTRICT 链精确拆除（tasks → projects → teams → users）。
"""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.exceptions import ForbiddenError, ResourceNotFoundError
from app.crud.project import create_project
from app.crud.task import get_task
from app.crud.team import add_team_member
from app.crud.user import create_user
from app.models.project import Project
from app.models.task import Task
from app.models.team import Team
from app.models.user import User
from app.schemas.task import TaskCreate, TaskUpdate
from app.services.task import (
    create_task,
    delete_task,
    get_task_for_user,
    list_tasks,
    update_task,
)

TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@127.0.0.1:5433/taskflow"

RUN_TOKEN = uuid.uuid4().hex[:10]
PASSWORD_HASH = "h"

engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
SessionFactory = async_sessionmaker(engine, expire_on_commit=False)


def _username(tag: str) -> str:
    return f"tasksvc_{RUN_TOKEN}_{tag}"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest_asyncio.fixture(autouse=True)
async def _cleanup():
    yield
    async with SessionFactory() as session:
        # RESTRICT 链精确拆除：tasks → projects → teams → users
        await session.execute(
            delete(Task).where(Task.title.like(f"tasksvc {RUN_TOKEN}%"))
        )
        await session.execute(
            delete(Project).where(Project.name.like(f"tasksvc proj {RUN_TOKEN}%"))
        )
        await session.execute(
            delete(Team).where(Team.name.like(f"tasksvc team {RUN_TOKEN}%"))
        )
        await session.execute(
            delete(User).where(User.username.like(f"tasksvc_{RUN_TOKEN}%"))
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
    """建 team + project（owner 兼任团队 owner 与项目创建者）。

    团队用 **service 层** `create_team` 创建——它会自动写入 OWNER 成员行
    （TASK-027 决策），owner 由此进入归属链；crud 层的 create_team 只写
    teams 行，不产生成员行。
    """
    from app.schemas.team import TeamCreate
    from app.services.team import create_team as create_team_service

    async with SessionFactory() as session:
        team = await create_team_service(
            session, owner, TeamCreate(name=f"tasksvc team {RUN_TOKEN} {name}")
        )
        project = await create_project(
            session,
            name=f"tasksvc proj {RUN_TOKEN} {name}",
            description=None,
            team_id=team.id,
            owner_id=owner.id,
        )
        await session.commit()
        await session.refresh(project)
        return project


async def _make_task(project_id: int, creator: User, tag: str) -> Task:
    async with SessionFactory() as session:
        from app.crud.task import create_task as create_task_crud

        task = await create_task_crud(
            session,
            project_id=project_id,
            title=f"tasksvc {RUN_TOKEN} {tag}",
            description=None,
            priority="MEDIUM",
            creator_id=creator.id,
        )
        await session.commit()
        await session.refresh(task)
        return task


# --- 决策 1：创建 = 团队成员即可，非成员 404 -------------------------------------


async def test_create_task_as_member_ok_and_creator_is_caller():
    owner = await _make_user("owner")
    member = await _make_user("member")
    project = await _make_project(owner, "create")
    async with SessionFactory() as session:
        await add_team_member(
            session, team_id=project.team_id, user_id=member.id, role_id=3
        )
        await session.commit()

    payload = TaskCreate(
        project_id=project.id, title=f"tasksvc {RUN_TOKEN} create"
    )
    async with SessionFactory() as session:
        task = await create_task(session, member, payload)
        await session.commit()
        assert task.creator_id == member.id
        assert task.status == "TODO"  # 强制 TODO 起步（TASK-032 决策）
        assert task.priority == "MEDIUM"


async def test_create_task_non_member_404():
    owner = await _make_user("owner2")
    outsider = await _make_user("outsider2")
    project = await _make_project(owner, "create2")

    payload = TaskCreate(
        project_id=project.id, title=f"tasksvc {RUN_TOKEN} x"
    )
    async with SessionFactory() as session:
        with pytest.raises(ResourceNotFoundError) as exc_info:
            await create_task(session, outsider, payload)
        assert exc_info.value.detail == "Project not found"


async def test_create_task_missing_project_404_same_message():
    nobody = await _make_user("nobody3")
    payload = TaskCreate(project_id=999999999, title=f"tasksvc {RUN_TOKEN} y")
    async with SessionFactory() as session:
        with pytest.raises(ResourceNotFoundError) as exc_info:
            await create_task(session, nobody, payload)
        assert exc_info.value.detail == "Project not found"


# --- 归属链可见性：读 / 列表 -----------------------------------------------------


async def test_get_task_visible_to_members_only():
    owner = await _make_user("owner4")
    member = await _make_user("member4")
    outsider = await _make_user("outsider4")
    project = await _make_project(owner, "vis")
    task = await _make_task(project.id, owner, "vis1")
    async with SessionFactory() as session:
        await add_team_member(
            session, team_id=project.team_id, user_id=member.id, role_id=3
        )
        await session.commit()

    async with SessionFactory() as session:
        got = await get_task_for_user(session, member, task.id)
        assert got.id == task.id
    # outsider（非成员）404
    async with SessionFactory() as session:
        with pytest.raises(ResourceNotFoundError) as e1:
            await get_task_for_user(session, outsider, task.id)
        assert e1.value.detail == "Task not found"
        # 不存在的任务同文案
        with pytest.raises(ResourceNotFoundError) as e2:
            await get_task_for_user(session, owner, 999999999)
        assert e2.value.detail == "Task not found"


async def test_list_tasks_project_scoped_and_member_only():
    owner = await _make_user("owner5")
    outsider = await _make_user("outsider5")
    p1 = await _make_project(owner, "l1")
    p2 = await _make_project(owner, "l2")
    t1 = await _make_task(p1.id, owner, "la")
    t2 = await _make_task(p1.id, owner, "lb")
    await _make_task(p2.id, owner, "lc")

    async with SessionFactory() as session:
        got = await list_tasks(session, owner, p1.id)
        assert [t.id for t in got] == [t1.id, t2.id]
    async with SessionFactory() as session:
        with pytest.raises(ResourceNotFoundError):
            await list_tasks(session, outsider, p1.id)


# --- 决策 2：更新成员即可；删除仅 OWNER/ADMIN -----------------------------------


async def test_update_task_by_plain_member_ok():
    owner = await _make_user("owner6")
    member = await _make_user("member6")
    project = await _make_project(owner, "upd")
    task = await _make_task(project.id, owner, "upd1")
    async with SessionFactory() as session:
        await add_team_member(
            session, team_id=project.team_id, user_id=member.id, role_id=3
        )
        await session.commit()

    payload = TaskUpdate(title=f"tasksvc {RUN_TOKEN} upd-new")
    async with SessionFactory() as session:
        updated = await update_task(session, member, task.id, payload)
        await session.commit()
        assert updated.title == f"tasksvc {RUN_TOKEN} upd-new"
        assert updated.status == "TODO"  # status 不受 update 影响


async def test_update_task_non_member_404():
    owner = await _make_user("owner7")
    outsider = await _make_user("outsider7")
    project = await _make_project(owner, "upd2")
    task = await _make_task(project.id, owner, "upd2t")

    payload = TaskUpdate(title="hacked")
    async with SessionFactory() as session:
        with pytest.raises(ResourceNotFoundError):
            await update_task(session, outsider, task.id, payload)


async def test_delete_task_by_owner_ok_and_by_member_403():
    owner = await _make_user("owner8")
    member = await _make_user("member8")
    project = await _make_project(owner, "del")
    task = await _make_task(project.id, owner, "del1")
    async with SessionFactory() as session:
        await add_team_member(
            session, team_id=project.team_id, user_id=member.id, role_id=3
        )
        await session.commit()

    # 团队 MEMBER 删除 → 403（调用者已在归属链、本就可见）
    async with SessionFactory() as session:
        with pytest.raises(ForbiddenError) as exc_info:
            await delete_task(session, member, task.id)
        assert exc_info.value.detail == "Only team owner or admin can delete tasks"

    # owner 删除成功
    async with SessionFactory() as session:
        await delete_task(session, owner, task.id)
        await session.commit()
        assert await get_task(session, task.id) is None


async def test_delete_task_non_member_404():
    owner = await _make_user("owner9")
    outsider = await _make_user("outsider9")
    project = await _make_project(owner, "del2")
    task = await _make_task(project.id, owner, "del2t")

    async with SessionFactory() as session:
        with pytest.raises(ResourceNotFoundError):
            await delete_task(session, outsider, task.id)
