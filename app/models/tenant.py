"""Tenant ORM model（开发文档 §61.3 多租户，TASK-093）.

平台 → 租户 → 用户/团队/项目 的顶层边界实体。字段定稿见
docs/DB_SCHEMA.md「tenants（TASK-093）」：

    tenants:
        id
        name                租户显示名（不加 UNIQUE，与 teams.name 同口径）
        slug                全局 UNIQUE，对外标识（未来子域/域名基础），创建后不可变
        status              active / suspended / deleted（CHECK 约束保证值域）
        member_limit        成员数上限，NULL = 未设限（配额执行在后续任务接入成员时实现）
        storage_limit_bytes 存储上限（字节），NULL = 未设限
        created_at
        updated_at

TASK-093 拍板并登记 docs/DECISIONS.md 065 的决策：

- ``status`` 的**值域**由 DB CHECK 保证；**转换白名单**（active ↔ suspended、
  active/suspended → deleted、deleted 为终态）由 Service 层执行——CHECK 表达
  不了「从哪个状态来」，两条防线缺一不可。
- ``slug`` 格式 ``^[a-z0-9]([a-z0-9-]*[a-z0-9])?$`` 也由 CHECK 兜底（Service/Schema
  层先行校验，DB 防绕过 API 的直写）。
- 本 TASK 只建模型与生命周期骨架，**不接业务表**：业务表 ``tenant_id`` 归属
  属 TASK-094，因此本表暂无被引用的级联行为。
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

#: slug 规则：小写字母/数字，中间可含连字符，不以连字符开头或结尾。
TENANT_SLUG_PATTERN = r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$"

#: 状态转换白名单（TaskFlow 的终态语义：deleted 单向不可逆）。
ALLOWED_TENANT_TRANSITIONS: dict[str, frozenset[str]] = {
    "active": frozenset({"suspended", "deleted"}),
    "suspended": frozenset({"active", "deleted"}),
    "deleted": frozenset(),
}


class Tenant(Base):
    __tablename__ = "tenants"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'suspended', 'deleted')",
            name="ck_tenants_status",
        ),
        CheckConstraint(
            f"slug ~ '{TENANT_SLUG_PATTERN}'",
            name="ck_tenants_slug_format",
        ),
        CheckConstraint(
            "member_limit IS NULL OR member_limit > 0",
            name="ck_tenants_member_limit",
        ),
        CheckConstraint(
            "storage_limit_bytes IS NULL OR storage_limit_bytes >= 0",
            name="ck_tenants_storage_limit",
        ),
        # 显式命名（而非列级 unique=True）：保证 ORM 元数据与迁移里的
        # uq_tenants_slug 同名同源，autogenerate 比对不会漂移；UNIQUE 约束
        # 在 PG 中自带索引，无需再建独立 ix_tenants_slug。
        UniqueConstraint("slug", name="uq_tenants_slug"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    slug: Mapped[str] = mapped_column(String(63), unique=True, nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="active", server_default=text("'active'")
    )
    member_limit: Mapped[int | None] = mapped_column(nullable=True)
    storage_limit_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
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
        return f"<Tenant id={self.id} slug={self.slug!r} status={self.status!r}>"
