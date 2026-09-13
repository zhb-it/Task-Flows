"""TASK-028：成员管理 HTTP 端到端验收（真实产品应用 + 真实 Token 认证链）。

与 TASK-027 同模式：对 `app.main.app` 走完整链路，仅覆盖 `get_db` 指向测试库。

验证重点（双层判定 = 全局 team:invite/team:read × 团队角色 OWNER/ADMIN）：
- 全局权限缺失 → 403 先于一切（含团队 ADMIN 无全局权限仍 403）；
- 团队角色不足（有全局权限但只是 MEMBER）→ 403；
- 团队不在归属链 → 404；目标用户不存在 → 404；重复邀请 → 409；
- role 仅 admin/member（"owner" → 422）；
- 移除层级 OWNER > ADMIN > MEMBER；owner 不可被移除；
- 成员列表团队成员可见。

零残留：先删团队（owner_id RESTRICT）再删用户。
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
from app.crud.team import add_team_member, get_team, get_team_member
from app.crud.user import create_user
from app.db.session import get_db
from app.main import app
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
    return f"tmemapi_{RUN_TOKEN}_{tag}"


def _team_name(tag: str) -> str:
    return f"tmemapi {RUN_TOKEN} {tag}"


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
            delete(Team).where(Team.name.like(f"tmemapi {RUN_TOKEN}%"))
        )
        await session.execute(
            delete(User).where(User.username.like(f"tmemapi_{RUN_TOKEN}%"))
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


async def _create_team(owner_id: int, tag: str) -> int:
    """直接经 Service 建队（owner_id = owner_id），绕过 HTTP 减少耦合。"""
    from app.schemas.team import TeamCreate
    from app.services.team import create_team

    async with SessionFactory() as session:
        user = await session.get(User, owner_id)
        team = await create_team(session, user, TeamCreate(name=_team_name(tag)))
        await session.commit()
        return team.id


# --- POST /teams/{team_id}/members ------------------------------------------------


async def test_invite_returns_201_with_member_row(client):
    owner = await _make_user("owner", ["admin"])
    target = await _make_user("target")
    team_id = await _create_team(owner.id, "inv")

    resp = await client.post(
        f"/api/v1/teams/{team_id}/members",
        headers=_bearer(create_access_token(owner.id)),
        json={"user_id": target.id},
    )
    assert resp.status_code == status.HTTP_201_CREATED, resp.text
    data = resp.json()["data"]
    assert data["user_id"] == target.id
    assert data["username"] == target.username
    assert data["role"] == "member"
    assert data["team_id"] == team_id

    async with SessionFactory() as session:
        row = await get_team_member(session, team_id=team_id, user_id=target.id)
    assert row is not None and row.role_id == TeamRole.MEMBER.value


async def test_invite_with_admin_role_and_owner_role_rejected(client):
    owner = await _make_user("owner2", ["admin"])
    target = await _make_user("target2")
    team_id = await _create_team(owner.id, "inv2")
    headers = _bearer(create_access_token(owner.id))

    ok = await client.post(
        f"/api/v1/teams/{team_id}/members",
        headers=headers,
        json={"user_id": target.id, "role": "admin"},
    )
    assert ok.status_code == 201, ok.text
    assert ok.json()["data"]["role"] == "admin"

    owner_role = await client.post(
        f"/api/v1/teams/{team_id}/members",
        headers=headers,
        json={"user_id": 999_999_998, "role": "owner"},
    )
    assert owner_role.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


async def test_invite_without_global_permission_403_even_for_team_admin(client):
    """双层判定：团队 ADMIN 但无全局 team:invite → 403（功能层先行）。"""
    owner = await _make_user("owner3", ["admin"])
    team_admin = await _make_user("tadmin3")  # 无全局角色
    target = await _make_user("target3")
    team_id = await _create_team(owner.id, "inv3")

    async with SessionFactory() as session:
        await add_team_member(
            session,
            team_id=team_id,
            user_id=team_admin.id,
            role_id=TeamRole.ADMIN.value,
        )
        await session.commit()

    resp = await client.post(
        f"/api/v1/teams/{team_id}/members",
        headers=_bearer(create_access_token(team_admin.id)),
        json={"user_id": target.id},
    )
    assert resp.status_code == 403, resp.text
    assert resp.json()["detail"] == "Permission denied: team:invite"


async def test_invite_global_admin_but_plain_member_403(client):
    """双层判定：有全局 team:invite 但团队角色只是 MEMBER → 403。"""
    owner = await _make_user("owner4", ["admin"])
    plain = await _make_user("plain4", ["admin"])
    target = await _make_user("target4")
    team_id = await _create_team(owner.id, "inv4")

    async with SessionFactory() as session:
        await add_team_member(
            session,
            team_id=team_id,
            user_id=plain.id,
            role_id=TeamRole.MEMBER.value,
        )
        await session.commit()

    resp = await client.post(
        f"/api/v1/teams/{team_id}/members",
        headers=_bearer(create_access_token(plain.id)),
        json={"user_id": target.id},
    )
    assert resp.status_code == 403, resp.text
    assert resp.json()["detail"] == "Only team owner or admin can manage members"


async def test_invite_duplicate_409_and_missing_user_404(client):
    owner = await _make_user("owner5", ["admin"])
    target = await _make_user("target5")
    team_id = await _create_team(owner.id, "inv5")
    headers = _bearer(create_access_token(owner.id))

    dup = await client.post(
        f"/api/v1/teams/{team_id}/members", headers=headers, json={"user_id": target.id}
    )
    assert dup.status_code == 201
    dup2 = await client.post(
        f"/api/v1/teams/{team_id}/members", headers=headers, json={"user_id": target.id}
    )
    assert dup2.status_code == 409, dup2.text
    assert dup2.json()["detail"] == "User is already a team member"

    missing = await client.post(
        f"/api/v1/teams/{team_id}/members",
        headers=headers,
        json={"user_id": 999_999_999},
    )
    assert missing.status_code == 404, missing.text
    assert missing.json()["detail"] == "User not found"


async def test_invite_to_invisible_team_404(client):
    owner = await _make_user("owner6", ["admin"])
    outsider = await _make_user("out6", ["admin"])
    target = await _make_user("target6")
    team_id = await _create_team(owner.id, "inv6")

    resp = await client.post(
        f"/api/v1/teams/{team_id}/members",
        headers=_bearer(create_access_token(outsider.id)),
        json={"user_id": target.id},
    )
    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"] == "Team not found"


# --- GET /teams/{team_id}/members --------------------------------------------------


async def test_list_members_visible_to_team_members_only(client):
    owner = await _make_user("owner7", ["admin"])
    outsider = await _make_user("out7", ["admin"])
    # 被邀请者持有全局 member 角色（team:read），验证资源级可见性
    target = await _make_user("target7", ["member"])
    team_id = await _create_team(owner.id, "list7")

    inv = await client.post(
        f"/api/v1/teams/{team_id}/members",
        headers=_bearer(create_access_token(owner.id)),
        json={"user_id": target.id, "role": "admin"},
    )
    assert inv.status_code == 201

    # 团队成员（owner + 新邀请的 admin）可见
    for uid in (owner.id, target.id):
        resp = await client.get(
            f"/api/v1/teams/{team_id}/members",
            headers=_bearer(create_access_token(uid)),
        )
        assert resp.status_code == 200, resp.text
        members = resp.json()["data"]
        roles = {m["username"]: m["role"] for m in members}
        assert roles[owner.username] == "owner"
        assert roles[target.username] == "admin"

    # 局外人（有 team:read 但不在归属链）404
    out = await client.get(
        f"/api/v1/teams/{team_id}/members",
        headers=_bearer(create_access_token(outsider.id)),
    )
    assert out.status_code == 404, out.text
    assert out.json()["detail"] == "Team not found"

    # 无全局角色者（团队成员资格之外先卡功能层）403
    plain = await _make_user("plain7")
    no_perm = await client.get(
        f"/api/v1/teams/{team_id}/members",
        headers=_bearer(create_access_token(plain.id)),
    )
    assert no_perm.status_code == 403, no_perm.text


# --- DELETE /teams/{team_id}/members/{user_id} -------------------------------------


async def test_owner_removes_member_via_api(client):
    owner = await _make_user("owner8", ["admin"])
    target = await _make_user("target8", ["member"])  # 有 team:read，可验证可见性翻转
    team_id = await _create_team(owner.id, "rm8")
    headers = _bearer(create_access_token(owner.id))

    await client.post(
        f"/api/v1/teams/{team_id}/members", headers=headers, json={"user_id": target.id}
    )
    resp = await client.delete(
        f"/api/v1/teams/{team_id}/members/{target.id}", headers=headers
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"] is None

    async with SessionFactory() as session:
        assert await get_team_member(session, team_id=team_id, user_id=target.id) is None
    # 被移除者：过得了功能层（team:read），但已不在归属链 → 404
    after = await client.get(
        f"/api/v1/teams/{team_id}", headers=_bearer(create_access_token(target.id))
    )
    assert after.status_code == 404


async def test_remove_hierarchy_enforced_via_api(client):
    """全局 admin + 团队 ADMIN：可移除 MEMBER，不可移除另一 ADMIN / owner。"""
    owner = await _make_user("owner9", ["admin"])
    team_admin = await _make_user("tadmin9", ["admin"])
    other_admin = await _make_user("tadmin9b")
    plain = await _make_user("plain9")
    team_id = await _create_team(owner.id, "rm9")

    async with SessionFactory() as session:
        for uid, role in (
            (team_admin.id, TeamRole.ADMIN),
            (other_admin.id, TeamRole.ADMIN),
            (plain.id, TeamRole.MEMBER),
        ):
            await add_team_member(
                session, team_id=team_id, user_id=uid, role_id=role.value
            )
        await session.commit()

    headers = _bearer(create_access_token(team_admin.id))
    ok = await client.delete(
        f"/api/v1/teams/{team_id}/members/{plain.id}", headers=headers
    )
    assert ok.status_code == 200, ok.text

    denied_admin = await client.delete(
        f"/api/v1/teams/{team_id}/members/{other_admin.id}", headers=headers
    )
    assert denied_admin.status_code == 403
    assert denied_admin.json()["detail"] == "Team admin can only remove members"

    denied_owner = await client.delete(
        f"/api/v1/teams/{team_id}/members/{owner.id}", headers=headers
    )
    assert denied_owner.status_code == 403
    assert denied_owner.json()["detail"] == "Team owner cannot be removed"

    # plain member（无全局权限）尝试移除 → 403 功能层
    plain_resp = await client.delete(
        f"/api/v1/teams/{team_id}/members/{owner.id}",
        headers=_bearer(create_access_token(plain.id)),
    )
    assert plain_resp.status_code == 403
    assert plain_resp.json()["detail"] == "Permission denied: team:invite"


async def test_remove_missing_member_404(client):
    owner = await _make_user("owner10", ["admin"])
    team_id = await _create_team(owner.id, "rm10")

    resp = await client.delete(
        f"/api/v1/teams/{team_id}/members/999999999",
        headers=_bearer(create_access_token(owner.id)),
    )
    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"] == "Team member not found"
