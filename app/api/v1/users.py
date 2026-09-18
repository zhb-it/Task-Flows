"""User endpoints — `/users/me` (TASK-017) + RBAC 管理 (TASK-082/083).

Router 只做 HTTP ⇄ Service 的翻译：认证由 `CurrentUser` 依赖完成，账号状态规则
（是否存在、是否被禁用）在 Service 层（项目规则 §4）。响应复用 `UserRead`，
因此永不包含 `password_hash`。

权限语义（TASK-082/083 决策，见 DECISIONS 060）：
- `GET /users`（列表）与 `GET /users/{id}/roles`（查看角色）挂 **user:read**
  ——与种子一致：member 也持有 user:read（协作场景需要找到同事）；
- `PUT /users/{id}/roles`（改角色）挂 **user:update** ——种子中仅 admin 持有，
  member 天然不可越权；
- `GET /users/me/permissions` 与 `GET /users/me/overview` 只要求登录
  （查自己的权限 / 自己的工作台，无需授权）。
- 路由声明顺序：`/me/*` 固定前缀必须在 `/users/{user_id}/*` 之前注册——
  FastAPI 按声明顺序匹配，`me` 会被 `{user_id}` 吃掉（int 解析失败变 422）。
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser, require_permission
from app.db.session import get_db
from app.schemas.common import SuccessResponse
from app.schemas.user import (
    MeOverviewRead,
    MePermissionsRead,
    RoleNamesUpdate,
    UserRead,
    UserRolesRead,
    UserWithRolesRead,
)
from app.models.user import User
from app.services import overview as overview_service
from app.services import user as user_service
from app.services.overview import RECENT_PROJECT_LIMIT

router = APIRouter(prefix="/users", tags=["users"])


@router.get(
    "/me",
    response_model=SuccessResponse[UserRead],
    status_code=status.HTTP_200_OK,
    summary="Get the currently authenticated user",
    responses={
        401: {"description": "Missing, invalid or expired access token"},
        403: {"description": "User account is disabled"},
    },
)
async def read_current_user(current_user: CurrentUser) -> SuccessResponse[UserRead]:
    """返回当前 Access Token 所属用户的资料。"""
    return SuccessResponse(data=UserRead.model_validate(current_user))


@router.get(
    "/me/permissions",
    response_model=SuccessResponse[MePermissionsRead],
    status_code=status.HTTP_200_OK,
    summary="List the effective permission names of the current user",
    responses={
        401: {"description": "Missing, invalid or expired access token"},
        403: {"description": "User account is disabled"},
    },
)
async def read_my_permissions(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SuccessResponse[MePermissionsRead]:
    """当前用户的有效权限集合（User → UserRole → Role → RolePermission）。

    与 ``require_permission`` 用同一数据源（``get_user_permissions``），
    前端据此做按钮级显隐（TASK-084），不与后端守卫产生两套真相。
    """
    permissions = await user_service.get_my_permission_names(db, current_user)
    return SuccessResponse(data=MePermissionsRead(permissions=permissions))


@router.get(
    "/me/overview",
    response_model=SuccessResponse[MeOverviewRead],
    status_code=status.HTTP_200_OK,
    summary="Aggregate the current user's workbench overview",
    responses={
        401: {"description": "Missing, invalid or expired access token"},
        403: {"description": "User account is disabled"},
    },
)
async def read_my_overview(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    recent_limit: Annotated[int, Query(ge=1, le=20)] = RECENT_PROJECT_LIMIT,
) -> SuccessResponse[MeOverviewRead]:
    """个人工作台聚合（TASK-129，规格 §61.6「个人视图」+「统计」）。

    一次请求取齐首页（Bento 仪表盘）所需的全部数字，避免前端为凑一屏
    连打五六个接口——那才是真正的 N+1。

    只要求登录（查自己的工作台，无需授权；与 ``/me/permissions`` 同口径）。
    作用域是「当前用户」而非「全局」：项目与任务的可见性、租户隔离分别由
    Service 的可见性谓词与 ``TenantScoped`` + RLS 保证，跨租户数据不会
    出现在本响应里。

    ``recent_limit`` 控制「最近项目」条数（1~20，默认 5）。口径（分母定义、
    「本周完成」用 ``updated_at`` 近似的理由、UTC 周起点）见
    `app/services/overview.py` 模块文档与 `docs/API_CONTRACT.md`。
    """
    overview = await overview_service.get_my_overview(
        db, current_user, recent_limit=recent_limit
    )
    return SuccessResponse(data=MeOverviewRead.model_validate(overview))


@router.get(
    "",
    response_model=SuccessResponse[list[UserWithRolesRead]],
    status_code=status.HTTP_200_OK,
    summary="List users with their role names",
    responses={401: {}, 403: {"description": "Missing user:read permission"}},
)
async def list_users(
    user: Annotated[User, Depends(require_permission("user:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
    q: Annotated[str | None, Query(max_length=64)] = None,
) -> SuccessResponse[list[UserWithRolesRead]]:
    """分页列出用户（含角色名）。member 持有 user:read（找同事/看负责人）。

    ``q`` 可选：按用户名/邮箱做大小写不敏感的子串过滤（TASK-085），
    供前端邀请成员/角色分配的选择器「按名字找人」；空串视同不过滤。
    """
    keyword = q.strip() if q else None
    pairs = await user_service.list_users_with_roles(
        db, skip=skip, limit=limit, q=keyword or None
    )
    data = [
        UserWithRolesRead(**UserRead.model_validate(u).model_dump(), roles=roles)
        for u, roles in pairs
    ]
    return SuccessResponse(data=data)


@router.get(
    "/{user_id}/roles",
    response_model=SuccessResponse[UserRolesRead],
    status_code=status.HTTP_200_OK,
    summary="List role names of a user",
    responses={
        401: {},
        403: {"description": "Missing user:read permission"},
        404: {"description": "User not found"},
    },
)
async def read_user_roles(
    user_id: int,
    user: Annotated[User, Depends(require_permission("user:read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SuccessResponse[UserRolesRead]:
    roles = await user_service.get_user_role_names(db, user_id)
    return SuccessResponse(data=UserRolesRead(user_id=user_id, roles=roles))


@router.put(
    "/{user_id}/roles",
    response_model=SuccessResponse[UserRolesRead],
    status_code=status.HTTP_200_OK,
    summary="Replace the roles of a user (admin)",
    responses={
        401: {},
        403: {
            "description": "Missing user:update permission, or modifying own roles"
        },
        404: {"description": "User or role not found"},
    },
)
async def replace_user_roles(
    user_id: int,
    payload: RoleNamesUpdate,
    user: Annotated[User, Depends(require_permission("user:update"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SuccessResponse[UserRolesRead]:
    """全量替换目标用户的角色集合（PUT 语义；Service 禁止操作自己）。"""
    roles = await user_service.replace_user_roles(
        db, operator=user, user_id=user_id, role_names=payload.roles
    )
    return SuccessResponse(data=UserRolesRead(user_id=user_id, roles=roles))
