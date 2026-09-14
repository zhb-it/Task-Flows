"""TaskAssignee ORM model（TASK-036，Phase 5 多人分配）.

规格 §5 硬约束：``UNIQUE(task_id, user_id)``——由复合主键天然落实，
一个用户在同一任务上最多一行。

字段（DB_SCHEMA「task_assignees」节，其中 ``assigned_by_id`` 为推断
设计——源文档未定义该表字段）：

    task_id        FK -> tasks(id) ON DELETE CASCADE（PK 之一，删任务清分配行）
    user_id        FK -> users(id) ON DELETE CASCADE（PK 之一，删用户清分配行，
                   不卡用户删除——与 creator_id 同决策，审计由 OperationLog 承担）
    assigned_by_id FK -> users(id) ON DELETE CASCADE——记录谁做的分配（最小审计）
    assigned_at    TIMESTAMPTZ NOT NULL DEFAULT now()

设计说明：

- **不建 Task -> assignees relationship**（沿用 TASK-031「Task 无
  relationship」决策）：assignees 的读取由 Service 层批量查询组装
  （列表场景一次 IN 查询避免 N+1），删除随 FK CASCADE 自动清理。
- ``user_id`` 单列索引：服务于 GET /tasks?assignee_id 过滤与未来的
  「我的任务」反查。
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TaskAssignee(Base):
    __tablename__ = "task_assignees"
    __table_args__ = (
        Index("ix_task_assignees_user_id", "user_id"),
    )

    task_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("tasks.id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    assigned_by_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        return (
            f"<TaskAssignee task_id={self.task_id} user_id={self.user_id} "
            f"assigned_by_id={self.assigned_by_id}>"
        )
