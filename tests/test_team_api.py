"""TASK-027：团队 CRUD HTTP 端到端验收（真实产品应用）。

TASK-027 首次为产品应用挂载资源型路由，因此不再用探针应用——直接对
`app.main.app` 走完整链路：真实 `require_permission` 依赖（种子权限解析）+
真实 `get_current_user` 认证链（真实 Token），仅覆盖 `get_db` 指向测试库。

验证重点：
- 功能级 403（member 无 team:create/update/delete）先于资源级 404；
- 资源级 404（非 owner / 他人团队 / 不存在）文案相同、不可区分；
- 创建自动写 OWNER 成员行；列表只返回「我参与的团队」；
- PATCH 部分更新语义（exclude_unset）与 422 校验；
- DELETE 后团队与成员行消失。

零残留：团队/用户按「本次运行唯一前缀」创建，teardown 先删团队（owner_id
RESTRICT）再删用户。
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
from app.crud.team import get_team, get_team_member
from app.crud.user import create_user
from app.db.session import get_db
from app.main import app
from app.models.team import Team
from app.models.team_member import TeamRole
from app.models.user import User
from app.schemas.team import TeamUpdate

TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@127.0.0.1:5433/taskflow"

RUN_TOKEN = uuid.uuid4().hex[:10]
PASSWORD_HASH = "h"

engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
SessionFactory = async_sessionmaker(engine, expire_on_commit=False)


async def _override_get_db():
    async with SessionFactory() as session:
        yield session


def _username(tag: str) -> str:
    return f"teamapi_{RUN_TOKEN}_{tag}"


def _team_name(tag: str) -> str:
    return f"teamapi {RUN_TOKEN} {tag}"


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
            delete(Team).where(Team.name.like(f"teamapi {RUN_TOKEN}%"))
        )
        await session.execute(
            delete(User).where(User.username.like(f"teamapi_{RUN_TOKEN}%"))
        )
        await session.commit()


async def _make_user(tag: str, role_names: list[str] | None = None) -> User:
    """创建用户并授予种子角色（只读种子，只写 user_roles 关联）。"""
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


async def _change_owner(team_id: int, new_owner_id: int) -> None:
    """直接改库转移 ownership（模拟后续 TASK 的转让能力，仅测试用）。"""
    async with SessionFactory() as session:
        team = await get_team(session, team_id)
        assert team is not None
        team.owner_id = new_owner_id
        await session.commit()


# --- 离线：路由注册与 Schema 契约 ------------------------------------------------


def test_team_routes_registered_on_product_app():
    # 本 FastAPI 版本的 include_router 是嵌套式（app.routes 中的 _IncludedRouter），
    # 离线遍历看不到扁平路径；openapi schema 在生成时完整展开，适合做注册断言。
    paths = set(app.openapi()["paths"])
    assert "/api/v1/teams" in paths
    assert "/api/v1/teams/{team_id}" in paths


def test_team_update_schema_exclude_unset_semantics():
    assert TeamUpdate().model_dump(exclude_unset=True) == {}
    assert TeamUpdate(name="a").model_dump(exclude_unset=True) == {"name": "a"}
    assert TeamUpdate(description=None).model_dump(exclude_unset=True) == {
        "description": None
    }


# --- POST /api/v1/teams ----------------------------------------------------------


async def test_create_team_returns_201_and_writes_owner_row(client):
    admin = await _make_user("creator", ["admin"])
    resp = await client.post(
        "/api/v1/teams",
        headers=_bearer(create_access_token(admin.id)),
        json={"name": _team_name("created"), "description": "hello"},
    )
    assert resp.status_code == status.HTTP_201_CREATED, resp.text
    body = resp.json()
    assert body["message"] == "success"
    data = body["data"]
    assert data["name"] == _team_name("created")
    assert data["description"] == "hello"
    assert data["owner_id"] == admin.id
    assert data["id"] > 0
    assert data["created_at"] and data["updated_at"]

    # 决策 1：team_members 自动写入 OWNER 行
    async with SessionFactory() as session:
        member = await get_team_member(
            session, team_id=data["id"], user_id=admin.id
        )
    assert member is not None
    assert member.role_id == TeamRole.OWNER.value


async def test_create_team_member_forbidden_403(client):
    member = await _make_user("m_creator", ["member"])
    resp = await client.post(
        "/api/v1/teams",
        headers=_bearer(create_access_token(member.id)),
        json={"name": _team_name("denied")},
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN, resp.text
    assert resp.json()["detail"] == "Permission denied: team:create"


async def test_create_team_unauthenticated_401(client):
    resp = await client.post("/api/v1/teams", json={"name": "x"})
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED, resp.text
    assert resp.headers["www-authenticate"] == "Bearer"


async def test_create_team_validation_422(client):
    admin = await _make_user("validator", ["admin"])
    headers = _bearer(create_access_token(admin.id))
    empty = await client.post(
        "/api/v1/teams", headers=headers, json={"name": ""}
    )
    assert empty.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    too_long = await client.post(
        "/api/v1/teams", headers=headers, json={"name": "x" * 151}
    )
    assert too_long.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    desc_too_long = await client.post(
        "/api/v1/teams",
        headers=headers,
        json={"name": _team_name("ok"), "description": "d" * 256},
    )
    assert desc_too_long.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


# --- GET /api/v1/teams（决策 3：列表 = 我参与的团队）------------------------------


async def test_list_teams_shows_only_participating(client):
    owner = await _make_user("lister", ["admin"])
    outsider = await _make_user("lister_out", ["admin"])
    created = await client.post(
        "/api/v1/teams",
        headers=_bearer(create_access_token(owner.id)),
        json={"name": _team_name("listed")},
    )
    team_id = created.json()["data"]["id"]

    owner_list = await client.get(
        "/api/v1/teams", headers=_bearer(create_access_token(owner.id))
    )
    assert owner_list.status_code == 200
    ids = [t["id"] for t in owner_list.json()["data"]]
    assert team_id in ids

    outsider_list = await client.get(
        "/api/v1/teams", headers=_bearer(create_access_token(outsider.id))
    )
    assert outsider_list.status_code == 200
    assert team_id not in [t["id"] for t in outsider_list.json()["data"]]


async def test_list_teams_member_visibility(client):
    owner = await _make_user("l_owner", ["admin"])
    member = await _make_user("l_member", ["admin"])
    created = await client.post(
        "/api/v1/teams",
        headers=_bearer(create_access_token(owner.id)),
        json={"name": _team_name("shared")},
    )
    team_id = created.json()["data"]["id"]
    async with SessionFactory() as session:
        await add_member_row(session, team_id, member.id)
        await session.commit()

    resp = await client.get(
        "/api/v1/teams", headers=_bearer(create_access_token(member.id))
    )
    assert resp.status_code == 200
    assert team_id in [t["id"] for t in resp.json()["data"]]


async def add_member_row(session, team_id: int, user_id: int):
    from app.crud.team import add_team_member

    return await add_team_member(
        session,
        team_id=team_id,
        user_id=user_id,
        role_id=TeamRole.MEMBER.value,
    )


# --- GET /api/v1/teams/{team_id}（IDOR 契约）-------------------------------------


async def test_get_team_detail_owner_outsider_missing(client):
    owner = await _make_user("g_owner", ["admin"])
    outsider = await _make_user("g_out", ["admin"])
    created = await client.post(
        "/api/v1/teams",
        headers=_bearer(create_access_token(owner.id)),
        json={"name": _team_name("detail")},
    )
    team_id = created.json()["data"]["id"]

    ok = await client.get(
        f"/api/v1/teams/{team_id}", headers=_bearer(create_access_token(owner.id))
    )
    assert ok.status_code == 200
    assert ok.json()["data"]["name"] == _team_name("detail")

    forbidden = await client.get(
        f"/api/v1/teams/{team_id}",
        headers=_bearer(create_access_token(outsider.id)),
    )
    assert forbidden.status_code == 404
    missing = await client.get(
        "/api/v1/teams/999999999", headers=_bearer(create_access_token(owner.id))
    )
    assert missing.status_code == 404
    # IDOR 契约：他人团队与不存在不可区分
    assert forbidden.json()["detail"] == missing.json()["detail"] == "Team not found"


# --- PATCH /api/v1/teams/{team_id}（决策 2：仅 owner）-----------------------------


async def test_patch_owner_partial_update(client):
    owner = await _make_user("p_owner", ["admin"])
    created = await client.post(
        "/api/v1/teams",
        headers=_bearer(create_access_token(owner.id)),
        json={"name": _team_name("before"), "description": "old"},
    )
    team_id = created.json()["data"]["id"]
    headers = _bearer(create_access_token(owner.id))

    # 只改 description：name 不变
    resp = await client.patch(
        f"/api/v1/teams/{team_id}", headers=headers, json={"description": "new"}
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["name"] == _team_name("before")
    assert data["description"] == "new"

    # 显式 null：清空
    cleared = await client.patch(
        f"/api/v1/teams/{team_id}", headers=headers, json={"description": None}
    )
    assert cleared.status_code == 200
    assert cleared.json()["data"]["description"] is None

    # 改 name
    renamed = await client.patch(
        f"/api/v1/teams/{team_id}", headers=headers, json={"name": _team_name("after")}
    )
    assert renamed.status_code == 200
    assert renamed.json()["data"]["name"] == _team_name("after")


async def test_patch_non_owner_admin_404_but_member_403(client):
    """功能层与资源层各自判定：member 缺 team:update → 403（先于归属）；
    admin 有 team:update 但非 owner → 404（IDOR）。"""
    owner = await _make_user("patch_owner", ["admin"])
    member = await _make_user("patch_member", ["member"])
    other_admin = await _make_user("patch_admin", ["admin"])
    created = await client.post(
        "/api/v1/teams",
        headers=_bearer(create_access_token(owner.id)),
        json={"name": _team_name("patched")},
    )
    team_id = created.json()["data"]["id"]
    payload = {"name": _team_name("hijack")}

    member_resp = await client.patch(
        f"/api/v1/teams/{team_id}",
        headers=_bearer(create_access_token(member.id)),
        json=payload,
    )
    assert member_resp.status_code == 403
    assert member_resp.json()["detail"] == "Permission denied: team:update"

    admin_resp = await client.patch(
        f"/api/v1/teams/{team_id}",
        headers=_bearer(create_access_token(other_admin.id)),
        json=payload,
    )
    assert admin_resp.status_code == 404
    assert admin_resp.json()["detail"] == "Team not found"

    verify = await client.get(
        f"/api/v1/teams/{team_id}", headers=_bearer(create_access_token(owner.id))
    )
    assert verify.json()["data"]["name"] == _team_name("patched")


async def test_owner_without_team_update_permission_gets_403(client):
    """owner 但缺功能权限 → 403（功能层判定不因归属而豁免）。"""
    owner = await _make_user("plain_owner", [])
    created = await client.post(
        "/api/v1/teams",
        headers=_bearer(create_access_token(await _admin_id())),
        json={"name": _team_name("transferred")},
    )
    team_id = created.json()["data"]["id"]
    await _change_owner(team_id, owner.id)

    resp = await client.patch(
        f"/api/v1/teams/{team_id}",
        headers=_bearer(create_access_token(owner.id)),
        json={"name": _team_name("nope")},
    )
    assert resp.status_code == 403, resp.text
    assert resp.json()["detail"] == "Permission denied: team:update"


async def _admin_id() -> int:
    user = await _make_user("aux_admin", ["admin"])
    return user.id


# --- DELETE /api/v1/teams/{team_id}（决策 2：仅 owner）---------------------------


async def test_delete_owner_team_gone_with_members(client):
    owner = await _make_user("d_owner", ["admin"])
    created = await client.post(
        "/api/v1/teams",
        headers=_bearer(create_access_token(owner.id)),
        json={"name": _team_name("doomed")},
    )
    team_id = created.json()["data"]["id"]

    resp = await client.delete(
        f"/api/v1/teams/{team_id}", headers=_bearer(create_access_token(owner.id))
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["message"] == "success"
    assert resp.json()["data"] is None

    after = await client.get(
        f"/api/v1/teams/{team_id}", headers=_bearer(create_access_token(owner.id))
    )
    assert after.status_code == 404

    async with SessionFactory() as session:
        assert await get_team(session, team_id) is None
        assert (
            await get_team_member(session, team_id=team_id, user_id=owner.id) is None
        )


async def test_delete_non_owner_admin_404(client):
    owner = await _make_user("del_owner", ["admin"])
    other_admin = await _make_user("del_admin", ["admin"])
    created = await client.post(
        "/api/v1/teams",
        headers=_bearer(create_access_token(owner.id)),
        json={"name": _team_name("survivor")},
    )
    team_id = created.json()["data"]["id"]

    resp = await client.delete(
        f"/api/v1/teams/{team_id}",
        headers=_bearer(create_access_token(other_admin.id)),
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Team not found"

    still_there = await client.get(
        f"/api/v1/teams/{team_id}", headers=_bearer(create_access_token(owner.id))
    )
    assert still_there.status_code == 200


async def test_delete_missing_404(client):
    admin = await _make_user("del_missing", ["admin"])
    resp = await client.delete(
        "/api/v1/teams/999999999", headers=_bearer(create_access_token(admin.id))
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Team not found"
