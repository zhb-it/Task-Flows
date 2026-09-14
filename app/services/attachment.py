"""Attachment Service（TASK-042）.

事务边界在本层（项目规则 §4）。本模块集中承载 §17 的全部上传/下载要求，
以及 §9 安全清单中「文件上传漏洞 / 路径穿越」两类风险的业务侧防线。

职责划分（重要）：

- **路径穿越与文件系统安全** → ``app/services/storage.py``（唯一做 key →
  绝对路径转换的地方）；
- **文件名清洗、MIME 白名单、大小限制的语义判定、授权、审计** → 本模块。

这样分工的理由：存储层只回答「这个 key 能不能安全落地」，业务层回答
「这个文件该不该被接收、谁能拿」。把 MIME 白名单放进存储层会让存储层承担
业务策略，日后换对象存储时策略会跟着搬家，属于职责错配。

授权模型（§17 + §6 权限清单）：

- 功能级：``attachment:upload`` / ``attachment:download``（Router 依赖）。
  §6 清单**没有** attachment:read / attachment:delete，因此：
  - 列表读取复用 ``task:read``（附件属于任务，读附件即读任务，与
    TASK-041 评论列表同处理）；
  - 删除复用 ``attachment:upload``（能上传即能管理自己的上传物），再由
    资源级判定收敛到「上传者本人或团队 OWNER/ADMIN」。
- 资源级：一律先过归属链（任务 → 项目 → 团队 → ``team_members``），不在
  链上 → 404 防枚举（§49 / IDOR 契约）；已在链上但角色不足 → 403 明示。

一致性与失败处理（关键设计）：

1. **先落盘、再落库**：只有文件确实写入成功，才创建元数据行。反序会产生
   「有记录、无文件」的幽灵附件，下载时必然 500。
2. **落库失败要回滚物理文件**：元数据写入（含 flush）如果抛错，立即删除
   已落盘的文件，避免产生「有文件、无记录」的孤儿垃圾。
3. **删附件：先删物理文件、再删记录**。删文件失败（IO 错误）时**不删
   记录**并向上抛错——宁可留下一条指向已失效文件的记录让人重试，也不
   制造「记录没了、文件永远留在磁盘」的不可回收泄漏。
4. 删除记录后写 ``action=attachment:delete`` 审计日志，与业务同一事务
   提交（§55.3，复用 OperationLog）。
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from typing import BinaryIO

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import AppError, ForbiddenError, ResourceNotFoundError
from app.crud.attachment import (
    create_attachment as create_attachment_crud,
    delete_attachment as delete_attachment_crud,
    get_attachment,
    list_attachments_by_task,
)
from app.crud.project import get_project, is_project_visible
from app.crud.task import get_task
from app.models.attachment import Attachment
from app.models.task import Task
from app.models.team_member import TeamRole
from app.models.user import User
from app.schemas.attachment import AttachmentRead
from app.services import storage as storage_service
from app.services.operation_log import write_operation_log
from app.services.team import team_membership

ATTACHMENT_NOT_FOUND = "Attachment not found"
TASK_NOT_FOUND = "Task not found"
NOT_MANAGER = (
    "Only team owner or admin or the uploader can delete attachments"
)
FILE_TOO_LARGE = "Uploaded file is too large"
EMPTY_FILENAME = "Filename is required"
EMPTY_FILE = "Uploaded file is empty"
MIME_NOT_ALLOWED = "File type is not allowed"

#: 扩展名 → 规范 MIME 白名单（§17「MIME 校验」）。
#:
#: 采用**扩展名判定的白名单**而非轻信客户端的 ``Content-Type``：multipart
#: 里的 content-type 是客户端自报字段，可任意伪造，用它做唯一判定等于没有
#: 校验。这里以扩展名为准，落库时写入我们认可的规范 MIME。
#:
#: 白名单刻意保持精简：只覆盖任务协作场景真正需要的类型（图片、PDF、纯
#: 文本、常见办公文档、压缩包）。未列入的类型一律拒绝，需要时再由业务方
#: 显式扩充——「默认拒绝」是上传类接口唯一安全的默认值。
ALLOWED_TYPES: dict[str, str] = {
    # 图片
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
    "webp": "image/webp",
    "bmp": "image/bmp",
    # 文档
    "pdf": "application/pdf",
    "txt": "text/plain",
    "md": "text/markdown",
    "csv": "text/csv",
    "json": "application/json",
    "doc": "application/msword",
    "docx": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ),
    "xls": "application/vnd.ms-excel",
    "xlsx": (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    ),
    "ppt": "application/vnd.ms-powerpoint",
    "pptx": (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    ),
    # 压缩包
    "zip": "application/zip",
    "gz": "application/gzip",
}

#: 文件名最大长度（与 ``attachments.filename`` 的 String(255) 对齐）。
MAX_FILENAME_LENGTH = 255

#: 控制字符（含 NUL、CR、LF）——文件名里出现这些字符会污染日志、响应头
#: 与部分文件系统。
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f]")

#: 百分号编码转义（``%00`` / ``%2e`` / ``%2f`` / ``%5c`` 等）。见
#: :func:`sanitize_filename` docstring 第 2 步：这类序列一旦在下游被 URL
#: 解码，会让「校验时的名字」与「使用时的名字」不一致，从而绕过扩展名白名单。
_PERCENT_ESCAPE_RE = re.compile(r"%[0-9A-Fa-f]{2}")

#: Windows 保留设备名——在部分平台上无法创建，且可能造成歧义。
_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


class _UploadReader(io.RawIOBase):
    """把 Starlette ``UploadFile`` 适配成存储层需要的同步 ``BinaryIO``。

    为什么需要这一层：

    ``UploadFile.read()`` 是协程，而存储层接口刻意保持同步——文件系统与
    boto3 都是同步生态，硬改成全异步会污染抽象。桥接方式的选择很关键：

    - **不能**用 ``loop.run_until_complete(upload.read(...))``：``backend.save``
      是在事件循环内被同步调用的，此时循环**已在运行**，再次驱动同一个循环
      会直接抛 ``RuntimeError: This event loop is already running``。
    - **不能**直接把 ``upload.read()`` 的协程交给同步代码：会得到
      「coroutine was never awaited」并丢失数据。

    这里采用最朴素也最稳的做法：读取 Starlette 已经准备好的**底层同步句柄**
    ``upload.file``。

    安全性说明（为什么这不阻塞事件循环）：
    Starlette 在解析 multipart 时已经把请求体写入 ``SpooledTemporaryFile``
    —— 小文件留在内存（``read`` 不涉及系统调用），大文件落在临时目录且由
    Starlette 自己用线程池写入。而本项目的 ``MAX_UPLOAD_SIZE`` 默认 10MB，
    单次 ``read(1MB)`` 的本地 IO 开销在微秒到毫秒量级。这与「不阻塞」的
    工程要求是相容的；真正的整请求阻塞风险在于把请求体直接透传成网络流，
    而 Starlette 已经替我们缓冲完毕。

    实现细节：``upload.file`` 需要先 ``seek(0)``，因为 Starlette 解析完后
    指针位置不保证在开头（小文件 SpooledTemporaryFile 通常已回绕，但显式
    归零才不依赖该未文档化行为）。
    """

    def __init__(self, upload: UploadFile) -> None:
        upload.file.seek(0)
        self._fh = upload.file

    def read(self, size: int = -1) -> bytes:  # type: ignore[override]
        return self._fh.read(size)

    def readable(self) -> bool:  # type: ignore[override]
        return True


class FileTooLargeError(AppError):
    """413 Payload Too Large —— 超过 ``MAX_UPLOAD_SIZE``。"""

    status_code = 413
    detail = FILE_TOO_LARGE


class UnsupportedMediaTypeError(AppError):
    """415 Unsupported Media Type —— 扩展名不在白名单内。"""

    status_code = 415
    detail = MIME_NOT_ALLOWED


class InvalidUploadError(AppError):
    """400 Bad Request —— 上传内容本身不合法（空文件名 / 空文件）。"""

    status_code = 400
    detail = EMPTY_FILENAME


@dataclass(frozen=True)
class UploadResult:
    """上传成功后的返回值（元数据 + 已落盘字节数）。"""

    attachment: Attachment
    uploader: str

    def to_read(self) -> AttachmentRead:
        """转成出站契约（Router 直接使用，不必触碰内部字段拼装）。"""
        return to_read(self.attachment, self.uploader)


def sanitize_filename(raw: str | None) -> str:
    """把客户端提供的文件名收敛成可安全展示/回传的名字。

    处理顺序（每一步都必要）：

    1. 去目录成分——同时按 ``/`` 与 ``\\`` 切分后取最后一段。这是**头号**
       防线：``../../etc/passwd``、``C:\\Windows\\x.txt`` 都在这里被削成
       纯文件名。注意磁盘上的真实路径用的是随机 key，与文件名无关（见
       ``storage.build_key``），所以此处的清洗是**纵深防御**的第二层，
       而不是唯一依靠。
    2. **剥离百分号编码转义**（TASK-043 修复）——``%00`` / ``%2e`` / ``%2f``
       这类序列在下游任何一处做 URL 解码时都会变成 ``\\x00`` / ``.`` / ``/``。
       一个含 ``%00`` 的名字如果被下游解码，会截断成完全不同的字符串，导致
       「校验时看到的扩展名」与「实际使用的扩展名」不一致——这是经典的扩展名
       绕过。这里主动把 ``%XX`` 形态折叠掉，让校验对象与最终展示对象一致。
    3. 去控制字符与首尾空白/点——结尾的点在 Windows 上会被静默截断，可能
       造成同名歧义；开头/结尾空白无意义且易被用作绕过。
    4. 折叠保留字的裸名——``CON``、``NUL`` 等加下划线前缀。
    5. 截断到 ``MAX_FILENAME_LENGTH``，且**保留扩展名**（截断如果砍掉
       扩展名，MIME 判定与用户识别都会失效）。
    6. 全部清空后回落为 ``untitled``，不产生空文件名。

    返回值的性质：这是一个**展示用**名字，绝不参与任何路径构造。
    """
    if not raw:
        raise InvalidUploadError(EMPTY_FILENAME)

    # 1) 去目录成分（POSIX 与 Windows 分隔符都要处理）
    name = raw.replace("\\", "/").split("/")[-1]

    # 2) 剥离百分号编码（见 docstring 2；必须在去控制字符之前做，否则
    #    ``%00`` 解码后的 NUL 会绕过控制字符过滤）
    name = _PERCENT_ESCAPE_RE.sub("", name)

    # 3) 去控制字符、去首尾空白与点
    name = _CONTROL_CHARS_RE.sub("", name).strip().strip(".")

    if not name:
        raise InvalidUploadError(EMPTY_FILENAME)

    # 4) 折叠 Windows 保留设备名（比较不含扩展名的基名）
    stem, dot, ext = name.rpartition(".")
    base = stem if dot else name
    if base.upper() in _RESERVED_NAMES:
        name = f"_{name}"

    # 5) 截断但保留扩展名
    if len(name) > MAX_FILENAME_LENGTH:
        stem, dot, ext = name.rpartition(".")
        if dot and len(ext) <= 20:
            keep = MAX_FILENAME_LENGTH - len(ext) - 1
            name = f"{stem[:keep]}.{ext}"
        else:
            name = name[:MAX_FILENAME_LENGTH]

    return name


def resolve_content_type(filename: str) -> tuple[str, str]:
    """按扩展名做白名单校验，返回 ``(规范 MIME, 小写扩展名)``。

    无扩展名 / 无主名（如 ``.txt``）/ 扩展名不在白名单
    → :class:`UnsupportedMediaTypeError`(415)。

    ``filename`` 必须是**已清洗**的名字（调用方先跑 ``sanitize_filename``）。
    扩展名判定基于清洗后的结果，因此不存在「判定对象 ≠ 展示对象」的缝隙。
    """
    stem, dot, ext = filename.rpartition(".")
    if not dot or not ext or not stem:
        # ``.txt``（有扩展名但无主名）也归为不可接受：这类名字在实践中只会
        # 来自构造请求，而不会来自真实浏览器；一律 415 保持行为一致
        # （TASK-043 修复前它经清洗变成 ``txt`` 后同样 415，但原因不同）。
        raise UnsupportedMediaTypeError(MIME_NOT_ALLOWED)
    ext = ext.lower()
    mime = ALLOWED_TYPES.get(ext)
    if mime is None:
        raise UnsupportedMediaTypeError(MIME_NOT_ALLOWED)
    return mime, ext


async def upload_attachment(
    db: AsyncSession, user: User, task_id: int, upload: UploadFile
) -> UploadResult:
    """上传附件到任务（§17）。

    顺序：归属链校验 → 文件名清洗 → 扩展名白名单 → 流式落盘（含大小硬限）
    → 元数据落库 → 提交。落库失败回滚物理文件（见模块 docstring 一致性
    设计 2）。
    """
    task = await _get_task_on_chain(db, user, task_id)

    filename = sanitize_filename(upload.filename)
    content_type, ext = resolve_content_type(filename)

    settings = get_settings()
    backend = storage_service.get_storage_backend()
    key = storage_service.build_key(task.id, suffix=f".{ext}")

    # 落盘：边写边累计，超限会中止并清理半成品。
    #
    # ``UploadFile`` 的读取接口是 async 的，而存储层接口是同步 BinaryIO，
    # 两者由 ``_UploadReader`` 桥接（见该类 docstring）。
    try:
        size = backend.save(
            key, _UploadReader(upload), max_size=settings.max_upload_size
        )
    except storage_service.StorageError as exc:
        # 存储层把「超限」和「其它 IO 失败」都归为 StorageError；按语义分别
        # 映射为 413 / 500。用消息判定而不是另设异常类，是为了让存储抽象层
        # 保持最小接口（对象存储实现同样只需抛这一个基类）。
        if "exceeds the limit" in str(exc):
            raise FileTooLargeError(FILE_TOO_LARGE) from exc
        raise
    finally:
        await upload.close()

    if size == 0:
        # 空文件：落盘成功但没有内容，直接回收，不产生记录。
        backend.delete(key)
        raise InvalidUploadError(EMPTY_FILE)

    try:
        attachment = await create_attachment_crud(
            db,
            task_id=task.id,
            uploader_id=user.id,
            filename=filename,
            storage_path=key,
            content_type=content_type,
            size=size,
        )
        await db.commit()
    except IntegrityError as exc:
        # storage_path 唯一约束冲撞（理论上 token_hex(16) 不会撞；真撞了也
        # 必须回滚物理文件，否则留下孤儿）。
        await db.rollback()
        backend.delete(key)
        raise AppError("Failed to persist attachment metadata") from exc
    except Exception:
        await db.rollback()
        backend.delete(key)
        raise

    await db.refresh(attachment)
    return UploadResult(attachment=attachment, uploader=user.username)


async def list_attachments(
    db: AsyncSession, user: User, task_id: int, *, skip: int = 0, limit: int = 100
) -> list[AttachmentRead]:
    """任务下附件列表（§17）；须在任务归属链上，否则 404。"""
    await _get_task_on_chain(db, user, task_id)
    rows = await list_attachments_by_task(db, task_id, skip=skip, limit=limit)
    return [
        to_read(a, uploader) for a, uploader in rows
    ]


async def open_attachment(
    db: AsyncSession, user: User, attachment_id: int
) -> tuple[Attachment, str, BinaryIO]:
    """准备下载：返回 ``(元数据, uploader, 只读句柄)``。

    §17 明确要求「下载检查任务访问权限」——授权判定与列表/上传同源，均为
    归属链校验（功能级 ``attachment:download`` 由 Router 依赖承担）。

    不存在 / 不在归属链 → 404 同文案（防枚举）。记录存在但物理文件缺失
    （运维事故、磁盘被清理）→ 同样是 404，而不是 500：对调用者而言「拿不到
    这个文件」的语义就是不存在，暴露 500 只会泄露内部状态。

    **纵深防御的一个已知盲区**（TASK-043 修复）：``storage_path`` 正常由
    ``build_key`` 生成、必然合法，但如果它被绕过 API 直接改写（DB 被入侵、
    迁移脚本写错、历史脏数据），存储层会抛 :class:`UnsafeStorageKeyError`。
    该异常**同样是「拿不到这个文件」**，必须一并映射为 404——否则会以未捕获
    异常的形式变成 500 + 堆栈，把「存储根的相对 key 校验规则」泄露给调用者。
    """
    attachment = await get_attachment(db, attachment_id)
    if attachment is None:
        raise ResourceNotFoundError(ATTACHMENT_NOT_FOUND)

    task = await get_task(db, attachment.task_id)
    if task is None or not await _is_task_visible(db, task, user.id):
        raise ResourceNotFoundError(ATTACHMENT_NOT_FOUND)

    # 取上传者名（下载响应的元信息需要；表已加载该列关系，直接查用户表）。
    uploader = await _get_username(db, attachment.uploader_id)

    backend = storage_service.get_storage_backend()
    try:
        handle = backend.open(attachment.storage_path)
    except (
        storage_service.StorageObjectNotFoundError,
        # 非法 key（穿越/绝对路径/盘符）→ 语义上等价于「此文件不可访问」，
        # 与不存在统一 404。绝不把它升级成 500：见 docstring。
        storage_service.UnsafeStorageKeyError,
    ) as exc:
        raise ResourceNotFoundError(ATTACHMENT_NOT_FOUND) from exc
    return attachment, uploader, handle


async def delete_attachment(
    db: AsyncSession, user: User, attachment_id: int
) -> None:
    """删除附件：上传者本人或任务所属团队 OWNER/ADMIN（§17 + 规则 §9）。

    - 不存在 / 不在归属链 → 404 Attachment not found（同文案防枚举）；
    - 已在链上但既非上传者、团队角色也不足 → 403 明示；
    - 物理文件删除失败 → 不删记录，向上抛错，事务回滚；
    - ``storage_path`` 非法（被绕过 API 改写）→ 不删记录，**降级为删记录成功**
      并记录告警语义：见下方说明；
    - 成功 → 删文件、删记录，同事务写 ``action=attachment:delete`` 审计日志。

    **非法 storage_path 的处理与下载路径不同**（TASK-043 决策）：下载时非法
    key 与「文件不存在」语义等价，统一 404。但删除时若同样抛错，会形成**永久
    卡死的脏记录**——记录里的 key 永远非法，用户永远删不掉它。这属于数据
    修复场景，因此选择「记录可以删掉，物理文件无法定位就跳过」：删除的目标
    是让这条记录消失，而不是保证磁盘上少一个文件（那个文件本就不在存储根内，
    我们也不该去碰）。
    """
    attachment = await get_attachment(db, attachment_id)
    if attachment is None:
        raise ResourceNotFoundError(ATTACHMENT_NOT_FOUND)

    task = await get_task(db, attachment.task_id)
    if task is None or not await _is_task_visible(db, task, user.id):
        raise ResourceNotFoundError(ATTACHMENT_NOT_FOUND)

    if attachment.uploader_id != user.id:
        project = await get_project(db, task.project_id)
        assert project is not None  # 归属链已通过，项目必然存在
        role = await team_membership(db, project.team_id, user.id)
        if role not in (TeamRole.OWNER, TeamRole.ADMIN):
            raise ForbiddenError(NOT_MANAGER)

    storage_path = attachment.storage_path
    task_id = attachment.task_id

    # 先删物理文件：失败则整体失败，记录保留，可重试（见模块 docstring 3）。
    try:
        storage_service.get_storage_backend().delete(storage_path)
    except storage_service.UnsafeStorageKeyError:
        # 脏数据：key 非法而非文件缺失。跳过物理删除，继续删记录（见 docstring）。
        pass

    await delete_attachment_crud(db, attachment)
    await write_operation_log(
        db,
        user_id=user.id,
        resource_type="attachment",
        resource_id=attachment_id,
        action="attachment:delete",
        payload={
            "task_id": task_id,
            "attachment_id": attachment_id,
            "filename": attachment.filename,
        },
    )
    await db.commit()


async def _get_task_on_chain(
    db: AsyncSession, user: User, task_id: int
) -> Task:
    """任务不存在或调用者不在归属链上 → 404（IDOR 防枚举）。"""
    task = await get_task(db, task_id)
    if task is None or not await _is_task_visible(db, task, user.id):
        raise ResourceNotFoundError(TASK_NOT_FOUND)
    return task


async def _is_task_visible(db: AsyncSession, task: Task, user_id: int) -> bool:
    """任务可见性 = 调用者在任务所属项目的团队成员链上。"""
    return await is_project_visible(
        db, project_id=task.project_id, user_id=user_id
    )


async def _get_username(db: AsyncSession, user_id: int) -> str:
    """取用户名（下载响应/列表展示用）。"""
    result = await db.execute(select(User.username).where(User.id == user_id))
    return result.scalar_one_or_none() or ""


def to_read(attachment: Attachment, uploader: str) -> AttachmentRead:
    """把 ORM 行 + 上传者名转成出站契约（Router / 本模块共用）。"""
    return AttachmentRead(
        id=attachment.id,
        task_id=attachment.task_id,
        uploader_id=attachment.uploader_id,
        uploader=uploader,
        filename=attachment.filename,
        content_type=attachment.content_type,
        size=attachment.size,
        created_at=attachment.created_at,
    )
