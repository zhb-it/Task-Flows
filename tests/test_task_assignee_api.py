"""TASK-036：TaskAssignee 多人分配 HTTP 端到端验收。

沿用 test_task_api.py / test_task_query_api.py 模式：真实产品应用 +
真实 Token 认证链，仅覆盖 `get_db` 指向测试库。TASK-036 用户确认决策：

- 分配/移除授权 = 功能级 task:update + 归属链上团队成员即可（协作式，
  可自领；分配是更新行为，不新增 seed 权限项）；
- 目标用户不存在或非任务所属团队成员 → 404 `User not found` 同文案
  （防枚举）；目标已是负责人 → 409；目标非该任务负责人 → 404
  `Assignee not found`；任务不在归属链 → 404 `Task not found`；
- TaskRead.assignees 内嵌 [{user_id, username, assigned_at}]；
- GET /tasks 增 assignee_id 可选过滤。

零残留：RESTRICT 链精确拆除（task_assignees → tasks → projects →
teams → users；assignee 行随任务/用户 FK CASCADE，显式兜底删除）。
"""

import uuid

import pytest
import pytest_asyncio
from fastapi import status
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

TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@127.0.0.1:5433/taskflow"

RUN_TOKEN = uuid.uuid4().hex[:10]
PASSWORD_HASH = "h"

engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
SessionFactory = async_sessionmaker(engine, expire_on_commit=False)


async def _override_get_db():
    async with SessionFactory() as session:
        yield session


def _username(tag: str) -> str:
    return f"tskasg_{RUN_TOKEN}_{tag}"


