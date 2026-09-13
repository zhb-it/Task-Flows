"""Role ORM model (TASK-021，开发文档 §6「RBAC 权限系统」).

§6 只给出表名与模型链（User → UserRole → Role → RolePermission → Permission），
未定义列。列集为 TASK-021 确认的推断设计（已登记 docs/DB_SCHEMA.md）：

    roles:
        id
        name            UNIQUE —— 角色标识（如 "admin" / "member"）
        description     可空
        created_at
        updated_at

关联表与权限表的定义见 `user_role.py` / `role_permission.py` / `permission.py`。
User 侧的反向关系在后续 TASK（权限依赖 / CRUD 有真实查询需求时）再补，
本 TASK 只做纯表定义。
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
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
        return f"<Role id={self.id} name={self.name!r}>"
