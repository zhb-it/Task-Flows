"""TASK-041：Comment API HTTP 端到端验收（真实产品应用 + 真实 Token 认证链）。

与 test_operation_log_api.py 同模式：对 `app.main.app` 走完整链路，仅覆盖
`get_db` 指向测试库。规格 §16 四条规则 + §25.6 三端点 + TASK-041 用户确认决策：

- `POST /tasks/{task_id}/comments`：功能级 `comment:create`（admin/member 均持有）
  + 资源级归属链（非成员/不存在 404 防枚举）；
- `GET /tasks/{task_id}/comments`：功能级 `task:read`（§6 无 comment:read，
  读评论复用读任务）+ 资源级归属链；时间升序；
- `DELETE /comments/{comment_id}`：功能级 `comment:delete`（种子仅 admin）+
  资源级**作者本人或任务所属团队 OWNER/ADMIN**，否则 403；不在链/不存在 404；
- 删除行为写入 OperationLog（`action=comment:delete`）。

零残留：审计日志 → 评论 → 任务 → 项目 → 团队 → 用户 精确拆除。
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
from app.models.comment import Comment
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
    return f"cmt_{RUN_TOKEN}_{tag}"


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
            delete(OperationLog).where(
                OperationLog.user_id.in_(
                    select(User.id).where(User.username.like(f"cmt_{RUN_TOKEN}%"))
                )
            )
        )
        await session.execute(
            delete(Comment).where(Comment.user_id.in_(
                select(User.id).where(User.username.like(f"cmt_{RUN_TOKEN}%"))
            ))
        )
        await session.execute(
            delete(Task).where(Task.title.like(f"cmt {RUN_TOKEN}%"))
        )
        await session.execute(
            delete(Project).where(Project.name.like(f"cmt proj {RUN_TOKEN}%"))
        )
        await session.execute(
            delete(Team).where(Team.name.like(f"cmt team {RUN_TOKEN}%"))
        )
        await session.execute(
            delete(User).where(User.username.like(f"cmt_{RUN_TOKEN}%"))
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
            session, owner, TeamCreate(name=f"cmt team {RUN_TOKEN} {tag}")
        )
        project = await create_project(
            session,
            name=f"cmt proj {RUN_TOKEN} {tag}",
            description=None,
            team_id=team.id,
            owner_id=owner.id,
        )
        await session.commit()
        await session.refresh(project)
        return project


async def _add_member(project: Project, user: User, role_id: int = 3) -> None:
    from app.crud.team import add_team_member

    async with SessionFactory() as session:
        await add_team_member(
            session, team_id=project.team_id, user_id=user.id, role_id=role_id
        )
        await session.commit()


async def _create_task(client, owner: User, project: Project, tag: str) -> int:
    resp = await client.post(
        "/api/v1/tasks",
        headers=_bearer(create_access_token(owner.id)),
        json={"project_id": project.id, "title": f"cmt {RUN_TOKEN} {tag}"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]["id"]


async def _post_comment(client, user: User, task_id: int, content: str):
    return await client.post(
        f"/api/v1/tasks/{task_id}/comments",
        headers=_bearer(create_access_token(user.id)),
        json={"content": content},
    )


# --- 创建 + 列表 ----------------------------------------------------------------


async def test_create_and_list_comments(client):
    owner = await _make_user("owner1", ["admin"])
    project = await _make_project(owner, "c1")
    task_id = await _create_task(client, owner, project, "c1")

    resp = await _post_comment(client, owner, task_id, "first comment")
    assert resp.status_code == 201, resp.text
    body = resp.json()["data"]
    assert body["task_id"] == task_id
    assert body["user_id"] == owner.id
    assert body["username"] == _username("owner1")
    assert body["content"] == "first comment"
    assert body["created_at"] == body["updated_at"]

    resp = await client.get(
        f"/api/v1/tasks/{task_id}/comments",
        headers=_bearer(create_access_token(owner.id)),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert len(data) == 1
    assert data[0]["id"] == body["id"]
    assert data[0]["username"] == _username("owner1")


async def test_comments_listed_in_time_order(client):
    owner = await _make_user("owner2", ["admin"])
    project = await _make_project(owner, "c2")
    task_id = await _create_task(client, owner, project, "c2")

    for i in range(3):
        assert (
            await _post_comment(client, owner, task_id, f"c{i}")
        ).status_code == 201

    resp = await client.get(
        f"/api/v1/tasks/{task_id}/comments",
        headers=_bearer(create_access_token(owner.id)),
    )
    contents = [c["content"] for c in resp.json()["data"]]
    assert contents == ["c0", "c1", "c2"]


# --- 权限：功能级 403 / 资源级 404 ----------------------------------------------


async def test_create_requires_permission_403(client):
    norole = await _make_user("norole3")  # 无任何角色
    owner = await _make_user("owner3", ["admin"])
    project = await _make_project(owner, "c3")
    task_id = await _create_task(client, owner, project, "c3")

    resp = await _post_comment(client, norole, task_id, "nope")
    assert resp.status_code == 403, resp.text
    assert resp.json()["detail"] == "Permission denied: comment:create"


async def test_outsider_and_nonexistent_task_404(client):
    owner = await _make_user("owner4", ["admin"])
    outsider = await _make_user("outsider4", ["member"])
    project = await _make_project(owner, "c4")
    task_id = await _create_task(client, owner, project, "c4")

    # 局外人对他人任务评论 → 404（防枚举）
    resp = await _post_comment(client, outsider, task_id, "hi")
    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"] == "Task not found"

    # 不存在的任务 → 同文案 404
    resp = await _post_comment(client, owner, 999999999, "hi")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Task not found"

    # 列表亦 404
    resp = await client.get(
        f"/api/v1/tasks/{task_id}/comments",
        headers=_bearer(create_access_token(outsider.id)),
    )
    assert resp.status_code == 404


# --- 删除：作者 / 团队管理者 / 功能级 403 ---------------------------------------


async def test_author_deletes_own_comment_200_writes_audit(client):
    author = await _make_user("author5", ["admin"])
    project = await _make_project(author, "c5")
    task_id = await _create_task(client, author, project, "c5")
    comment_id = (await _post_comment(client, author, task_id, "mine")).json()["data"]["id"]

    resp = await client.delete(
        f"/api/v1/comments/{comment_id}",
        headers=_bearer(create_access_token(author.id)),
    )
    assert resp.status_code == 200, resp.text

    # §16 规则 4：删除写入操作日志
    resp = await client.get(
        f"/api/v1/logs/comment/{comment_id}",
        headers=_bearer(create_access_token(author.id)),
    )
    # comment 资源类型在 TASK-039 仅 task 支持查询 → 404；
    # 改用直连库核对审计行（下同）
    async with SessionFactory() as session:
        result = await session.execute(
            select(OperationLog).where(
                OperationLog.resource_type == "comment",
                OperationLog.resource_id == comment_id,
            )
        )
        logs = list(result.scalars().all())
    assert len(logs) == 1
    assert logs[0].action == "comment:delete"
    assert logs[0].user_id == author.id
    assert logs[0].payload == {"task_id": task_id, "comment_id": comment_id}

    # 评论已删除
    async with SessionFactory() as session:
        result = await session.execute(
            select(Comment).where(Comment.id == comment_id)
        )
        assert result.scalar_one_or_none() is None


async def test_team_admin_deletes_others_comment_200(client):
    owner = await _make_user("owner6", ["admin"])
    tadmin = await _make_user("tadmin6", ["admin"])
    author = await _make_user("author6", ["admin"])
    project = await _make_project(owner, "c6")
    await _add_member(project, tadmin, role_id=2)  # 团队 ADMIN
    await _add_member(project, author, role_id=3)  # 团队 MEMBER

    task_id = await _create_task(client, owner, project, "c6")
    comment_id = (
        await _post_comment(client, author, task_id, "by author")
    ).json()["data"]["id"]

    # 团队 ADMIN 可删他人评论
    resp = await client.delete(
        f"/api/v1/comments/{comment_id}",
        headers=_bearer(create_access_token(tadmin.id)),
    )
    assert resp.status_code == 200, resp.text


async def test_member_cannot_delete_others_comment_403(client):
    owner = await _make_user("owner7", ["admin"])
    author = await _make_user("author7", ["admin"])
    member = await _make_user("member7", ["admin"])
    project = await _make_project(owner, "c7")
    await _add_member(project, author, role_id=3)
    await _add_member(project, member, role_id=3)  # 团队 MEMBER

    task_id = await _create_task(client, owner, project, "c7")
    comment_id = (
        await _post_comment(client, author, task_id, "by author")
    ).json()["data"]["id"]

    # 团队成员（非作者、非管理者）删他人评论 → 403
    resp = await client.delete(
        f"/api/v1/comments/{comment_id}",
        headers=_bearer(create_access_token(member.id)),
    )
    assert resp.status_code == 403, resp.text
    assert resp.json()["detail"] == (
        "Only team owner or admin or the comment author can delete comments"
    )


async def test_delete_missing_permission_403(client):
    """功能级 comment:delete 仅 admin 持有——member 全局角色被 403 挡下。"""
    owner = await _make_user("owner8", ["admin"])
    author = await _make_user("author8", ["member"])  # 有 comment:create 无 delete
    project = await _make_project(owner, "c8")
    await _add_member(project, author, role_id=3)

    task_id = await _create_task(client, owner, project, "c8")
    resp = await _post_comment(client, author, task_id, "mine")
    assert resp.status_code == 201
    comment_id = resp.json()["data"]["id"]

    # member 是作者本人，但功能级无 comment:delete → 403（先于资源级判定）
    resp = await client.delete(
        f"/api/v1/comments/{comment_id}",
        headers=_bearer(create_access_token(author.id)),
    )
    assert resp.status_code == 403, resp.text
    assert resp.json()["detail"] == "Permission denied: comment:delete"


async def test_delete_outsider_and_nonexistent_404(client):
    owner = await _make_user("owner9", ["admin"])
    outsider = await _make_user("outsider9", ["admin"])
    project = await _make_project(owner, "c9")
    task_id = await _create_task(client, owner, project, "c9")
    comment_id = (
        await _post_comment(client, owner, task_id, "hi")
    ).json()["data"]["id"]

    for cid, tag in ((comment_id, "他人评论"), (999999999, "不存在")):
        resp = await client.delete(
            f"/api/v1/comments/{cid}",
            headers=_bearer(create_access_token(outsider.id)),
        )
        assert resp.status_code == 404, f"{tag}: {resp.text}"
        assert resp.json()["detail"] == "Comment not found"


# --- 请求体校验：422 -------------------------------------------------------------


async def test_create_comment_validation_422(client):
    owner = await _make_user("owner10", ["admin"])
    project = await _make_project(owner, "c10")
    task_id = await _create_task(client, owner, project, "c10")

    for payload, desc in (("", "空字符串"), ("x" * 2001, "超长")):
        resp = await client.post(
            f"/api/v1/tasks/{task_id}/comments",
            headers=_bearer(create_access_token(owner.id)),
            json={"content": payload},
        )
        assert resp.status_code == 422, f"{desc}: {resp.text}"

    # 缺字段
    resp = await client.post(
        f"/api/v1/tasks/{task_id}/comments",
        headers=_bearer(create_access_token(owner.id)),
        json={},
    )
    assert resp.status_code == 422


# --- 级联：删任务清评论 ----------------------------------------------------------


async def test_delete_task_cascades_comments(client):
    owner = await _make_user("owner11", ["admin"])
    project = await _make_project(owner, "c11")
    task_id = await _create_task(client, owner, project, "c11")
    comment_id = (
        await _post_comment(client, owner, task_id, "will cascade")
    ).json()["data"]["id"]

    resp = await client.delete(
        f"/api/v1/tasks/{task_id}",
        headers=_bearer(create_access_token(owner.id)),
    )
    assert resp.status_code == 200, resp.text

    async with SessionFactory() as session:
        result = await session.execute(
            select(Comment).where(Comment.id == comment_id)
        )
        assert result.scalar_one_or_none() is None
