"""Auth endpoints — `POST /api/v1/auth/register` (TASK-015).

The router only translates HTTP ⇄ Service: it validates the payload via the
Pydantic schema, delegates to the Service and wraps the result in the project's
success envelope. No business rules live here (项目规则 §4).
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.common import SuccessResponse
from app.schemas.user import UserCreate, UserRead
from app.services.auth import register_user

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=SuccessResponse[UserRead],
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
    responses={409: {"description": "Username or email already registered"}},
)
async def register(
    payload: UserCreate,
    db: AsyncSession = Depends(get_db),
) -> SuccessResponse[UserRead]:
    user = await register_user(db, payload)
    return SuccessResponse(data=UserRead.model_validate(user))
