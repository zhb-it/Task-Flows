"""OperationLogArchive ORM model（TASK-050 日志归档）.

源开发文档 §23 把「归档操作日志」列为 Celery 后台任务之一；§15 定义
``operation_logs`` 为审计日志（谁 / 何时 / 对什么资源 / 做了什么）。

TASK-050 已确认决策（用户确认）：归档 = **把超过保留期的 operation_logs
行从主表迁到 ``operation_logs_archive`` 历史表**——主表瘦身、审计历史完整
保留，最贴合「归档」字面（DECISIONS 031）。

设计取舍
--------
- **复用原日志 id 作为归档表主键** ``autoincrement=False``：归档是「同一条
  记录搬家」而非「新建记录」。复用 id 让归档表与源表按 id 直接对账，并为
  任务的幂等性提供天然去重点（见下）。
- **``archived_at`` 记录归档时间**：审计迁移事件本身需要可追溯（何时被归档）。
- **字段与 operation_logs 同构**：user_id / resource_type / resource_id /
  action / payload / created_at 全部原样搬入，保证历史表可承担原表的全部查询
  语义（按用户时间线、按资源维度）。
- **不加 CHECK / 不加外键**：与原表一致（§6 Service 负责业务规则；审计
  独立性——user_id 无外键，删用户不卡归档表）。
- **幂等落点**：任务用 ``INSERT ... ON CONFLICT (id) DO NOTHING`` + 同事务
  ``DELETE`` 主表，配合「id 即原 id」——at-least-once 重投时，已归档行被
  ON CONFLICT 跳过、主表对应行早已删除，重投变 no-op（见 ``maintenance_tasks``）。
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, String, func, text, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.tenant_context import TenantScoped
from app.db.base import Base


class OperationLogArchive(TenantScoped, Base):
    __tablename__ = "operation_logs_archive"
    __table_args__ = (
        # 与原表 (user_id, created_at) 对应，但归档后时间语义变为 archived_at。
        Index(
            "ix_operation_logs_archive_user_archived",
            "user_id",
            "archived_at",
        ),
        # 资源维度对账（与原 ix_operation_logs_resource 一致）。
        Index(
            "ix_operation_logs_archive_resource",
            "resource_type",
            "resource_id",
        ),
    )

    #: 复用原日志 id（非自增）——归档是搬家不是新建。
    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=False
    )
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False)
    resource_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    #: 操作上下文（JSONB），原样搬入。
    payload: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    #: 原日志的创建时间（保留原始事件时间，不被归档时间覆盖）。
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    #: 归挡执行时间（审计迁移事件本身可追溯）。
    archived_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
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
            f"<OperationLogArchive id={self.id} user_id={self.user_id} "
            f"resource_type={self.resource_type!r} resource_id={self.resource_id} "
            f"action={self.action!r}>"
        )
