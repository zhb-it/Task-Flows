"""Attachment endpoints — 任务附件（TASK-042）.

Router 只做 HTTP ⇄ Service 的翻译（项目规则 §4）。§25.7 三端点：

- ``POST /tasks/{task_id}/attachments``：上传。功能级 ``attachment:upload``
  + 资源级归属链（Service，不在链上 404 防枚举）。入参为 multipart，
  文件字段名 ``file``；
- ``GET /tasks/{task_id}/attachments``：附件列表。**功能级复用
  ``task:read``** —— §6 权限清单无 attachment:read（仅 upload/download），
  附件属于任务，读附件即读任务（与 TASK-041 评论列表同处理）；
- ``GET /attachments/{attachment_id}``：下载单个附件。功能级
  ``attachment:download`` + 资源级归属链校验（§17「下载检查任务访问
  权限」）；响应为文件流而非 JSON，因此**不带** ``SuccessResponse`` 包装。

注意：§25.7 只列出上述三个端点，因此**没有** DELETE 端点之外的写操作；
删除附件的能力落在 ``DELETE /attachments/{attachment_id}``（本 TASK 一并
实现，用于支撑 TASK-043 的权限与安全专项回归）。
"""

from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_permission
from app.db.session import get_db
from app.models.user import User
from app.schemas.attachment import AttachmentRead
from app.schemas.common import SuccessResponse
from app.services import attachment as attachment_service

router = APIRouter(tags=["attachments"])

#: 下载时的分块大小（1MB）；与存储层 CHUNK_SIZE 一致。
_DOWNLOAD_CHUNK_SIZE = 1024 * 1024


@router.post(
    "/tasks/{task_id}/attachments",
    response_model=SuccessResponse[AttachmentRead],
    status_code=status.HTTP_201_CREATED,
    summary="Upload an attachment to a task (project team members only)",
    responses={
        400: {"description": "Empty filename or empty file"},
        403: {"description": "Missing attachment:upload permission"},
        404: {"description": "Task not found (or not on caller's team chain)"},
        413: {"description": "File exceeds MAX_UPLOAD_SIZE"},
        415: {"description": "File extension is not in the MIME allow-list"},
    },
)
async def upload_attachment(
    task_id: int,
    file: Annotated[UploadFile, File(description="The file to attach")],
    user: Annotated[User, Depends(require_permission("attachment:upload"))],
    db: AsyncSession = Depends(get_db),
) -> SuccessResponse[AttachmentRead]:
    result = await attachment_service.upload_attachment(db, user, task_id, file)
    return SuccessResponse(data=result.to_read())


@router.get(
    "/tasks/{task_id}/attachments",
    response_model=SuccessResponse[list[AttachmentRead]],
    status_code=status.HTTP_200_OK,
    summary="List attachments of a task (project team members only)",
    responses={
        403: {"description": "Missing task:read permission"},
        404: {"description": "Task not found (or not on caller's team chain)"},
    },
)
async def list_attachments(
    task_id: int,
    user: Annotated[User, Depends(require_permission("task:read"))],
    skip: Annotated[int, Query(ge=0, description="Pagination offset")] = 0,
    limit: Annotated[int, Query(ge=1, le=100, description="Page size")] = 100,
    db: AsyncSession = Depends(get_db),
) -> SuccessResponse[list[AttachmentRead]]:
    attachments = await attachment_service.list_attachments(
        db, user, task_id, skip=skip, limit=limit
    )
    return SuccessResponse(data=attachments)


@router.get(
    "/attachments/{attachment_id}",
    status_code=status.HTTP_200_OK,
    summary="Download an attachment (project team members only)",
    response_class=StreamingResponse,
    responses={
        200: {"content": {"application/octet-stream": {}}},
        403: {"description": "Missing attachment:download permission"},
        404: {"description": "Attachment not found (or not on caller's team chain)"},
    },
)
async def download_attachment(
    attachment_id: int,
    user: Annotated[User, Depends(require_permission("attachment:download"))],
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """以文件流返回附件。

    响应头处理（§9 安全清单「XSS / 响应头注入」）：

    - ``Content-Disposition`` 用手工拼装的 ``filename*=UTF-8''...`` 形式而
      不是直接塞原始文件名。文件名虽已在 Service 层清洗过，但此处仍走
      ``quote()`` 百分号编码，确保响应头中**不可能**出现换行或引号，从结构
      上杜绝响应头注入；
    - ``X-Content-Type-Options: nosniff`` 阻止浏览器忽略我们声明的类型去
      嗅探内容。这是上传型接口的必备项：否则一个 ``.txt`` 里放的 HTML 在
      某些浏览器里可能被当作页面执行，形成存储型 XSS；
    - ``Content-Type`` 回落到 ``application/octet-stream``。白名单内的
      ``text/*`` 与 ``image/*`` 在浏览器里可能内联渲染，配合 nosniff 已是
      安全默认；需要强制下载的调用方可加 ``?download=1``，但默认不隐式
      改变类型。
    """
    from urllib.parse import quote

    attachment, _uploader, handle = await attachment_service.open_attachment(
        db, user, attachment_id
    )

    encoded = quote(attachment.filename, safe="")
    disposition = f"attachment; filename*=UTF-8''{encoded}"

    return StreamingResponse(
        _iter_file(handle),
        media_type=attachment.content_type or "application/octet-stream",
        headers={
            "Content-Disposition": disposition,
            "Content-Length": str(attachment.size),
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.delete(
    "/attachments/{attachment_id}",
    response_model=SuccessResponse[None],
    status_code=status.HTTP_200_OK,
    summary=(
        "Delete an attachment (uploader or team owner/admin; writes an audit log)"
    ),
    responses={
        403: {
            "description": "Caller is neither the uploader nor team OWNER/ADMIN",
            "detail": "Missing attachment:upload permission or role too low",
        },
        404: {"description": "Attachment not found (or not on caller's team chain)"},
    },
)
async def delete_attachment(
    attachment_id: int,
    user: Annotated[User, Depends(require_permission("attachment:upload"))],
    db: AsyncSession = Depends(get_db),
) -> SuccessResponse[None]:
    await attachment_service.delete_attachment(db, user, attachment_id)
    return SuccessResponse(data=None)


async def _iter_file(handle) -> object:
    """把只读句柄分块吐给客户端，并在结束时关闭句柄。

    用生成器而不是一次性 ``read()``：大文件不该整体驻留内存；同时也保证了
    客户端中断连接时句柄会被正确关闭（finally）。
    """
    try:
        while True:
            chunk = handle.read(_DOWNLOAD_CHUNK_SIZE)
            if not chunk:
                break
            yield chunk
    finally:
        handle.close()
