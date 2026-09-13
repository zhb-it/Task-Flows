"""Auth endpoints — register (TASK-015), login (TASK-016), refresh (TASK-018)
and logout (TASK-019).

The router only translates HTTP ⇄ Service: it validates the payload via the
Pydantic schema, delegates to the Service and wraps the result in the project's
success envelope. No business rules live here (项目规则 §4).
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser
from app.db.session import get_db
from app.schemas.auth import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    TokenResponse,
)
from app.schemas.common import SuccessResponse
from app.schemas.user import UserCreate, UserRead
from app.services.auth import (
    authenticate_user,
    issue_token_pair,
    logout_user,
    register_user,
    rotate_tokens,
)

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
    summary="Log in and obtain an access/refresh token pair",
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
    access_token, refresh_token = await issue_token_pair(db, user)
    return SuccessResponse(
        data=TokenResponse(
            access_token=access_token, refresh_token=refresh_token
        )
    )


@router.post(
    "/refresh",
    response_model=SuccessResponse[TokenResponse],
    status_code=status.HTTP_200_OK,
    summary="Exchange a refresh token for a new token pair",
    responses={
        401: {"description": "Missing, invalid, expired or revoked refresh token"},
        403: {"description": "User account is disabled"},
    },
)
async def refresh(
    payload: RefreshRequest,
    db: AsyncSession = Depends(get_db),
) -> SuccessResponse[TokenResponse]:
    access_token, refresh_token = await rotate_tokens(db, payload.refresh_token)
    return SuccessResponse(
        data=TokenResponse(
            access_token=access_token, refresh_token=refresh_token
        )
    )


@router.post(
    "/logout",
    response_model=SuccessResponse[None],
    status_code=status.HTTP_200_OK,
    summary="Revoke the given refresh token (log out)",
    responses={
        401: {"description": "Missing, invalid or expired access token"},
        403: {"description": "Refresh token does not belong to current user"},
    },
)
async def logout(
    payload: LogoutRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> SuccessResponse[None]:
    await logout_user(db, current_user, payload.refresh_token)
    return SuccessResponse(data=None)
