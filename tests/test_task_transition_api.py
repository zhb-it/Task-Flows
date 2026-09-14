"""TASK-038：Transition API HTTP 端到端验收（真实产品应用 + 真实 Token 认证链）。

与 test_task_api.py 同模式：对 `app.main.app` 走完整链路，仅覆盖 `get_db`
指向测试库。规格 §11 / §55.3 + TASK-037 状态机决策 + TASK-038 用户确认决策：

- 请求体 `{"to_status": "<状态>"}`（决策 1）；
- 功能级 `task:transition`（种子仅 admin 持有，member 403）+ 资源级
  **任务所属团队成员即可**（决策 2，协作式，与更新/分配同语义）；
- 合法流转 200 并返回更新后的 TaskRead（含 assignees 内嵌）；
- 非法流转——相邻回退 / 跨级跳转 / 终态（DONE/CANCELLED）任何出边 /
  同状态重复流转——→ 409 `Invalid status transition`，且任务状态不被改动；
- 不在归属链 / 不存在 → 404 同文案（IDOR 防枚举）。

零残留：RESTRICT 链精确拆除（tasks → projects → teams → users）。
"""

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

TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@127.0.0.1:5433/taskflow"

RUN_TOKEN = uuid.uuid4().hex[:10]
PASSWORD_HASH = "h"

engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
SessionFactory = async_sessionmaker(engine, expire_on_commit=False)


async def _override_get_db():
    async with SessionFactory() as session:
        yield session


