"""TASK-053：通知 Service/API + 派发点接线 HTTP 端到端验收（真实产品应用 + 真实 Token）.

与 test_operation_log_api.py 同模式：对 ``app.main.app`` 走完整链路，仅覆盖
``get_db`` 指向测试库。覆盖 §18 通知系统 / §25.8 接口 / DECISIONS 035 的权限决策：

## A. 通知 API
- ``GET /notifications`` 仅返回 **当前用户自己** 的通知（资源级隔离，最小暴露面）；
- 按 ``created_at DESC`` 排序、分页（skip/limit）；
- ``PATCH /notifications/{id}/read`` 标记自己的一条为已读；已在读幂等；
- 非接收人 / 不存在 → 404 同文案（IDOR 防枚举）；
- 无 Token → 401（仅需认证，无功能级权限）。

## B. 派发点接线（§24 通知异步化，TASK-049 任务 + 本 TASK 接线）
经 ``notification_dispatch`` spy 验证 TaskService 在事务提交后调用
``_dispatch_notification``（→ ``create_notification.delay``），且不真连 broker：
- 任务分配 → 仅通知被分派者；自领不产生通知；
- 任务状态变更 → 通知任务全部负责人、排除触发者本人。

零残留：用户（含其通知 FK CASCADE）/ 团队链资源按本批前缀精确清理。
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.security import create_access_token
from app.crud.role import assign_role_to_user, get_role_by_name
from app.crud.user import create_user
from app.db.session import get_db
from app.main import app
from app.models.notification import Notification
from app.models.project import Project
from app.models.task import Task
from app.models.team import Team
from app.models.user import User

TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@127.0.0.1:5433/taskflow"

RUN_TOKEN = uuid.uuid4().hex[:10]
PASSWORD_HASH = "h"

engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
SessionFactory = async_sessionmaker(engine, expire_on_commit=False)


async def _override_get_db():
    async with SessionFactory() as session:
        yield session


def _username(tag: str) -> str:
    return f"ntfapi_{RUN_TOKEN}_{tag}"


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
        # 通知随 users CASCADE；其余按依赖顺序拆除（同 test_operation_log_api）。
        await session.execute(
            delete(Task).where(Task.title.like(f"ntfapi {RUN_TOKEN}%"))
        )
        await session.execute(
            delete(Project).where(Project.name.like(f"ntfapi proj {RUN_TOKEN}%"))
        )
        await session.execute(
            delete(Team).where(Team.name.like(f"ntfapi team {RUN_TOKEN}%"))
        )
        await session.execute(
            delete(User).where(User.username.like(f"ntfapi_{RUN_TOKEN}%"))
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


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _insert_notification(
    user_id: int,
    ntype: str,
    title: str,
    content: str | None = None,
    *,
    minutes_ago: int = 0,
) -> int:
    """直连造一条通知行（绕开 API——通知只能由系统派发，无创建端点）。"""
    async with SessionFactory() as session:
        notif = Notification(
            user_id=user_id,
            type=ntype,
            title=title,
            content=content,
            created_at=datetime.now(timezone.utc) - timedelta(minutes=minutes_ago),
        )
        session.add(notif)
        await session.commit()
        await session.refresh(notif)
        return notif.id


async def _make_project(owner: User, tag: str) -> Project:
    from app.crud.project import create_project
    from app.schemas.team import TeamCreate
    from app.services.team import create_team as create_team_service

    async with SessionFactory() as session:
        team = await create_team_service(
            session, owner, TeamCreate(name=f"ntfapi team {RUN_TOKEN} {tag}")
        )
        project = await create_project(
            session,
            name=f"ntfapi proj {RUN_TOKEN} {tag}",
            description=None,
            team_id=team.id,
            owner_id=owner.id,
        )
        await session.commit()
        await session.refresh(project)
        return project


async def _add_member(project: Project, user: User) -> None:
    from app.crud.team import add_team_member

    async with SessionFactory() as session:
        await add_team_member(
            session, team_id=project.team_id, user_id=user.id, role_id=3
        )
        await session.commit()


async def _create_task(client, owner: User, project: Project, tag: str) -> int:
    resp = await client.post(
        "/api/v1/tasks",
        headers=_bearer(create_access_token(owner.id)),
        json={"project_id": project.id, "title": f"ntfapi {RUN_TOKEN} {tag}"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]["id"]


async def _assign(client, actor: User, task_id: int, target_user_id: int) -> int:
    resp = await client.post(
        f"/api/v1/tasks/{task_id}/assignees",
        headers=_bearer(create_access_token(actor.id)),
        json={"user_id": target_user_id},
    )
    assert resp.status_code == 201, resp.text
    return resp.status_code


async def _transition(client, actor: User, task_id: int, to: str) -> int:
    resp = await client.post(
        f"/api/v1/tasks/{task_id}/transition",
        headers=_bearer(create_access_token(actor.id)),
        json={"to_status": to},
    )
    assert resp.status_code == 200, resp.text
    return resp.status_code


# --- A. 通知 API：资源级隔离 ------------------------------------------------


async def test_list_returns_only_own_notifications(client):
    a = await _make_user("a", ["admin"])
    b = await _make_user("b", ["admin"])
    await _insert_notification(a.id, "task_assigned", "A-1")
    await _insert_notification(a.id, "task_status_changed", "A-2")
    await _insert_notification(b.id, "task_assigned", "B-1")

    resp = await client.get(
        "/api/v1/notifications", headers=_bearer(create_access_token(a.id))
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert len(data) == 2
    assert all(n["user_id"] == a.id for n in data)
    assert {n["title"] for n in data} == {"A-1", "A-2"}


async def test_list_pagination_desc(client):
    u = await _make_user("u", ["admin"])
    await _insert_notification(u.id, "t", "old", minutes_ago=30)
    await _insert_notification(u.id, "t", "mid", minutes_ago=10)
    await _insert_notification(u.id, "t", "new", minutes_ago=1)

    resp = await client.get(
        "/api/v1/notifications?limit=1",
        headers=_bearer(create_access_token(u.id)),
    )
    assert resp.status_code == 200
    assert resp.json()["data"][0]["title"] == "new"

    resp = await client.get(
        "/api/v1/notifications?limit=1&skip=1",
        headers=_bearer(create_access_token(u.id)),
    )
    assert resp.json()["data"][0]["title"] == "mid"


async def test_mark_read_own(client):
    u = await _make_user("u2", ["admin"])
    nid = await _insert_notification(u.id, "task_assigned", "请查收")

    resp = await client.patch(
        f"/api/v1/notifications/{nid}/read",
        headers=_bearer(create_access_token(u.id)),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()["data"]
    assert body["id"] == nid
    assert body["is_read"] is True

    # GET 复查
    resp = await client.get(
        "/api/v1/notifications", headers=_bearer(create_access_token(u.id))
    )
    assert resp.json()["data"][0]["is_read"] is True


async def test_mark_read_idempotent(client):
    u = await _make_user("u3", ["admin"])
    nid = await _insert_notification(u.id, "task_assigned", "已读条目", content="x")
    # 先标已读
    await client.patch(
        f"/api/v1/notifications/{nid}/read",
        headers=_bearer(create_access_token(u.id)),
    )
    # 再标一次：仍 200，不产生错误（幂等）
    resp = await client.patch(
        f"/api/v1/notifications/{nid}/read",
        headers=_bearer(create_access_token(u.id)),
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["is_read"] is True


async def test_mark_read_others_404(client):
    a = await _make_user("a4", ["admin"])
    b = await _make_user("b4", ["admin"])
    nid = await _insert_notification(a.id, "task_assigned", "A 的私信")

    resp = await client.patch(
        f"/api/v1/notifications/{nid}/read",
        headers=_bearer(create_access_token(b.id)),
    )
    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"] == "Notification not found"


async def test_mark_read_nonexistent_404(client):
    u = await _make_user("u5", ["admin"])
    resp = await client.patch(
        f"/api/v1/notifications/999999/read",
        headers=_bearer(create_access_token(u.id)),
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Notification not found"


async def test_unauthenticated_401(client):
    resp = await client.get("/api/v1/notifications")
    assert resp.status_code == 401
    resp = await client.patch("/api/v1/notifications/1/read")
    assert resp.status_code == 401
    resp = await client.patch("/api/v1/notifications/read-all")
    assert resp.status_code == 401


# --- A2. read-all 标记全部已读（TASK-054）------------------------------------


async def test_read_all_marks_only_unread_and_is_idempotent(client):
    u = await _make_user("ra1", ["admin"])
    for i in range(3):
        await _insert_notification(u.id, "task_assigned", f"unread-{i}")
    nid_read = await _insert_notification(u.id, "task_assigned", "already-read")
    # 预置一条已读（走单条端点，顺带覆盖混合初态）
    resp = await client.patch(
        f"/api/v1/notifications/{nid_read}/read",
        headers=_bearer(create_access_token(u.id)),
    )
    assert resp.status_code == 200, resp.text

    resp = await client.patch(
        "/api/v1/notifications/read-all",
        headers=_bearer(create_access_token(u.id)),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["marked"] == 3  # 只统计真翻转的未读条数

    # GET 复查：全部已读
    resp = await client.get(
        "/api/v1/notifications", headers=_bearer(create_access_token(u.id))
    )
    assert {n["is_read"] for n in resp.json()["data"]} == {True}

    # 幂等：再调一次 → 0
    resp = await client.patch(
        "/api/v1/notifications/read-all",
        headers=_bearer(create_access_token(u.id)),
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["marked"] == 0


async def test_read_all_scoped_to_own_inbox(client):
    a = await _make_user("ra2a", ["admin"])
    b = await _make_user("ra2b", ["admin"])
    await _insert_notification(a.id, "task_assigned", "A-1")
    await _insert_notification(a.id, "task_status_changed", "A-2")
    await _insert_notification(b.id, "task_assigned", "B-1")

    resp = await client.patch(
        "/api/v1/notifications/read-all",
        headers=_bearer(create_access_token(a.id)),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["marked"] == 2  # 只动自己的

    # b 的通知不受影响
    resp = await client.get(
        "/api/v1/notifications", headers=_bearer(create_access_token(b.id))
    )
    assert all(n["is_read"] is False for n in resp.json()["data"])


async def test_read_all_empty_inbox_returns_zero(client):
    u = await _make_user("ra3", ["admin"])
    resp = await client.patch(
        "/api/v1/notifications/read-all",
        headers=_bearer(create_access_token(u.id)),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["marked"] == 0  # 没有未读是合法的 0，不是 404


# --- B. 派发点接线（§24）-------------------------------------------------


async def test_assign_dispatches_to_assignee(client, notification_dispatch):
    admin_a = await _make_user("admin_a", ["admin"])
    member_b = await _make_user("member_b", ["member"])
    project = await _make_project(admin_a, "d1")
    await _add_member(project, member_b)
    task_id = await _create_task(client, admin_a, project, "d1")

    await _assign(client, admin_a, task_id, member_b.id)

    assert len(notification_dispatch) == 1
    args, _kwargs = notification_dispatch[0]
    assert args[0] == member_b.id  # 接收人 = 被分派者
    assert args[1] == "task_assigned"


async def test_self_assign_does_not_dispatch(client, notification_dispatch):
    admin_a = await _make_user("admin_sa", ["admin"])
    project = await _make_project(admin_a, "sa")
    task_id = await _create_task(client, admin_a, project, "sa")

    # 自领：分配自己
    resp = await client.post(
        f"/api/v1/tasks/{task_id}/assignees",
        headers=_bearer(create_access_token(admin_a.id)),
        json={"user_id": admin_a.id},
    )
    assert resp.status_code == 201, resp.text
    assert notification_dispatch == []  # 自领不产生通知


async def test_transition_dispatches_to_assignees_excluding_actor(
    client, notification_dispatch
):
    admin_a = await _make_user("admin_ta", ["admin"])  # admin 持有 task:transition
    member_b = await _make_user("member_ta", ["member"])
    project = await _make_project(admin_a, "ta")
    await _add_member(project, member_b)
    task_id = await _create_task(client, admin_a, project, "ta")
    # 双方都是负责人：admin_a 分派 member_b、member_b 分派 admin_a
    # （这两次分配各自派发 task_assigned，已记入 spy）
    await _assign(client, admin_a, task_id, member_b.id)
    await _assign(client, member_b, task_id, admin_a.id)
    notification_dispatch.clear()  # 隔离：只断言状态变更这一步的派发

    # admin_a 触发状态变更 → 应通知 member_b，排除触发者 admin_a 本人
    await _transition(client, admin_a, task_id, "IN_PROGRESS")

    assert len(notification_dispatch) == 1
    args, _kwargs = notification_dispatch[0]
    assert args[0] == member_b.id
    assert args[1] == "task_status_changed"


async def test_transition_without_assignees_no_dispatch(client, notification_dispatch):
    admin_a = await _make_user("admin_na", ["admin"])  # admin 持有 task:transition
    member_b = await _make_user("member_na", ["member"])
    project = await _make_project(admin_a, "na")
    await _add_member(project, member_b)
    task_id = await _create_task(client, admin_a, project, "na")

    # 任务无负责人，admin_a 触发流转
    await _transition(client, admin_a, task_id, "IN_PROGRESS")
    assert notification_dispatch == []
