"""TASK-043：附件上传/下载权限与安全校验的对抗性专项测试。

TASK-042 已交付功能与基础安全校验（27 项）。本文件不重复那些断言，而是从
**攻击者视角**补齐 042 未覆盖的盲区，并固化 TASK-043 修复的三个真实缺陷。

规格依据：
- §17 上传要求（文件大小限制 / MIME 校验 / 文件名安全处理 / 不允许路径穿越 /
  下载检查任务访问权限）；
- §48 安全要求（文件上传漏洞、路径穿越、敏感日志泄露、认证 ≠ 授权）；
- §49 资源级权限（知道 id 也不能访问不属于自己的资源）；
- §56 Phase 9 验收（文件上传 / 文件下载 / 权限检查 / 文件大小限制）。

TASK-043 修复的三个缺陷（由真实探测发现，非推测）：

1. **非法 storage_path 触发 500**：``storage_path`` 若被绕过 API 改写为穿越
   key 或绝对路径，存储层抛 ``UnsafeStorageKeyError``，而 042 只捕获了
   ``StorageObjectNotFoundError`` → 未捕获异常变成 500 + 堆栈，把存储根的
   校验规则泄露出去。修复：下载路径一并映射为 404；删除路径跳过物理删除
   直接删记录（否则形成永远删不掉的脏记录）。
2. **``%XX`` 百分号编码绕过**：``a.txt%00.png`` 被判为 ``image/png``，但
   ``%00`` 在下游任何一处 URL 解码后会变成 NUL 并截断字符串，使「校验时的
   扩展名」与「实际使用的扩展名」不一致。修复：``sanitize_filename`` 主动
   剥离 ``%XX`` 序列。
3. **无主名文件名行为不一致**：``.txt`` 经清洗变成 ``txt`` 后被 415 拒绝，
   原因（扩展名不在白名单）与表象不符。修复：无主名显式判定并统一 415。

另验证一批「看似可疑但实际安全」的行为，把它们固化为**契约**，避免后续
重构时误改成真漏洞（如 ``shell.php.txt`` 判为 txt、``a.png.exe`` 判 415）。
"""

import asyncio
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
from app.services import attachment as attachment_service
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
    return f"sec_{RUN_TOKEN}_{tag}"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest_asyncio.fixture
async def storage_root(tmp_path) -> Path:
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
        await session.execute(
            delete(OperationLog).where(
                OperationLog.user_id.in_(
                    select(User.id).where(User.username.like(f"sec_{RUN_TOKEN}%"))
                )
            )
        )
        await session.execute(
            delete(Attachment).where(
                Attachment.uploader_id.in_(
                    select(User.id).where(User.username.like(f"sec_{RUN_TOKEN}%"))
                )
            )
        )
        await session.execute(
            delete(Task).where(Task.title.like(f"sec {RUN_TOKEN}%"))
        )
        await session.execute(
            delete(Project).where(Project.name.like(f"sec proj {RUN_TOKEN}%"))
        )
        await session.execute(
            delete(Team).where(Team.name.like(f"sec team {RUN_TOKEN}%"))
        )
        await session.execute(
            delete(User).where(User.username.like(f"sec_{RUN_TOKEN}%"))
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
            session, owner, TeamCreate(name=f"sec team {RUN_TOKEN} {tag}")
        )
        project = await create_project(
            session,
            name=f"sec proj {RUN_TOKEN} {tag}",
            description=None,
            team_id=team.id,
            owner_id=owner.id,
        )
        await session.commit()
        await session.refresh(project)
        return project


