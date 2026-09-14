"""OperationLog CRUD（TASK-039）.

写入只 ``flush`` —— 事务边界在 Service 层（项目规则 §4 / ARCHITECTURE.md）。
审计日志与触发它的业务动作（如 transition）在同一事务内提交，保证原子性：
业务失败回滚时日志也不会落库。

查询按 ``created_at DESC`` 排序（最新在前），支持 ``skip`` / ``limit`` 分页，
与 teams / projects / tasks 列表惯例一致。
"""

from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.operation_log import OperationLog


async def create_operation_log(
    db: AsyncSession,
    *,
    user_id: int,
    resource_type: str,
    resource_id: int,
    action: str,
    payload: dict[str, Any] | None = None,
) -> OperationLog:
    """插入一条审计日志（仅 flush，由调用方 commit）。"""
    log = OperationLog(
        user_id=user_id,
        resource_type=resource_type,
        resource_id=resource_id,
        action=action,
        payload=payload if payload is not None else {},
    )
    db.add(log)
    await db.flush()
    await db.refresh(log)
    return log


async def list_by_user(
    db: AsyncSession,
    user_id: int,
    *,
    skip: int = 0,
    limit: int = 100,
) -> list[OperationLog]:
    """当前用户的操作时间线（最新在前）。"""
    stmt = (
        select(OperationLog)
        .where(OperationLog.user_id == user_id)
        .order_by(desc(OperationLog.created_at))
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def list_by_resource(
    db: AsyncSession,
    resource_type: str,
    resource_id: int,
    *,
    skip: int = 0,
    limit: int = 100,
) -> list[OperationLog]:
    """某资源的全部操作日志（最新在前）。"""
    stmt = (
        select(OperationLog)
        .where(
            OperationLog.resource_type == resource_type,
            OperationLog.resource_id == resource_id,
        )
        .order_by(desc(OperationLog.created_at))
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())
