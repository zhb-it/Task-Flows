"""Permission ORM model (TASK-021，开发文档 §6「RBAC 权限系统」).

§6 只给出表名、模型链与权限命名**示例**（"user:read" / "team:invite" 等
`resource:action` 形态的字符串），未定义列。列集为 TASK-021 确认的推断设计
（已登记 docs/DB_SCHEMA.md）：

    permissions:
        id
        name            UNIQUE —— 权限标识，严格为 "resource:action" 格式
        description     可空
        created_at
        updated_at

按 TASK-021 决策采用**单列 name**（而非拆 resource/action 两列），与 §6 示例
的字符串形态直接对齐，应用层以 `"user:read"` 这样的字符串判断权限。
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
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
        return f"<Permission id={self.id} name={self.name!r}>"
