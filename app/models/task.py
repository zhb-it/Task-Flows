"""Task ORM model（TASK-031 决策，已确认并登记 docs/DB_SCHEMA.md）.

源开发文档未定义 tasks 字段，以下为 TASK-031 用户确认的决策；DB_SCHEMA
硬约束（status / priority CHECK 值集、Task 索引清单）全部落实：

    tasks:
        id
        project_id   （任务所属项目，Project -> Task 链）
        title
        description
        status       TODO / IN_PROGRESS / REVIEW / DONE / CANCELLED
        priority     LOW / MEDIUM / HIGH / URGENT
        creator_id   （创建者）
        due_at       （可空）
        created_at
        updated_at

Decisions confirmed for TASK-031:

- **无 assignee 列**：多人分配由 ``task_assignees`` 承担（TASK-036），
  ``UNIQUE(task_id, user_id)``（规格 §5）。
- **creator_id ON DELETE CASCADE**：任务是项目资产、creator 只是创建者
  （非 owner 式所有者），删用户级联清其创建的任务，不卡用户删除；
  审计追溯由后续 OperationLog 承担。
- **status / priority 为 VARCHAR + CHECK**（存字面字符串 'TODO' 等）：
  API / DB / 日志同字面值，排查直观；Python 侧 :class:`TaskStatus` /
  :class:`TaskPriority` str Enum 提供同值常量。
- **索引**（DB_SCHEMA「Task 索引」清单）：复合 ``(project_id, status)``、
  ``(creator_id)``、``due_at`` 部分索引（仅未完成/未取消任务）。
- 状态流转规则（TODO -> IN_PROGRESS -> REVIEW -> DONE；任意 -> CANCELLED；
  DONE/CANCELLED 终态）由状态机（TASK-037）与 transition API（TASK-038）
  消费，**status 不允许经普通 PATCH 修改**（规格 §5 / Decision 005）。
"""

import enum
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TaskStatus(enum.StrEnum):
    """规格 §5 任务状态。DB 存字面字符串，CHECK 约束兜底。"""

    TODO = "TODO"
    IN_PROGRESS = "IN_PROGRESS"
    REVIEW = "REVIEW"
    DONE = "DONE"
    CANCELLED = "CANCELLED"


class TaskPriority(enum.StrEnum):
    """任务优先级四档。DB 存字面字符串，CHECK 约束兜底。"""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    URGENT = "URGENT"


#: 未完成/未取消（due_at 部分索引的谓词，与 DB_SCHEMA「Task 索引」一致）。
OPEN_STATUSES = (TaskStatus.TODO, TaskStatus.IN_PROGRESS, TaskStatus.REVIEW)


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint(
            "status IN ('TODO', 'IN_PROGRESS', 'REVIEW', 'DONE', 'CANCELLED')",
            name="ck_tasks_status_values",
        ),
        CheckConstraint(
            "priority IN ('LOW', 'MEDIUM', 'HIGH', 'URGENT')",
            name="ck_tasks_priority_values",
        ),
        Index("ix_tasks_project_id_status", "project_id", "status"),
        Index(
            "ix_tasks_due_at_open",
            "due_at",
            postgresql_where="status IN ('TODO', 'IN_PROGRESS', 'REVIEW')",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    project_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: 状态字面值（'TODO' 等），见 :class:`TaskStatus`；新任务默认 TODO。
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="TODO"
    )
    priority: Mapped[str] = mapped_column(
        String(10), nullable=False, server_default="MEDIUM"
    )
    creator_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    due_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self) -> str:
        return (
            f"<Task id={self.id} project_id={self.project_id} "
            f"title={self.title!r} status={self.status}>"
        )
