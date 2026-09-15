"""TASK-029：项目 CRUD HTTP 端到端验收（真实产品应用 + 真实 Token 认证链）。

与 TASK-027/028 同模式：对 `app.main.app` 走完整链路，仅覆盖 `get_db` 指向
测试库。Service 层路径经 API 全覆盖。

验证重点（TASK-029 决策：双层判定 / 成员即可创建 / 团队 OWNER+ADMIN 改删 /
列表=我所在团队的项目）：
- 全局权限缺失 → 403（member 全局角色无 project:create → 普通成员建项目 403）；
- 团队不存在或非成员创建 → 404（同一文案，IDOR）；
- 创建 201，owner_id 恒为调用者；
- 列表只含我所在团队的项目；
- 详情团队成员可见、局外人 404；
- 改删：团队角色不足（普通 MEMBER）→ 403；团队 OWNER/ADMIN 可改删；
- PATCH exclude_unset 部分更新语义；
- 删团队级联清项目（团队 RESTRICT 先删，项目随 CASCADE 消失）。

零残留：先删团队（级联清项目）再删用户。
"""

import uuid

import pytest
import pytest_asyncio
from fastapi import status
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.security import create_access_token
from app.crud.role import assign_role_to_user, get_role_by_name
from app.crud.team import add_team_member
from app.crud.user import create_user
from app.db.session import get_db
from app.main import app
from app.models.project import Project
from app.models.team import Team
from app.models.team_member import TeamRole
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
    return f"prjapi_{RUN_TOKEN}_{tag}"


def _team_name(tag: str) -> str:
    return f"prjapi {RUN_TOKEN} {tag}"


def _project_name(tag: str) -> str:
    return f"prjapi project {RUN_TOKEN} {tag}"


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
                select(User).where(User.username.like(f"prjapi_{RUN_TOKEN}%"))
            )
        ).scalars().all()
        for u in users:
            teams = (
                await session.execute(select(Team).where(Team.owner_id == u.id))
            ).scalars().all()
            for t in teams:
                await session.delete(t)  # 级联清项目
            await session.flush()
            await session.delete(u)
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


async def _create_team(owner_id: int, tag: str) -> int:
    """直接经 Service 建队（自动写 OWNER 成员行），绕过 HTTP 减少耦合。"""
    from app.schemas.team import TeamCreate
    from app.services.team import create_team

    async with SessionFactory() as session:
        user = await session.get(User, owner_id)
        team = await create_team(session, user, TeamCreate(name=_team_name(tag)))
        await session.commit()
        return team.id


# --- POST /projects ----------------------------------------------------------------


async def test_create_project_201_creator_is_owner(client):
    owner = await _make_user("owner", ["admin"])
    team_id = await _create_team(owner.id, "cr")

    resp = await client.post(
        "/api/v1/projects",
        headers=_bearer(create_access_token(owner.id)),
        json={"team_id": team_id, "name": _project_name("cr"), "description": "d0"},
    )
    assert resp.status_code == status.HTTP_201_CREATED, resp.text
    data = resp.json()["data"]
    assert data["name"] == _project_name("cr")
    assert data["team_id"] == team_id
    assert data["owner_id"] == owner.id
    assert data["description"] == "d0"


async def test_create_project_team_not_found_or_not_member_404(client):
    admin = await _make_user("nf", ["admin"])
    headers = _bearer(create_access_token(admin.id))

    # 团队不存在 → 404
    missing = await client.post(
        "/api/v1/projects",
        headers=headers,
        json={"team_id": 99999999, "name": _project_name("nf1")},
    )
    assert missing.status_code == status.HTTP_404_NOT_FOUND, missing.text
    assert missing.json()["detail"] == "Team not found"

    # 团队存在但调用者不是成员 → 404（同一文案，IDOR 防枚举）
    outsider = await _make_user("nf2", ["admin"])
    team_id = await _create_team(admin.id, "nf")
    by_outsider = await client.post(
        "/api/v1/projects",
        headers=_bearer(create_access_token(outsider.id)),
        json={"team_id": team_id, "name": _project_name("nf2")},
    )
    assert by_outsider.status_code == status.HTTP_404_NOT_FOUND, by_outsider.text
    assert by_outsider.json()["detail"] == "Team not found"