def _username(tag: str) -> str:
    return f"tasktrans_{RUN_TOKEN}_{tag}"


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
            delete(Task).where(Task.title.like(f"tasktrans {RUN_TOKEN}%"))
        )
        await session.execute(
            delete(Project).where(Project.name.like(f"tasktrans proj {RUN_TOKEN}%"))
        )
        await session.execute(
            delete(Team).where(Team.name.like(f"tasktrans team {RUN_TOKEN}%"))
        )
        await session.execute(
            delete(User).where(User.username.like(f"tasktrans_{RUN_TOKEN}%"))
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
            session, owner, TeamCreate(name=f"tasktrans team {RUN_TOKEN} {tag}")
        )
        project = await create_project(
            session,
            name=f"tasktrans proj {RUN_TOKEN} {tag}",
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
        json={"project_id": project.id, "title": f"tasktrans {RUN_TOKEN} {tag}"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]["id"]


#: 从 TODO 出发走到目标状态的合法路径（经 transition API 真实驱动）。
_PATHS = {
    "TODO": [],
    "IN_PROGRESS": ["IN_PROGRESS"],
    "REVIEW": ["IN_PROGRESS", "REVIEW"],
    "DONE": ["IN_PROGRESS", "REVIEW", "DONE"],
    "CANCELLED": ["CANCELLED"],
}


async def _drive_to(client, owner: User, task_id: int, target: str) -> None:
    for step in _PATHS[target]:
        resp = await client.post(
            f"/api/v1/tasks/{task_id}/transition",
            headers=_bearer(create_access_token(owner.id)),
            json={"to_status": step},
        )
        assert resp.status_code == 200, resp.text


# --- 合法流转：前进链 / →CANCELLED ----------------------------------------------


async def test_transition_forward_chain_200(client):
    owner = await _make_user("owner1", ["admin"])
    project = await _make_project(owner, "f1")
    task_id = await _create_task(client, owner, project, "f1")

    for step in ("IN_PROGRESS", "REVIEW", "DONE"):
        resp = await client.post(
            f"/api/v1/tasks/{task_id}/transition",
            headers=_bearer(create_access_token(owner.id)),
            json={"to_status": step},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()["data"]
        assert body["id"] == task_id
        assert body["status"] == step
        assert body["assignees"] == []  # 内嵌字段恒存在

    # 流转持久化：GET 复查为 DONE
    resp = await client.get(
        f"/api/v1/tasks/{task_id}",
        headers=_bearer(create_access_token(owner.id)),
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "DONE"


async def test_transition_to_cancelled_from_every_non_terminal(client):
    for start, tag in (("TODO", "c1"), ("IN_PROGRESS", "c2"), ("REVIEW", "c3")):
        owner = await _make_user(f"owner_c_{tag}", ["admin"])
        project = await _make_project(owner, f"c_{tag}")
        task_id = await _create_task(client, owner, project, f"c_{tag}")
        await _drive_to(client, owner, task_id, start)

        resp = await client.post(
            f"/api/v1/tasks/{task_id}/transition",
            headers=_bearer(create_access_token(owner.id)),
            json={"to_status": "CANCELLED"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["status"] == "CANCELLED"


# --- 非法流转：409 且状态不变 -----------------------------------------------------


async def test_transition_illegal_targets_409_and_status_unchanged(client):
    owner = await _make_user("owner2", ["admin"])
    project = await _make_project(owner, "i1")

    illegal_pairs = [
        ("TODO", "TODO"),  # 同状态重复流转
        ("TODO", "REVIEW"),  # 跨级
        ("TODO", "DONE"),  # 跨级
        ("IN_PROGRESS", "TODO"),  # 回退
        ("IN_PROGRESS", "DONE"),  # 跨级
        ("REVIEW", "TODO"),  # 跨级
        ("REVIEW", "IN_PROGRESS"),  # 回退
        ("DONE", "IN_PROGRESS"),  # 终态出边
        ("DONE", "CANCELLED"),  # 终态出边
        ("CANCELLED", "TODO"),  # 终态出边
        ("CANCELLED", "CANCELLED"),  # 终态 + 同状态
    ]
    for i, (start, target) in enumerate(illegal_pairs):
        task_id = await _create_task(client, owner, project, f"i1_{i}")
        await _drive_to(client, owner, task_id, start)

        resp = await client.post(
            f"/api/v1/tasks/{task_id}/transition",
            headers=_bearer(create_access_token(owner.id)),
            json={"to_status": target},
        )
        assert resp.status_code == 409, f"{start}->{target}: {resp.text}"
        assert resp.json()["detail"] == "Invalid status transition"

        # 被拒绝的流转不改动状态
        resp = await client.get(
            f"/api/v1/tasks/{task_id}",
            headers=_bearer(create_access_token(owner.id)),
        )
        assert resp.json()["data"]["status"] == start, f"{start}->{target}"


# --- 请求体校验：422 ---------------------------------------------------------------


async def test_transition_request_validation_422(client):
    owner = await _make_user("owner3", ["admin"])
    project = await _make_project(owner, "v1")
    task_id = await _create_task(client, owner, project, "v1")
    headers = _bearer(create_access_token(owner.id))

    for payload, desc in (
        ({"to_status": "PAUSED"}, "非法状态值"),
        ({}, "缺字段"),
        ({"to_status": None}, "null"),
    ):
        resp = await client.post(
            f"/api/v1/tasks/{task_id}/transition", headers=headers, json=payload
        )
        assert resp.status_code == 422, f"{desc}: {resp.text}"


# --- 功能级权限：403 ---------------------------------------------------------------


async def test_transition_missing_permission_403(client):
    owner = await _make_user("owner4", ["admin"])
    member = await _make_user("member4", ["member"])  # 有 task:update，无 task:transition
    norole = await _make_user("norole4")  # 无任何角色
    project = await _make_project(owner, "p1")
    await _add_member(project, member)
    await _add_member(project, norole)
    task_id = await _create_task(client, owner, project, "p1")

    for user, tag in ((member, "member"), (norole, "no-role")):
        resp = await client.post(
            f"/api/v1/tasks/{task_id}/transition",
            headers=_bearer(create_access_token(user.id)),
            json={"to_status": "IN_PROGRESS"},
        )
        assert resp.status_code == 403, f"{tag}: {resp.text}"
        assert resp.json()["detail"] == "Permission denied: task:transition"


# --- 资源级：404 防枚举 / 团队成员协作式流转 ----------------------------------------


async def test_transition_outsider_and_nonexistent_404(client):
    owner = await _make_user("owner5", ["admin"])
    outsider = await _make_user("outsider5", ["admin"])
    project = await _make_project(owner, "r1")
    task_id = await _create_task(client, owner, project, "r1")

    for tid, tag in ((task_id, "他人任务"), (999999999, "不存在")):
        resp = await client.post(
            f"/api/v1/tasks/{tid}/transition",
            headers=_bearer(create_access_token(outsider.id)),
            json={"to_status": "IN_PROGRESS"},
        )
        assert resp.status_code == 404, f"{tag}: {resp.text}"
        assert resp.json()["detail"] == "Task not found"


async def test_transition_by_team_member_200(client):
    """决策 2：资源级团队成员即可——全局 admin + 团队 MEMBER（非 owner）可流转。"""
    owner = await _make_user("owner6", ["admin"])
    tmember = await _make_user("tmember6", ["admin"])
    project = await _make_project(owner, "m1")
    await _add_member(project, tmember)
    task_id = await _create_task(client, owner, project, "m1")

    resp = await client.post(
        f"/api/v1/tasks/{task_id}/transition",
        headers=_bearer(create_access_token(tmember.id)),
        json={"to_status": "IN_PROGRESS"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["status"] == "IN_PROGRESS"
