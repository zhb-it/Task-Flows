"""TASK-035：Task 列表多条件过滤 / 分页 / 排序 HTTP 端到端验收。

沿用 test_task_api.py 模式：真实产品应用 + 真实 Token 认证链，仅覆盖
`get_db` 指向测试库。TASK-035 用户确认决策：

- 分页沿用 skip/limit（与 teams/projects 一致），响应仍为纯列表；
- 过滤：status / priority 精确 + keyword 标题 ILIKE（通配符按字面匹配）；
- 排序：sort 白名单 id/created_at/due_at/priority + order asc/desc，
  priority 按业务权重（URGENT > HIGH > MEDIUM > LOW）而非字母序；
- project_id 保持必填（缺失 422）。

status 过滤需要非 TODO 行：POST 恒 TODO 起步（TASK-032），故不同 status
的行由 fixture 直插数据库（等价于未来 transition API 的产出）。

零残留：RESTRICT 链精确拆除（tasks → projects → teams → users）。
"""

import uuid
from datetime import datetime, timedelta, timezone

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
    return f"taskqry_{RUN_TOKEN}_{tag}"


def _title(tag: str) -> str:
    return f"taskqry {RUN_TOKEN} {tag}"


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
            delete(Task).where(Task.title.like(f"taskqry {RUN_TOKEN}%"))
        )
        await session.execute(
            delete(Project).where(Project.name.like(f"taskqry proj {RUN_TOKEN}%"))
        )
        await session.execute(
            delete(Team).where(Team.name.like(f"taskqry team {RUN_TOKEN}%"))
        )
        await session.execute(
            delete(User).where(User.username.like(f"taskqry_{RUN_TOKEN}%"))
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
            session, owner, TeamCreate(name=f"taskqry team {RUN_TOKEN} {tag}")
        )
        project = await create_project(
            session,
            name=f"taskqry proj {RUN_TOKEN} {tag}",
            description=None,
            team_id=team.id,
            owner_id=owner.id,
        )
        await session.commit()
        await session.refresh(project)
        return project


