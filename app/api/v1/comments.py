"""Comment endpoints — 任务评论（TASK-041）.

Router 只做 HTTP ⇄ Service 的翻译（项目规则 §4）。§16 / §25.6 三端点：

- ``POST /tasks/{task_id}/comments``：发表评论。功能级 ``comment:create``
  + 资源级归属链（Service，不在链上 404 防枚举）；
- ``GET /tasks/{task_id}/comments``：评论列表。**功能级复用 ``task:read``**
  ——§6 权限清单无 comment:read 项（仅 comment:create/delete），评论是任务的
  一部分，读评论即读任务；资源级归属链同创建；
- ``DELETE /comments/{comment_id}``：删除评论。功能级 ``comment:delete``
  （种子仅 admin 持有）+ 资源级 Service 判定（评论作者本人或任务所属团队
  OWNER/ADMIN，否则 403）；删除写 OperationLog（§16 规则 4）。
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_permission
from app.db.session import get_db
from app.models.user import User
from app.schemas.comment import CommentCreate, CommentRead
from app.schemas.common import SuccessResponse
from app.services import comment as comment_service

router = APIRouter(tags=["comments"])


@router.post(
    "/tasks/{task_id}/comments",
    response_model=SuccessResponse[CommentRead],
    status_code=status.HTTP_201_CREATED,
    summary="Post a comment on a task (project team members only)",
    responses={
        403: {"description": "Missing comment:create permission"},
        404: {"description": "Task not found (or not on caller's team chain)"},
    },
)
async def create_comment(
    task_id: int,
    payload: CommentCreate,
    user: Annotated[User, Depends(require_permission("comment:create"))],
    db: AsyncSession = Depends(get_db),
) -> SuccessResponse[CommentRead]:
    comment = await comment_service.create_comment(db, user, task_id, payload.content)
    return SuccessResponse(data=comment)


@router.get(
    "/tasks/{task_id}/comments",
    response_model=SuccessResponse[list[CommentRead]],
    status_code=status.HTTP_200_OK,
    summary="List comments of a task (project team members only)",
    responses={
        403: {"description": "Missing task:read permission"},
        404: {"description": "Task not found (or not on caller's team chain)"},
    },
)
async def list_comments(
    task_id: int,
    user: Annotated[User, Depends(require_permission("task:read"))],
    skip: Annotated[int, Query(ge=0, description="Pagination offset")] = 0,
    limit: Annotated[int, Query(ge=1, le=100, description="Page size")] = 100,
    db: AsyncSession = Depends(get_db),
) -> SuccessResponse[list[CommentRead]]:
    comments = await comment_service.list_comments(
        db, user, task_id, skip=skip, limit=limit
    )
    return SuccessResponse(data=comments)


@router.delete(
    "/comments/{comment_id}",
    response_model=SuccessResponse[None],
    status_code=status.HTTP_200_OK,
    summary=(
        "Delete a comment (author or team owner/admin; writes an audit log)"
    ),
    responses={
        403: {"description": "Caller is neither the author nor team OWNER/ADMIN"},
        404: {"description": "Comment not found (or not on caller's team chain)"},
    },
)
async def delete_comment(
    comment_id: int,
    user: Annotated[User, Depends(require_permission("comment:delete"))],
    db: AsyncSession = Depends(get_db),
) -> SuccessResponse[None]:
    await comment_service.delete_comment(db, user, comment_id)
    return SuccessResponse(data=None)
