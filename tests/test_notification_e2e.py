"""TASK-055：通知端到端测试（Phase 9 收尾，纯测试任务，未改应用代码）.

TASK-053 的 ``test_notification_api.py`` 用 ``_isolate_notification_dispatch``
（conftest autouse，把 ``_dispatch_notification`` 换 no-op）+ ``notification_dispatch``
间谍夹具**只验证接线**——派发不真连 broker，通知行从不被真实写出。

TASK-055 的定位是 **端到端整合验收**：恢复真实派发，让一次真实的 API 动作
（任务分配 / 状态变更）真的把通知写进收件箱，再走真实端点
（`GET /notifications` / ``PATCH .../read`` / ``PATCH /read-all``）验证
「动作 → 入库 → 可见 → 可读 → 全部已读」整条链路，且不影响他人。

## 为什么用独立线程跑真实任务体（而非 Celery eager）

通知任务（``app.tasks.notification_tasks.create_notification``）体内用
``asyncio.run`` 写库。若直接在本测试的 async event loop 调用栈里跑
``.delay()``（eager），会触发 ``RuntimeError: asyncio.run() cannot be called
from a running event loop``。生产里 Worker 是独立进程（独立 loop），这里用
**守护线程**等价模拟：任务在独立线程内跑自己的 loop，不干扰测试 loop，且仍
执行真实的入库 + Redis 幂等标记逻辑（与 TASK-049 直接调任务体验证 §24 一致）。
任务注册 / 接线已由 TASK-049/051/053 覆盖，本文件只关心「通知真的进收件箱」。

## 覆盖范围
- 任务分配 → 被分派者收件箱出现 ``task_assigned``，自领不产生通知；
- 任务状态变更 → 全部负责人收到 ``task_status_changed``、排除触发者本人；
- 真实写入的通知可用单条 ``PATCH .../read`` 标记已读；
- 真实多通知下 ``PATCH /read-all`` 返回正确 ``marked`` 且收件箱全已读；
- 通知 title/content 由派发方按 §18 场景填充；
- 收件箱资源级隔离（他人通知不可见）。

零残留：用户（含其通知 FK CASCADE）按 ``ntfe2e_<RUN_TOKEN>_`` 前缀精确清理。
"""

import threading
import uuid

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
from app.models.project import Project
from app.models.task import Task
from app.models.team import Team
from app.models.user import User
from app.services import task as task_service
from app.tasks import notification_tasks

TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@127.0.0.1:5433/taskflow"

RUN_TOKEN = uuid.uuid4().hex[:10]
PASSWORD_HASH = "h"

engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
SessionFactory = async_sessionmaker(engine, expire_on_commit=False)


async def _override_get_db():
    async with SessionFactory() as session:
        yield session


def _username(tag: str) -> str:
    return f"ntfe2e_{RUN_TOKEN}_{tag}"


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
        await session.execute(
            delete(Task).where(Task.title.like(f"ntfe2e {RUN_TOKEN}%"))
        )
        await session.execute(
            delete(Project).where(Project.name.like(f"ntfe2e proj {RUN_TOKEN}%"))
        )
        await session.execute(
            delete(Team).where(Team.name.like(f"ntfe2e team {RUN_TOKEN}%"))
        )
        await session.execute(
            delete(User).where(User.username.like(f"ntfe2e_{RUN_TOKEN}%"))
        )
        await session.commit()


@pytest.fixture
def real_notification_dispatch(monkeypatch):
    """TASK-055 端到端：恢复真实派发（覆盖 conftest 的 autouse no-op）。

    用独立线程跑真实任务体（见模块 docstring 的「running loop」约束说明），
    等价模拟 Worker 进程，写库后 join 确保通知已落库再返回（确定性）。
    """

    def _dispatch(*args, **kwargs):
        def _run():
            notification_tasks.create_notification(*args, **kwargs)

        t = threading.Thread(target=_run)
        t.start()
        t.join()

    monkeypatch.setattr(task_service, "_dispatch_notification", _dispatch)
    yield


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


