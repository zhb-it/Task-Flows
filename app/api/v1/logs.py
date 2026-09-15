"""OperationLog endpoints（TASK-039 审计查询）.

Router 只做 HTTP ⇄ Service 翻译（项目规则 §4）。授权分两层（TASK-039
决策，用户确认）：

- 功能级：``require_permission("log:read")`` 缺权限 → 403；种子中 admin
  与 member 均持有该权限。
- 资源级：``GET /logs/{type}/{id}`` 由 Service 层校验调用者对目标资源的
  归属权限（规则 §9）；``GET /logs`` 仅返回当前用户自己的时间线，无需
  额外资源校验。

响应统一 ``SuccessResponse[list[OperationLogRead]]``，payload 原样透传。
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_permission
from app.db.session import get_db
from app.models.user import User
from app.schemas.operation_log import OperationLogRead
from app.schemas.common import SuccessResponse
from app.services import operation_log as log_service

router = APIRouter(prefix="/logs", tags=["operation-logs"])


@router.get(
    "",
    response_model=SuccessResponse[list[OperationLogRead]],
    status_code=status.HTTP_200_OK,
    summary="List current user's operation logs (own timeline only)",
    responses={
        403: {"description": "Missing log:read permission"},
    },
)
async def list_my_logs(
    user: Annotated[User, Depends(require_permission("log:read"))],
    skip: Annotated[int, Query(ge=0, description="Pagination offset")] = 0,
    limit: Annotated[int, Query(ge=1, le=100, description="Page size")] = 100,
    db: AsyncSession = Depends(get_db),
) -> SuccessResponse[list[OperationLogRead]]:
    logs = await log_service.list_user_logs(db, user, skip=skip, limit=limit)
    return SuccessResponse(data=[OperationLogRead.model_validate(log) for log in logs])


@router.get(
    "/{resource_type}/{resource_id}",
    response_model=SuccessResponse[list[OperationLogRead]],
    status_code=status.HTTP_200_OK,
    summary="List operation logs of a resource (caller must own it)",
    responses={
        403: {"description": "Missing log:read permission"},
        404: {
            "description": (
                "Resource not found / not on caller's team chain / "
                "unsupported resource type"
            ),
        },
    },
)
async def list_resource_logs(
    resource_type: str,
    resource_id: int,
    user: Annotated[User, Depends(require_permission("log:read"))],
    skip: Annotated[int, Query(ge=0, description="Pagination offset")] = 0,
    limit: Annotated[int, Query(ge=1, le=100, description="Page size")] = 100,
    db: AsyncSession = Depends(get_db),
) -> SuccessResponse[list[OperationLogRead]]:
    logs = await log_service.list_resource_logs(
        db, user, resource_type, resource_id, skip=skip, limit=limit
    )
    return SuccessResponse(data=[OperationLogRead.model_validate(log) for log in logs])
