"""N+1 查询护栏（TASK-062；开发文档 §46 / §45）。

背景：`TaskRead.assignees` 是列表响应里的内嵌字段。最自然的实现是给 `Task` 挂一个
`relationship("TaskAssignee")`，然后 `for t in tasks: t.assignees` —— 一次列表请求
变成 1 + N 条 SQL，N 是任务数。本项目**故意不用 `relationship()`**，改用一次
`WHERE task_id IN (...)` 批量查询（`app/crud/task_assignee.py::list_assignees_for_tasks`）。

`tests/test_quality_checks.py` 已从**静态**上钉死「模型里没有 relationship()」；
本文件从**运行时**再钉一层：真的发一次 HTTP 请求，统计底层 SQL 语句条数，验证它
**不随结果集大小增长**。两层互补——静态层挡住「有人加回关系映射」，运行时层挡住
「有人把批量查询拆成循环里的单条查询」（这种改动不会新增任何 relationship）。

判定方式（两条独立断言，任意一条被破坏都会红）：

1. **语句总数与任务数无关**：3 个任务与 12 个任务的请求，SELECT 条数必须相等；
2. **访问 task_assignees 表的语句恰好 1 条**：这是「批量」最直接的证据。

两次测量各用**独立 project**（同一 team 下），因此第二次请求的结果集不受第一次
播种影响——否则 12 行的断言会拿到 3+12=15 行。

零残留：RUN_TOKEN 前缀 + teardown 精确删除（tasks → projects → teams → users；
task_assignees / team_members / user_roles 随 FK CASCADE 清理）。
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.security import create_access_token
from app.crud.role import assign_role_to_user, get_role_by_name
from app.crud.task_assignee import add_task_assignee
from app.crud.team import add_team_member
from app.crud.user import create_user
from app.db.session import get_db
from app.main import app
from app.models.project import Project
from app.models.task import Task
from app.models.team import Team
from app.models.team_member import TeamRole
from app.models.user import User

TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@127.0.0.1:5433/taskflow"

RUN_TOKEN = uuid.uuid4().hex[:10]
PASSWORD_HASH = "h"

#: 每个任务分配几个负责人——让「内嵌字段」真的有数据可查，否则测不出 N+1。
ASSIGNEES_PER_TASK = 3

engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
SessionFactory = async_sessionmaker(engine, expire_on_commit=False)


@contextmanager
def _count_selects(sync_engine):
    """上下文内统计落在 `sync_engine` 上的 SELECT 语句（yield statements 列表）。

    只数 SELECT：写路径（INSERT/UPDATE）与本测试的「读取放大」无关，混进来会让断言
    对 fixture 的写入次数敏感。
    """
    statements: list[str] = []

    def _before_cursor_execute(
        conn, cursor, statement, parameters, context, executemany
    ):  # noqa: ANN001 - SQLAlchemy 事件签名固定
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    event.listen(sync_engine, "before_cursor_execute", _before_cursor_execute)
    try:
        yield statements
    finally:
        event.remove(sync_engine, "before_cursor_execute", _before_cursor_execute)


async def _override_get_db():
    async with SessionFactory() as session:
        yield session


def _username(tag: str) -> str:
    return f"taskn1_{RUN_TOKEN}_{tag}"


def _title(tag: str) -> str:
    return f"taskn1 {RUN_TOKEN} {tag}"


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def client():
    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c
    app.dependency_overrides.pop(get_db, None)


@pytest_asyncio.fixture(autouse=True)
async def _cleanup():
    yield
    async with SessionFactory() as session:
        await session.execute(delete(Task).where(Task.title.like(f"taskn1 {RUN_TOKEN}%")))
        await session.execute(
            delete(Project).where(Project.name.like(f"taskn1 proj {RUN_TOKEN}%"))
        )
        await session.execute(
            delete(Team).where(Team.name.like(f"taskn1 team {RUN_TOKEN}%"))
        )
        await session.execute(
            delete(User).where(User.username.like(f"taskn1_{RUN_TOKEN}%"))
        )
        await session.commit()


async def _make_user(tag: str, role_names: list[str] | None = None) -> User:
    async with SessionFactory() as session:
        user = await create_user(
            session,
            username=_username(tag),
            email=f"{_username(tag)}@example.com",
            password_hash=PASSWORD_HASH,
        )
        for role_name in role_names or []:
            role = await get_role_by_name(session, role_name)
            assert role is not None, f"seed role {role_name!r} missing"
            await assign_role_to_user(session, user_id=user.id, role_id=role.id)
        await session.commit()
        await session.refresh(user)
        return user


async def _build_fixture() -> tuple[User, Team, list[User]]:
    """建 1 个 owner（admin 角色）+ 3 个 team member（同一 team），返回 (owner, team, members)。

    同一用例内的两次测量复用这一个 team（team 名称唯一，重复创建会撞 UNIQUE）。
    """
    from app.schemas.team import TeamCreate
    from app.services.team import create_team as create_team_service

    owner = await _make_user("owner", ["admin"])
    members = [await _make_user(f"m{i}") for i in range(ASSIGNEES_PER_TASK)]

    async with SessionFactory() as session:
        team = await create_team_service(
            session, owner, TeamCreate(name=f"taskn1 team {RUN_TOKEN}")
        )
        for member in members:
            await add_team_member(
                session, team_id=team.id, user_id=member.id, role_id=TeamRole.MEMBER
            )
        await session.commit()
        await session.refresh(team)

    return owner, team, members


async def _make_project(team: Team, owner: User, tag: str) -> Project:
    from app.crud.project import create_project

    async with SessionFactory() as session:
        project = await create_project(
            session,
            name=f"taskn1 proj {RUN_TOKEN} {tag}",
            description=None,
            team_id=team.id,
            owner_id=owner.id,
        )
        await session.commit()
        await session.refresh(project)
        return project


async def _seed_tasks(project: Project, owner: User, members: list[User], count: int) -> None:
    """直插 `count` 个任务，每个任务分配 `ASSIGNEES_PER_TASK` 个负责人。"""
    async with SessionFactory() as session:
        for i in range(count):
            task = Task(
                project_id=project.id,
                title=_title(f"{project.id}-{i:02d}"),
                creator_id=owner.id,
            )
            session.add(task)
            await session.flush()
            for member in members:
                await add_task_assignee(
                    session,
                    task_id=task.id,
                    user_id=member.id,
                    assigned_by_id=owner.id,
                )
        await session.commit()


async def _measure_list_selects(
    client, owner: User, team: Team, members: list[User], count: int, tag: str
) -> list[str]:
    """在**全新 project** 下建 count 个任务并发起一次列表请求，返回其 SELECT 语句列表。"""
    project = await _make_project(team, owner, tag)
    await _seed_tasks(project, owner, members, count)

    headers = _bearer(create_access_token(owner.id))
    with _count_selects(engine.sync_engine) as statements:
        resp = await client.get(
            "/api/v1/tasks",
            headers=headers,
            params={"project_id": project.id, "limit": 100},
        )

    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert len(data) == count, f"期望 {count} 个任务，实际 {len(data)}"
    # 内嵌字段真的带上了 assignees —— 否则本测试会「因为没数据查」而假绿。
    for row in data:
        assert len(row["assignees"]) == ASSIGNEES_PER_TASK, row
    return statements


async def test_list_tasks_select_count_does_not_scale_with_row_count(client):
    """§46：一次列表请求的语句总数与返回条数无关（3 行 vs 12 行必须相等）。

    若有人把 assignees 的批量查询改回「循环里逐个查」，12 行的请求会多出 9 条
    SQL —— 这条断言立刻变红，而不是等线上列表接口随数据量变慢。
    """
    owner, team, members = await _build_fixture()

    small = await _measure_list_selects(client, owner, team, members, 3, "small")
    large = await _measure_list_selects(client, owner, team, members, 12, "large")

    assert len(large) == len(small), (
        "列表请求的 SQL 条数随结果集增长（疑似 N+1）："
        f" 3 行={len(small)} 条，12 行={len(large)} 条\n"
        + "\n".join(f"  {i+1}. {s.splitlines()[0][:110]}" for i, s in enumerate(large))
    )


async def test_assignees_are_fetched_in_a_single_batched_query(client):
    """§46：访问 `task_assignees` 表的语句恰好 1 条（批量 IN 的直接证据）。"""
    owner, team, members = await _build_fixture()

    statements = await _measure_list_selects(client, owner, team, members, 8, "batch")

    assignee_hits = [s for s in statements if "task_assignees" in s]
    assert len(assignee_hits) == 1, (
        f"8 个任务的列表请求命中了 {len(assignee_hits)} 条 task_assignees 查询，"
        "应为 1 条批量查询：\n"
        + "\n".join(f"  - {s.splitlines()[0][:110]}" for s in assignee_hits)
    )
    assert " IN " in assignee_hits[0].upper(), (
        "批量查询应当使用 IN (...)：" + assignee_hits[0].splitlines()[0][:160]
    )