async def test_create_project_member_without_global_perm_403(client):
    """普通 member 全局角色（无 project:create）：团队成员但 403 先行。"""
    owner = await _make_user("g403o", ["admin"])
    plain_member = await _make_user("g403m", ["member"])
    team_id = await _create_team(owner.id, "g403")
    # 把 plain_member 拉进团队（经 Service 原语）
    async with SessionFactory() as session:
        await add_team_member(
            session,
            team_id=team_id,
            user_id=plain_member.id,
            role_id=TeamRole.MEMBER.value,
        )
        await session.commit()

    resp = await client.post(
        "/api/v1/projects",
        headers=_bearer(create_access_token(plain_member.id)),
        json={"team_id": team_id, "name": _project_name("g403")},
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN, resp.text
    assert resp.json()["detail"] == "Permission denied: project:create"


async def test_create_project_no_auth_401(client):
    resp = await client.post(
        "/api/v1/projects", json={"team_id": 1, "name": "x"}
    )
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED, resp.text


# --- GET /projects -----------------------------------------------------------------


async def test_list_projects_only_teams_i_belong_to(client):
    owner = await _make_user("lso", ["admin"])
    teammate = await _make_user("lsm", ["member"])
    other = await _make_user("lso2", ["admin"])

    team_a = await _create_team(owner.id, "lsa")
    team_b = await _create_team(other.id, "lsb")

    headers = _bearer(create_access_token(owner.id))
    for tag in ("p1", "p2"):
        resp = await client.post(
            "/api/v1/projects",
            headers=headers,
            json={"team_id": team_a, "name": _project_name(tag)},
        )
        assert resp.status_code == 201, resp.text
    # team_b（别人团队，owner 不是成员）下也建一个
    resp = await client.post(
        "/api/v1/projects",
        headers=_bearer(create_access_token(other.id)),
        json={"team_id": team_b, "name": _project_name("p3")},
    )
    assert resp.status_code == 201, resp.text

    # owner 只看到 team_a 的 2 个项目
    listed = await client.get("/api/v1/projects", headers=headers)
    assert listed.status_code == 200, listed.text
    names = [p["name"] for p in listed.json()["data"]]
    assert names == [_project_name("p1"), _project_name("p2")]

    # 队友（team_a 成员）也能看到这 2 个
    async with SessionFactory() as session:
        await add_team_member(
            session,
            team_id=team_a,
            user_id=teammate.id,
            role_id=TeamRole.MEMBER.value,
        )
        await session.commit()
    listed2 = await client.get(
        "/api/v1/projects", headers=_bearer(create_access_token(teammate.id))
    )
    assert listed2.status_code == 200, listed2.text
    assert {p["name"] for p in listed2.json()["data"]} == {
        _project_name("p1"),
        _project_name("p2"),
    }


# --- GET /projects/{project_id} ----------------------------------------------------


async def test_get_project_member_visible_outsider_404(client):
    owner = await _make_user("go", ["admin"])
    teammate = await _make_user("gm", ["member"])
    outsider = await _make_user("gx", ["admin"])
    team_id = await _create_team(owner.id, "g")

    headers = _bearer(create_access_token(owner.id))
    created = await client.post(
        "/api/v1/projects",
        headers=headers,
        json={"team_id": team_id, "name": _project_name("g")},
    )
    assert created.status_code == 201, created.text
    project_id = created.json()["data"]["id"]

    async with SessionFactory() as session:
        await add_team_member(
            session,
            team_id=team_id,
            user_id=teammate.id,
            role_id=TeamRole.MEMBER.value,
        )
        await session.commit()

    # 团队成员可见
    ok = await client.get(
        f"/api/v1/projects/{project_id}",
        headers=_bearer(create_access_token(teammate.id)),
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["data"]["id"] == project_id

    # 局外人（有全局权限、不在归属链）→ 404
    denied = await client.get(
        f"/api/v1/projects/{project_id}",
        headers=_bearer(create_access_token(outsider.id)),
    )
    assert denied.status_code == status.HTTP_404_NOT_FOUND, denied.text
    assert denied.json()["detail"] == "Project not found"


# --- PATCH /projects/{project_id} --------------------------------------------------


async def test_patch_by_team_owner_and_admin(client):
    owner = await _make_user("po", ["admin"])
    team_admin = await _make_user("pa", ["admin"])
    team_id = await _create_team(owner.id, "p")

    async with SessionFactory() as session:
        await add_team_member(
            session,
            team_id=team_id,
            user_id=team_admin.id,
            role_id=TeamRole.ADMIN.value,
        )
        await session.commit()

    created = await client.post(
        "/api/v1/projects",
        headers=_bearer(create_access_token(owner.id)),
        json={"team_id": team_id, "name": _project_name("p"), "description": "d0"},
    )
    project_id = created.json()["data"]["id"]

    # 团队 OWNER（全局 admin）改
    resp = await client.patch(
        f"/api/v1/projects/{project_id}",
        headers=_bearer(create_access_token(owner.id)),
        json={"description": "d1"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["description"] == "d1"
    assert data["name"] == _project_name("p")  # exclude_unset：未传不动

    # 团队 ADMIN（全局 admin）改
    resp2 = await client.patch(
        f"/api/v1/projects/{project_id}",
        headers=_bearer(create_access_token(team_admin.id)),
        json={"name": _project_name("p2")},
    )
    assert resp2.status_code == 200, resp2.text
    assert resp2.json()["data"]["name"] == _project_name("p2")


async def test_patch_by_plain_team_member_403(client):
    """普通成员（全局 admin 但团队角色 MEMBER）→ 资源级 403。"""
    owner = await _make_user("pmo", ["admin"])
    plain = await _make_user("pmm", ["admin"])
    team_id = await _create_team(owner.id, "pm")

    async with SessionFactory() as session:
        await add_team_member(
            session,
            team_id=team_id,
            user_id=plain.id,
            role_id=TeamRole.MEMBER.value,
        )
        await session.commit()

    created = await client.post(
        "/api/v1/projects",
        headers=_bearer(create_access_token(owner.id)),
        json={"team_id": team_id, "name": _project_name("pm")},
    )
    project_id = created.json()["data"]["id"]

    resp = await client.patch(
        f"/api/v1/projects/{project_id}",
        headers=_bearer(create_access_token(plain.id)),
        json={"description": "hack"},
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN, resp.text
    assert resp.json()["detail"] == "Only team owner or admin can manage projects"


async def test_patch_outsider_404(client):
    owner = await _make_user("po404", ["admin"])
    outsider = await _make_user("px404", ["admin"])
    team_id = await _create_team(owner.id, "p404")

    created = await client.post(
        "/api/v1/projects",
        headers=_bearer(create_access_token(owner.id)),
        json={"team_id": team_id, "name": _project_name("p404")},
    )
    project_id = created.json()["data"]["id"]

    resp = await client.patch(
        f"/api/v1/projects/{project_id}",
        headers=_bearer(create_access_token(outsider.id)),
        json={"description": "x"},
    )
    assert resp.status_code == status.HTTP_404_NOT_FOUND, resp.text
    assert resp.json()["detail"] == "Project not found"


# --- DELETE /projects/{project_id} -------------------------------------------------


async def test_delete_by_team_owner_then_404(client):
    owner = await _make_user("do", ["admin"])
    team_id = await _create_team(owner.id, "d")

    created = await client.post(
        "/api/v1/projects",
        headers=_bearer(create_access_token(owner.id)),
        json={"team_id": team_id, "name": _project_name("d")},
    )
    project_id = created.json()["data"]["id"]

    resp = await client.delete(
        f"/api/v1/projects/{project_id}",
        headers=_bearer(create_access_token(owner.id)),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"] is None

    again = await client.get(
        f"/api/v1/projects/{project_id}",
        headers=_bearer(create_access_token(owner.id)),
    )
    assert again.status_code == status.HTTP_404_NOT_FOUND, again.text
    assert again.json()["detail"] == "Project not found"


async def test_delete_team_cascades_projects(client):
    owner = await _make_user("co", ["admin"])
    team_id = await _create_team(owner.id, "c")

    created = await client.post(
        "/api/v1/projects",
        headers=_bearer(create_access_token(owner.id)),
        json={"team_id": team_id, "name": _project_name("c")},
    )
    assert created.status_code == 201, created.text

    # 删团队（owner-only，TASK-027 语义）→ 项目随 CASCADE 消失
    deleted = await client.delete(
        f"/api/v1/teams/{team_id}",
        headers=_bearer(create_access_token(owner.id)),
    )
    assert deleted.status_code == 200, deleted.text

    async with SessionFactory() as session:
        remaining = (
            await session.execute(
                select(Project).where(Project.name == _project_name("c"))
            )
        ).scalar_one_or_none()
    assert remaining is None


async def test_project_routes_registered_on_product_app():
    spec = app.openapi()
    assert "/api/v1/projects" in spec["paths"]
    assert "/api/v1/projects/{project_id}" in spec["paths"]
