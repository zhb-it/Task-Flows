"""Notification ORM model（§18 通知系统 / TASK-049）.

源开发文档 §18 定义 notifications：

    notifications:
        id
        user_id
        type
        title
        content
        is_read
        created_at

本表按用户确认**提前于 TASK-052 建模**（通知异步任务 TASK-049 需要真
实落库，否则 §24 的可重试/不重复语义无法实现和测试；TASK-052 届时为
检查项，沿用 TASK-058 提前完成的先例）。

决策（记 docs/DECISIONS.md）：

- **user_id FK→users ON DELETE CASCADE**：通知是"写给某个用户"的内容，
  用户删除后通知失去意义，级联清理（与 ``comments.user_id`` 同惯例）。
  注意与 OperationLog（TASK-039，无外键）的对比：审计日志要留痕，通知
  不需要。
- **type 用 String(50) 不加 CHECK**：§18 列出四个通知场景（任务分配/
  任务状态变更/任务被评论/团队邀请）但未定义为封闭枚举；TASK-053 定义
  Service 时若需要收窄，届时再加约束（避免提前锁死）。
- **content 可空**：§18 未定义可空性；标题（title）是通知摘要、可自足，
  正文允许缺省比强行填空串更诚实。title NOT NULL。
- **is_read NOT NULL 默认 false**：通知产生时必然未读（§18 语义）。
- **索引 (user_id, created_at)**：``GET /api/v1/notifications`` 按接收人
  + 时间序查询的主访问路径（§25.8），沿用 comments 的 (task_id,
  created_at) 模式。
"""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notifications_user_id_created_at", "user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_read: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        return (
            f"<Notification id={self.id} user_id={self.user_id} "
            f"type={self.type!r} is_read={self.is_read}>"
        )
