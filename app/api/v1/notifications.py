"""Notification endpoints (TASK-053).

Router 只做 HTTP ⇄ Service 翻译（项目规则 §4）。通知是用户私有收件箱，
仅需认证（``CurrentUser``），无需功能级权限依赖——权限理由见
``app.services.notification`` 模块 docstring。

端点：
- ``GET /notifications``：当前用户自己的通知时间线（最新在前，分页）。
- ``PATCH /notifications/{notification_id}/read``：标记自己的一条通知为已读；
  非接收人 / 不存在 → 404 同文案（IDOR 防枚举）。
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser
from app.db.session import get_db
from app.schemas.common import SuccessResponse
from app.schemas.notification import NotificationRead
from app.services.notification import (
    list_user_notifications,
    mark_notification_read as svc_mark_notification_read,
)

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get(
    "",
    response_model=SuccessResponse[list[NotificationRead]],
    status_code=status.HTTP_200_OK,
    summary="List current user's notifications (own inbox only)",
)
async def list_my_notifications(
    user: CurrentUser,
    skip: Annotated[int, Query(ge=0, description="Pagination offset")] = 0,
    limit: Annotated[int, Query(ge=1, le=100, description="Page size")] = 100,
    db: AsyncSession = Depends(get_db),
) -> SuccessResponse[list[NotificationRead]]:
    """返回当前登录用户自己的通知（资源级隔离，看不到别人的）。"""
    notifs = await list_user_notifications(db, user, skip=skip, limit=limit)
    return SuccessResponse(
        data=[NotificationRead.model_validate(n) for n in notifs]
    )


@router.patch(
    "/{notification_id}/read",
    response_model=SuccessResponse[NotificationRead],
    status_code=status.HTTP_200_OK,
    summary="Mark a notification as read (own inbox only)",
    responses={
        404: {"description": "Notification not found / not owned by caller"},
    },
)
async def mark_notification_read(
    notification_id: int,
    user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> SuccessResponse[NotificationRead]:
    """标记一条通知为已读；非接收人 / 不存在 → 404（同文案防枚举）。"""
    notif = await svc_mark_notification_read(db, user, notification_id)
    return SuccessResponse(data=NotificationRead.model_validate(notif))
