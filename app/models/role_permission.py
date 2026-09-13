"""RolePermission association ORM model (TASK-021，开发文档 §6「RBAC 权限系统」).

§6 只给出表名与模型链，未定义列。结构为 TASK-021 确认的推断设计（已登记
docs/DB_SCHEMA.md）：

    role_permissions:
        id
        role_id         FK roles.id ON DELETE CASCADE，建索引
        permission_id   FK permissions.id ON DELETE CASCADE，建索引
        UNIQUE (role_id, permission_id) —— 同一角色不可重复绑定同一权限

复合 UNIQUE 防重复绑定；`ON DELETE CASCADE` 保证删除角色或权限时关联记录
被一并清理。表不带头部时间戳（TASK-021 决策：保持纯关联语义）。
"""

from sqlalchemy import BigInteger, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RolePermission(Base):
    __tablename__ = "role_permissions"
    __table_args__ = (
        UniqueConstraint(
            "role_id", "permission_id", name="uq_role_permissions_role_id_permission_id"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
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
            f"<RolePermission id={self.id} role_id={self.role_id} "
            f"permission_id={self.permission_id}>"
        )
