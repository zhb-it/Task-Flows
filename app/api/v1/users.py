"""User endpoints — `GET /users/me` (TASK-017).

Router 只做 HTTP ⇄ Service 的翻译：认证由 `CurrentUser` 依赖完成，账号状态规则
（是否存在、是否被禁用）在 Service 层（项目规则 §4）。响应复用 `UserRead`，
因此永不包含 `password_hash`。
"""

from fastapi import APIRouter, status

from app.core.deps import CurrentUser
from app.schemas.common import SuccessResponse
from app.schemas.user import UserRead

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
