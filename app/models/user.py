"""User ORM model.

Field set is taken verbatim from the project spec (docs/PROJECT_SPEC.md and
the development document §5.1):

    users:
        id
        username        UNIQUE
        email           UNIQUE
        password_hash   (never stored in plaintext)
        is_active
        created_at
        updated_at

The `creator_id BIGINT NOT NULL REFERENCES users(id)` constraint used
elsewhere confirms the primary key is a BIGINT. Password hashing helpers are
introduced later (TASK-014); this model only persists the resulting hash.
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class User(Base):
    __table_args__ = (
        # 唯一性租户化（§5 修订 / TASK-094）：username 与 email 在租户内唯一，
        # 不同租户可存在同名用户——全局 UNIQUE 已在迁移 a9b7c5d3e1f0 删除。
        # ORM 用显式命名约束与迁移同名同源（TASK-093 教训：列级 unique=True
        # 生成匿名约束会让 autogenerate 漂移）。
        UniqueConstraint(
            "tenant_id", "username", name="uq_users_tenant_username"
        ),
        UniqueConstraint("tenant_id", "email", name="uq_users_tenant_email"),
        # 全局查询过渡索引（迁移 a9b7c5d3e1f0 同步创建）：复合唯一以
        # tenant_id 前导，覆盖不了按 username/email 的全局查找。
        Index("ix_users_username", "username"),
        Index("ix_users_email", "email"),
    )

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    username: Mapped[str] = mapped_column(String(150), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
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
        return f"<User id={self.id} username={self.username!r}>"
