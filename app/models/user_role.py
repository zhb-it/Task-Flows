"""UserRole association ORM model (TASK-021，开发文档 §6「RBAC 权限系统」).

§6 只给出表名与模型链，未定义列。结构为 TASK-021 确认的推断设计（已登记
docs/DB_SCHEMA.md）：

    user_roles:
        id
        tenant_id   FK tenants.id ON DELETE RESTRICT，前导索引（TASK-096 租户化）
        user_id     FK users.id ON DELETE CASCADE，建索引
        role_id     FK roles.id ON DELETE CASCADE，建索引
        UNIQUE (user_id, role_id) —— 同一用户不可重复授予同一角色

TASK-096 起用户-角色授予是**租户内**实体（§61.3.4）：user_roles 跟随用户与
角色归属到同一租户，写入由 `before_flush` 从租户上下文注入，查询由
`do_orm_execute` 自动过滤，越权由 RLS 兜底。用户与角色均携带 tenant_id，本表的
tenant_id 与之同源——任意一方跨租户即违反一致性（由 RLS WITH CHECK 兜底拦截）。
表不带头部时间戳（TASK-021 决策：保持纯关联语义）。
"""

from sqlalchemy import BigInteger, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.tenant_context import TenantScoped
from app.db.base import Base


class UserRole(Base, TenantScoped):
    __tablename__ = "user_roles"
    __table_args__ = (
        UniqueConstraint("user_id", "role_id", name="uq_user_roles_user_id_role_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("roles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    def __repr__(self) -> str:
        return (
            f"<UserRole id={self.id} tenant_id={self.tenant_id} "
            f"user_id={self.user_id} role_id={self.role_id}>"
        )
