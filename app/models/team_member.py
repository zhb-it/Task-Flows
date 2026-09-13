"""TeamMember ORM model（开发文档 §7）.

Field set taken verbatim from the development document §7:

    team_members:
        id
        team_id
        user_id
        role_id
        joined_at

Decisions confirmed for TASK-026 (registered in docs/DB_SCHEMA.md):

- ``role_id`` 表示**团队角色**（OWNER / ADMIN / MEMBER，§7 示例），与全局
  RBAC 角色（``roles`` 表，管 `resource:action` 功能权限）是两个维度。
  存储为 ``SmallInteger`` + 数据库 ``CHECK IN (1, 2, 3)`` 枚举，Python 侧
  用 :class:`TeamRole` IntEnum 提供可读名。
- ``team_id`` / ``user_id`` 外键 ON DELETE CASCADE：纯从属数据，随主体
  清理（与 ``user_roles`` 惯例一致）。
- 复合 UNIQUE ``(team_id, user_id)``：§7「一个用户不能重复加入同一个团队」
  （DB_SCHEMA 已明确约束）。
"""

import enum
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    SmallInteger,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TeamRole(enum.IntEnum):
    """§7 团队角色示例。DB 中存 1/2/3，CHECK 约束兜底。"""

    OWNER = 1
    ADMIN = 2
    MEMBER = 3


class TeamMember(Base):
    __tablename__ = "team_members"
    __table_args__ = (
        CheckConstraint(
            "role_id IN (1, 2, 3)", name="ck_team_members_role_id"
        ),
        UniqueConstraint("team_id", "user_id", name="uq_team_members_team_user"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    team_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("teams.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    #: 团队角色（OWNER/ADMIN/MEMBER），见 :class:`TeamRole`。
    role_id: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        return (
            f"<TeamMember id={self.id} team_id={self.team_id} "
            f"user_id={self.user_id} role={TeamRole(self.role_id).name}>"
        )
