"""UserRole association ORM model (TASK-021，开发文档 §6「RBAC 权限系统」).

§6 只给出表名与模型链，未定义列。结构为 TASK-021 确认的推断设计（已登记
docs/DB_SCHEMA.md）：

    user_roles:
        id
        user_id     FK users.id ON DELETE CASCADE，建索引
        role_id     FK roles.id ON DELETE CASCADE，建索引
        UNIQUE (user_id, role_id) —— 同一用户不可重复授予同一角色

复合 UNIQUE 防重复授权；`ON DELETE CASCADE` 保证删除用户或角色时关联记录
被一并清理，不产生悬挂授权。表不带头部时间戳（TASK-021 决策：保持纯关联
语义）。
"""

from sqlalchemy import BigInteger, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UserRole(Base):
    __tablename__ = "user_roles"
    __table_args__ = (
        UniqueConstraint("user_id", "role_id", name="uq_user_roles_user_id_role_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
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
        return f"<UserRole id={self.id} user_id={self.user_id} role_id={self.role_id}>"