def _title(tag: str) -> str:
    return f"tskasg {RUN_TOKEN} {tag}"


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
            delete(Task).where(Task.title.like(f"tskasg {RUN_TOKEN}%"))
        )
        await session.execute(
            delete(Project).where(Project.name.like(f"tskasg proj {RUN_TOKEN}%"))
        )
        await session.execute(
            delete(Team).where(Team.name.like(f"tskasg team {RUN_TOKEN}%"))
        )
        await session.execute(
            delete(User).where(User.username.like(f"tskasg_{RUN_TOKEN}%"))
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


async def _make_project(owner: User, tag: str) -> Project:
    """service 层建 team（写 OWNER 成员行）+ crud 建 project。"""
    from app.crud.project import create_project
    from app.schemas.team import TeamCreate
    from app.services.team import create_team as create_team_service

    async with SessionFactory() as session:
        team = await create_team_service(
            session, owner, TeamCreate(name=f"tskasg team {RUN_TOKEN} {tag}")
        )
        project = await create_project(
            session,
            name=f"tskasg proj {RUN_TOKEN} {tag}",
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


async def _api_create_task(client, owner: User, project: Project, tag: str) -> int:
    resp = await client.post(
        "/api/v1/tasks",
        headers=_bearer(create_access_token(owner.id)),
        json={"project_id": project.id, "title": _title(tag)},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()["data"]
    assert body["assignees"] == []  # 新任务恒无负责人（内嵌字段稳定为空列表）
    return body["id"]


# --- 分配：201 / 403 / 404 / 409 -------------------------------------------------


async def test_assign_member_201_and_embedded_in_read_and_list(client):
    owner = await _make_user("o1", ["admin"])
    member = await _make_user("m1", ["member"])
    project = await _make_project(owner, "a1")
    await _add_member(project, member)
    task_id = await _api_create_task(client, owner, project, "a1")

    resp = await client.post(
        f"/api/v1/tasks/{task_id}/assignees",
        headers=_bearer(create_access_token(owner.id)),
        json={"user_id": member.id},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()["data"]
    assert body["user_id"] == member.id
    assert body["username"] == _username("m1")
    assert body["assigned_at"] is not None

    # 详情内嵌
    resp = await client.get(
        f"/api/v1/tasks/{task_id}", headers=_bearer(create_access_token(owner.id))
    )
    got = resp.json()["data"]["assignees"]
    assert [a["user_id"] for a in got] == [member.id]

    # 列表内嵌
    resp = await client.get(
        "/api/v1/tasks",
        headers=_bearer(create_access_token(member.id)),
        params={"project_id": project.id},
    )
    got = resp.json()["data"][0]["assignees"]
    assert [a["user_id"] for a in got] == [member.id]
    assert got[0]["username"] == _username("m1")


async def test_member_can_assign_and_self_assign(client):
    """协作式分配：归属链成员可分配他人，也可自领。"""
    owner = await _make_user("o2", ["admin"])
    member = await _make_user("m2", ["member"])
    project = await _make_project(owner, "a2")
    await _add_member(project, member)
    task_a = await _api_create_task(client, owner, project, "a2a")
    task_b = await _api_create_task(client, owner, project, "a2b")

    # member 分配 owner（团队成员）→ 201
    resp = await client.post(
        f"/api/v1/tasks/{task_a}/assignees",
        headers=_bearer(create_access_token(member.id)),
        json={"user_id": owner.id},
    )
    assert resp.status_code == 201, resp.text

    # member 自领 → 201
    resp = await client.post(
        f"/api/v1/tasks/{task_b}/assignees",
        headers=_bearer(create_access_token(member.id)),
        json={"user_id": member.id},
    )
    assert resp.status_code == 201, resp.text


async def test_assign_duplicate_409(client):
    owner = await _make_user("o3", ["admin"])
    member = await _make_user("m3", ["member"])
    project = await _make_project(owner, "a3")
    await _add_member(project, member)
    task_id = await _api_create_task(client, owner, project, "a3")
    headers = _bearer(create_access_token(owner.id))
    payload = {"user_id": member.id}

    resp = await client.post(
        f"/api/v1/tasks/{task_id}/assignees", headers=headers, json=payload
    )
    assert resp.status_code == 201, resp.text
    resp = await client.post(
        f"/api/v1/tasks/{task_id}/assignees", headers=headers, json=payload
    )
    assert resp.status_code == 409, resp.text
    assert resp.json()["detail"] == "User already assigned to this task"


async def test_assign_target_unknown_or_non_member_404_same_message(client):
    owner = await _make_user("o4", ["admin"])
    member = await _make_user("m4", ["member"])
    outsider = await _make_user("x4", ["admin"])  # 有身份但不在团队
    project = await _make_project(owner, "a4")
    await _add_member(project, member)
    task_id = await _api_create_task(client, owner, project, "a4")
    headers = _bearer(create_access_token(owner.id))

    # 不存在的用户 & 非团队成员用户 → 404 同文案（防枚举）
    for bad_id in (999999999, outsider.id):
        resp = await client.post(
            f"/api/v1/tasks/{task_id}/assignees",
            headers=headers,
            json={"user_id": bad_id},
        )
        assert resp.status_code == 404, resp.text
        assert resp.json()["detail"] == "User not found"


async def test_assign_task_off_chain_404_and_no_permission_403(client):
    insider = await _make_user("o5", ["admin"])
    norole = await _make_user("n5")  # 无任何全局角色 → 功能级 403
    outsider = await _make_user("x5", ["admin"])  # 有全局权限但不在团队
    project = await _make_project(insider, "a5")
    task_id = await _api_create_task(client, insider, project, "a5")

    # 无全局 task:update → 403（功能级先挡）
    resp = await client.post(
        f"/api/v1/tasks/{task_id}/assignees",
        headers=_bearer(create_access_token(norole.id)),
        json={"user_id": insider.id},
    )
    assert resp.status_code == 403, resp.text
    assert resp.json()["detail"] == "Permission denied: task:update"

    # 有全局权限但任务不在归属链 → 404 Task not found（IDOR）
    resp = await client.post(
        f"/api/v1/tasks/{task_id}/assignees",
        headers=_bearer(create_access_token(outsider.id)),
        json={"user_id": insider.id},
    )
    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"] == "Task not found"


# --- 移除：200 / 404 -------------------------------------------------------------


async def test_unassign_200_then_404(client):
    owner = await _make_user("o6", ["admin"])
    member = await _make_user("m6", ["member"])
    project = await _make_project(owner, "u1")
    await _add_member(project, member)
    task_id = await _api_create_task(client, owner, project, "u1")
    headers = _bearer(create_access_token(owner.id))

    resp = await client.post(
        f"/api/v1/tasks/{task_id}/assignees", headers=headers, json={"user_id": member.id}
    )
    assert resp.status_code == 201

    # member 也可移除（协作式）
    resp = await client.delete(
        f"/api/v1/tasks/{task_id}/assignees/{member.id}",
        headers=_bearer(create_access_token(member.id)),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"] is None

    # 移除后详情内嵌为空
    resp = await client.get(
        f"/api/v1/tasks/{task_id}", headers=_bearer(create_access_token(owner.id))
    )
    assert resp.json()["data"]["assignees"] == []

    # 再移除 → 404 Assignee not found
    resp = await client.delete(
        f"/api/v1/tasks/{task_id}/assignees/{member.id}", headers=headers
    )
    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"] == "Assignee not found"

    # 从未分配过的目标移除 → 同 404
    resp = await client.delete(
        f"/api/v1/tasks/{task_id}/assignees/{999999999}", headers=headers
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Assignee not found"


# --- assignee_id 负责人筛选 -------------------------------------------------------


async def test_list_filter_by_assignee_id(client):
    owner = await _make_user("o7", ["admin"])
    member = await _make_user("m7", ["member"])
    project = await _make_project(owner, "f1")
    await _add_member(project, member)
    task_a = await _api_create_task(client, owner, project, "f1a")
    task_b = await _api_create_task(client, owner, project, "f1b")
    headers = _bearer(create_access_token(owner.id))

    # 未分配时过滤任何人 → 空
    resp = await client.get(
        "/api/v1/tasks",
        headers=headers,
        params={"project_id": project.id, "assignee_id": member.id},
    )
    assert resp.status_code == 200
    assert resp.json()["data"] == []

    # 分配 task_a 给 member → 只命中 a
    resp = await client.post(
        f"/api/v1/tasks/{task_a}/assignees", headers=headers, json={"user_id": member.id}
    )
    assert resp.status_code == 201
    resp = await client.get(
        "/api/v1/tasks",
        headers=headers,
        params={"project_id": project.id, "assignee_id": member.id},
    )
    assert [t["id"] for t in resp.json()["data"]] == [task_a]

    # task_b 分配 owner → member 过滤仍只 a；不过滤则两条
    resp = await client.post(
        f"/api/v1/tasks/{task_b}/assignees", headers=headers, json={"user_id": owner.id}
    )
    assert resp.status_code == 201
    resp = await client.get(
        "/api/v1/tasks",
        headers=headers,
        params={"project_id": project.id, "assignee_id": member.id},
    )
    assert [t["id"] for t in resp.json()["data"]] == [task_a]
    resp = await client.get(
        "/api/v1/tasks", headers=headers, params={"project_id": project.id}
    )
    assert len(resp.json()["data"]) == 2

    # 移除后过滤 → 空
    resp = await client.delete(
        f"/api/v1/tasks/{task_a}/assignees/{member.id}", headers=headers
    )
    assert resp.status_code == 200
    resp = await client.get(
        "/api/v1/tasks",
        headers=headers,
        params={"project_id": project.id, "assignee_id": member.id},
    )
    assert resp.json()["data"] == []


# --- 级联与多负责人 ---------------------------------------------------------------


async def test_multiple_assignees_and_task_delete_cascade(client):
    owner = await _make_user("o8", ["admin"])
    member = await _make_user("m8", ["member"])
    project = await _make_project(owner, "c1")
    await _add_member(project, member)
    task_id = await _api_create_task(client, owner, project, "c1")
    headers = _bearer(create_access_token(owner.id))

    for uid in (owner.id, member.id):
        resp = await client.post(
            f"/api/v1/tasks/{task_id}/assignees", headers=headers, json={"user_id": uid}
        )
        assert resp.status_code == 201, resp.text

    resp = await client.get(
        f"/api/v1/tasks/{task_id}", headers=_bearer(create_access_token(owner.id))
    )
    assert {a["user_id"] for a in resp.json()["data"]["assignees"]} == {
        owner.id,
        member.id,
    }

    # 删任务 → task_assignees 行随 FK CASCADE 清理（直查库实证）
    resp = await client.delete(f"/api/v1/tasks/{task_id}", headers=headers)
    assert resp.status_code == 200

    from app.models.task_assignee import TaskAssignee
    from sqlalchemy import select

    async with SessionFactory() as session:
        rows = (
            (await session.execute(select(TaskAssignee).where(TaskAssignee.task_id == task_id)))
            .scalars()
            .all()
        )
        assert rows == []  # 级联清理实证
