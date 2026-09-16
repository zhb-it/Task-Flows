"""TASK-044：Phase 7（评论与附件）整合验收测试（纯测试任务，未改应用代码）。

定位与 TASK-040 一致——**不是**重复 TASK-041/042/043 的细粒度断言，而是补上
三个分散模块未整合的**跨模块验收链路**：

- **§16 评论四条规则**与 **§17 附件五项上传要求**在**同一任务**上并存时的行为；
- **§55.2 创建任务业务流程**中「验证 Permission → 写 OperationLog → 提交事务」
  这一形状在评论/附件写操作上的**事务原子性**（TESTING.md 优先级 #3）；
- **§48 安全要求**的跨模块一致性：认证 ≠ 授权、「知道 id 也不能越权」在评论与
  附件两个资源上必须表现**完全一致**（同文案 404、同判定的 401 vs 403）；
- **§57 最终验收标准**中 Comment / Attachment / Operation Log 三项的联合验收。

已覆盖面（不在此重复，见各文件）：
- `tests/test_comment_api.py`（TASK-041，11 项）——评论单模块细粒度；
- `tests/test_attachment_api.py`（TASK-042，27 项）——附件单模块细粒度；
- `tests/test_attachment_security.py`（TASK-043，19 项）——附件对抗性安全。

本文件要回答的是这些模块**放在一起**才暴露的问题：
1. 评论与附件的**审计日志同一张表、同一 action 命名空间**，混用时不串号；
2. 删除任务时**两类子资源同时级联**，且级联过程不留下悬挂的审计引用；
3. 同一个「局外人」对两类资源的越权表现必须**逐字节一致**（否则前端无法用
   统一逻辑处理 404）；
4. 删除权限的**层级差异**（评论=作者或管理者；附件=上传者或管理者）在同一
   团队阵容下必须同时成立——这是最容易在重构中被抹平的一条。

沿用既有模式：真实产品应用 + 真实 Token + 本次运行唯一前缀 + teardown 精确
删除（含 RESTRICT 全链与审计日志清理）。
"""

import io
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
from app.models.attachment import Attachment
from app.models.comment import Comment
from app.models.operation_log import OperationLog
from app.models.project import Project
from app.models.task import Task
from app.models.team import Team
from app.models.user import User
from app.services import storage as storage_service

TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@127.0.0.1:5433/taskflow"

RUN_TOKEN = uuid.uuid4().hex[:10]
PASSWORD_HASH = "h"

engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
SessionFactory = async_sessionmaker(engine, expire_on_commit=False)


async def _override_get_db():
    async with SessionFactory() as session:
        yield session


def _username(tag: str) -> str:
    return f"caflow_{RUN_TOKEN}_{tag}"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest_asyncio.fixture
async def storage_root(tmp_path):
    """把存储后端指向临时目录（全项目唯一注入点）。"""
    previous = storage_service._backend
    storage_service._backend = storage_service.LocalStorageBackend(tmp_path)
    yield tmp_path
    storage_service._backend = previous


@pytest_asyncio.fixture
async def client(storage_root):
    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c
    app.dependency_overrides.pop(get_db, None)


@pytest_asyncio.fixture(autouse=True)
async def _cleanup():
    """审计日志 → 附件 → 评论 → 任务 → 项目 → 团队 → 用户（RESTRICT 全链）。"""
    yield
    async with SessionFactory() as session:
        await session.execute(
            delete(OperationLog).where(
                OperationLog.user_id.in_(
                    select(User.id).where(User.username.like(f"caflow_{RUN_TOKEN}%"))
                )
            )
        )
        await session.execute(
            delete(Attachment).where(
                Attachment.uploader_id.in_(
                    select(User.id).where(User.username.like(f"caflow_{RUN_TOKEN}%"))
                )
            )
        )
        await session.execute(
            delete(Comment).where(
                Comment.user_id.in_(
                    select(User.id).where(User.username.like(f"caflow_{RUN_TOKEN}%"))
                )
            )
        )
        await session.execute(
            delete(Task).where(Task.title.like(f"caflow {RUN_TOKEN}%"))
        )
        await session.execute(
            delete(Project).where(Project.name.like(f"caflow proj {RUN_TOKEN}%"))
        )
        await session.execute(
            delete(Team).where(Team.name.like(f"caflow team {RUN_TOKEN}%"))
        )
        await session.execute(
            delete(User).where(User.username.like(f"caflow_{RUN_TOKEN}%"))
        )
        await session.commit()