async def _api_create(client, owner: User, project: Project, tag: str, **extra) -> dict:
    resp = await client.post(
        "/api/v1/tasks",
        headers=_bearer(create_access_token(owner.id)),
        json={"project_id": project.id, "title": _title(tag), **extra},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


async def _db_insert_task(project: Project, owner: User, tag: str, **fields) -> Task:
    """直插任意字段组合的 Task 行（覆盖 status 过滤——API 只能建 TODO）。

    creator_id 为 NOT NULL 列，由调用者传入（owner 即可，不影响查询断言）。
    """
    async with SessionFactory() as session:
        task = Task(
            project_id=project.id,
            title=_title(tag),
            creator_id=owner.id,
            **fields,
        )
        session.add(task)
        await session.commit()
        await session.refresh(task)
        return task


# --- 过滤 -----------------------------------------------------------------------


async def test_list_filter_status(client):
    owner = await _make_user("o1", ["admin"])
    project = await _make_project(owner, "f1")
    todo = await _api_create(client, owner, project, "todo")
    await _db_insert_task(project, owner, "prog", status="IN_PROGRESS")
    await _db_insert_task(project, owner, "done", status="DONE")

    def ids(resp):
        assert resp.status_code == 200, resp.text
        return sorted(t["id"] for t in resp.json()["data"])

    headers = _bearer(create_access_token(owner.id))
    base = {"project_id": project.id}

    # 不带 status = 全部（3 行：API 建的 TODO + 直插的 IN_PROGRESS/DONE）
    all_rows = (
        await client.get("/api/v1/tasks", headers=headers, params=base)
    ).json()["data"]
    all_ids = sorted(t["id"] for t in all_rows)
    assert len(all_ids) == 3 and todo["id"] in all_ids

    # status=TODO 精确过滤
    r = await client.get("/api/v1/tasks", headers=headers, params={**base, "status": "TODO"})
    assert [t["id"] for t in r.json()["data"]] == [todo["id"]]
    assert all(t["status"] == "TODO" for t in r.json()["data"])

    # status=IN_PROGRESS（API 建不出的状态，fixture 直插）
    r = await client.get(
        "/api/v1/tasks", headers=headers, params={**base, "status": "IN_PROGRESS"}
    )
    assert len(r.json()["data"]) == 1
    assert r.json()["data"][0]["status"] == "IN_PROGRESS"

    # 非法 status → 422
    r = await client.get("/api/v1/tasks", headers=headers, params={**base, "status": "BAD"})
    assert r.status_code == 422


async def test_list_filter_priority(client):
    owner = await _make_user("o2", ["admin"])
    project = await _make_project(owner, "f2")
    high = await _api_create(client, owner, project, "hi", priority="HIGH")
    await _api_create(client, owner, project, "lo", priority="LOW")

    headers = _bearer(create_access_token(owner.id))
    base = {"project_id": project.id, "priority": "HIGH"}
    r = await client.get("/api/v1/tasks", headers=headers, params=base)
    assert r.status_code == 200
    data = r.json()["data"]
    assert [t["id"] for t in data] == [high["id"]]
    assert all(t["priority"] == "HIGH" for t in data)

    # 非法 priority → 422
    r = await client.get(
        "/api/v1/tasks", headers=headers, params={**base, "priority": "EXTREME"}
    )
    assert r.status_code == 422


async def test_list_keyword_literal_and_case_insensitive(client):
    owner = await _make_user("o3", ["admin"])
    project = await _make_project(owner, "f3")
    hit = await _api_create(client, owner, project, "AlphaReport")
    await _api_create(client, owner, project, "unrelated")

    headers = _bearer(create_access_token(owner.id))
    base = {"project_id": project.id}

    # 大小写不敏感子串命中
    r = await client.get(
        "/api/v1/tasks", headers=headers, params={**base, "keyword": "alpharep"}
    )
    assert r.status_code == 200
    assert [t["id"] for t in r.json()["data"]] == [hit["id"]]

    # % 作为字面字符：title 不含 % 的任务不被命中
    r = await client.get(
        "/api/v1/tasks", headers=headers, params={**base, "keyword": "a%a"}
    )
    assert r.status_code == 200
    assert r.json()["data"] == []

    # title 本身含 % 时按字面匹配命中（转义生效）
    pct = await _db_insert_task(project, owner, "100%pct")
    r = await client.get(
        "/api/v1/tasks", headers=headers, params={**base, "keyword": "100%"}
    )
    assert r.status_code == 200
    assert [t["id"] for t in r.json()["data"]] == [pct.id]

    # 纯空白 keyword 视为未传（返回全部）
    r = await client.get(
        "/api/v1/tasks", headers=headers, params={**base, "keyword": "   "}
    )
    assert r.status_code == 200
    assert len(r.json()["data"]) == 3


# --- 分页 -----------------------------------------------------------------------


async def test_list_pagination_skip_limit(client):
    owner = await _make_user("o4", ["admin"])
    project = await _make_project(owner, "pg")
    created = [
        (await _api_create(client, owner, project, f"pg{i}"))["id"] for i in range(5)
    ]  # id 升序
    headers = _bearer(create_access_token(owner.id))
    base = {"project_id": project.id}

    # limit 截断
    r = await client.get("/api/v1/tasks", headers=headers, params={**base, "limit": 2})
    assert [t["id"] for t in r.json()["data"]] == created[:2]

    # skip + limit 窗口
    r = await client.get(
        "/api/v1/tasks", headers=headers, params={**base, "skip": 2, "limit": 2}
    )
    assert [t["id"] for t in r.json()["data"]] == created[2:4]

    # skip 超出总数 → 空列表（200，非 404）
    r = await client.get(
        "/api/v1/tasks", headers=headers, params={**base, "skip": 100}
    )
    assert r.status_code == 200
    assert r.json()["data"] == []

    # 边界非法：limit=0 / limit=101 / skip=-1 → 422
    for bad in ({"limit": 0}, {"limit": 101}, {"skip": -1}):
        r = await client.get("/api/v1/tasks", headers=headers, params={**base, **bad})
        assert r.status_code == 422, bad

    # project_id 缺失依旧 422（TASK-034 契约保持）
    r = await client.get("/api/v1/tasks", headers=headers)
    assert r.status_code == 422


# --- 排序 -----------------------------------------------------------------------


async def test_list_sort_id_and_priority_business_order(client):
    owner = await _make_user("o5", ["admin"])
    project = await _make_project(owner, "s1")
    ids = {}
    for p in ("URGENT", "HIGH", "MEDIUM", "LOW"):
        row = await _api_create(client, owner, project, f"s{p}", priority=p)
        ids[p] = row["id"]
    headers = _bearer(create_access_token(owner.id))
    base = {"project_id": project.id}

    # 默认 id 升序
    r = await client.get("/api/v1/tasks", headers=headers, params=base)
    got = [t["id"] for t in r.json()["data"]]
    assert got == sorted(got)

    # sort=id&order=desc 翻转
    r = await client.get(
        "/api/v1/tasks", headers=headers, params={**base, "sort": "id", "order": "desc"}
    )
    got = [t["id"] for t in r.json()["data"]]
    assert got == sorted(got, reverse=True)

    # sort=priority 业务权重（非字母序）：desc → URGENT > HIGH > MEDIUM > LOW
    r = await client.get(
        "/api/v1/tasks", headers=headers, params={**base, "sort": "priority", "order": "desc"}
    )
    assert [t["priority"] for t in r.json()["data"]] == [
        "URGENT", "HIGH", "MEDIUM", "LOW",
    ]

    # asc 反向
    r = await client.get(
        "/api/v1/tasks", headers=headers, params={**base, "sort": "priority", "order": "asc"}
    )
    assert [t["priority"] for t in r.json()["data"]] == [
        "LOW", "MEDIUM", "HIGH", "URGENT",
    ]


async def test_list_sort_due_at_desc(client):
    owner = await _make_user("o6", ["admin"])
    project = await _make_project(owner, "s2")
    base_dt = datetime(2026, 9, 14, tzinfo=timezone.utc)
    rows = []
    for i, days in enumerate((3, 1, 2)):
        rows.append(
            (
                await _db_insert_task(
                    project,
                    owner,
                    f"due{i}",
                    due_at=base_dt + timedelta(days=days),
                )
            ).id
        )
    headers = _bearer(create_access_token(owner.id))
    r = await client.get(
        "/api/v1/tasks",
        headers=headers,
        params={"project_id": project.id, "sort": "due_at", "order": "desc"},
    )
    assert r.status_code == 200, r.text
    # desc：due_at 大的在先（+3d, +2d, +1d）
    assert [t["id"] for t in r.json()["data"]] == [rows[0], rows[2], rows[1]]


async def test_list_sort_invalid_field_422(client):
    owner = await _make_user("o7", ["admin"])
    project = await _make_project(owner, "s3")
    headers = _bearer(create_access_token(owner.id))
    base = {"project_id": project.id}
    for bad in ({"sort": "description"}, {"order": "ascending"}):
        r = await client.get("/api/v1/tasks", headers=headers, params={**base, **bad})
        assert r.status_code == 422, bad


# --- 过滤 + 分页组合 / 可见性不变 -------------------------------------------------


async def test_list_combined_query_and_visibility(client):
    owner = await _make_user("o8", ["admin"])
    outsider = await _make_user("o8x", ["admin"])
    project = await _make_project(owner, "cb")
    await _api_create(client, owner, project, "cb-hi-alpha", priority="HIGH")
    await _api_create(client, owner, project, "cb-hi-beta", priority="HIGH")
    await _db_insert_task(project, owner, "cb-lo-alpha", priority="LOW", status="DONE")
    headers = _bearer(create_access_token(owner.id))
    base = {"project_id": project.id, "priority": "HIGH", "keyword": "alpha"}

    # 过滤组合：HIGH + alpha → 1 行
    r = await client.get("/api/v1/tasks", headers=headers, params=base)
    assert r.status_code == 200
    data = r.json()["data"]
    assert len(data) == 1
    assert data[0]["priority"] == "HIGH" and "alpha" in data[0]["title"]

    # 过滤 + 分页组合：全量 2 行 HIGH，limit=1 取第一页
    r = await client.get(
        "/api/v1/tasks", headers=headers, params={**base, "keyword": "hi", "limit": 1}
    )
    assert len(r.json()["data"]) == 1

    # 可见性不变：局外人 → 404 同文案
    r = await client.get(
        "/api/v1/tasks",
        headers=_bearer(create_access_token(outsider.id)),
        params={"project_id": project.id},
    )
    assert r.status_code == 404
    assert r.json()["detail"] == "Task not found"
