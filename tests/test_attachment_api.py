"""TASK-042：Attachment API HTTP 端到端验收（真实产品应用 + 真实 Token 认证链）。

与 test_comment_api.py 同模式：对 `app.main.app` 走完整链路，仅覆盖 `get_db`
指向测试库，并额外覆盖存储后端根目录到 ``tmp_path``（不污染真实 ``storage/``）。

覆盖点（§17 上传要求 + §25.7 端点 + §9 安全清单）：

- 上传成功 + 列表（时间升序、含 uploader 名）；
- 大小限制 413（真实超限字节流，非伪造 Content-Length）；
- MIME 白名单 415（无扩展名 / 未列入扩展名）；
- 文件名清洗：``../../etc/passwd`` → 纯文件名且磁盘 key 与文件名无关；
- 空文件 400；
- 功能级 403（无角色 / 缺 attachment:download）；
- 资源级 404（局外人、不存在）——上传 / 列表 / 下载 / 删除四端点一致；
- 下载内容字节一致 + Content-Disposition 百分号编码 + nosniff 头；
- 删除：上传者本人 / 团队 ADMIN 可删，普通成员 403，写 `attachment:delete` 审计；
- 删除后元数据与物理文件同时消失；
- storage_path 唯一性 + 相对性（不含绝对路径）；
- 删任务级联清附件元数据（物理文件由 TASK-050 清理任务负责）。

零残留：审计日志 → 附件 → 任务 → 项目 → 团队 → 用户 精确拆除（RESTRICT 全链）。
"""

import io
import uuid
from pathlib import Path

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
    return f"att_{RUN_TOKEN}_{tag}"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest_asyncio.fixture
