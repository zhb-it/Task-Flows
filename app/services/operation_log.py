"""OperationLog Service（TASK-039）.

事务边界在本层：``write_operation_log`` 仅 flush，由调用方（如 transition
业务）在其事务内 commit，保证审计与业务动作原子提交。

查询授权（TASK-039 决策，用户确认）：

- ``list_user_logs``：``GET /logs`` 只返回 **当前用户自己** 的日志，无需
  额外资源校验（调用者只能看自己的时间线）。
- ``list_resource_logs``：``GET /logs/{type}/{id}`` 须验证调用者对目标资源
  的归属权限（规则 §9 资源级校验）——当前仅 ``task`` 资源有埋点，校验其
  是否在调用者所属团队链上；不在链 / 不存在 → 404（同文案，IDOR 防枚举）。
"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ResourceNotFoundError
from app.crud.operation_log import (
    create_operation_log,
    list_by_resource,
    list_by_user,
)
from app.crud.project import is_project_visible
from app.crud.task import get_task
from app.models.user import User

RESOURCE_NOT_FOUND = "Resource not found"
UNSUPPORTED_RESOURCE = "Unsupported resource type"


async def write_operation_log(
    db: AsyncSession,
    *,
    user_id: int,
    resource_type: str,
    resource_id: int,
    action: str,
    payload: dict[str, Any] | None = None,
) -> None:
    """写入一条审计日志（仅 flush，由调用方提交事务）。"""
    await create_operation_log(
        db,
        user_id=user_id,
        resource_type=resource_type,
        resource_id=resource_id,
        action=action,
        payload=payload,
    )


async def list_user_logs(
    db: AsyncSession,
    user: User,
    *,
    skip: int = 0,
    limit: int = 100,
) -> list:
    """当前用户的操作时间线（最新在前）。"""
    return await list_by_user(db, user.id, skip=skip, limit=limit)


async def list_resource_logs(
    db: AsyncSession,
    user: User,
    resource_type: str,
    resource_id: int,
    *,
    skip: int = 0,
    limit: int = 100,
) -> list:
    """某资源的操作日志（最新在前）；调用者须对该资源有归属权限。

    - 仅 ``task`` 资源支持（当前唯一埋点类型）；其他类型 → 404
      ``Unsupported resource type``；
    - 任务不在归属链 / 不存在 → 404（IDOR 防枚举）。
    """
    if resource_type != "task":
        raise ResourceNotFoundError(UNSUPPORTED_RESOURCE)

    task = await get_task(db, resource_id)
    if task is None or not await is_project_visible(
        db, project_id=task.project_id, user_id=user.id
    ):
        raise ResourceNotFoundError(RESOURCE_NOT_FOUND)

    return await list_by_resource(
        db, resource_type, resource_id, skip=skip, limit=limit
    )
