"""Tenant 平台管理端点（TASK-093）.

全部端点挂 ``require_permission("tenant:manage")``——平台管理员能力面
（DECISIONS 065）。租户内成员访问「自己租户」的端点属后续任务（前端
TASK-100 一并交付），本 TASK 只交付平台管理面骨架。

生命周期端点：
- POST   /tenants            创建（slug 冲突 409）
- GET    /tenants            分页列表（items + total）
- GET    /tenants/{id}       详情
- PATCH  /tenants/{id}       更新显示名/配额（slug 不可变；deleted 终态 409）
- PATCH  /tenants/{id}/status 状态机转换（白名单，非法转换 409）
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_permission
from app.db.session import get_db
from app.schemas.common import SuccessResponse
from app.schemas.tenant import (
    TenantCreate,
    TenantListRead,
    TenantRead,
    TenantStatusUpdate,
    TenantUpdate,
)
from app.services import tenant as tenant_service

router = APIRouter(prefix="/tenants", tags=["tenants"])


@router.post(
    "",
    response_model=SuccessResponse[TenantRead],
    status_code=status.HTTP_201_CREATED,
    summary="Create a tenant (platform admin)",
    responses={
        401: {},
        403: {"description": "Missing tenant:manage permission"},
        409: {"description": "Tenant slug already exists"},
    },
)
async def create_tenant(
    payload: TenantCreate,
    user: Annotated[object, Depends(require_permission("tenant:manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SuccessResponse[TenantRead]:
    """创建租户。slug 全局唯一，冲突返回 409。"""
    tenant = await tenant_service.create_tenant_with_checks(db, payload)
    return SuccessResponse(data=TenantRead.model_validate(tenant))


@router.get(
    "",
    response_model=SuccessResponse[TenantListRead],
    status_code=status.HTTP_200_OK,
    summary="List tenants with pagination (platform admin)",
    responses={
        401: {},
        403: {"description": "Missing tenant:manage permission"},
    },
)
async def list_tenants(
    user: Annotated[object, Depends(require_permission("tenant:manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> SuccessResponse[TenantListRead]:
    """分页列出全部租户（含 deleted 终态行，平台管理面需要看全量）。"""
    rows, total = await tenant_service.list_tenants_paged(db, skip=skip, limit=limit)
    return SuccessResponse(
        data=TenantListRead(
            items=[TenantRead.model_validate(t) for t in rows], total=total
        )
    )


@router.get(
    "/{tenant_id}",
    response_model=SuccessResponse[TenantRead],
    status_code=status.HTTP_200_OK,
    summary="Get a tenant by id (platform admin)",
    responses={
        401: {},
        403: {"description": "Missing tenant:manage permission"},
        404: {"description": "Tenant not found"},
    },
)
async def get_tenant(
    tenant_id: int,
    user: Annotated[object, Depends(require_permission("tenant:manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SuccessResponse[TenantRead]:
    """租户详情（含 deleted 终态行）。"""
    tenant = await tenant_service.get_tenant_or_404(db, tenant_id)
    return SuccessResponse(data=TenantRead.model_validate(tenant))


@router.patch(
    "/{tenant_id}",
    response_model=SuccessResponse[TenantRead],
    status_code=status.HTTP_200_OK,
    summary="Update tenant name/quotas (platform admin)",
    responses={
        401: {},
        403: {"description": "Missing tenant:manage permission"},
        404: {"description": "Tenant not found"},
        409: {"description": "Tenant is deleted (terminal state)"},
        422: {"description": "Validation error"},
    },
)
async def update_tenant(
    tenant_id: int,
    payload: TenantUpdate,
    user: Annotated[object, Depends(require_permission("tenant:manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SuccessResponse[TenantRead]:
    """部分更新显示名/配额。slug 不可变；deleted 终态不可改。"""
    tenant = await tenant_service.get_tenant_or_404(db, tenant_id)
    tenant = await tenant_service.update_tenant_fields(db, tenant, payload)
    return SuccessResponse(data=TenantRead.model_validate(tenant))


@router.patch(
    "/{tenant_id}/status",
    response_model=SuccessResponse[TenantRead],
    status_code=status.HTTP_200_OK,
    summary="Transition tenant status (platform admin)",
    responses={
        401: {},
        403: {"description": "Missing tenant:manage permission"},
        404: {"description": "Tenant not found"},
        409: {"description": "Illegal status transition (whitelist)"},
    },
)
async def change_tenant_status(
    tenant_id: int,
    payload: TenantStatusUpdate,
    user: Annotated[object, Depends(require_permission("tenant:manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SuccessResponse[TenantRead]:
    """状态机转换：active ↔ suspended、→ deleted 单向；deleted 为终态。"""
    tenant = await tenant_service.get_tenant_or_404(db, tenant_id)
    tenant = await tenant_service.change_tenant_status(db, tenant, payload)
    return SuccessResponse(data=TenantRead.model_validate(tenant))
