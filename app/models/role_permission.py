"""RolePermission association ORM model (TASK-021，开发文档 §6「RBAC 权限系统」).

§6 只给出表名与模型链，未定义列。结构为 TASK-021 确认的推断设计（已登记
docs/DB_SCHEMA.md）：

    role_permissions:
        id
        tenant_id   FK tenants.id ON DELETE RESTRICT，前导索引（TASK-096 租户化）
        role_id         FK roles.id ON DELETE CASCADE，建索引
        permission_id   FK permissions.id ON DELETE CASCADE，建索引
        UNIQUE (role_id, permission_id) —— 同一角色不可重复绑定同一权限

TASK-096 起授权关系是**租户内**实体（§61.3.4「角色与授权关系带 tenant_id」）：
role_permissions 跟随其 role 归属到租户，写入由 `before_flush` 从租户上下文注入，
查询由 `do_orm_execute` 自动过滤，越权由 RLS 兜底。permission 本身是全局权限
目录（不随租户复制），故本表只挂租户、不挂 permission 的租户。
"""

from sqlalchemy import BigInteger, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.tenant_context import TenantScoped
from app.db.base import Base


class RolePermission(Base, TenantScoped):
    __tablename__ = "role_permissions"
    __table_args__ = (
        UniqueConstraint(
            "role_id", "permission_id", name="uq_role_permissions_role_id_permission_id"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    role_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("roles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    permission_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("permissions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    def __repr__(self) -> str:
        return (
            f"<RolePermission id={self.id} tenant_id={self.tenant_id} "
            f"role_id={self.role_id} permission_id={self.permission_id}>"
        )
