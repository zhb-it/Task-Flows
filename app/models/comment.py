"""Comment ORM model（TASK-041 评论）.

源开发文档 §16 定义 comments（任务下的协作讨论）：

    comments:
        id
        task_id
        user_id
        content
        created_at
        updated_at

TASK-041 已确认决策（用户确认）：

- **user_id FK→users ON DELETE CASCADE**：评论是用户产出内容，删用户
  级联清其评论（与 ``tasks.creator_id`` 同惯例）；审计追溯由
  OperationLog（TASK-039）承担。
- **task_id FK→tasks ON DELETE CASCADE**：评论必须属于任务（§16 规则 2），
  删任务级联清其全部评论。
- **updated_at 保留但本 TASK 不做编辑端点**（§25.6 端点清单仅
  POST/GET/DELETE）：字段由 DB 维护，创建时等于 created_at，编辑能力
  留后续 TASK。
- **索引 (task_id, created_at)**：评论列表按任务维度 + 时间序查询的主
  访问路径（§16 未显式定义，按查询模式推断并登记）。
- content 用 TEXT（用户输入可能较长），NOT NULL 且非空由 Schema 校验。
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, func, Index, Text, text

from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Comment(Base):
    __tablename__ = "comments"
    __table_args__ = (
        Index("ix_comments_task_id_created_at", "task_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    task_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
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
            f"<Comment id={self.id} task_id={self.task_id} "
            f"user_id={self.user_id}>"
        )
