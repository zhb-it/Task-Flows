"""TASK-030：团队与项目权限矩阵验收（Phase 4 收尾）.

把 TASK-027/028/029 分散实现的授权语义整合为一份系统性矩阵：
**全局 RBAC 角色 × 团队角色 × 操作**，并落实开发文档 §56 Phase 4 验收点
「ADMIN / MEMBER 权限表现不同」。

用户阵容（每个测试独立搭建，RUN_TOKEN 保证唯一）：

====== ================ ==================
用户    全局角色         团队角色（T）
====== ================ ==================
owner   admin            OWNER（建队自动）
tmember admin            MEMBER
tadmin  admin            ADMIN
gmember member           MEMBER
outsidr admin            （非成员）
nobody  （无角色）       （非成员）
====== ================ ==================

种子基线（TASK-022）：``admin`` = 全部 22 项权限；``member`` = 读 5 项
（user/team/project/task/log:read）+ 基础写 5 项（task:create/update、
comment:create、attachment:upload/download），**不含任何 team:/project:
写权限**。

矩阵语义（已确认决策的汇总验证）：
- 功能级（全局权限）缺失 → 403 ``Permission denied: {perm}``，先于一切；
- 资源级归属链外 → 404（与不存在同文案，IDOR 防枚举）；
- 资源级团队角色不足（调用者已在归属链）→ 403 明示权限不足；
- 团队改删 = 仅 owner；团队/项目成员管理 = 团队 OWNER/ADMIN；
  项目改删 = 团队 OWNER/ADMIN；项目创建 = 团队成员即可。

零残留：先删团队（级联清项目）再删用户。
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
from app.models.team import Team
from app.models.team_member import TeamRole
from app.models.user import User
from app.schemas.team import TeamCreate
from app.services.team import create_team as create_team_service

TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@127.0.0.1:5433/taskflow"

RUN_TOKEN = uuid.uuid4().hex[:10]

engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
SessionFactory = async_sessionmaker(engine, expire_on_commit=False)


async def _override_get_db():
    async with SessionFactory() as session:
        yield session


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
                select(User).where(User.username.like(f"mtrx_{RUN_TOKEN}%"))
            )
        ).scalars().all()
        for u in users:
            teams = (
                await session.execute(select(Team).where(Team.owner_id == u.id))
            ).scalars().all()
            for t in teams:
                await session.delete(t)
            await session.flush()
            await session.delete(u)
        await session.commit()


class World:
    """一次测试世界：固定阵容 + 一个团队 + 一个项目。"""

    def __init__(self, users: dict, team_id: int, project_id: int):
        self.users = users
        self.team_id = team_id
        self.project_id = project_id

    def headers(self, tag: str) -> dict:
        return {"Authorization": f"Bearer {create_access_token(self.users[tag].id)}"}


async def _make_user(tag: str, role_names: list[str] | None = None) -> User:
    async with SessionFactory() as session:
        user = await create_user(
            session,
            username=f"mtrx_{RUN_TOKEN}_{tag}",
            email=f"mtrx_{RUN_TOKEN}_{tag}@example.com",
            password_hash="h",
        )
        for role_name in role_names or []:
            role = await get_role_by_name(session, role_name)
            assert role is not None, f"seed role {role_name!r} missing"
            await assign_role_to_user(session, user_id=user.id, role_id=role.id)
        await session.commit()
        await session.refresh(user)
        return user


async def _make_world() -> World:
    """搭建矩阵世界：owner 建队/建项目，其余成员经 Service 原语入队。"""
    from app.crud.team import add_team_member
    from app.schemas.project import ProjectCreate
    from app.services.project import create_project as create_project_service

    users = {
        "owner": await _make_user("owner", ["admin"]),
        "tmember": await _make_user("tmember", ["admin"]),
        "tadmin": await _make_user("tadmin", ["admin"]),
        "gmember": await _make_user("gmember", ["member"]),
        "outsider": await _make_user("outsider", ["admin"]),
        "nobody": await _make_user("nobody"),
    }

    async with SessionFactory() as session:
        owner = await session.get(User, users["owner"].id)
        team = await create_team_service(
            session, owner, TeamCreate(name=f"mtrx team {RUN_TOKEN}")
        )
        for tag, role in (
            ("tmember", TeamRole.MEMBER),
            ("tadmin", TeamRole.ADMIN),
            ("gmember", TeamRole.MEMBER),
        ):
            await add_team_member(
                session,
                team_id=team.id,
                user_id=users[tag].id,
                role_id=role.value,
            )
        project = await create_project_service(
            session,
            owner,
            ProjectCreate(team_id=team.id, name=f"mtrx project {RUN_TOKEN}"),
        )
        await session.commit()
        return World(users, team.id, project.id)


# --- §56 验收点：ADMIN / MEMBER 权限表现不同 ---------------------------------------


async def test_admin_vs_member_on_team_create(client):
    w = await _make_world()
    ok = await client.post(
        "/api/v1/teams",
        headers=w.headers("owner"),
        json={"name": f"mtrx team2 {RUN_TOKEN}"},
    )
    assert ok.status_code == 201, ok.text

    denied = await client.post(
        "/api/v1/teams",
        headers=w.headers("gmember"),
        json={"name": f"mtrx team3 {RUN_TOKEN}"},
    )
    assert denied.status_code == 403, denied.text
    assert denied.json()["detail"] == "Permission denied: team:create"

    nobody = await client.post(
        "/api/v1/teams",
        headers=w.headers("nobody"),
        json={"name": f"mtrx team4 {RUN_TOKEN}"},
    )
    assert nobody.status_code == 403, nobody.text
    assert nobody.json()["detail"] == "Permission denied: team:create"


async def test_admin_vs_member_on_project_create(client):
    w = await _make_world()
    denied = await client.post(
        "/api/v1/projects",
        headers=w.headers("gmember"),
        json={"team_id": w.team_id, "name": f"mtrx p2 {RUN_TOKEN}"},
    )
    assert denied.status_code == 403, denied.text
    assert denied.json()["detail"] == "Permission denied: project:create"

    nobody = await client.post(
        "/api/v1/projects",
        headers=w.headers("nobody"),
        json={"team_id": w.team_id, "name": f"mtrx p3 {RUN_TOKEN}"},
    )
    assert nobody.status_code == 403, nobody.text

    # 全局 admin + 团队成员 → 成员即可创建（TASK-029 决策 2）
    ok = await client.post(
        "/api/v1/projects",
        headers=w.headers("tmember"),
        json={"team_id": w.team_id, "name": f"mtrx p4 {RUN_TOKEN}"},
    )
    assert ok.status_code == 201, ok.text
    assert ok.json()["data"]["owner_id"] == w.users["tmember"].id


# --- member 全局角色 = 只读面 ------------------------------------------------------


async def test_global_member_read_only_on_teams(client):
    w = await _make_world()
    h = w.headers("gmember")

    listed = await client.get("/api/v1/teams", headers=h)
    assert listed.status_code == 200, listed.text
    assert [t["id"] for t in listed.json()["data"]] == [w.team_id]

    detail = await client.get(f"/api/v1/teams/{w.team_id}", headers=h)
    assert detail.status_code == 200, detail.text

    for method, path in (("patch", f"/api/v1/teams/{w.team_id}"),):
        resp = await getattr(client, method)(path, headers=h, json={"name": "x"})
        assert resp.status_code == 403, resp.text
        assert resp.json()["detail"] == "Permission denied: team:update"
    resp = await client.delete(f"/api/v1/teams/{w.team_id}", headers=h)
    assert resp.status_code == 403, resp.text
    assert resp.json()["detail"] == "Permission denied: team:delete"


async def test_global_member_read_only_on_projects(client):
    w = await _make_world()
    h = w.headers("gmember")

    listed = await client.get("/api/v1/projects", headers=h)
    assert listed.status_code == 200, listed.text
    assert [p["id"] for p in listed.json()["data"]] == [w.project_id]

    detail = await client.get(f"/api/v1/projects/{w.project_id}", headers=h)
    assert detail.status_code == 200, detail.text

    resp = await client.patch(
        f"/api/v1/projects/{w.project_id}", headers=h, json={"name": "x"}
    )
    assert resp.status_code == 403, resp.text
    assert resp.json()["detail"] == "Permission denied: project:update"

    resp = await client.delete(f"/api/v1/projects/{w.project_id}", headers=h)
    assert resp.status_code == 403, resp.text
    assert resp.json()["detail"] == "Permission denied: project:delete"


# --- 资源级：团队角色约束全局 admin -------------------------------------------------


async def test_team_owner_only_mutations_block_team_member(client):
    """全局 admin + 团队 MEMBER ≠ 团队 owner：改/删团队 404（非 owner）。"""
    w = await _make_world()
    h = w.headers("tmember")

    resp = await client.patch(f"/api/v1/teams/{w.team_id}", headers=h, json={"name": "x"})
    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"] == "Team not found"

    resp = await client.delete(f"/api/v1/teams/{w.team_id}", headers=h)
    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"] == "Team not found"


async def test_team_invite_dual_layer(client):
    """邀请 = 全局 team:invite × 团队 OWNER/ADMIN，两层各自可见。"""
    w = await _make_world()
    target = await _make_user("target")
    body = {"user_id": target.id}

    # 层 1：gmember（团队 MEMBER，无全局 team:invite）→ 功能级 403
    r1 = await client.post(
        f"/api/v1/teams/{w.team_id}/members", headers=w.headers("gmember"), json=body
    )
    assert r1.status_code == 403, r1.text
    assert r1.json()["detail"] == "Permission denied: team:invite"

    # 层 2：tmember（全局 admin 有 team:invite，团队 MEMBER）→ 资源级 403
    r2 = await client.post(
        f"/api/v1/teams/{w.team_id}/members", headers=w.headers("tmember"), json=body
    )
    assert r2.status_code == 403, r2.text
    assert r2.json()["detail"] == "Only team owner or admin can manage members"

    # 两层皆过：tadmin（全局 admin + 团队 ADMIN）→ 201
    r3 = await client.post(
        f"/api/v1/teams/{w.team_id}/members", headers=w.headers("tadmin"), json=body
    )
    assert r3.status_code == 201, r3.text


async def test_global_member_team_admin_still_cannot_invite(client):
    """双层判定的另一方向：团队角色再高也补不了全局权限缺失。

    gmember（全局 member）升为团队 ADMIN 后邀请仍 403 team:invite。
    """
    from app.crud.team import get_team_member

    w = await _make_world()
    async with SessionFactory() as session:
        member = await get_team_member(
            session, team_id=w.team_id, user_id=w.users["gmember"].id
        )
        member.role_id = TeamRole.ADMIN.value
        await session.commit()

    target = await _make_user("target2")
    resp = await client.post(
        f"/api/v1/teams/{w.team_id}/members",
        headers=w.headers("gmember"),
        json={"user_id": target.id},
    )
    assert resp.status_code == 403, resp.text
    assert resp.json()["detail"] == "Permission denied: team:invite"


async def test_project_mutations_require_team_manager(client):
    """项目改删 = 团队 OWNER/ADMIN（TASK-029 决策 3）。"""
    w = await _make_world()
    h_member = w.headers("tmember")
    h_admin = w.headers("tadmin")

    # 团队 MEMBER（全局 admin）：资源级 403
    resp = await client.patch(
        f"/api/v1/projects/{w.project_id}", headers=h_member, json={"name": "x"}
    )
    assert resp.status_code == 403, resp.text
    assert (
        resp.json()["detail"] == "Only team owner or admin can manage projects"
    )
    resp = await client.delete(f"/api/v1/projects/{w.project_id}", headers=h_member)
    assert resp.status_code == 403, resp.text

    # 团队 ADMIN（全局 admin）：可改
    resp = await client.patch(
        f"/api/v1/projects/{w.project_id}",
        headers=h_admin,
        json={"description": "by tadmin"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["description"] == "by tadmin"


# --- IDOR 404 契约与可见性翻转 ------------------------------------------------------


async def test_outsider_idor_404_contract(client):
    """归属链外的全局 admin：读/改/删全部 404，与「不存在」同文案。"""
    w = await _make_world()
    h = w.headers("outsider")

    cases = [
        ("get", f"/api/v1/teams/{w.team_id}", None, "Team not found"),
        ("patch", f"/api/v1/teams/{w.team_id}", {"name": "x"}, "Team not found"),
        ("delete", f"/api/v1/teams/{w.team_id}", None, "Team not found"),
        ("get", f"/api/v1/projects/{w.project_id}", None, "Project not found"),
        ("patch", f"/api/v1/projects/{w.project_id}", {"name": "x"}, "Project not found"),
        ("delete", f"/api/v1/projects/{w.project_id}", None, "Project not found"),
    ]
    for method, path, body, message in cases:
        kwargs = {"headers": h}
        if body is not None:
            kwargs["json"] = body
        resp = await getattr(client, method)(path, **kwargs)
        assert resp.status_code == 404, (method, path, resp.text)
        assert resp.json()["detail"] == message, (method, path)

    # 列表也不泄露：outsider 看不到 T 与其项目
    teams = await client.get("/api/v1/teams", headers=h)
    assert teams.json()["data"] == []
    projects = await client.get("/api/v1/projects", headers=h)
    assert projects.json()["data"] == []


async def test_visibility_flips_after_invite(client):
    """被邀请入队后可见性即刻翻转：outsider → 团队成员。"""
    w = await _make_world()
    h = w.headers("outsider")

    before = await client.get(f"/api/v1/projects/{w.project_id}", headers=h)
    assert before.status_code == 404, before.text

    invited = await client.post(
        f"/api/v1/teams/{w.team_id}/members",
        headers=w.headers("owner"),
        json={"user_id": w.users["outsider"].id},
    )
    assert invited.status_code == 201, invited.text

    after = await client.get(f"/api/v1/projects/{w.project_id}", headers=h)
    assert after.status_code == 200, after.text
    teams = await client.get("/api/v1/teams", headers=h)
    assert [t["id"] for t in teams.json()["data"]] == [w.team_id]


async def test_no_role_user_403_on_every_endpoint(client):
    """无全局角色：所有端点被功能级 403 挡在归属判定之前。"""
    w = await _make_world()
    h = w.headers("nobody")

    expected_first = [
        ("get", "/api/v1/teams", None, "Permission denied: team:read"),
        ("get", f"/api/v1/teams/{w.team_id}", None, "Permission denied: team:read"),
        ("get", "/api/v1/projects", None, "Permission denied: project:read"),
        (
            "get",
            f"/api/v1/projects/{w.project_id}",
            None,
            "Permission denied: project:read",
        ),
    ]
    for method, path, body, detail in expected_first:
        kwargs = {"headers": h}
        if body is not None:
            kwargs["json"] = body
        resp = await getattr(client, method)(path, **kwargs)
        assert resp.status_code == 403, (method, path, resp.text)
        assert resp.json()["detail"] == detail, (method, path)