async def storage_root(tmp_path) -> Path:
    """把存储后端指向临时目录，并在此夹具内保持单例。

    覆盖的是 ``app.services.storage`` 的进程内单例——这是全项目唯一注入点
    （见 storage.py 的 ``get_storage_backend``），因此不必 monkeypatch 每个
    调用方。
    """
    from app.services import storage as storage_service

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
    yield
    async with SessionFactory() as session:
        # 审计日志 → 附件 → 任务 → 项目 → 团队 → 用户（RESTRICT 全链精确拆除）
        await session.execute(
            delete(OperationLog).where(
                OperationLog.user_id.in_(
                    select(User.id).where(User.username.like(f"att_{RUN_TOKEN}%"))
                )
            )
        )
        await session.execute(
            delete(Attachment).where(
                Attachment.uploader_id.in_(
                    select(User.id).where(User.username.like(f"att_{RUN_TOKEN}%"))
                )
            )
        )
        await session.execute(
            delete(Task).where(Task.title.like(f"att {RUN_TOKEN}%"))
        )
        await session.execute(
            delete(Project).where(Project.name.like(f"att proj {RUN_TOKEN}%"))
        )
        await session.execute(
            delete(Team).where(Team.name.like(f"att team {RUN_TOKEN}%"))
        )
        await session.execute(
            delete(User).where(User.username.like(f"att_{RUN_TOKEN}%"))
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
            session, owner, TeamCreate(name=f"att team {RUN_TOKEN} {tag}")
        )
        project = await create_project(
            session,
            name=f"att proj {RUN_TOKEN} {tag}",
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
        json={"project_id": project.id, "title": f"att {RUN_TOKEN} {tag}"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]["id"]


async def _upload(
    client,
    user: User,
    task_id: int,
    *,
    filename: str | None,
    content: bytes,
    content_type: str = "application/octet-stream",
):
    files = {
        "file": (filename, io.BytesIO(content), content_type),
    }
    return await client.post(
        f"/api/v1/tasks/{task_id}/attachments",
        headers=_bearer(create_access_token(user.id)),
        files=files,
    )


# --- 上传 + 列表 ----------------------------------------------------------------


async def test_upload_and_list(client, storage_root):
    owner = await _make_user("owner1", ["admin"])
    project = await _make_project(owner, "a1")
    task_id = await _create_task(client, owner, project, "a1")

    resp = await _upload(
        client, owner, task_id, filename="notes.txt", content=b"hello world"
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()["data"]
    assert body["task_id"] == task_id
    assert body["uploader_id"] == owner.id
    assert body["uploader"] == _username("owner1")
    assert body["filename"] == "notes.txt"
    assert body["content_type"] == "text/plain"
    assert body["size"] == 11

    # 元数据里存的是相对 key（不含绝对路径），且文件确实落在注入的根目录下
    async with SessionFactory() as session:
        row = (
            await session.execute(
                select(Attachment).where(Attachment.id == body["id"])
            )
        ).scalar_one()
    # TASK-094：key 以租户为前导目录（tenants/{tid}/tasks/{task_id}/...）。
    assert row.storage_path.startswith("tenants/") and f"/tasks/{task_id}/" in row.storage_path
    assert ":" not in row.storage_path and not row.storage_path.startswith("/")
    assert (storage_root / row.storage_path).is_file()

    # 列表
    resp = await client.get(
        f"/api/v1/tasks/{task_id}/attachments",
        headers=_bearer(create_access_token(owner.id)),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert len(data) == 1
    assert data[0]["id"] == body["id"]
    assert data[0]["uploader"] == _username("owner1")


async def test_upload_multiple_listed_in_order(client):
    owner = await _make_user("owner2", ["admin"])
    project = await _make_project(owner, "a2")
    task_id = await _create_task(client, owner, project, "a2")

    for i in range(3):
        assert (
            await _upload(
                client, owner, task_id, filename=f"f{i}.txt", content=b"x"
            )
        ).status_code == 201

    resp = await client.get(
        f"/api/v1/tasks/{task_id}/attachments",
        headers=_bearer(create_access_token(owner.id)),
    )
    names = [a["filename"] for a in resp.json()["data"]]
    assert names == ["f0.txt", "f1.txt", "f2.txt"]


async def test_storage_keys_are_unique_per_upload(client):
    """同名文件重复上传：storage_path 随机，互不覆盖（§17 安全）。"""
    owner = await _make_user("owner3", ["admin"])
    project = await _make_project(owner, "a3")
    task_id = await _create_task(client, owner, project, "a3")

    ids = []
    for payload in (b"first", b"second"):
        resp = await _upload(
            client, owner, task_id, filename="same.txt", content=payload
        )
        assert resp.status_code == 201, resp.text
        ids.append(resp.json()["data"]["id"])

    async with SessionFactory() as session:
        rows = (
            await session.execute(
                select(Attachment).where(Attachment.id.in_(ids))
            )
        ).scalars().all()
    paths = {r.storage_path for r in rows}
    assert len(paths) == 2, "storage_path must be unique per upload"

    # 两个文件内容各自独立（后上传没有覆盖先上传）
    for aid, expected in zip(ids, (b"first", b"second")):
        resp = await client.get(
            f"/api/v1/attachments/{aid}",
            headers=_bearer(create_access_token(owner.id)),
        )
        assert resp.status_code == 200
        assert resp.content == expected


# --- 大小限制 413 --------------------------------------------------------------


async def test_upload_exceeding_max_size_413(client, storage_root, monkeypatch):
    """真实超限字节流被拒；不依赖伪造 Content-Length（§17 大小限制）。"""
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "max_upload_size", 1024, raising=False)

    owner = await _make_user("owner4", ["admin"])
    project = await _make_project(owner, "a4")
    task_id = await _create_task(client, owner, project, "a4")

    resp = await _upload(
        client, owner, task_id, filename="big.zip", content=b"x" * 4096
    )
    assert resp.status_code == 413, resp.text
    assert resp.json()["detail"] == "Uploaded file is too large"

    # 不产生元数据，也不留半成品文件
    async with SessionFactory() as session:
        rows = (
            await session.execute(
                select(Attachment).where(Attachment.task_id == task_id)
            )
        ).scalars().all()
    assert rows == []
    leftover = [p for p in storage_root.rglob("*") if p.is_file()]
    assert leftover == [], f"oversized upload left files: {leftover}"


async def test_upload_within_limit_ok(client, storage_root, monkeypatch):
    """边界：恰好等于上限应当通过（不误伤）。"""
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "max_upload_size", 1024, raising=False)

    owner = await _make_user("owner5", ["admin"])
    project = await _make_project(owner, "a5")
    task_id = await _create_task(client, owner, project, "a5")

    resp = await _upload(
        client, owner, task_id, filename="exact.zip", content=b"y" * 1024
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["data"]["size"] == 1024


# --- MIME 白名单 415 -----------------------------------------------------------


async def test_upload_disallowed_extension_415(client):
    owner = await _make_user("owner6", ["admin"])
    project = await _make_project(owner, "a6")
    task_id = await _create_task(client, owner, project, "a6")

    for filename, desc in (
        ("payload.exe", "可执行文件"),
        ("script.sh", "shell 脚本"),
        ("noext", "无扩展名"),
        ("page.html", "HTML（存储型 XSS 载体）"),
        ("a.php", "PHP"),
    ):
        resp = await _upload(
            client, owner, task_id, filename=filename, content=b"MZ"
        )
        assert resp.status_code == 415, f"{desc}: {resp.text}"
        assert resp.json()["detail"] == "File type is not allowed"


async def test_extension_check_is_case_insensitive(client):
    owner = await _make_user("owner7", ["admin"])
    project = await _make_project(owner, "a7")
    task_id = await _create_task(client, owner, project, "a7")

    resp = await _upload(
        client, owner, task_id, filename="PHOTO.PNG", content=b"\x89PNG"
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["data"]["content_type"] == "image/png"


async def test_content_type_comes_from_extension_not_client(client):
    """客户端自报的 Content-Type 不可信——以扩展名为准（§17 MIME 校验）。"""
    owner = await _make_user("owner8", ["admin"])
    project = await _make_project(owner, "a8")
    task_id = await _create_task(client, owner, project, "a8")

    resp = await _upload(
        client,
        owner,
        task_id,
        filename="report.pdf",
        content=b"%PDF-1.4",
        content_type="text/html",  # 伪造
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["data"]["content_type"] == "application/pdf"


# --- 文件名清洗与路径穿越 -------------------------------------------------------


async def test_filename_traversal_is_sanitized(client, storage_root):
    """``../../etc/passwd`` 型文件名被削成纯文件名；磁盘 key 与之完全无关。"""
    owner = await _make_user("owner9", ["admin"])
    project = await _make_project(owner, "a9")
    task_id = await _create_task(client, owner, project, "a9")

    resp = await _upload(
        client,
        owner,
        task_id,
        filename="../../../../etc/passwd.txt",
        content=b"root:x:0:0",
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()["data"]
    assert body["filename"] == "passwd.txt", body["filename"]
    assert ".." not in body["filename"] and "/" not in body["filename"]

    async with SessionFactory() as session:
        row = (
            await session.execute(
                select(Attachment).where(Attachment.id == body["id"])
            )
        ).scalar_one()

    # key 完全由服务端生成：不含用户输入的任何片段
    assert row.storage_path.startswith("tenants/") and f"/tasks/{task_id}/" in row.storage_path
    assert "passwd" not in row.storage_path
    assert ".." not in row.storage_path
    # 落盘位置在注入的根目录内，且根目录外没有被写入
    resolved = (storage_root / row.storage_path).resolve()
    assert storage_root.resolve() in resolved.parents or resolved.parent == storage_root.resolve()


async def test_windows_style_traversal_is_sanitized(client):
    owner = await _make_user("owner10", ["admin"])
    project = await _make_project(owner, "a10")
    task_id = await _create_task(client, owner, project, "a10")

    resp = await _upload(
        client,
        owner,
        task_id,
        filename="..\\..\\Windows\\win.ini.txt",
        content=b"[fonts]",
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["data"]["filename"] == "win.ini.txt"


async def test_filename_control_chars_and_reserved_names(client):
    owner = await _make_user("owner11", ["admin"])
    project = await _make_project(owner, "a11")
    task_id = await _create_task(client, owner, project, "a11")

    # 控制字符被剥离（含 CR/LF——防响应头注入）
    resp = await _upload(
        client,
        owner,
        task_id,
        filename="evil\r\nX-Injected: 1.txt",
        content=b"x",
    )
    assert resp.status_code == 201, resp.text
    assert "\r" not in resp.json()["data"]["filename"]
    assert "\n" not in resp.json()["data"]["filename"]

    # Windows 保留设备名被折叠
    resp = await _upload(
        client, owner, task_id, filename="CON.txt", content=b"x"
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["data"]["filename"] == "_CON.txt"


async def test_empty_file_400(client, storage_root):
    owner = await _make_user("owner12", ["admin"])
    project = await _make_project(owner, "a12")
    task_id = await _create_task(client, owner, project, "a12")

    resp = await _upload(
        client, owner, task_id, filename="empty.txt", content=b""
    )
    assert resp.status_code == 400, resp.text
    assert resp.json()["detail"] == "Uploaded file is empty"

    # 空文件已回收，不留孤儿文件
    assert [p for p in storage_root.rglob("*") if p.is_file()] == []


# --- 权限：功能级 403 -----------------------------------------------------------


async def test_upload_requires_permission_403(client):
    norole = await _make_user("norole13")  # 无任何角色
    owner = await _make_user("owner13", ["admin"])
    project = await _make_project(owner, "a13")
    task_id = await _create_task(client, owner, project, "a13")

    resp = await _upload(
        client, norole, task_id, filename="x.txt", content=b"x"
    )
    assert resp.status_code == 403, resp.text
    assert resp.json()["detail"] == "Permission denied: attachment:upload"


async def test_download_and_list_require_permission_403(client):
    norole = await _make_user("norole14")
    owner = await _make_user("owner14", ["admin"])
    project = await _make_project(owner, "a14")
    task_id = await _create_task(client, owner, project, "a14")
    aid = (
        await _upload(client, owner, task_id, filename="x.txt", content=b"x")
    ).json()["data"]["id"]

    resp = await client.get(
        f"/api/v1/attachments/{aid}",
        headers=_bearer(create_access_token(norole.id)),
    )
    assert resp.status_code == 403, resp.text
    assert resp.json()["detail"] == "Permission denied: attachment:download"

    resp = await client.get(
        f"/api/v1/tasks/{task_id}/attachments",
        headers=_bearer(create_access_token(norole.id)),
    )
    assert resp.status_code == 403, resp.text
    assert resp.json()["detail"] == "Permission denied: task:read"


# --- 权限：资源级 404（IDOR 防枚举，四端点一致） --------------------------------


async def test_outsider_gets_404_on_every_endpoint(client):
    owner = await _make_user("owner15", ["admin"])
    outsider = await _make_user("outsider15", ["admin"])  # 有全部功能级权限
    project = await _make_project(owner, "a15")
    task_id = await _create_task(client, owner, project, "a15")
    aid = (
        await _upload(client, owner, task_id, filename="secret.txt", content=b"top")
    ).json()["data"]["id"]

    hdr = _bearer(create_access_token(outsider.id))

    resp = await _upload(client, outsider, task_id, filename="x.txt", content=b"x")
    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"] == "Task not found"

    resp = await client.get(f"/api/v1/tasks/{task_id}/attachments", headers=hdr)
    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"] == "Task not found"

    resp = await client.get(f"/api/v1/attachments/{aid}", headers=hdr)
    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"] == "Attachment not found"

    resp = await client.delete(f"/api/v1/attachments/{aid}", headers=hdr)
    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"] == "Attachment not found"


async def test_nonexistent_ids_404_with_same_message(client):
    owner = await _make_user("owner16", ["admin"])
    hdr = _bearer(create_access_token(owner.id))

    resp = await _upload(client, owner, 999999999, filename="x.txt", content=b"x")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Task not found"

    resp = await client.get("/api/v1/attachments/999999999", headers=hdr)
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Attachment not found"

    resp = await client.delete("/api/v1/attachments/999999999", headers=hdr)
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Attachment not found"


async def test_member_can_upload_and_download(client):
    """团队成员（非管理者）可上传/下载——§17 的正常协作路径。"""
    owner = await _make_user("owner17", ["admin"])
    member = await _make_user("member17", ["member"])
    project = await _make_project(owner, "a17")
    await _add_member(project, member, role_id=3)
    task_id = await _create_task(client, owner, project, "a17")

    resp = await _upload(
        client, member, task_id, filename="m.txt", content=b"from member"
    )
    assert resp.status_code == 201, resp.text
    aid = resp.json()["data"]["id"]

    resp = await client.get(
        f"/api/v1/attachments/{aid}",
        headers=_bearer(create_access_token(owner.id)),
    )
    assert resp.status_code == 200, resp.text
    assert resp.content == b"from member"


# --- 下载 ----------------------------------------------------------------------


async def test_download_headers_and_bytes(client):
    owner = await _make_user("owner18", ["admin"])
    project = await _make_project(owner, "a18")
    task_id = await _create_task(client, owner, project, "a18")
    payload = b"line1\nline2\n\x00\xff binary"
    aid = (
        await _upload(
            client, owner, task_id, filename="data.zip", content=payload
        )
    ).json()["data"]["id"]

    resp = await client.get(
        f"/api/v1/attachments/{aid}",
        headers=_bearer(create_access_token(owner.id)),
    )
    assert resp.status_code == 200, resp.text
    assert resp.content == payload
    assert resp.headers["content-type"] == "application/zip"
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["content-disposition"] == (
        "attachment; filename*=UTF-8''data.zip"
    )
    assert resp.headers["content-length"] == str(len(payload))


async def test_download_non_ascii_filename_is_percent_encoded(client):
    """非 ASCII 文件名用 RFC 5987 形式编码，响应头保持纯 ASCII。"""
    owner = await _make_user("owner19", ["admin"])
    project = await _make_project(owner, "a19")
    task_id = await _create_task(client, owner, project, "a19")
    aid = (
        await _upload(
            client, owner, task_id, filename=" отчет 报告.pdf", content=b"%PDF"
        )
    ).json()["data"]["id"]

    resp = await client.get(
        f"/api/v1/attachments/{aid}",
        headers=_bearer(create_access_token(owner.id)),
    )
    assert resp.status_code == 200, resp.text
    disposition = resp.headers["content-disposition"]
    assert disposition.startswith("attachment; filename*=UTF-8''")
    disposition.encode("ascii")  # 不含非 ASCII 字节 → 不会破坏响应头


async def test_download_missing_physical_file_404(client, storage_root):
    """元数据在但文件被外部清理 → 404，而非 500（不泄露内部状态）。"""
    owner = await _make_user("owner20", ["admin"])
    project = await _make_project(owner, "a20")
    task_id = await _create_task(client, owner, project, "a20")
    body = (
        await _upload(client, owner, task_id, filename="gone.txt", content=b"x")
    ).json()["data"]

    async with SessionFactory() as session:
        row = (
            await session.execute(
                select(Attachment).where(Attachment.id == body["id"])
            )
        ).scalar_one()
    (storage_root / row.storage_path).unlink()

    resp = await client.get(
        f"/api/v1/attachments/{body['id']}",
        headers=_bearer(create_access_token(owner.id)),
    )
    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"] == "Attachment not found"


# --- 删除 ----------------------------------------------------------------------


async def test_uploader_deletes_own_attachment_200_writes_audit(client, storage_root):
    uploader = await _make_user("owner21", ["admin"])
    project = await _make_project(uploader, "a21")
    task_id = await _create_task(client, uploader, project, "a21")
    body = (
        await _upload(client, uploader, task_id, filename="mine.txt", content=b"x")
    ).json()["data"]

    async with SessionFactory() as session:
        row = (
            await session.execute(
                select(Attachment).where(Attachment.id == body["id"])
            )
        ).scalar_one()
    path = storage_root / row.storage_path
    assert path.is_file()

    resp = await client.delete(
        f"/api/v1/attachments/{body['id']}",
        headers=_bearer(create_access_token(uploader.id)),
    )
    assert resp.status_code == 200, resp.text

    # 元数据消失
    async with SessionFactory() as session:
        assert (
            await session.execute(
                select(Attachment).where(Attachment.id == body["id"])
            )
        ).scalar_one_or_none() is None

    # 物理文件消失
    assert not path.exists()

    # 审计日志（§17 + 复用 OperationLog）
    async with SessionFactory() as session:
        logs = (
            await session.execute(
                select(OperationLog).where(
                    OperationLog.resource_type == "attachment",
                    OperationLog.resource_id == body["id"],
                )
            )
        ).scalars().all()
    assert len(logs) == 1
    assert logs[0].action == "attachment:delete"
    assert logs[0].user_id == uploader.id
    assert logs[0].payload == {
        "task_id": task_id,
        "attachment_id": body["id"],
        "filename": "mine.txt",
    }


async def test_team_admin_deletes_others_attachment_200(client):
    owner = await _make_user("owner22", ["admin"])
    tadmin = await _make_user("tadmin22", ["admin"])
    uploader = await _make_user("uploader22", ["admin"])
    project = await _make_project(owner, "a22")
    await _add_member(project, tadmin, role_id=2)  # 团队 ADMIN
    await _add_member(project, uploader, role_id=3)

    task_id = await _create_task(client, owner, project, "a22")
    aid = (
        await _upload(client, uploader, task_id, filename="u.txt", content=b"x")
    ).json()["data"]["id"]

    resp = await client.delete(
        f"/api/v1/attachments/{aid}",
        headers=_bearer(create_access_token(tadmin.id)),
    )
    assert resp.status_code == 200, resp.text


async def test_member_cannot_delete_others_attachment_403(client):
    owner = await _make_user("owner23", ["admin"])
    uploader = await _make_user("uploader23", ["admin"])
    member = await _make_user("member23", ["admin"])
    project = await _make_project(owner, "a23")
    await _add_member(project, uploader, role_id=3)
    await _add_member(project, member, role_id=3)  # 团队 MEMBER

    task_id = await _create_task(client, owner, project, "a23")
    aid = (
        await _upload(client, uploader, task_id, filename="u.txt", content=b"x")
    ).json()["data"]["id"]

    resp = await client.delete(
        f"/api/v1/attachments/{aid}",
        headers=_bearer(create_access_token(member.id)),
    )
    assert resp.status_code == 403, resp.text
    assert resp.json()["detail"] == (
        "Only team owner or admin or the uploader can delete attachments"
    )


async def test_member_deletes_own_attachment_200(client):
    """member 持 attachment:upload，可删除自己上传的附件。"""
    owner = await _make_user("owner24", ["admin"])
    member = await _make_user("member24", ["member"])
    project = await _make_project(owner, "a24")
    await _add_member(project, member, role_id=3)
    task_id = await _create_task(client, owner, project, "a24")

    aid = (
        await _upload(client, member, task_id, filename="m.txt", content=b"x")
    ).json()["data"]["id"]

    resp = await client.delete(
        f"/api/v1/attachments/{aid}",
        headers=_bearer(create_access_token(member.id)),
    )
    assert resp.status_code == 200, resp.text


async def test_delete_missing_permission_403(client):
    """无角色用户：功能级 attachment:upload 缺失 → 403（先于资源级判定）。"""
    owner = await _make_user("owner25", ["admin"])
    norole = await _make_user("norole25")
    project = await _make_project(owner, "a25")
    task_id = await _create_task(client, owner, project, "a25")
    aid = (
        await _upload(client, owner, task_id, filename="x.txt", content=b"x")
    ).json()["data"]["id"]

    resp = await client.delete(
        f"/api/v1/attachments/{aid}",
        headers=_bearer(create_access_token(norole.id)),
    )
    assert resp.status_code == 403, resp.text
    assert resp.json()["detail"] == "Permission denied: attachment:upload"


# --- 级联 ----------------------------------------------------------------------


async def test_delete_task_cascades_attachment_metadata(client):
    owner = await _make_user("owner26", ["admin"])
    project = await _make_project(owner, "a26")
    task_id = await _create_task(client, owner, project, "a26")
    aid = (
        await _upload(client, owner, task_id, filename="c.txt", content=b"x")
    ).json()["data"]["id"]

    resp = await client.delete(
        f"/api/v1/tasks/{task_id}",
        headers=_bearer(create_access_token(owner.id)),
    )
    assert resp.status_code == 200, resp.text

    async with SessionFactory() as session:
        assert (
            await session.execute(
                select(Attachment).where(Attachment.id == aid)
            )
        ).scalar_one_or_none() is None


async def test_delete_user_cascades_attachment_metadata(client):
    owner = await _make_user("owner27", ["admin"])
    uploader = await _make_user("uploader27", ["admin"])
    project = await _make_project(owner, "a27")
    await _add_member(project, uploader, role_id=3)
    task_id = await _create_task(client, owner, project, "a27")
    aid = (
        await _upload(client, uploader, task_id, filename="u.txt", content=b"x")
    ).json()["data"]["id"]

    async with SessionFactory() as session:
        await session.execute(delete(User).where(User.id == uploader.id))
        await session.commit()

    async with SessionFactory() as session:
        assert (
            await session.execute(
                select(Attachment).where(Attachment.id == aid)
            )
        ).scalar_one_or_none() is None
