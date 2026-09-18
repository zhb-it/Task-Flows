"""TASK-129：`GET /users/me/overview` 个人工作台聚合的测试。

规格依据：开发文档 §61.6「**个人视图（新增）**：提供跨项目的『我的任务』
与工作台聚合」+「**统计（新增）**：……进度口径（**分母定义必须写明**）」。

断言分四组：

1. 认证与账号状态：无凭证 401、禁用账号 403（与 `/users/me` 同口径）。
2. **口径正确性**：`assigned_open` / `overdue` / `completed_this_week` /
   `task_status` / `teams` / `projects` / `unread_notifications` 各自的计数边界。
3. **作用域（分母）**：只统计「我所属团队下的项目」，且「我的」口径必须再
   与「分配给我」求交——非成员项目的任务即使把用户写进 `task_assignees`
   也不得出现（这是本端点最容易被写漏的一条谓词）。
4. **契约**：OpenAPI 已注册且声明为受保护端点；`recent_limit` 生效；
   「本周」边界按 UTC 周一起算（用注入 `now` 的直连 Service 调用固定时间）；
   聚合是纯读，不得顺手把通知标成已读。

「本周完成」用 `updated_at` 近似完成时刻（tasks 表无 completed_at 列），
理由与边界见 `app/services/overview.py` 模块文档；本文件用**内核 update**
绕过 ORM `onupdate=func.now()`，才能在用例里固定 `updated_at`。

零残留：先删团队（级联清项目 → 任务 → 分配行）再删用户（通知随用户级联）。
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.security import create_access_token
from app.crud.task import create_task
from app.crud.task_assignee import add_task_assignee
from app.crud.team import add_team_member
from app.crud.user import create_user
from app.db.session import get_db
from app.main import app
from app.models.notification import Notification
from app.models.project import Project
from app.models.task import Task
from app.models.team import Team
from app.models.team_member import TeamRole
from app.models.user import User
from app.services import overview as overview_service

TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@127.0.0.1:5433/taskflow"

RUN_TOKEN = uuid.uuid4().hex[:10]
PASSWORD_HASH = "h"

#: 固定「现在」，用于把「本周 / 逾期」的边界钉死（UTC）。周起点由
#: `NOW.weekday()` 推导，用例不假设它是星期几。
NOW = datetime(2026, 9, 17, 12, 0, 0, tzinfo=timezone.utc)

engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
SessionFactory = async_sessionmaker(engine, expire_on_commit=False)


async def _override_get_db():
    async with SessionFactory() as session:
        yield session


def _username(tag: str) -> str:
    return f"meov_{RUN_TOKEN}_{tag}"


def _team_name(tag: str) -> str:
    return f"meov team {RUN_TOKEN} {tag}"


def _project_name(tag: str) -> str:
    return f"meov project {RUN_TOKEN} {tag}"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


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
        users = (
            await session.execute(
                select(User).where(User.username.like(f"meov_{RUN_TOKEN}%"))
            )
        ).scalars().all()
        for u in users:
            teams = (
                await session.execute(select(Team).where(Team.owner_id == u.id))
            ).scalars().all()
            for t in teams:
                await session.delete(t)  # 级联清项目 → 任务 → 分配行
            await session.flush()
            await session.delete(u)  # 通知随用户级联
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


def _bearer(user_id: int) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user_id)}"}


async def _create_team(owner_id: int, tag: str) -> int:
    """经 Service 建队（自动写 OWNER 成员行），绕过 HTTP 减少耦合。"""
    from app.schemas.team import TeamCreate
    from app.services.team import create_team

    async with SessionFactory() as session:
        user = await session.get(User, owner_id)
        team = await create_team(session, user, TeamCreate(name=_team_name(tag)))
        await session.commit()
        return team.id


async def _add_member(team_id: int, user_id: int) -> None:
    async with SessionFactory() as session:
        await add_team_member(
            session, team_id=team_id, user_id=user_id, role_id=TeamRole.MEMBER
        )
        await session.commit()


async def _create_project(team_id: int, owner_id: int, tag: str) -> int:
    from app.crud.project import create_project

    async with SessionFactory() as session:
        project = await create_project(
            session,
            name=_project_name(tag),
            description=None,
            team_id=team_id,
            owner_id=owner_id,
        )
        await session.commit()
        return project.id


async def _add_task(
    project_id: int,
    creator_id: int,
    tag: str,
    *,
    status: str | None = None,
    due_at: datetime | None = None,
    updated_at: datetime | None = None,
    assignees: tuple[int, ...] = (),
) -> int:
    """建任务并可选地指派 / 钉死状态与 `updated_at`。

    状态与 `updated_at` 用**内核 update** 改写：`Task.updated_at` 带
    `onupdate=func.now()`，走 ORM 属性赋值会在 flush 时被覆盖掉，用例就
    无法固定「本周完成」的时间边界。
    """
    async with SessionFactory() as session:
        task = await create_task(
            session,
            project_id=project_id,
            title=f"meov task {RUN_TOKEN} {tag}",
            description=None,
            priority="MEDIUM",
            creator_id=creator_id,
            due_at=due_at,
        )
        await session.flush()
        task_id = task.id
        for uid in assignees:
            await add_task_assignee(
                session, task_id=task_id, user_id=uid, assigned_by_id=creator_id
            )
        if status is not None or updated_at is not None:
            values: dict = {}
            if status is not None:
                values["status"] = status
            if updated_at is not None:
                values["updated_at"] = updated_at
            await session.execute(
                update(Task).where(Task.id == task_id).values(**values)
            )
        await session.commit()
        return task_id


async def _add_notifications(user_id: int, unread: int, read: int = 0) -> None:
    async with SessionFactory() as session:
        for i in range(unread):
            session.add(
                Notification(
                    user_id=user_id, type="system", title=f"unread {i}", is_read=False
                )
            )
        for i in range(read):
            session.add(
                Notification(
                    user_id=user_id, type="system", title=f"read {i}", is_read=True
                )
            )
        await session.commit()


async def _set_updated_at(project_id: int, moment: datetime) -> None:
    async with SessionFactory() as session:
        await session.execute(
            update(Project).where(Project.id == project_id).values(updated_at=moment)
        )
        await session.commit()


def _week_start(moment: datetime = NOW) -> datetime:
    """与服务同口径的本周起点：当日 00:00（UTC）再退到周一。"""
    start_of_day = moment.replace(hour=0, minute=0, second=0, microsecond=0)
    return start_of_day - timedelta(days=start_of_day.weekday())


async def _overview(user_id: int, *, now: datetime = NOW) -> dict:
    """直连 Service 取聚合（注入 `now`，把时间边界钉死）。"""
    async with SessionFactory() as session:
        user = await session.get(User, user_id)
        return await overview_service.get_my_overview(session, user, now=now)


# --- 认证与账号状态 -------------------------------------------------------


async def test_missing_token_returns_401(client) -> None:
    resp = await client.get("/api/v1/users/me/overview")

    assert resp.status_code == 401, resp.text
    assert resp.headers.get("www-authenticate") == "Bearer"


async def test_disabled_account_returns_403(client) -> None:
    user = await _make_user("disabled")
    async with SessionFactory() as session:
        await session.execute(
            update(User).where(User.id == user.id).values(is_active=False)
        )
        await session.commit()

    resp = await client.get("/api/v1/users/me/overview", headers=_bearer(user.id))

    assert resp.status_code == 403, resp.text
    assert resp.json()["detail"] == "User account is disabled"


# --- 空账号基线 -----------------------------------------------------------


async def test_empty_account_returns_zeroed_overview(client) -> None:
    """没有团队 / 项目 / 任务 / 通知的账号必须拿到全 0，而不是 500 或缺失字段。"""
    user = await _make_user("empty")

    resp = await client.get("/api/v1/users/me/overview", headers=_bearer(user.id))

    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["teams"] == 0
    assert data["projects"] == 0
    assert data["unread_notifications"] == 0
    assert data["my_tasks"] == {
        "assigned_open": 0,
        "overdue": 0,
        "completed_this_week": 0,
    }
    assert data["task_status"]["total"] == 0
    assert data["recent_projects"] == []
    # 口径字段必须回传，前端不自己猜周起点。
    assert data["generated_at"] and data["week_start"]


# --- 口径正确性 -----------------------------------------------------------


async def test_counts_reflect_my_assigned_tasks() -> None:
    """我的待办 / 逾期 / 本周完成各自按口径计数。"""
    me = await _make_user("me")
    other = await _make_user("other")
    team_id = await _create_team(me.id, "counts")
    await _add_member(team_id, other.id)
    # 第二个团队：我加入但还没有项目——`teams` 与 `projects` 因此必须不同，
    # 否则前端新账号引导会把「已建团队」误判成「已建项目」。
    second_team_id = await _create_team(me.id, "counts2")
    await _add_member(second_team_id, other.id)
    project_id = await _create_project(team_id, me.id, "counts")

    week_start = _week_start()
    await _add_task(
        project_id, me.id, "open", status="TODO", assignees=(me.id,)
    )  # 待办
    await _add_task(
        project_id,
        me.id,
        "overdue",
        status="IN_PROGRESS",
        due_at=NOW - timedelta(days=1),
        assignees=(me.id,),
    )  # 待办 + 逾期
    await _add_task(
        project_id,
        me.id,
        "duefuture",
        status="TODO",
        due_at=NOW + timedelta(days=1),
        assignees=(me.id,),
    )  # 待办，未逾期
    await _add_task(
        project_id,
        me.id,
        "doneweek",
        status="DONE",
        updated_at=week_start + timedelta(hours=1),
        assignees=(me.id,),
    )  # 本周完成
    await _add_task(
        project_id,
        me.id,
        "donelast",
        status="DONE",
        updated_at=week_start - timedelta(hours=1),
        assignees=(me.id,),
    )  # 上周完成 → 不计
    await _add_task(
        project_id,
        me.id,
        "cancelled",
        status="CANCELLED",
        assignees=(me.id,),
    )  # 终态 → 非待办
    await _add_task(
        project_id, me.id, "notmine", status="TODO", assignees=(other.id,)
    )  # 非我负责 → 不计入我的口径
    await _add_notifications(me.id, unread=3, read=2)

    data = await _overview(me.id)

    assert data["teams"] == 2
    assert data["projects"] == 1
    assert data["unread_notifications"] == 3
    assert data["my_tasks"]["assigned_open"] == 3  # open / overdue / duefuture
    assert data["my_tasks"]["overdue"] == 1
    assert data["my_tasks"]["completed_this_week"] == 1  # doneweek
    # task_status 是全项目口径（含非我负责的任务）。
    assert data["task_status"]["total"] == 7
    assert data["task_status"]["TODO"] == 3  # open / duefuture / notmine
    assert data["task_status"]["IN_PROGRESS"] == 1
    assert data["task_status"]["DONE"] == 2
    assert data["task_status"]["CANCELLED"] == 1
    assert data["task_status"]["REVIEW"] == 0


async def test_overdue_is_a_subset_of_assigned_open() -> None:
    """`overdue` 是 `assigned_open` 的子集——终态任务过期了也不算逾期。"""
    me = await _make_user("subset")
    team_id = await _create_team(me.id, "subset")
    project_id = await _create_project(team_id, me.id, "subset")

    await _add_task(
        project_id,
        me.id,
        "doneoverdue",
        status="DONE",
        due_at=NOW - timedelta(days=5),
        updated_at=NOW,
        assignees=(me.id,),
    )
    await _add_task(
        project_id,
        me.id,
        "cancelledoverdue",
        status="CANCELLED",
        due_at=NOW - timedelta(days=5),
        assignees=(me.id,),
    )
    await _add_task(
        project_id,
        me.id,
        "nodue",
        status="TODO",
        due_at=None,
        assignees=(me.id,),
    )

    data = await _overview(me.id)

    assert data["my_tasks"]["assigned_open"] == 1  # 只有 nodue
    assert data["my_tasks"]["overdue"] == 0
    assert data["my_tasks"]["completed_this_week"] == 1


async def test_week_boundary_is_monday_utc() -> None:
    """周一 00:00 UTC 是本周边界：前一秒不算本周，边界本身算。"""
    me = await _make_user("week")
    team_id = await _create_team(me.id, "week")
    project_id = await _create_project(team_id, me.id, "week")

    week_start = _week_start()
    task_id = await _add_task(
        project_id,
        me.id,
        "edge",
        status="DONE",
        updated_at=week_start - timedelta(seconds=1),
        assignees=(me.id,),
    )

    data = await _overview(me.id)
    assert data["week_start"] == week_start
    assert data["my_tasks"]["completed_this_week"] == 0

    async with SessionFactory() as session:
        await session.execute(
            update(Task).where(Task.id == task_id).values(updated_at=week_start)
        )
        await session.commit()

    data = await _overview(me.id)
    assert data["my_tasks"]["completed_this_week"] == 1


# --- 作用域（分母） -------------------------------------------------------


async def test_tasks_outside_my_teams_are_excluded(client) -> None:
    """非成员项目下的任务不得进入任何计数——即使被写进 `task_assignees`。"""
    me = await _make_user("scope")
    outsider = await _make_user("outsider")

    my_team = await _create_team(me.id, "scope")
    my_project = await _create_project(my_team, me.id, "scope")

    other_team = await _create_team(outsider.id, "other")
    other_project = await _create_project(other_team, outsider.id, "other")

    await _add_task(my_project, me.id, "mine", status="TODO", assignees=(me.id,))
    await _add_task(
        other_project, outsider.id, "leak", status="TODO", assignees=(me.id,)
    )

    resp = await client.get("/api/v1/users/me/overview", headers=_bearer(me.id))

    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["teams"] == 1  # 另一个团队不属于我 → 不计入
    assert data["projects"] == 1
    assert data["my_tasks"]["assigned_open"] == 1
    assert data["task_status"]["total"] == 1


async def test_other_users_overview_is_independent(client) -> None:
    """两个用户各自的工作台互不串味（未读通知与项目数都按各自作用域）。"""
    me = await _make_user("iso_me")
    other = await _make_user("iso_other")
    team_id = await _create_team(me.id, "iso")
    await _create_project(team_id, me.id, "iso")
    await _add_notifications(me.id, unread=4)
    await _add_notifications(other.id, unread=1)

    mine = await client.get("/api/v1/users/me/overview", headers=_bearer(me.id))
    theirs = await client.get("/api/v1/users/me/overview", headers=_bearer(other.id))

    assert mine.status_code == 200 and theirs.status_code == 200
    assert mine.json()["data"]["projects"] == 1
    assert mine.json()["data"]["unread_notifications"] == 4
    assert theirs.json()["data"]["projects"] == 0
    assert theirs.json()["data"]["unread_notifications"] == 1


# --- 契约 -----------------------------------------------------------------


async def test_recent_projects_ordered_and_limited(client) -> None:
    """最近项目按 `updated_at` 倒序，且 `recent_limit` 生效。"""
    me = await _make_user("recent")
    team_id = await _create_team(me.id, "recent")
    p1 = await _create_project(team_id, me.id, "r1")
    p2 = await _create_project(team_id, me.id, "r2")
    p3 = await _create_project(team_id, me.id, "r3")
    await _set_updated_at(p1, NOW - timedelta(days=3))
    await _set_updated_at(p2, NOW)
    await _set_updated_at(p3, NOW - timedelta(days=1))

    resp = await client.get(
        "/api/v1/users/me/overview?recent_limit=2", headers=_bearer(me.id)
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert [p["id"] for p in data["recent_projects"]] == [p2, p3]
    assert data["projects"] == 3  # 总数是全量，不受 recent_limit 影响


@pytest.mark.parametrize("bad", ["0", "21", "abc"])
async def test_recent_limit_out_of_range_is_422(client, bad: str) -> None:
    me = await _make_user("limit")

    resp = await client.get(
        f"/api/v1/users/me/overview?recent_limit={bad}", headers=_bearer(me.id)
    )

    assert resp.status_code == 422, resp.text


async def test_endpoint_is_registered_in_openapi(client) -> None:
    resp = await client.get("/openapi.json")

    assert resp.status_code == 200
    path = resp.json()["paths"]["/api/v1/users/me/overview"]
    assert "get" in path
    assert "security" in path["get"]


async def test_overview_does_not_mutate_data(client) -> None:
    """只读聚合：调用前后任务状态与 updated_at 不变。"""
    me = await _make_user("nomutate")
    team_id = await _create_team(me.id, "nomutate")
    project_id = await _create_project(team_id, me.id, "nomutate")
    task_id = await _add_task(
        project_id, me.id, "keep", status="TODO", assignees=(me.id,)
    )

    async with SessionFactory() as session:
        before = (
            await session.execute(select(Task).where(Task.id == task_id))
        ).scalar_one()
        before_updated = before.updated_at

    resp = await client.get("/api/v1/users/me/overview", headers=_bearer(me.id))
    assert resp.status_code == 200, resp.text

    async with SessionFactory() as session:
        after = (
            await session.execute(select(Task).where(Task.id == task_id))
        ).scalar_one()
        assert after.updated_at == before_updated
        assert after.status == "TODO"


async def test_notifications_are_untouched_by_overview(client) -> None:
    """聚合不得顺手把通知标成已读（那会让前端的未读红点自己消失）。"""
    me = await _make_user("unread")
    await _add_notifications(me.id, unread=2)

    await client.get("/api/v1/users/me/overview", headers=_bearer(me.id))

    async with SessionFactory() as session:
        unread = (
            await session.execute(
                select(Notification.id).where(
                    Notification.user_id == me.id,
                    Notification.is_read.is_(False),
                )
            )
        ).scalars().all()
    assert len(unread) == 2
