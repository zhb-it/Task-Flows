"""Notification Service (TASK-053).

通知是用户私有收件箱：任何已认证用户只看自己的（资源级隔离，最小暴露面，
同 OperationLog 的 ``GET /logs`` 仅返回自己）。

权限决策：本模块端点**仅认证**，不加功能级权限依赖。理由——
§18 通知写给「某个用户」、与登录身份强绑定，任何已认证用户访问自己的收件箱
是天然合理的，引入 ``notification:read`` 之类权限项既无对应业务语义、又需
改动 RBAC seed（§6 权限清单亦无 ``notification:*`` 项）；最小权限原则下「不加
多余的权限闸门」优于「为每个端点机械套用 require_permission」。若后续出现
「管理员代看他人通知」等需求，再单独加权限项。
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ResourceNotFoundError
from app.crud.notification import list_by_user, mark_all_read, mark_read
from app.models.notification import Notification
from app.models.user import User

NOTIFICATION_NOT_FOUND = "Notification not found"  # 不存在/不属于你同文案，防枚举


async def list_user_notifications(
    db: AsyncSession, user: User, *, skip: int = 0, limit: int = 100
) -> list[Notification]:
    """当前用户的通知时间线（最新在前）。"""
    return await list_by_user(db, user.id, skip=skip, limit=limit)


async def mark_notification_read(
    db: AsyncSession, user: User, notification_id: int
) -> Notification:
    """标记某通知为已读（仅当属于当前用户）。

    - 已在读 → 幂等返回原行；
    - 非接收人 / 不存在 → 404（与「不存在」不可区分，IDOR 防枚举）。
    """
    notif = await mark_read(db, user.id, notification_id)
    if notif is None:
        raise ResourceNotFoundError(NOTIFICATION_NOT_FOUND)
    await db.commit()
    return notif


async def mark_all_notifications_read(db: AsyncSession, user: User) -> int:
    """把当前用户全部未读通知标记为已读（TASK-054）。

    返回本次真正翻转的条数（已是已读的不计入，重复调用幂等返回 0）。
    资源级隔离由 CRUD 的 WHERE 条件保证——只更新 ``user_id`` 属于
    当前用户的行，不存在 404 语义（「没有未读」是合法的 0，不是错误）。
    """
    marked = await mark_all_read(db, user.id)
    await db.commit()
    return marked
