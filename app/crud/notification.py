"""Notification CRUD (TASK-053).

主访问路径是 ``(user_id, created_at DESC)``（§25.8 的 ``GET /notifications``
按接收人 + 时间序查询），复用模型上已建的复合索引
``ix_notifications_user_id_created_at``。

写入只 ``flush`` —— 事务边界在 Service 层（项目规则 §4 / ARCHITECTURE.md）。
``mark_read`` 改属性后 flush，由调用方（Service）提交；读取侧返回 None 表示
「不存在或非接收人」，交给 Service 统一转 404（IDOR 防枚举）。
"""

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification


async def list_by_user(
    db: AsyncSession, user_id: int, *, skip: int = 0, limit: int = 100
) -> list[Notification]:
    """某用户的通知时间线（最新在前），分页。"""
    stmt = (
        select(Notification)
        .where(Notification.user_id == user_id)
        .order_by(desc(Notification.created_at))
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_for_user(
    db: AsyncSession, user_id: int, notification_id: int
) -> Notification | None:
    """取单条并校验归属：通知只属于其接收人。

    非接收人 / 不存在统一返回 None（不区分，防枚举）。
    """
    stmt = select(Notification).where(
        Notification.id == notification_id,
        Notification.user_id == user_id,
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def mark_read(
    db: AsyncSession, user_id: int, notification_id: int
) -> Notification | None:
    """标记已读（flush-only，Service 提交）；非接收人返回 None。

    已读的通知再次标记是幂等操作：不抛错、不产生副作用（保持原行）。
    """
    notif = await get_for_user(db, user_id, notification_id)
    if notif is None:
        return None
    if not notif.is_read:
        notif.is_read = True
        await db.flush()
    return notif
