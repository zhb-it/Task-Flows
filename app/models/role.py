"""Role ORM model (TASK-021，开发文档 §6「RBAC 权限系统」).

§6 只给出表名与模型链（User → UserRole → Role → RolePermission → Permission），
未定义列。列集为 TASK-021 确认的推断设计（已登记 docs/DB_SCHEMA.md）：

    roles:
        id
        tenant_id   FK tenants.id ON DELETE RESTRICT，前导索引（TASK-096 租户化）
        name            UNIQUE —— 角色标识（如 "admin" / "member"），租户内唯一
        description     可空
        created_at
        updated_at

关联表与权限表的定义见 `user_role.py` / `role_permission.py` / `permission.py`。
TASK-096 起角色为**租户内**实体（§61.3「RBAC 改为租户内角色与权限」）：name
在租户内唯一，不同租户可以有同名角色；平台管理员与租户管理员严格区分。
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.tenant_context import TenantScoped
from app.db.base import Base


class Role(Base, TenantScoped):
    __tablename__ = "roles"
    # name 在租户内唯一（不同租户可同名角色）；全局 UNIQUE 由 TASK-096 迁移
    # c2d4e6f8a0b1 从 roles_name_key 改为本复合约束。命名与迁移同源，避免
    # autogenerate 漂移。
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_roles_tenant_name"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False)
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
        return f"<Role id={self.id} tenant_id={self.tenant_id} name={self.name!r}>"
