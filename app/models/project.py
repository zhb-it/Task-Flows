"""Project ORM model（TASK-029 决策，已确认并登记 docs/DB_SCHEMA.md）.

源开发文档未定义 projects 表字段（§7 只给到团队），本模型按 TASK-029
用户确认的决策落地，关系链遵循 DB_SCHEMA 的 ``Team -> Project -> Task``：

    projects:
        id
        name
        description
        team_id     （项目所属团队）
        owner_id    （创建者，可后续转让）
        created_at
        updated_at

Decisions confirmed for TASK-029:

- ``team_id`` FK → ``teams(id)`` **ON DELETE CASCADE**：项目是团队资产，
  团队删除时项目（未来还有其下任务）随之清理，与 team_members 惯例一致。
- ``owner_id`` FK → ``users(id)`` **ON DELETE RESTRICT**：与 teams.owner_id
  同语义——项目记创建者便于后续转让，删用户前必须先处理其项目。
- ``name`` 不加 UNIQUE：源文档未定义，不凭空增加约束。
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, func, String, text

from sqlalchemy.orm import Mapped, mapped_column

from app.core.tenant_context import TenantScoped
from app.db.base import Base


class Project(TenantScoped, Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    team_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("teams.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
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
            f"<Project id={self.id} name={self.name!r} "
            f"team_id={self.team_id} owner_id={self.owner_id}>"
        )