# ---------------------------------------------------------------------------
# 造数helpers
# ---------------------------------------------------------------------------


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


async def _make_team_and_project(owner: User, tag: str) -> tuple[Team, Project]:
    from app.crud.project import create_project
    from app.schemas.team import TeamCreate
    from app.services.team import create_team as create_team_service

    async with SessionFactory() as session:
        team = await create_team_service(
            session, owner, TeamCreate(name=f"caflow team {RUN_TOKEN} {tag}")
        )
        project = await create_project(
            session,
            name=f"caflow proj {RUN_TOKEN} {tag}",
            description=None,
            team_id=team.id,
            owner_id=owner.id,
        )
        await session.commit()
        await session.refresh(team)
        await session.refresh(project)
        return team, project


async def _add_member(project_or_team, user: User, role_id: int = 3) -> None:
    """把用户以指定团队角色加入团队（``role_id``：1=OWNER 2=ADMIN 3=MEMBER）。"""
    from app.crud.team import add_team_member

    team_id = getattr(project_or_team, "team_id", None) or project_or_team.id
    async with SessionFactory() as session:
        await add_team_member(
            session, team_id=team_id, user_id=user.id, role_id=role_id
        )
        await session.commit()


async def _create_task(client, owner: User, project: Project, tag: str) -> int:
    resp = await client.post(
        "/api/v1/tasks",
        headers=_bearer(create_access_token(owner.id)),
        json={"project_id": project.id, "title": f"caflow {RUN_TOKEN} {tag}"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]["id"]


async def _post_comment(client, user: User, task_id: int, content: str):
    return await client.post(
        f"/api/v1/tasks/{task_id}/comments",
        headers=_bearer(create_access_token(user.id)),
        json={"content": content},
    )


async def _upload(client, user: User, task_id: int, *, filename: str, content: bytes):
    return await client.post(
        f"/api/v1/tasks/{task_id}/attachments",
        headers=_bearer(create_access_token(user.id)),
        files={"file": (filename, io.BytesIO(content), "application/octet-stream")},
    )


async def _logs_for(resource_type: str, resource_id: int) -> list[OperationLog]:
    async with SessionFactory() as session:
        result = await session.execute(
            select(OperationLog)
            .where(
                OperationLog.resource_type == resource_type,
                OperationLog.resource_id == resource_id,
            )
            .order_by(OperationLog.id)
        )
        return list(result.scalars().all())


async def _all_logs_for_users(user_ids: list[int]) -> list[OperationLog]:
    async with SessionFactory() as session:
        result = await session.execute(
            select(OperationLog).where(OperationLog.user_id.in_(user_ids))
        )
        return list(result.scalars().all())


async def _count(table, id_column, ids: list[int]) -> int:
    async with SessionFactory() as session:
        result = await session.execute(
            select(table).where(id_column.in_(ids))
        )
        return len(list(result.scalars().all()))


# ===========================================================================
# 1. §16 + §17 联合验收：同一任务上评论与附件并存
# ===========================================================================


async def test_comments_and_attachments_coexist_on_one_task(client, storage_root):
    """§57 验收：同一任务下评论与附件互不干扰，各自独立可枚举。"""
    owner = await _make_user("coex1", ["admin"])
    _team, project = await _make_team_and_project(owner, "coex1")
    task_id = await _create_task(client, owner, project, "coex1")

    # 交错写入：评论、附件、评论、附件 —— 验证两条时间线互不污染
    c1 = await _post_comment(client, owner, task_id, "first comment")
    assert c1.status_code == 201, c1.text
    a1 = await _upload(client, owner, task_id, filename="one.txt", content=b"one")
    assert a1.status_code == 201, a1.text
    c2 = await _post_comment(client, owner, task_id, "second comment")
    a2 = await _upload(client, owner, task_id, filename="two.pdf", content=b"%PDF")
    assert c2.status_code == 201 and a2.status_code == 201

    H = _bearer(create_access_token(owner.id))

    # 评论时间线只有评论
    resp = await client.get(f"/api/v1/tasks/{task_id}/comments", headers=H)
    assert resp.status_code == 200
    comments = resp.json()["data"]
    assert [c["content"] for c in comments] == ["first comment", "second comment"]
    assert all("filename" not in c for c in comments)

    # 附件列表只有附件
    resp = await client.get(f"/api/v1/tasks/{task_id}/attachments", headers=H)
    assert resp.status_code == 200
    atts = resp.json()["data"]
    assert [a["filename"] for a in atts] == ["one.txt", "two.pdf"]
    assert all("content" not in a for a in atts)

    # 磁盘上正好两个文件，且都属于该任务的目录
    files = [p for p in storage_root.rglob("*") if p.is_file()]
    assert len(files) == 2
    assert all(f"tasks/{task_id}" in str(p).replace("\\", "/") for p in files)


async def test_two_tasks_do_not_leak_into_each_other(client, storage_root):
    """§16 规则「评论必须属于任务」+ §17 同理——跨任务零串联。"""
    owner = await _make_user("iso1", ["admin"])
    _team, project = await _make_team_and_project(owner, "iso1")
    t1 = await _create_task(client, owner, project, "iso1-a")
    t2 = await _create_task(client, owner, project, "iso1-b")

    await _post_comment(client, owner, t1, "on task one")
    await _upload(client, owner, t1, filename="t1.txt", content=b"t1")
    await _post_comment(client, owner, t2, "on task two")
    await _upload(client, owner, t2, filename="t2.txt", content=b"t2")

    H = _bearer(create_access_token(owner.id))

    r1 = await client.get(f"/api/v1/tasks/{t1}/comments", headers=H)
    assert [c["content"] for c in r1.json()["data"]] == ["on task one"]
    r2 = await client.get(f"/api/v1/tasks/{t2}/comments", headers=H)
    assert [c["content"] for c in r2.json()["data"]] == ["on task two"]

    r1 = await client.get(f"/api/v1/tasks/{t1}/attachments", headers=H)
    assert [a["filename"] for a in r1.json()["data"]] == ["t1.txt"]
    r2 = await client.get(f"/api/v1/tasks/{t2}/attachments", headers=H)
    assert [a["filename"] for a in r2.json()["data"]] == ["t2.txt"]


# ===========================================================================
# 2. 审计日志：两类资源同表共存，action 命名空间不串号
# ===========================================================================


async def test_audit_namespaces_do_not_collide(client, storage_root):
    """评论删删除与附件删除写同一张表，action/resource_type 必须各归其位。"""
    owner = await _make_user("audit1", ["admin"])
    _team, project = await _make_team_and_project(owner, "audit1")
    task_id = await _create_task(client, owner, project, "audit1")

    cid = (await _post_comment(client, owner, task_id, "to delete")).json()["data"]["id"]
    aid = (
        await _upload(client, owner, task_id, filename="del.txt", content=b"x")
    ).json()["data"]["id"]

    H = _bearer(create_access_token(owner.id))
    assert (await client.delete(f"/api/v1/comments/{cid}", headers=H)).status_code == 200
    assert (
        await client.delete(f"/api/v1/attachments/{aid}", headers=H)
    ).status_code == 200

    clog = await _logs_for("comment", cid)
    alog = await _logs_for("attachment", aid)

    assert len(clog) == 1
    assert clog[0].action == "comment:delete"
    assert clog[0].payload == {"task_id": task_id, "comment_id": cid}

    assert len(alog) == 1
    assert alog[0].action == "attachment:delete"
    assert alog[0].payload == {
        "task_id": task_id,
        "attachment_id": aid,
        "filename": "del.txt",
    }

    # 交叉检查：comment 的 id 空间与 attachment 的 id 空间可能重号，
    # 但 resource_type 必须把它们分开（这正是索引 (type,id) 的意义）
    assert clog[0].resource_type != alog[0].resource_type


async def test_creating_comment_and_uploading_do_not_write_audit_logs(
    client, storage_root
):
    """契约：只有**删除**写审计日志（§16 规则 4 / TASK-041 决策）。

    创建评论与上传附件都不写日志——把它固定下来，防止后续有人「顺手加审计」
    改变 §15 的语义边界（审计的是破坏性/状态性操作，不是普通写入）。
    """
    owner = await _make_user("noaudit1", ["admin"])
    _team, project = await _make_team_and_project(owner, "noaudit1")
    task_id = await _create_task(client, owner, project, "noaudit1")

    await _post_comment(client, owner, task_id, "no log expected")
    await _upload(client, owner, task_id, filename="nolog.txt", content=b"x")

    logs = await _all_logs_for_users([owner.id])
    comment_actions = [log for log in logs if log.resource_type == "comment"]
    attach_actions = [log for log in logs if log.resource_type == "attachment"]
    assert comment_actions == []
    assert attach_actions == []


# ===========================================================================
# 3. §48：认证 ≠ 授权，两类资源的越权表现必须逐字节一致
# ===========================================================================


async def test_outsider_gets_byte_identical_404_on_both_resources(
    client, storage_root
):
    """§48/§49：局外人对评论与附件的越权响应必须完全一致。

    前端要用统一逻辑区分「无权限(403)」与「不存在(404)」。若两类资源在
    「不在归属链」时给出不同文案，前端就得为每种资源写特例——这是设计缺陷。
    """
    ins = await _make_user("outs1", ["admin"])
    out = await _make_user("outs2", ["admin"])
    _team, project = await _make_team_and_project(ins, "outs1")
    task_id = await _create_task(client, ins, project, "outs1")

    cid = (
        await _post_comment(client, ins, task_id, "secret")
    ).json()["data"]["id"]
    aid = (
        await _upload(client, ins, task_id, filename="secret.txt", content=b"s")
    ).json()["data"]["id"]

    HO = _bearer(create_access_token(out.id))

    # 对不存在 id 的响应
    ghost_c = await client.delete("/api/v1/comments/99999999", headers=HO)
    ghost_a = await client.delete("/api/v1/attachments/99999999", headers=HO)
    ghost_dl = await client.get("/api/v1/attachments/99999999", headers=HO)
    ghost_list_c = await client.get("/api/v1/tasks/99999999/comments", headers=HO)
    ghost_list_a = await client.get("/api/v1/tasks/99999999/attachments", headers=HO)

    # 对真实 id 但不在归属链的响应
    real_c = await client.delete(f"/api/v1/comments/{cid}", headers=HO)
    real_a = await client.delete(f"/api/v1/attachments/{aid}", headers=HO)
    real_dl = await client.get(f"/api/v1/attachments/{aid}", headers=HO)

    # 全部 404
    for label, r in [
        ("ghost comment delete", ghost_c),
        ("ghost attachment delete", ghost_a),
        ("ghost attachment download", ghost_dl),
        ("ghost comment list", ghost_list_c),
        ("ghost attachment list", ghost_list_a),
        ("real comment delete", real_c),
        ("real attachment delete", real_a),
        ("real attachment download", real_dl),
    ]:
        assert r.status_code == 404, f"{label}: {r.status_code} {r.text[:120]}"

    # 「不存在」与「存在但无权」同文案（防枚举）
    assert ghost_c.json()["detail"] == real_c.json()["detail"] == "Comment not found"
    assert (
        ghost_a.json()["detail"]
        == real_a.json()["detail"]
        == real_dl.json()["detail"]
        == "Attachment not found"
    )
    assert (
        ghost_list_c.json()["detail"]
        == ghost_list_a.json()["detail"]
        == "Task not found"
    )

    # 关键：响应体里不含任何资源标识/内容片段
    blob = " ".join(
        r.text for r in [ghost_c, real_c, ghost_a, real_a, real_dl]
    )
    assert "secret" not in blob
    assert str(cid) not in real_c.text or "not found" in real_c.text
    assert "storage" not in blob.lower()
    assert "traceback" not in blob.lower()


async def test_unauthenticated_is_401_on_every_phase7_endpoint(client, storage_root):
    """§48 认证 ≠ 授权：无 Token → 401（不是 404/403），且 5 个端点一致。"""
    ins = await _make_user("unauth1", ["admin"])
    _team, project = await _make_team_and_project(ins, "unauth1")
    task_id = await _create_task(client, ins, project, "unauth1")
    aid = (
        await _upload(client, ins, task_id, filename="u.txt", content=b"u")
    ).json()["data"]["id"]

    results = {
        "post comment": await client.post(
            f"/api/v1/tasks/{task_id}/comments", json={"content": "x"}
        ),
        "list comments": await client.get(f"/api/v1/tasks/{task_id}/comments"),
        "delete comment": await client.delete("/api/v1/comments/1"),
        "upload attachment": await client.post(
            f"/api/v1/tasks/{task_id}/attachments",
            files={"file": ("a.txt", io.BytesIO(b"x"), "text/plain")},
        ),
        "list attachments": await client.get(f"/api/v1/tasks/{task_id}/attachments"),
        "download attachment": await client.get(f"/api/v1/attachments/{aid}"),
        "delete attachment": await client.delete(f"/api/v1/attachments/{aid}"),
    }
    for label, r in results.items():
        assert r.status_code == 401, f"{label}: {r.status_code} {r.text[:120]}"


async def test_permission_layer_precedes_resource_layer(client, storage_root):
    """无全局权限者被 403 拦下，**看不到**资源是否存在（403 先于 404）。

    这是信息泄露防线：若先做资源级判定，攻击者可用状态码差异枚举 id。
    """
    ins = await _make_user("layers1", ["admin"])
    nobody = await _make_user("layers2")  # 无任何全局角色
    _team, project = await _make_team_and_project(ins, "layers1")
    task_id = await _create_task(client, ins, project, "layers1")
    cid = (
        await _post_comment(client, ins, task_id, "x")
    ).json()["data"]["id"]
    aid = (
        await _upload(client, ins, task_id, filename="x.txt", content=b"x")
    ).json()["data"]["id"]

    HN = _bearer(create_access_token(nobody.id))

    # 对**真实存在的**资源：403（功能级先挡）
    real = [
        await client.post(
            f"/api/v1/tasks/{task_id}/comments", headers=HN, json={"content": "x"}
        ),
        await client.get(f"/api/v1/tasks/{task_id}/comments", headers=HN),
        await client.delete(f"/api/v1/comments/{cid}", headers=HN),
        await client.post(
            f"/api/v1/tasks/{task_id}/attachments",
            headers=HN,
            files={"file": ("a.txt", io.BytesIO(b"x"), "text/plain")},
        ),
        await client.get(f"/api/v1/attachments/{aid}", headers=HN),
        await client.delete(f"/api/v1/attachments/{aid}", headers=HN),
    ]
    for r in real:
        assert r.status_code == 403, f"{r.status_code} {r.text[:120]}"
        assert r.json()["detail"].startswith("Permission denied:")

    # 对**不存在的**资源：同样是 403，不得因 id 不存在而变成 404
    ghosts = [
        await client.delete("/api/v1/comments/99999999", headers=HN),
        await client.get("/api/v1/tasks/99999999/comments", headers=HN),
        await client.get("/api/v1/attachments/99999999", headers=HN),
    ]
    for r in ghosts:
        assert r.status_code == 403, f"{r.status_code} {r.text[:120]}"


# ===========================================================================
# 4. 删除权限层级：两类资源在同一阵容下必须各自成立
# ===========================================================================


async def test_delete_authorization_differs_per_resource_same_roster(
    client, storage_root
):
    """同一团队阵容下，评论与附件的删除授权规则必须**各自精确**。

    - 评论：作者本人 或 团队 OWNER/ADMIN（TASK-041 决策）
    - 附件：上传者本人 或 团队 OWNER/ADMIN（TASK-042 决策）

    两者形状相同但**主体不同**（作者 vs 上传者），且都不允许「普通成员删
    他人内容」。最容易在重构中被抹平的就是这一条，因此用同一组用户同时
    验证两条规则。
    """
    # owner(admin) / admin(admin+团队ADMIN) / member(admin+团队MEMBER)
    boss = await _make_user("perm_owner", ["admin"])
    tadmin = await _make_user("perm_admin", ["admin"])
    tmember = await _make_user("perm_member", ["admin"])

    team, project = await _make_team_and_project(boss, "perm")
    await _add_member(team, tadmin, 2)  # TeamRole.ADMIN
    await _add_member(team, tmember, 3)  # TeamRole.MEMBER

    task_id = await _create_task(client, boss, project, "perm")

    # tmember 与 tadmin 各创建一条评论 + 一个附件
    m_cid = (
        await _post_comment(client, tmember, task_id, "member comment")
    ).json()["data"]["id"]
    m_aid = (
        await _upload(client, tmember, task_id, filename="member.txt", content=b"m")
    ).json()["data"]["id"]
    a_cid = (
        await _post_comment(client, tadmin, task_id, "admin comment")
    ).json()["data"]["id"]
    a_aid = (
        await _upload(client, tadmin, task_id, filename="admin.txt", content=b"a")
    ).json()["data"]["id"]

    HM = _bearer(create_access_token(tmember.id))
    HA = _bearer(create_access_token(tadmin.id))
    HB = _bearer(create_access_token(boss.id))

    # ① 普通成员不能删他人内容（评论与附件都 403，且文案各自准确）
    r = await client.delete(f"/api/v1/comments/{a_cid}", headers=HM)
    assert r.status_code == 403, r.text
    assert r.json()["detail"] == (
        "Only team owner or admin or the comment author can delete comments"
    )

    r = await client.delete(f"/api/v1/attachments/{a_aid}", headers=HM)
    assert r.status_code == 403, r.text
    assert r.json()["detail"] == (
        "Only team owner or admin or the uploader can delete attachments"
    )

    # ② 普通成员可以删**自己**的内容
    assert (
        await client.delete(f"/api/v1/comments/{m_cid}", headers=HM)
    ).status_code == 200
    assert (
        await client.delete(f"/api/v1/attachments/{m_aid}", headers=HM)
    ).status_code == 200

    # ③ 团队 ADMIN 可以删他人内容（两资源都 200）
    assert (
        await client.delete(f"/api/v1/comments/{a_cid}", headers=HA)
    ).status_code == 200
    assert (
        await client.delete(f"/api/v1/attachments/{a_aid}", headers=HA)
    ).status_code == 200

    # ④ 团队 OWNER 同理（再造两条，验证 OWNER 分支）
    o_cid = (
        await _post_comment(client, tadmin, task_id, "for owner")
    ).json()["data"]["id"]
    o_aid = (
        await _upload(client, tadmin, task_id, filename="forowner.txt", content=b"o")
    ).json()["data"]["id"]
    assert (
        await client.delete(f"/api/v1/comments/{o_cid}", headers=HB)
    ).status_code == 200
    assert (
        await client.delete(f"/api/v1/attachments/{o_aid}", headers=HB)
    ).status_code == 200


async def test_member_without_delete_permissions_gets_functional_403(
    client, storage_root
):
    """member 全局角色删自己内容仍被 403 —— 功能级缺失**先于**资源级。

    这是与上一条互补的边界：资源级「你自己的内容自己删」逻辑上成立，但
    member 角色不带 comment:delete / attachment:upload 写权限位，因此连
    功能级门槛都过不去。两条测试合起来把「功能级 vs 资源级」的先后顺序
    钉死。
    """
    boss = await _make_user("func_owner", ["admin"])
    plain = await _make_user("func_member", ["member"])

    team, project = await _make_team_and_project(boss, "func")
    await _add_member(team, plain, 3)  # 普通成员

    # member 需要 task:create 才能建任务吗？不需要——由 boss 建
    task_id = await _create_task(client, boss, project, "func")

    # member 可以评论吗？member 角色有 comment:create（种子）
    resp = await _post_comment(client, plain, task_id, "member speaks")
    assert resp.status_code == 201, resp.text
    cid = resp.json()["data"]["id"]

    # 但 member 无 comment:delete → 删自己的评论也 403
    HP = _bearer(create_access_token(plain.id))
    r = await client.delete(f"/api/v1/comments/{cid}", headers=HP)
    assert r.status_code == 403, r.text
    assert r.json()["detail"] == "Permission denied: comment:delete"


# ===========================================================================
# 5. 级联：删除任务时两类子资源同时清理
# ===========================================================================


async def test_deleting_task_cascades_both_comments_and_attachments(
    client, storage_root
):
    """§16/§17：删任务 → 评论与附件元数据同时级联（FK CASCADE）。"""
    owner = await _make_user("casc1", ["admin"])
    _team, project = await _make_team_and_project(owner, "casc1")
    task_id = await _create_task(client, owner, project, "casc1")

    cids = []
    aids = []
    for i in range(3):
        cids.append(
            (await _post_comment(client, owner, task_id, f"c{i}")).json()["data"]["id"]
        )
        aids.append(
            (
                await _upload(
                    client, owner, task_id, filename=f"f{i}.txt", content=b"x"
                )
            ).json()["data"]["id"]
        )

    H = _bearer(create_access_token(owner.id))
    resp = await client.delete(f"/api/v1/tasks/{task_id}", headers=H)
    assert resp.status_code == 200, resp.text

    assert await _count(Comment, Comment.id, cids) == 0
    assert await _count(Attachment, Attachment.id, aids) == 0


async def test_cascade_via_user_deletion_removes_content_but_keeps_audit(
    client, storage_root
):
    """§17/§48：删用户 → 其评论与附件级联清，但审计日志保留（agent 独立性）。

    评论与附件都 FK CASCADE 到 users（内容随人走）；而 operation_logs.user_id
    **无外键**（TASK-039 决策），因此审计留痕不丢。这三条规则放在一起才是
    完整的数据生命周期契约。
    """
    owner = await _make_user("casc2", ["admin"])
    victim = await _make_user("casc2v", ["admin"])
    team, project = await _make_team_and_project(owner, "casc2")
    await _add_member(team, victim, 3)  # 普通成员
    task_id = await _create_task(client, owner, project, "casc2")

    # victim 造内容
    cid = (
        await _post_comment(client, victim, task_id, "victim comment")
    ).json()["data"]["id"]
    aid = (
        await _upload(client, victim, task_id, filename="victim.txt", content=b"v")
    ).json()["data"]["id"]

    # owner（团队 OWNER）删掉 victim 的评论 → 产生一条属于 owner 的审计日志
    HO = _bearer(create_access_token(owner.id))
    assert (
        await client.delete(f"/api/v1/comments/{cid}", headers=HO)
    ).status_code == 200

    logs_before = await _all_logs_for_users([owner.id])
    assert any(log.action == "comment:delete" for log in logs_before)

    # 删除 victim 用户：其附件随 FK CASCADE 消失，审计日志不受影响
    async with SessionFactory() as session:
        await session.execute(delete(User).where(User.id == victim.id))
        await session.commit()

    assert await _count(Attachment, Attachment.id, [aid]) == 0
    assert await _count(Comment, Comment.id, [cid]) == 0

    logs_after = await _all_logs_for_users([owner.id])
    assert len(logs_after) == len(logs_before)
    assert any(log.action == "comment:delete" for log in logs_after)


# ===========================================================================
# 6. §55.2 事务原子性：审计日志与业务变更同事务
# ===========================================================================


async def test_comment_delete_audit_is_atomic(client, storage_root, monkeypatch):
    """§55.2「写 OperationLog → 提交事务」：写日志失败 → 删除一并回滚。

    评论与附件都必须满足「要么都成，要么都不成」，不允许出现
    「评论没了但没日志」或「日志写了但评论还在」。
    """
    from app.services import comment as comment_service

    owner = await _make_user("atom1", ["admin"])
    _team, project = await _make_team_and_project(owner, "atom1")
    task_id = await _create_task(client, owner, project, "atom1")
    cid = (
        await _post_comment(client, owner, task_id, "atomic")
    ).json()["data"]["id"]

    async def _boom(*args, **kwargs):
        raise RuntimeError("audit write failed")

    # 必须 patch 引用方模块内的符号绑定（comment 服务里 from ... import）
    monkeypatch.setattr(comment_service, "write_operation_log", _boom)

    H = _bearer(create_access_token(owner.id))
    # TASK-090 起：未捕获异常被 MetricsErrorMiddleware 转换为 500 统一信封，
    # 不再向 ASGI 栈外冒泡（对外契约见 API_CONTRACT.md「未处理异常」）。
    # 原子性本身由下面的库态断言证明：写日志失败 → 删除一并回滚。
    resp = await client.delete(f"/api/v1/comments/{cid}", headers=H)
    assert resp.status_code == 500
    assert resp.json() == {"detail": "Internal server error"}

    # 评论仍在（回滚），且无日志
    assert await _count(Comment, Comment.id, [cid]) == 1
    assert await _logs_for("comment", cid) == []


async def test_attachment_delete_audit_is_atomic(client, storage_root, monkeypatch):
    """同上，附件删除路径。注意物理文件在事务之外——见下方说明。"""
    from app.services import attachment as attachment_service

    owner = await _make_user("atom2", ["admin"])
    _team, project = await _make_team_and_project(owner, "atom2")
    task_id = await _create_task(client, owner, project, "atom2")
    aid = (
        await _upload(client, owner, task_id, filename="atom.txt", content=b"a")
    ).json()["data"]["id"]

    async with SessionFactory() as session:
        row = await session.get(Attachment, aid)
        stored_key = row.storage_path

    async def _boom(*args, **kwargs):
        raise RuntimeError("audit write failed")

    monkeypatch.setattr(attachment_service, "write_operation_log", _boom)

    H = _bearer(create_access_token(owner.id))
    # TASK-090 起：未捕获异常被转换为 500 统一信封（同上，不再冒泡）。
    resp = await client.delete(f"/api/v1/attachments/{aid}", headers=H)
    assert resp.status_code == 500
    assert resp.json() == {"detail": "Internal server error"}

    # DB 记录回滚保留
    assert await _count(Attachment, Attachment.id, [aid]) == 1
    assert await _logs_for("attachment", aid) == []
    # 说明：物理文件此时已被 unlink（删除顺序为「先删文件再删记录」），
    # 这是 TASK-042 决策下的已知取舍——文件不可回收优于「记录删了文件还在」。
    # 断言它确实不在了，把该行为固定为契约。
    assert not (storage_root / stored_key).exists()


# ===========================================================================
# 7. 分页一致性：两类列表遵循同一分页契约
# ===========================================================================


async def test_both_lists_respect_pagination_contract(client, storage_root):
    """评论与附件列表的 skip/limit 语义必须一致（含边界）。"""
    owner = await _make_user("page1", ["admin"])
    _team, project = await _make_team_and_project(owner, "page1")
    task_id = await _create_task(client, owner, project, "page1")

    for i in range(5):
        await _post_comment(client, owner, task_id, f"c{i}")
        await _upload(client, owner, task_id, filename=f"p{i}.txt", content=b"x")

    H = _bearer(create_access_token(owner.id))

    # 全量
    rc = await client.get(f"/api/v1/tasks/{task_id}/comments", headers=H)
    ra = await client.get(f"/api/v1/tasks/{task_id}/attachments", headers=H)
    assert len(rc.json()["data"]) == 5
    assert len(ra.json()["data"]) == 5

    # limit 切片（顺序稳定，可预期前 N 条）
    rc = await client.get(
        f"/api/v1/tasks/{task_id}/comments", headers=H, params={"limit": 2}
    )
    ra = await client.get(
        f"/api/v1/tasks/{task_id}/attachments", headers=H, params={"limit": 2}
    )
    assert [c["content"] for c in rc.json()["data"]] == ["c0", "c1"]
    assert [a["filename"] for a in ra.json()["data"]] == ["p0.txt", "p1.txt"]

    # skip 偏移
    rc = await client.get(
        f"/api/v1/tasks/{task_id}/comments", headers=H, params={"skip": 3}
    )
    ra = await client.get(
        f"/api/v1/tasks/{task_id}/attachments", headers=H, params={"skip": 3}
    )
    assert [c["content"] for c in rc.json()["data"]] == ["c3", "c4"]
    assert [a["filename"] for a in ra.json()["data"]] == ["p3.txt", "p4.txt"]

    # 越界参数（limit=0 / limit=101 / skip=-1）→ 422，两类一致
    for url in [
        f"/api/v1/tasks/{task_id}/comments",
        f"/api/v1/tasks/{task_id}/attachments",
    ]:
        for params in [{"limit": 0}, {"limit": 101}, {"skip": -1}]:
            r = await client.get(url, headers=H, params=params)
            assert r.status_code == 422, f"{url} {params}: {r.status_code}"


# ===========================================================================
# 8. 存储一致性：附件删除后磁盘/DB 同步，评论删除不影响附件
# ===========================================================================


async def test_comment_deletion_does_not_touch_attachments(client, storage_root):
    """两类资源生命周期独立：删评论不得影响附件（文件与记录都在）。"""
    owner = await _make_user("indep1", ["admin"])
    _team, project = await _make_team_and_project(owner, "indep1")
    task_id = await _create_task(client, owner, project, "indep1")

    cid = (
        await _post_comment(client, owner, task_id, "c")
    ).json()["data"]["id"]
    resp = await _upload(client, owner, task_id, filename="keep.txt", content=b"keep")
    aid = resp.json()["data"]["id"]

    async with SessionFactory() as session:
        key = (await session.get(Attachment, aid)).storage_path
    assert (storage_root / key).is_file()

    H = _bearer(create_access_token(owner.id))
    assert (
        await client.delete(f"/api/v1/comments/{cid}", headers=H)
    ).status_code == 200

    # 附件记录与物理文件均完好
    assert await _count(Attachment, Attachment.id, [aid]) == 1
    assert (storage_root / key).is_file()
    dl = await client.get(f"/api/v1/attachments/{aid}", headers=H)
    assert dl.status_code == 200
    assert dl.content == b"keep"


async def test_attachment_deletion_leaves_no_orphan_file(client, storage_root):
    """删除附件后磁盘与 DB 同步清除（§17 存储一致性）。"""
    owner = await _make_user("orphan1", ["admin"])
    _team, project = await _make_team_and_project(owner, "orphan1")
    task_id = await _create_task(client, owner, project, "orphan1")

    aid = (
        await _upload(client, owner, task_id, filename="bye.txt", content=b"bye")
    ).json()["data"]["id"]
    async with SessionFactory() as session:
        key = (await session.get(Attachment, aid)).storage_path

    H = _bearer(create_access_token(owner.id))
    assert (
        await client.delete(f"/api/v1/attachments/{aid}", headers=H)
    ).status_code == 200

    assert not (storage_root / key).exists()
    assert [p for p in storage_root.rglob("*") if p.is_file()] == []
    assert await _count(Attachment, Attachment.id, [aid]) == 0