async def _create_task(client, owner: User, project: Project, tag: str) -> int:
    resp = await client.post(
        "/api/v1/tasks",
        headers=_bearer(create_access_token(owner.id)),
        json={"project_id": project.id, "title": f"sec {RUN_TOKEN} {tag}"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]["id"]


async def _upload(
    client,
    user: User,
    task_id: int,
    *,
    filename: str | None,
    content: bytes = b"x",
    content_type: str = "application/octet-stream",
):
    return await client.post(
        f"/api/v1/tasks/{task_id}/attachments",
        headers=_bearer(create_access_token(user.id)),
        files={"file": (filename, io.BytesIO(content), content_type)},
    )


# =============================================================================
# 缺陷 1：非法 storage_path 不得产生 500
# =============================================================================


async def test_tampered_traversal_key_returns_404_not_500(client, storage_root):
    """DB 里的 storage_path 被改写为穿越 key → 404，绝不 500。

    这是 TASK-043 修复的核心缺陷：042 只捕获 StorageObjectNotFoundError，
    非法 key 抛出的 UnsafeStorageKeyError 会穿透成未捕获异常（500 + 堆栈），
    把存储根的校验规则泄露给调用者。
    """
    owner = await _make_user("t1", ["admin"])
    project = await _make_project(owner, "t1")
    task_id = await _create_task(client, owner, project, "t1")
    aid = (
        await _upload(client, owner, task_id, filename="a.txt", content=b"data")
    ).json()["data"]["id"]

    tampered = [
        "tasks/1/../../../../etc/passwd",
        "../../etc/passwd",
        "/etc/passwd",
        "C:/Windows/win.ini",
        "tasks\\1\\x.txt",
        "tasks/1/",
        "",
    ]
    for bad_key in tampered:
        async with SessionFactory() as session:
            row = await session.get(Attachment, aid)
            row.storage_path = bad_key
            await session.commit()

        resp = await client.get(
            f"/api/v1/attachments/{aid}",
            headers=_bearer(create_access_token(owner.id)),
        )
        assert resp.status_code == 404, f"{bad_key!r}: {resp.status_code} {resp.text}"
        assert resp.json()["detail"] == "Attachment not found"

        # 列表端点不受影响（列表不触碰物理存储）
        resp = await client.get(
            f"/api/v1/tasks/{task_id}/attachments",
            headers=_bearer(create_access_token(owner.id)),
        )
        assert resp.status_code == 200


async def test_tampered_key_delete_removes_record_instead_of_deadlock(
    client, storage_root
):
    """非法 storage_path 的记录仍可被删除（否则形成永久脏记录）。

    删除路径与下载路径的处理**刻意不同**：下载时非法 key 等价于「文件不可
    访问」→ 404；删除时若同样抛错，记录将永远删不掉。删除的目标是让记录
    消失，物理文件无法定位则跳过。
    """
    owner = await _make_user("t2", ["admin"])
    project = await _make_project(owner, "t2")
    task_id = await _create_task(client, owner, project, "t2")
    aid = (
        await _upload(client, owner, task_id, filename="a.txt")
    ).json()["data"]["id"]

    async with SessionFactory() as session:
        row = await session.get(Attachment, aid)
        row.storage_path = "../../../etc/passwd"
        await session.commit()

    resp = await client.delete(
        f"/api/v1/attachments/{aid}",
        headers=_bearer(create_access_token(owner.id)),
    )
    assert resp.status_code == 200, resp.text

    async with SessionFactory() as session:
        assert (
            await session.execute(select(Attachment).where(Attachment.id == aid))
        ).scalar_one_or_none() is None

    # 审计日志仍然写入（删除动作真实发生了）
    async with SessionFactory() as session:
        logs = (
            await session.execute(
                select(OperationLog).where(
                    OperationLog.resource_type == "attachment",
                    OperationLog.resource_id == aid,
                )
            )
        ).scalars().all()
    assert len(logs) == 1
    assert logs[0].action == "attachment:delete"


async def test_no_file_escapes_storage_root(client, storage_root):
    """任何文件名/篡改组合都不得在存储根之外写出文件。"""
    owner = await _make_user("t3", ["admin"])
    project = await _make_project(owner, "t3")
    task_id = await _create_task(client, owner, project, "t3")

    hostile_names = [
        "../../../../tmp/evil.txt",
        "..%2f..%2f..%2ftmp%2fevil.txt",
        "%2e%2e/%2e%2e/evil.txt",
        "....//....//evil.txt",
        "..\\..\\..\\evil.txt",
        "/abs/evil.txt",
        "C:\\evil.txt",
    ]
    for name in hostile_names:
        resp = await _upload(client, owner, task_id, filename=name)
        assert resp.status_code in (201, 400, 415), f"{name!r}: {resp.text}"
        if resp.status_code == 201:
            stored = resp.json()["data"]["filename"]
            assert "/" not in stored and "\\" not in stored
            assert not stored.startswith(".")

    # 存储根的直接子项只应有 tasks/ 目录（所有内容都在根内）
    direct_children = sorted(p.name for p in storage_root.iterdir())
    assert direct_children == ["tasks"], direct_children


# =============================================================================
# 缺陷 2：百分号编码绕过
# =============================================================================


async def test_percent_encoded_nul_does_not_change_effective_extension(
    client, storage_root
):
    """``a.txt%00.png`` 不得让「校验的扩展名」与「展示的名字」分叉。

    TASK-043 修复前：名字原样入库为 ``a.txt%00.png``，却按 ``png`` 校验。
    ``%00`` 一旦在下游被 URL 解码成 NUL，字符串会截断为 ``a.txt``——校验
    对象与实际对象不一致，是典型的扩展名绕过（§48 文件上传漏洞）。
    """
    owner = await _make_user("p1", ["admin"])
    project = await _make_project(owner, "p1")
    task_id = await _create_task(client, owner, project, "p1")

    resp = await _upload(client, owner, task_id, filename="a.txt%00.png")
    assert resp.status_code == 201, resp.text
    stored = resp.json()["data"]["filename"]

    # 入库名中不得残留任何 %XX 转义
    assert "%" not in stored, stored
    # 有效扩展名必须与展示名一致：都是 png
    assert stored.endswith(".png"), stored
    assert resp.json()["data"]["content_type"] == "image/png"
    # 名字里不得含 NUL 或控制字符
    assert "\x00" not in stored and "\n" not in stored


async def test_percent_encoded_traversal_is_neutralised(client, storage_root):
    """``%2e%2e%2f`` 形式的编码穿越被折叠，不残留路径片段。"""
    owner = await _make_user("p2", ["admin"])
    project = await _make_project(owner, "p2")
    task_id = await _create_task(client, owner, project, "p2")

    resp = await _upload(
        client, owner, task_id, filename="%2e%2e%2f%2e%2e%2fetc%2fpasswd.txt"
    )
    assert resp.status_code == 201, resp.text
    stored = resp.json()["data"]["filename"]
    assert "%" not in stored
    assert ".." not in stored and "/" not in stored

    async with SessionFactory() as session:
        row = (
            await session.execute(
                select(Attachment).where(Attachment.id == resp.json()["data"]["id"])
            )
        ).scalar_one()
    assert row.storage_path.startswith(f"tasks/{task_id}/")
    assert "passwd" not in row.storage_path


async def test_percent_encoded_extensions_in_matrix(client):
    """百分号编码矩阵：剥离后仍按剩余的最后扩展名判定（默认拒绝）。"""
    owner = await _make_user("p3", ["admin"])
    project = await _make_project(owner, "p3")
    task_id = await _create_task(client, owner, project, "p3")

    # 剥离 %XX 后最后扩展名仍是 txt → 允许
    resp = await _upload(client, owner, task_id, filename="doc%20final.txt")
    assert resp.status_code == 201, resp.text
    assert resp.json()["data"]["content_type"] == "text/plain"

    # 剥离后最后扩展名是 exe → 拒绝
    resp = await _upload(client, owner, task_id, filename="report%2epdf%2eexe")
    assert resp.status_code == 415, resp.text


# =============================================================================
# 缺陷 3：无主名 / 畸形文件名的一致行为
# =============================================================================


async def test_degenerate_filenames_are_rejected_consistently(client):
    """纯分隔符/空白/点 → 400；纯扩展名无主名（``.txt``）→ 415。

    两者语义不同：(a) 清洗后什么都不剩 → 400（文件名缺失）；(b) 有扩展名但
    无主名 → 415（类型不可接受）。修复前 (b) 会先被清洗成 ``txt`` 再 415，
    链路上原因与表象不符。
    """
    owner = await _make_user("d1", ["admin"])
    project = await _make_project(owner, "d1")
    task_id = await _create_task(client, owner, project, "d1")

    for name in ["..", ".", "...", "  ", "./", "../", "/", "\\", "a/", "a\\"]:
        resp = await _upload(client, owner, task_id, filename=name)
        assert resp.status_code == 400, f"{name!r}: {resp.status_code} {resp.text}"
        assert resp.json()["detail"] == "Filename is required"

    for name in [".txt", ".png", ".pdf"]:
        resp = await _upload(client, owner, task_id, filename=name)
        assert resp.status_code == 415, f"{name!r}: {resp.status_code} {resp.text}"
        assert resp.json()["detail"] == "File type is not allowed"


async def test_filename_is_truncated_preserving_extension(client):
    """超长文件名截断到列宽上限，且**保留扩展名**（否则 MIME 判定失效）。"""
    owner = await _make_user("d2", ["admin"])
    project = await _make_project(owner, "d2")
    task_id = await _create_task(client, owner, project, "d2")

    resp = await _upload(client, owner, task_id, filename="a" * 500 + ".txt")
    assert resp.status_code == 201, resp.text
    stored = resp.json()["data"]["filename"]
    assert len(stored) <= attachment_service.MAX_FILENAME_LENGTH
    assert stored.endswith(".txt")
    assert resp.json()["data"]["content_type"] == "text/plain"


# =============================================================================
# 扩展名判定契约（固化「看似可疑但安全」的行为）
# =============================================================================


async def test_only_last_extension_decides_and_disk_key_is_whitelisted(client, storage_root):
    """多段扩展名只看最后一段；磁盘 key 用的是白名单扩展名。

    ``shell.php.txt`` 入库为 ``txt``：判定与磁盘都不涉及 ``php``。这条做成
    契约测试，防止后续有人「顺手」改成检查所有扩展名（那会让
    ``v1.0.tar.gz`` 之类的正常文件名被误拒），或误以为这里是漏洞而放开。
    """
    owner = await _make_user("m1", ["admin"])
    project = await _make_project(owner, "m1")
    task_id = await _create_task(client, owner, project, "m1")

    resp = await _upload(client, owner, task_id, filename="shell.php.txt")
    assert resp.status_code == 201, resp.text
    body = resp.json()["data"]
    assert body["filename"] == "shell.php.txt"
    assert body["content_type"] == "text/plain"

    async with SessionFactory() as session:
        row = (
            await session.execute(
                select(Attachment).where(Attachment.id == body["id"])
            )
        ).scalar_one()
    # 磁盘 key 的扩展名取自白名单解析结果，与用户提供的中间扩展名无关
    assert row.storage_path.endswith(".txt")
    assert "php" not in row.storage_path

    # 最后一段不在白名单 → 拒绝
    resp = await _upload(client, owner, task_id, filename="archive.tar.bz2")
    assert resp.status_code == 415, resp.text

    # 白名单内的多段名正常通过（这条防「检查所有扩展名」的过度收紧）
    resp = await _upload(client, owner, task_id, filename="release.tar.gz")
    assert resp.status_code == 201, resp.text
    assert resp.json()["data"]["content_type"] == "application/gzip"


async def test_hostile_content_type_never_reaches_storage_decisions(client):
    """客户端 Content-Type 无论多离谱都不影响入库类型与磁盘 key。"""
    owner = await _make_user("m2", ["admin"])
    project = await _make_project(owner, "m2")
    task_id = await _create_task(client, owner, project, "m2")

    for fake_ct in [
        "text/html",
        "application/x-php",
        "image/svg+xml",
        "application/octet-stream",
        "",
    ]:
        resp = await _upload(
            client,
            owner,
            task_id,
            filename="safe.pdf",
            content=b"%PDF-1.4",
            content_type=fake_ct,
        )
        assert resp.status_code == 201, f"{fake_ct!r}: {resp.text}"
        assert resp.json()["data"]["content_type"] == "application/pdf"


# =============================================================================
# 响应头注入
# =============================================================================


async def test_response_header_injection_is_blocked(client):
    """文件名含引号/CRLF/冒号 → 响应头无注入、无额外头字段。"""
    owner = await _make_user("h1", ["admin"])
    project = await _make_project(owner, "h1")
    task_id = await _create_task(client, owner, project, "h1")

    hostile = [
        'evil"\r\nX-Injected: 1.txt',
        "evil\r\n\r\nHTTP/1.1 200 OK.txt",
        "evil;filename=other.txt",
        "evil\x00.txt",
    ]
    for name in hostile:
        resp = await _upload(client, owner, task_id, filename=name)
        assert resp.status_code == 201, f"{name!r}: {resp.text}"
        aid = resp.json()["data"]["id"]
        stored = resp.json()["data"]["filename"]
        assert "\r" not in stored and "\n" not in stored and "\x00" not in stored

        dl = await client.get(
            f"/api/v1/attachments/{aid}",
            headers=_bearer(create_access_token(owner.id)),
        )
        assert dl.status_code == 200, dl.text

        # 不得出现注入的头字段
        header_names = {k.lower() for k in dl.headers}
        assert "x-injected" not in header_names

        # Content-Disposition 必须是我们构造的那一条，且整体为 ASCII
        cd = dl.headers["content-disposition"]
        assert cd.startswith("attachment; filename*=UTF-8''")
        assert "\r" not in cd and "\n" not in cd
        cd.encode("ascii")  # 非 ASCII 字节会破坏响应头 → 必须编码干净

        await client.delete(
            f"/api/v1/attachments/{aid}",
            headers=_bearer(create_access_token(owner.id)),
        )


async def test_download_content_length_matches_stored_size(client):
    """下载的 Content-Length、DB size、实际字节数三者一致。

    不一致会让客户端截断/挂起，也是「用 Content-Length 撒谎绕过大小限制」
    的镜像问题——本项目按真实字节入库，因此三者必须恒等。
    """
    owner = await _make_user("h2", ["admin"])
    project = await _make_project(owner, "h2")
    task_id = await _create_task(client, owner, project, "h2")

    for payload in [b"a", b"x" * 1024, bytes(range(256)) * 8]:
        resp = await _upload(
            client, owner, task_id, filename="payload.zip", content=payload
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()["data"]
        assert body["size"] == len(payload)

        dl = await client.get(
            f"/api/v1/attachments/{body['id']}",
            headers=_bearer(create_access_token(owner.id)),
        )
        assert dl.status_code == 200
        assert len(dl.content) == len(payload)
        assert dl.content == payload
        assert int(dl.headers["content-length"]) == len(payload)

        async with SessionFactory() as session:
            row = (
                await session.execute(
                    select(Attachment).where(Attachment.id == body["id"])
                )
            ).scalar_one()
        assert row.size == len(payload)


# =============================================================================
# 请求层对抗：协议畸形与并发
# =============================================================================


async def test_malformed_multipart_requests(client):
    """畸形的 multipart 请求一律被拒，且不得产生 500。

    预期的具体状态码分两类，都由框架在进入业务逻辑之前给出：

    - **422**：请求结构合法但缺少必需字段（无 body、字段名不对、体是 JSON）；
    - **400**：声明了 ``multipart/form-data`` 却没有 ``boundary``——这是
      Starlette 解析器层面的协议错误。它给出 400 而非 422 是上游行为，
      我们只需保证「被拒绝且不是 500」。此处把两者都接受并注释原因，
      避免这条测试在框架版本升级时无谓地变红。
    """
    owner = await _make_user("r1", ["admin"])
    project = await _make_project(owner, "r1")
    task_id = await _create_task(client, owner, project, "r1")
    h = _bearer(create_access_token(owner.id))
    url = f"/api/v1/tasks/{task_id}/attachments"

    # 1) 完全没有 body
    assert (await client.post(url, headers=h)).status_code == 422
    # 2) 字段名错误
    resp = await client.post(
        url, headers=h, files={"wrong": ("a.txt", io.BytesIO(b"x"), "text/plain")}
    )
    assert resp.status_code == 422, resp.text
    # 3) 声明 multipart 但缺 boundary（协议层错误 → 400）
    resp = await client.post(
        url, headers={**h, "Content-Type": "multipart/form-data"}, content=b"{}"
    )
    assert resp.status_code in (400, 422), resp.text
    assert resp.status_code != 500
    # 4) 纯 JSON 体
    resp = await client.post(url, headers=h, json={"filename": "a.txt"})
    assert resp.status_code == 422, resp.text

    # 所有畸形请求都不得留下附件记录
    async with SessionFactory() as session:
        rows = (
            await session.execute(
                select(Attachment).where(Attachment.task_id == task_id)
            )
        ).scalars().all()
    assert rows == []


async def test_concurrent_same_name_uploads_do_not_collide(client, storage_root):
    """同名文件并发上传：各自生成独立 key，互不覆盖，内容各自正确。

    并发是同名覆盖类漏洞的常见触发条件（检查与写入之间的 TOCTOU）。本项目
    的 key 由 token_hex(16) 生成且无「先查存在再写入」的步骤，因此天然免疫；
    这条测试把它锁死。
    """
    owner = await _make_user("c1", ["admin"])
    project = await _make_project(owner, "c1")
    task_id = await _create_task(client, owner, project, "c1")
    h = _bearer(create_access_token(owner.id))
    url = f"/api/v1/tasks/{task_id}/attachments"

    payloads = [f"payload-{i}".encode() * 50 for i in range(8)]

    async def _one(payload: bytes):
        return await client.post(
            url,
            headers=h,
            files={"file": ("same.txt", io.BytesIO(payload), "text/plain")},
        )

    responses = await asyncio.gather(*(_one(p) for p in payloads))
    ids = []
    for resp, payload in zip(responses, payloads):
        assert resp.status_code == 201, resp.text
        ids.append(resp.json()["data"]["id"])

    assert len(set(ids)) == len(payloads), "attachment ids must be unique"

    async with SessionFactory() as session:
        rows = (
            await session.execute(
                select(Attachment).where(Attachment.id.in_(ids))
            )
        ).scalars().all()
    assert len({r.storage_path for r in rows}) == len(payloads), (
        "storage_path must be unique per upload"
    )

    # 每个 id 下回来的内容都能唯一对应回一个原始 payload
    recovered = set()
    for aid in ids:
        dl = await client.get(f"/api/v1/attachments/{aid}", headers=h)
        assert dl.status_code == 200
        recovered.add(dl.content)
    assert recovered == set(payloads)


# =============================================================================
# 权限对抗：认证 ≠ 授权（§48）
# =============================================================================


async def test_token_of_outsider_with_full_permissions_still_404(client):
    """持有效 Token 且有全部功能级权限，仍不能碰到他人任务的附件。

    §48「认证 ≠ 授权」+ §49 资源级权限：这条与 042 的对应用例互补——这里
    覆盖**下载与删除**两个更强操作的组合，并确认响应不泄露资源是否存在。
    """
    owner = await _make_user("a1", ["admin"])
    outsider = await _make_user("a2", ["admin"])  # 有 attachment:download/upload
    project = await _make_project(owner, "a1")
    task_id = await _create_task(client, owner, project, "a1")
    aid = (
        await _upload(client, owner, task_id, filename="secret.pdf", content=b"top")
    ).json()["data"]["id"]

    oh = _bearer(create_access_token(outsider.id))

    resp = await client.get(f"/api/v1/attachments/{aid}", headers=oh)
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Attachment not found"
    assert b"top" not in resp.content

    resp = await client.delete(f"/api/v1/attachments/{aid}", headers=oh)
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Attachment not found"

    # 附件仍然完好（越权删除没有生效）
    resp = await client.get(
        f"/api/v1/attachments/{aid}",
        headers=_bearer(create_access_token(owner.id)),
    )
    assert resp.status_code == 200
    assert resp.content == b"top"


async def test_unauthenticated_access_is_401_not_404(client):
    """无 Token → 401（认证缺失），而不是 404。

    与「有 Token 但无权」的 404 形成对照：两类失败必须可区分，否则前端无法
    判断该引导登录还是提示无权限。
    """
    owner = await _make_user("a3", ["admin"])
    project = await _make_project(owner, "a3")
    task_id = await _create_task(client, owner, project, "a3")
    aid = (
        await _upload(client, owner, task_id, filename="a.txt")
    ).json()["data"]["id"]

    for method, url in [
        ("get", f"/api/v1/attachments/{aid}"),
        ("delete", f"/api/v1/attachments/{aid}"),
        ("get", f"/api/v1/tasks/{task_id}/attachments"),
    ]:
        resp = await getattr(client, method)(url)
        assert resp.status_code == 401, f"{method} {url}: {resp.status_code}"
        assert "www-authenticate" in {k.lower() for k in resp.headers}

    resp = await client.post(
        f"/api/v1/tasks/{task_id}/attachments",
        files={"file": ("a.txt", io.BytesIO(b"x"), "text/plain")},
    )
    assert resp.status_code == 401


async def test_audit_log_does_not_leak_storage_path(client, storage_root):
    """审计日志只记业务字段，不含 storage_path（§48 敏感日志泄露）。"""
    owner = await _make_user("a4", ["admin"])
    project = await _make_project(owner, "a4")
    task_id = await _create_task(client, owner, project, "a4")
    body = (
        await _upload(client, owner, task_id, filename="audit.txt")
    ).json()["data"]

    async with SessionFactory() as session:
        row = (
            await session.execute(
                select(Attachment).where(Attachment.id == body["id"])
            )
        ).scalar_one()
    storage_path = row.storage_path

    resp = await client.delete(
        f"/api/v1/attachments/{body['id']}",
        headers=_bearer(create_access_token(owner.id)),
    )
    assert resp.status_code == 200, resp.text

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
    payload = logs[0].payload
    assert set(payload) == {"task_id", "attachment_id", "filename"}
    # 存储布局属于内部信息，不进审计日志
    assert storage_path not in str(payload)
    assert "storage" not in str(payload).lower()


async def test_storage_error_message_is_not_exposed_to_client(client, storage_root):
    """存储层的内部错误文案不得出现在响应体里。

    非法 key 的修复如果只把异常「包一层 500」，调用者仍会看到
    ``storage key must not contain traversal segments`` 这类内部规则描述。
    修复后响应体只有中性文案。
    """
    owner = await _make_user("a5", ["admin"])
    project = await _make_project(owner, "a5")
    task_id = await _create_task(client, owner, project, "a5")
    aid = (
        await _upload(client, owner, task_id, filename="a.txt")
    ).json()["data"]["id"]

    async with SessionFactory() as session:
        row = await session.get(Attachment, aid)
        row.storage_path = "../../etc/passwd"
        await session.commit()

    resp = await client.get(
        f"/api/v1/attachments/{aid}",
        headers=_bearer(create_access_token(owner.id)),
    )
    assert resp.status_code == 404
    body = resp.text.lower()
    for leak in ("storage", "traversal", "key", "root", "resolve", "traceback"):
        assert leak not in body, f"internal detail leaked: {leak!r} in {resp.text!r}"


# =============================================================================
# 大小限制的对抗面
# =============================================================================


async def test_size_limit_uses_real_bytes_not_declared_length(
    client, storage_root, monkeypatch
):
    """上限按真实写入字节数判定，且超限后无任何残留。

    与 042 的用例互补：这里在**接近上限**的多个点做边界扫描，确认「等于上限
    通过、超一字节拒绝」是精确的，不是粗略的近似。
    """
    from app.core.config import get_settings

    settings = get_settings()
    limit = 2048
    monkeypatch.setattr(settings, "max_upload_size", limit, raising=False)

    owner = await _make_user("s1", ["admin"])
    project = await _make_project(owner, "s1")
    task_id = await _create_task(client, owner, project, "s1")

    cases = [
        (limit - 1, 201),
        (limit, 201),
        (limit + 1, 413),
        (limit * 3, 413),
    ]
    for size, expected in cases:
        resp = await _upload(
            client, owner, task_id, filename="s.zip", content=b"z" * size
        )
        assert resp.status_code == expected, f"size={size}: {resp.status_code}"

    async with SessionFactory() as session:
        rows = (
            await session.execute(
                select(Attachment).where(Attachment.task_id == task_id)
            )
        ).scalars().all()
    assert sorted(r.size for r in rows) == [limit - 1, limit]

    # 被拒的两个文件在磁盘上不留痕
    files = [p for p in storage_root.rglob("*") if p.is_file()]
    assert len(files) == 2, [str(p) for p in files]
