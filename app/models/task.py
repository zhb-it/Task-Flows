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
        search_vector （TASK-064：DB 端生成的全文检索列，§14）

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
    Computed,
    DateTime,
    ForeignKey,
    func,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
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

#: 全文检索列的生成表达式（开发文档 §14 原文）。
#:
#: 用**两参数**形式 `to_tsvector(regconfig, text)` 而非 `to_tsvector(text)`：
#: 只有前者是 IMMUTABLE，`GENERATED ... STORED` 才接受它（单参数形式是 STABLE）。
#: `'simple'` 配置不做词干还原、也**不做中文分词**——中文短语会成为单个 token，
#: 因此该列对中文内容的检索能力有限，这是刻意按 §14 原文实现并已知的边界
#: （见 DECISIONS 045）。
SEARCH_VECTOR_SQL = (
    "to_tsvector('simple', "
    "coalesce(title, '') || ' ' || coalesce(description, ''))"
)


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
        # TASK-064（开发文档 §14）：pg_trgm 模糊匹配索引，让 keyword 的
        # `ILIKE '%x%'` 从顺序扫描变成索引扫描（B-tree 对 `%...%` 无效）。
        # 需要 `CREATE EXTENSION pg_trgm` 先存在——由迁移显式创建。
        Index(
            "ix_tasks_title_trgm",
            "title",
            postgresql_using="gin",
            postgresql_ops={"title": "gin_trgm_ops"},
        ),
        # 全文检索列的 GIN 索引（列定义见下方 `search_vector`）。
        Index("ix_tasks_search_vector", "search_vector", postgresql_using="gin"),
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
    #: 全文检索列（TASK-064，开发文档 §14 / DB_SCHEMA「PostgreSQL 能力」）。
    #:
    #: 由 **DB 端生成**（`GENERATED ALWAYS AS (<SEARCH_VECTOR_SQL>) STORED`），
    #: 应用层只读不写——`Computed` 让 SQLAlchemy 自动把它排除在 INSERT/UPDATE
    #: 之外，无需 Service 层配合。声明在 ORM 里是为了让 `alembic
    #: revision --autogenerate` 的 diff 保持干净（否则它会被当成「库里多出来的
    #: 列」而生成一条 drop_column）。
    search_vector: Mapped[str | None] = mapped_column(
        TSVECTOR, Computed(SEARCH_VECTOR_SQL, persisted=True), nullable=True
    )

    #: 所属租户（§61.3 多租户，TASK-094）。ON DELETE RESTRICT：租户的删除
    #: 是状态机事务（DECISIONS 065），物理删除租户一律拒绝而非级联清光。
    tenant_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        # 写入桥接（TASK-094，TASK-095 落认证租户后退化为兜底）：ORM 声明
        # 与 DB 列 DEFAULT 同源——INSERT 未赋值时省略该列、由 DB 归属默认
        # 租户；显式赋值优先（如归档拷贝）。
        server_default=text("current_default_tenant_id()"),
        nullable=False,
        index=True,
    )

    def __repr__(self) -> str:
        return (
            f"<Task id={self.id} project_id={self.project_id} "
            f"title={self.title!r} status={self.status}>"
        )