async def _make_project(owner: User, tag: str) -> Project:
    from app.crud.project import create_project
    from app.schemas.team import TeamCreate
    from app.services.team import create_team as create_team_service

    async with SessionFactory() as session:
        team = await create_team_service(
            session, owner, TeamCreate(name=f"ntfe2e team {RUN_TOKEN} {tag}")
        )
        project = await create_project(
            session,
            name=f"ntfe2e proj {RUN_TOKEN} {tag}",
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
        json={"project_id": project.id, "title": f"ntfe2e {RUN_TOKEN} {tag}"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]["id"]


async def _assign(client, actor: User, task_id: int, target_user_id: int) -> None:
    resp = await client.post(
        f"/api/v1/tasks/{task_id}/assignees",
        headers=_bearer(create_access_token(actor.id)),
        json={"user_id": target_user_id},
    )
    assert resp.status_code == 201, resp.text


async def _transition(client, actor: User, task_id: int, to: str) -> None:
    resp = await client.post(
        f"/api/v1/tasks/{task_id}/transition",
        headers=_bearer(create_access_token(actor.id)),
        json={"to_status": to},
    )
    assert resp.status_code == 200, resp.text


async def _list_inbox(client, user: User) -> list[dict]:
    resp = await client.get(
        "/api/v1/notifications", headers=_bearer(create_access_token(user.id))
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


# --- 端到端：动作 → 入库 → 收件箱可见 -----------------------------------------


async def test_assign_creates_inbox_notification_e2e(client, real_notification_dispatch):
    admin = await _make_user("a", ["admin"])
    member = await _make_user("m", ["member"])
    project = await _make_project(admin, "d1")
    await _add_member(project, member)
    task_id = await _create_task(client, admin, project, "d1")

    await _assign(client, admin, task_id, member.id)

    inbox = await _list_inbox(client, member)
    assert len(inbox) == 1
    n = inbox[0]
    assert n["user_id"] == member.id
    assert n["type"] == "task_assigned"
    assert n["is_read"] is False
    assert "d1" in n["title"]  # §18 场景：标题含任务摘要


async def test_self_assign_does_not_create_notification_e2e(
    client, real_notification_dispatch
):
    admin = await _make_user("sa", ["admin"])
    project = await _make_project(admin, "sa")
    task_id = await _create_task(client, admin, project, "sa")

    await _assign(client, admin, task_id, admin.id)  # 自领

    inbox = await _list_inbox(client, admin)
    assert inbox == []  # 自领不产生通知（与 TASK-053 决策一致）


async def test_transition_notifies_assignees_excluding_actor_e2e(
    client, real_notification_dispatch
):
    admin = await _make_user("ta", ["admin"])  # 持有 task:transition
    member = await _make_user("tm", ["member"])
    project = await _make_project(admin, "ta")
    await _add_member(project, member)
    task_id = await _create_task(client, admin, project, "ta")
    # 双方都是负责人：admin 自领（无通知）+ admin 分派 member（member 收 task_assigned）
    await _assign(client, admin, task_id, admin.id)
    await _assign(client, admin, task_id, member.id)

    # admin 触发状态变更
    await _transition(client, admin, task_id, "IN_PROGRESS")

    # 被通知人 member：应收到 1 条 task_status_changed（外加早前的 1 条 task_assigned）
    member_inbox = await _list_inbox(client, member)
    assert any(
        n["type"] == "task_status_changed" for n in member_inbox
    ), "成员应收到状态变更通知"
    # 触发者 admin：自领无通知 + 状态变更排除自己 → 收件箱为空
    admin_inbox = await _list_inbox(client, admin)
    assert admin_inbox == [], "触发者本人不应收到自己触发的状态变更通知"


# --- 端到端：真实写入的通知可读 / 全部已读 -----------------------------------


async def test_mark_read_e2e(client, real_notification_dispatch):
    admin = await _make_user("mr", ["admin"])
    member = await _make_user("mm", ["member"])
    project = await _make_project(admin, "mr")
    await _add_member(project, member)
    task_id = await _create_task(client, admin, project, "mr")

    await _assign(client, admin, task_id, member.id)

    inbox = await _list_inbox(client, member)
    nid = inbox[0]["id"]
    assert inbox[0]["is_read"] is False

    resp = await client.patch(
        f"/api/v1/notifications/{nid}/read",
        headers=_bearer(create_access_token(member.id)),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["is_read"] is True

    inbox = await _list_inbox(client, member)
    assert inbox[0]["is_read"] is True


async def test_read_all_e2e(client, real_notification_dispatch):
    admin = await _make_user("ra", ["admin"])
    member = await _make_user("rm", ["member"])
    project = await _make_project(admin, "ra")
    await _add_member(project, member)

    # 三个不同任务都分派给 member → 3 条真实 task_assigned 通知
    for i in range(3):
        task_id = await _create_task(client, admin, project, f"ra-{i}")
        await _assign(client, admin, task_id, member.id)

    assert len(await _list_inbox(client, member)) == 3

    resp = await client.patch(
        "/api/v1/notifications/read-all",
        headers=_bearer(create_access_token(member.id)),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["marked"] == 3

    inbox = await _list_inbox(client, member)
    assert len(inbox) == 3
    assert all(n["is_read"] is True for n in inbox)


# --- 端到端：通知内容 + 资源级隔离 -------------------------------------------


async def test_notification_title_and_content_e2e(client, real_notification_dispatch):
    admin = await _make_user("c", ["admin"])
    member = await _make_user("cm", ["member"])
    project = await _make_project(admin, "c")
    await _add_member(project, member)
    task_id = await _create_task(client, admin, project, "c")

    await _assign(client, admin, task_id, member.id)

    n = (await _list_inbox(client, member))[0]
    # 派发方按 §18 场景填充 title/content（见 task_service.assign_task）
    assert n["title"] == f"你被分配到任务「ntfe2e {RUN_TOKEN} c」"
    assert n["content"] == f"{admin.username} 将你分配到任务 #{task_id}"


async def test_inbox_isolation_across_users_e2e(client, real_notification_dispatch):
    admin = await _make_user("iso_a", ["admin"])
    member_b = await _make_user("iso_b", ["member"])
    outsider = await _make_user("iso_o", ["member"])
    project = await _make_project(admin, "iso")
    await _add_member(project, member_b)
    task_id = await _create_task(client, admin, project, "iso")

    await _assign(client, admin, task_id, member_b.id)  # 只通知 member_b

    # 局外人收件箱为空——通知不泄露给非接收人
    assert await _list_inbox(client, outsider) == []
    # 持有者能看到自己的
    assert len(await _list_inbox(client, member_b)) == 1
