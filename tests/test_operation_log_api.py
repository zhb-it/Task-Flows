"""TASK-039：OperationLog 审计查询 HTTP 端到端验收（真实产品应用 + 真实 Token）。

与 test_task_transition_api.py 同模式：对 `app.main.app` 走完整链路，仅覆盖
`get_db` 指向测试库。规格 §15 + TASK-039 用户确认决策：

- transition 动作自动写入审计日志（action=task:transition，payload=
  {old_status, new_status}），与业务同事务；
- `GET /logs` 仅返回 **当前用户自己** 的日志（资源级隔离，最小暴露面）；
- `GET /logs/{type}/{id}` 须验证调用者对资源的归属权限（task：团队链），
  非成员 → 404（IDOR 防枚举），非 task 资源类型 → 404（暂不支持）；
- 功能级 `log:read`（种子 admin 与 member 均持有，无角色用户 403）。

零残留：RESTRICT 链精确拆除 + 审计日志（user_id 无 FK，须显式清）。
"""

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.security import create_access_token
from app.crud.role import assign_role_to_user, get_role_by_name
from app.crud.user import create_user
from app.db.session import get_db
from app.main import app
from app.models.operation_log import OperationLog
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
    return f"oplog_{RUN_TOKEN}_{tag}"


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
        # user_id 无 FK：先清审计日志（按本批用户名），再清资源链。
        await session.execute(
            delete(OperationLog).where(
                OperationLog.user_id.in_(
                    select(User.id).where(User.username.like(f"oplog_{RUN_TOKEN}%"))
                )
            )
        )
        await session.execute(
            delete(Task).where(Task.title.like(f"oplog {RUN_TOKEN}%"))
        )
        await session.execute(
            delete(Project).where(Project.name.like(f"oplog proj {RUN_TOKEN}%"))
        )
        await session.execute(
            delete(Team).where(Team.name.like(f"oplog team {RUN_TOKEN}%"))
        )
        await session.execute(
            delete(User).where(User.username.like(f"oplog_{RUN_TOKEN}%"))
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
    from app.crud.project import create_project
    from app.schemas.team import TeamCreate
    from app.services.team import create_team as create_team_service

    async with SessionFactory() as session:
        team = await create_team_service(
            session, owner, TeamCreate(name=f"oplog team {RUN_TOKEN} {tag}")
        )
        project = await create_project(
            session,
            name=f"oplog proj {RUN_TOKEN} {tag}",
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
        json={"project_id": project.id, "title": f"oplog {RUN_TOKEN} {tag}"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]["id"]


async def _transition(client, user: User, task_id: int, to: str) -> int:
    resp = await client.post(
        f"/api/v1/tasks/{task_id}/transition",
        headers=_bearer(create_access_token(user.id)),
        json={"to_status": to},
    )
    assert resp.status_code == 200, resp.text
    return resp.status_code


# --- transition 埋点 + GET /logs ----------------------------------------------


async def test_transition_writes_log_and_get_logs_returns_it(client):
    owner = await _make_user("owner1", ["admin"])
    project = await _make_project(owner, "f1")
    task_id = await _create_task(client, owner, project, "f1")

    await _transition(client, owner, task_id, "IN_PROGRESS")

    resp = await client.get(
        "/api/v1/logs", headers=_bearer(create_access_token(owner.id))
    )
    assert resp.status_code == 200, resp.text
    logs = resp.json()["data"]
    assert len(logs) == 1
    log = logs[0]
    assert log["user_id"] == owner.id
    assert log["resource_type"] == "task"
    assert log["resource_id"] == task_id
    assert log["action"] == "task:transition"
    assert log["payload"] == {"old_status": "TODO", "new_status": "IN_PROGRESS"}
    assert "created_at" in log

    # GET /logs/task/{id} 也返回同一条
    resp = await client.get(
        f"/api/v1/logs/task/{task_id}",
        headers=_bearer(create_access_token(owner.id)),
    )
    assert resp.status_code == 200
    assert resp.json()["data"][0]["id"] == log["id"]


# --- 资源级隔离：只看自己的日志 ------------------------------------------------


async def test_get_logs_only_own(client):
    owner_a = await _make_user("owner_a", ["admin"])
    owner_b = await _make_user("owner_b", ["admin"])
    proj_a = await _make_project(owner_a, "a")
    proj_b = await _make_project(owner_b, "b")
    task_a = await _create_task(client, owner_a, proj_a, "a")
    task_b = await _create_task(client, owner_b, proj_b, "b")

    await _transition(client, owner_a, task_a, "IN_PROGRESS")
    await _transition(client, owner_b, task_b, "IN_PROGRESS")

    resp = await client.get(
        "/api/v1/logs", headers=_bearer(create_access_token(owner_a.id))
    )
    assert resp.status_code == 200
    logs = resp.json()["data"]
    assert len(logs) == 1
    assert logs[0]["user_id"] == owner_a.id
    assert logs[0]["resource_id"] == task_a


# --- 资源级归属：非成员 GET /logs/task/{id} 404 ------------------------------


async def test_get_logs_resource_requires_membership_404(client):
    owner = await _make_user("owner2", ["admin"])
    outsider = await _make_user("outsider2", ["admin"])
    project = await _make_project(owner, "r1")
    task_id = await _create_task(client, owner, project, "r1")

    resp = await client.get(
        f"/api/v1/logs/task/{task_id}",
        headers=_bearer(create_access_token(outsider.id)),
    )
    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"] == "Resource not found"


# --- 不支持的资源类型 404 ------------------------------------------------------


async def test_get_logs_unsupported_resource_404(client):
    owner = await _make_user("owner3", ["admin"])
    resp = await client.get(
        "/api/v1/logs/comment/1",
        headers=_bearer(create_access_token(owner.id)),
    )
    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"] == "Unsupported resource type"


# --- 分页 ----------------------------------------------------------------


async def test_get_logs_pagination_desc(client):
    owner = await _make_user("owner4", ["admin"])
    project = await _make_project(owner, "p1")
    task_id = await _create_task(client, owner, project, "p1")

    await _transition(client, owner, task_id, "IN_PROGRESS")
    await _transition(client, owner, task_id, "REVIEW")

    # 最新在前，limit=1 应只剩 REVIEW 那次
    resp = await client.get(
        "/api/v1/logs?limit=1",
        headers=_bearer(create_access_token(owner.id)),
    )
    assert resp.status_code == 200
    logs = resp.json()["data"]
    assert len(logs) == 1
    assert logs[0]["payload"] == {"old_status": "IN_PROGRESS", "new_status": "REVIEW"}

    # skip=1 取较早那条（IN_PROGRESS）
    resp = await client.get(
        "/api/v1/logs?limit=1&skip=1",
        headers=_bearer(create_access_token(owner.id)),
    )
    logs = resp.json()["data"]
    assert len(logs) == 1
    assert logs[0]["payload"] == {"old_status": "TODO", "new_status": "IN_PROGRESS"}


# --- 功能级权限：403 ----------------------------------------------------------


async def test_get_logs_missing_permission_403(client):
    norole = await _make_user("norole5")  # 无任何角色
    resp = await client.get(
        "/api/v1/logs", headers=_bearer(create_access_token(norole.id))
    )
    assert resp.status_code == 403, resp.text
    assert resp.json()["detail"] == "Permission denied: log:read"
