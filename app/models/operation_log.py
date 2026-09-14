"""OperationLog ORM model（TASK-039 操作审计日志）.

源开发文档 §15 定义 operation_logs，记录「谁 / 什么时候 / 对什么资源 /
执行了什么操作」：

    operation_logs:
        id
        user_id
        resource_type
        resource_id
        action
        payload        JSONB（操作上下文，如 {old_status, new_status}）
        created_at

TASK-039 已确认决策（用户确认）：

- **user_id 不加外键**：审计日志独立于用户生命周期，删用户后日志完整
  保留（不卡用户删除），追溯由日志自身承担；user_id 仍 NOT NULL（每条
  日志都由已认证用户产生）。与 §15 SQL 一致（SQL 未写 REFERENCES）。
- **payload 用 JSONB**：规格 §15 明示，配合 GIN 索引支持结构化查询；
  默认 ``'{}'::jsonb``，写时不传也能落库。
- **索引**（§15「索引」全量落实）：``(resource_type, resource_id)`` 资源
  维度查询、``(user_id, created_at DESC)`` 用户时间线、GIN(payload)
  结构查询。
- **无 CHECK**：action / resource_type 取值随业务演进，数据库不做枚举
  约束（与项目「不为炫技加高级功能」原则一致）。
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, String, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class OperationLog(Base):
    __tablename__ = "operation_logs"
    __table_args__ = (
        Index(
            "ix_operation_logs_resource",
            "resource_type",
            "resource_id",
        ),
        Index(
            "ix_operation_logs_user_created",
            "user_id",
            "created_at",
        ),
        Index(
            "ix_operation_logs_payload",
            "payload",
            postgresql_using="gin",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    #: 操作者；NOT NULL 但不加 FK（审计独立性，见模块 docstring）。
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False)
    resource_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    #: 操作上下文（JSONB）；写时不传默认为空对象。
    payload: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        return (
            f"<OperationLog id={self.id} user_id={self.user_id} "
            f"resource_type={self.resource_type!r} resource_id={self.resource_id} "
            f"action={self.action!r}>"
        )
