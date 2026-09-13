"""Auth endpoints — register (TASK-015) and login (TASK-016).

The router only translates HTTP ⇄ Service: it validates the payload via the
Pydantic schema, delegates to the Service and wraps the result in the project's
success envelope. No business rules live here (项目规则 §4).
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.db.session import get_db
from app.schemas.auth import LoginRequest, TokenResponse
from app.schemas.common import SuccessResponse
from app.schemas.user import UserCreate, UserRead
from app.services.auth import authenticate_user, register_user

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


@router.post(
    "/login",
    response_model=SuccessResponse[TokenResponse],
    status_code=status.HTTP_200_OK,
    summary="Log in and obtain an access token",
    responses={
        401: {"description": "Invalid username or password"},
        403: {"description": "User account is disabled"},
    },
)
async def login(
    payload: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> SuccessResponse[TokenResponse]:
    user = await authenticate_user(db, payload)
    token = create_access_token(user.id)
    return SuccessResponse(data=TokenResponse(access_token=token))
