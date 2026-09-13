"""Team ORM model（开发文档 §7）.

Field set taken verbatim from the development document §7:

    teams:
        id
        name
        description
        owner_id
        created_at
        updated_at

Decisions confirmed for TASK-026 (registered in docs/DB_SCHEMA.md):

- ``owner_id`` FK → ``users(id)`` **ON DELETE RESTRICT**：团队是聚合根
  （未来挂项目/任务），owner 被删时静默级联删掉整个团队风险过大；必须
  先显式转让所有权才能删除用户。这是项目里第一个 RESTRICT 外键，
  刻意区别于纯从属数据（tokens / 关联表）的 CASCADE 惯例。
- ``name`` 不加 UNIQUE：文档 §7 未定义，DB_SCHEMA「不凭空增加约束」。
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    owner_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
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
        return f"<Team id={self.id} name={self.name!r} owner_id={self.owner_id}>"
