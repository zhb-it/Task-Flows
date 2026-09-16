"""Permission matrix endpoint — `GET /permissions` (TASK-083).

只读视图：列出全部角色及其持有的权限名。守卫选 **user:update**（种子中仅
admin 持有）——权限矩阵是 RBAC 的管理面配置数据，member 持有的 user:read
语义是「读用户/协作对象」，不该顺带看到全部 RBAC 配置。决策见 DECISIONS 060。
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_permission
from app.db.session import get_db
from app.schemas.common import SuccessResponse
from app.schemas.role import RoleWithPermissionsRead
from app.models.user import User
from app.services import rbac

router = APIRouter(prefix="/permissions", tags=["rbac"])


@router.get(
    "",
    response_model=SuccessResponse[list[RoleWithPermissionsRead]],
    status_code=200,
    summary="List all roles with their permission names (admin view)",
    responses={401: {}, 403: {"description": "Missing user:update permission"}},
)
async def list_permission_matrix(
    user: Annotated[User, Depends(require_permission("user:update"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SuccessResponse[list[RoleWithPermissionsRead]]:
    return SuccessResponse(data=await rbac.get_permission_matrix(db))
