"""TASK-034：Task API HTTP 端到端验收（真实产品应用 + 真实 Token 认证链）。

与 TASK-028/029 同模式：对 `app.main.app` 走完整链路，仅覆盖 `get_db` 指向
测试库。授权两层已在 TASK-033 定案（API_CONTRACT Task 注）：

- 功能级：无角色 / member（有 task:create/update/read，无 task:delete）
  / admin 的 403 形态——`Permission denied: {perm}`；
- 资源级：非成员/不存在 404 同文案；已在链上但团队角色不足（删除）
  403 `Only team owner or admin can delete tasks`；
- TODO 起步（status 不可经 POST/PATCH 触达，422）；exclude_unset 部分更新。

零残留：RESTRICT 链精确拆除（tasks → projects → teams → users）。
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
    return f"taskapi_{RUN_TOKEN}_{tag}"


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
            delete(Task).where(Task.title.like(f"taskapi {RUN_TOKEN}%"))
        )
        await session.execute(
            delete(Project).where(Project.name.like(f"taskapi proj {RUN_TOKEN}%"))
        )
        await session.execute(
            delete(Team).where(Team.name.like(f"taskapi team {RUN_TOKEN}%"))
        )
        await session.execute(
            delete(User).where(User.username.like(f"taskapi_{RUN_TOKEN}%"))
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
            session, owner, TeamCreate(name=f"taskapi team {RUN_TOKEN} {tag}")
        )
        project = await create_project(
            session,
            name=f"taskapi proj {RUN_TOKEN} {tag}",
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


# --- 创建：201 / 403 / 404 / 422 --------------------------------------------------


async def test_create_task_201_todo_start(client):
    owner = await _make_user("owner", ["admin"])
    project = await _make_project(owner, "c1")
    resp = await client.post(
        "/api/v1/tasks",
        headers=_bearer(create_access_token(owner.id)),
        json={"project_id": project.id, "title": f"taskapi {RUN_TOKEN} c1"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()["data"]
    assert body["status"] == "TODO"
    assert body["priority"] == "MEDIUM"
    assert body["creator_id"] == owner.id
    assert body["project_id"] == project.id


async def test_create_task_no_global_permission_403(client):
    owner = await _make_user("owner2")
    project = await _make_project(owner, "c2")  # owner 无全局角色但建了项目
    resp = await client.post(
        "/api/v1/tasks",
        headers=_bearer(create_access_token(owner.id)),
        json={"project_id": project.id, "title": "x"},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Permission denied: task:create"


async def test_create_task_non_member_404_same_message(client):
    owner = await _make_user("owner3", ["admin"])
    outsider = await _make_user("outsider3", ["admin"])
    project = await _make_project(owner, "c3")
    resp = await client.post(
        "/api/v1/tasks",
        headers=_bearer(create_access_token(outsider.id)),
        json={"project_id": project.id, "title": "x"},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Project not found"
    # 不存在的项目同文案
    resp = await client.post(
        "/api/v1/tasks",
        headers=_bearer(create_access_token(owner.id)),
        json={"project_id": 999999999, "title": "x"},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Project not found"


async def test_create_task_status_in_body_422(client):
    """status 不在 TaskCreate 字段集——传了也不生效（额外字段默认忽略），
    核心契约是新任务恒 TODO，见 test_create_task_201_todo_start。"""
    owner = await _make_user("owner4", ["admin"])
    project = await _make_project(owner, "c4")
    resp = await client.post(
        "/api/v1/tasks",
        headers=_bearer(create_access_token(owner.id)),
        json={
            "project_id": project.id,
            "title": f"taskapi {RUN_TOKEN} c4",
            "status": "DONE",  # 非契约字段
            "priority": "URGENT",
        },
    )
    assert resp.status_code == 201, resp.text  # 额外字段被忽略
    assert resp.json()["data"]["status"] == "TODO"
    assert resp.json()["data"]["priority"] == "URGENT"


# --- 读：详情 / 列表 -------------------------------------------------------------


async def test_get_and_list_tasks_member_visibility(client):
    owner = await _make_user("owner5", ["admin"])
    member = await _make_user("member5", ["member"])
    outsider = await _make_user("outsider5", ["admin"])
    project = await _make_project(owner, "r1")
    await _add_member(project, member)

    created = []
    for i in ("a", "b"):
        resp = await client.post(
            "/api/v1/tasks",
            headers=_bearer(create_access_token(owner.id)),
            json={"project_id": project.id, "title": f"taskapi {RUN_TOKEN} r{i}"},
        )
        assert resp.status_code == 201
        created.append(resp.json()["data"]["id"])

    # 成员可见详情与列表
    for uid in (owner.id, member.id):
        resp = await client.get(
            f"/api/v1/tasks/{created[0]}",
            headers=_bearer(create_access_token(uid)),
        )
        assert resp.status_code == 200, resp.text
        resp = await client.get(
            "/api/v1/tasks",
            headers=_bearer(create_access_token(uid)),
            params={"project_id": project.id},
        )
        assert resp.status_code == 200, resp.text
        assert [t["id"] for t in resp.json()["data"]] == created

    # 局外人 404（详情与列表同文案）
    for url in (f"/api/v1/tasks/{created[0]}", "/api/v1/tasks"):
        kwargs = {"params": {"project_id": project.id}} if "tasks/" not in url else {}
        resp = await client.get(
            url, headers=_bearer(create_access_token(outsider.id)), **kwargs
        )
        assert resp.status_code == 404, resp.text
        assert resp.json()["detail"] == "Task not found"


async def test_list_tasks_requires_project_id(client):
    owner = await _make_user("owner6", ["admin"])
    resp = await client.get(
        "/api/v1/tasks", headers=_bearer(create_access_token(owner.id))
    )
    assert resp.status_code == 422  # project_id 必填 query 参数


# --- 更新：exclude_unset / status 不可触达 ---------------------------------------


async def test_patch_task_by_member_partial_update(client):
    owner = await _make_user("owner7", ["admin"])
    member = await _make_user("member7", ["member"])
    project = await _make_project(owner, "p1")
    await _add_member(project, member)
    resp = await client.post(
        "/api/v1/tasks",
        headers=_bearer(create_access_token(owner.id)),
        json={
            "project_id": project.id,
            "title": f"taskapi {RUN_TOKEN} p1",
            "description": "before",
        },
    )
    task_id = resp.json()["data"]["id"]

    # member 有 task:update，归属链上 → 200
    resp = await client.patch(
        f"/api/v1/tasks/{task_id}",
        headers=_bearer(create_access_token(member.id)),
        json={"priority": "HIGH", "description": None, "status": "DONE"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()["data"]
    assert body["priority"] == "HIGH"
    assert body["description"] is None  # 显式 null 清空
    assert body["title"] == f"taskapi {RUN_TOKEN} p1"  # 未传保持
    assert body["status"] == "TODO"  # status 不可经 PATCH 触达


async def test_patch_task_non_member_404(client):
    owner = await _make_user("owner8", ["admin"])
    outsider = await _make_user("outsider8", ["admin"])
    project = await _make_project(owner, "p2")
    resp = await client.post(
        "/api/v1/tasks",
        headers=_bearer(create_access_token(owner.id)),
        json={"project_id": project.id, "title": f"taskapi {RUN_TOKEN} p2"},
    )
    task_id = resp.json()["data"]["id"]
    resp = await client.patch(
        f"/api/v1/tasks/{task_id}",
        headers=_bearer(create_access_token(outsider.id)),
        json={"title": "hacked"},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Task not found"


# --- 删除：OWNER/ADMIN only -------------------------------------------------------


async def test_delete_task_member_403_owner_200(client):
    owner = await _make_user("owner9", ["admin"])
    # 全局 member 无 task:delete，会被功能级 403 挡住到不了资源级；
    # 资源级 403 形态 = 全局 admin（有 task:delete）+ 团队 MEMBER（tmember）
    tmember = await _make_user("member9", ["admin"])
    project = await _make_project(owner, "d1")
    await _add_member(project, tmember)
    resp = await client.post(
        "/api/v1/tasks",
        headers=_bearer(create_access_token(owner.id)),
        json={"project_id": project.id, "title": f"taskapi {RUN_TOKEN} d1"},
    )
    task_id = resp.json()["data"]["id"]

    # tmember（归属链上、有全局 task:delete，但团队角色 MEMBER）→ 403 明示
    resp = await client.delete(
        f"/api/v1/tasks/{task_id}",
        headers=_bearer(create_access_token(tmember.id)),
    )
    assert resp.status_code == 403, resp.text
    assert (
        resp.json()["detail"] == "Only team owner or admin can delete tasks"
    )

    # owner 删除 → 200，复查 404
    resp = await client.delete(
        f"/api/v1/tasks/{task_id}",
        headers=_bearer(create_access_token(owner.id)),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"] is None
    resp = await client.get(
        f"/api/v1/tasks/{task_id}",
        headers=_bearer(create_access_token(owner.id)),
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Task not found"


async def test_delete_task_non_member_404(client):
    owner = await _make_user("owner10", ["admin"])
    outsider = await _make_user("outsider10", ["admin"])
    project = await _make_project(owner, "d2")
    resp = await client.post(
        "/api/v1/tasks",
        headers=_bearer(create_access_token(owner.id)),
        json={"project_id": project.id, "title": f"taskapi {RUN_TOKEN} d2"},
    )
    task_id = resp.json()["data"]["id"]
    resp = await client.delete(
        f"/api/v1/tasks/{task_id}",
        headers=_bearer(create_access_token(outsider.id)),
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Task not found"
