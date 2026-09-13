"""Auth services — user registration (TASK-015) and login (TASK-016).

Business rules enforced here (not in the router):

- username / email must be unique → ``ConflictError`` (HTTP 409)
- the plain-text password is hashed exactly once, here, via
  ``app.core.security.hash_password``; only the hash reaches the CRUD layer
- login verifies the password before the account state, and rejects disabled
  accounts → ``UnauthorizedError`` (401) / ``ForbiddenError`` (403)
- the Service owns the transaction boundary (项目规则 §4 / ARCHITECTURE.md)
"""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ForbiddenError, UnauthorizedError
from app.core.security import hash_password, verify_password
from app.crud.user import create_user, get_user_by_email, get_user_by_username
from app.models.user import User
from app.schemas.auth import LoginRequest
from app.schemas.user import UserCreate


async def register_user(db: AsyncSession, payload: UserCreate) -> User:
    """Register a new active user and return the persisted row.

    Raises:
        ConflictError: if the username or the email is already taken.
    """
    if await get_user_by_username(db, payload.username) is not None:
        raise ConflictError("Username is already registered")
    if await get_user_by_email(db, payload.email) is not None:
        raise ConflictError("Email is already registered")

    user = await create_user(
        db,
        username=payload.username,
        email=payload.email,
        password_hash=hash_password(payload.password),
    )

    try:
        await db.commit()
    except IntegrityError as exc:
        # Two concurrent registrations can both pass the checks above; the DB
        # unique constraints are the real guard, so translate the violation.
        await db.rollback()
        raise ConflictError("Username or email is already registered") from exc

    await db.refresh(user)
    return user


async def authenticate_user(db: AsyncSession, payload: LoginRequest) -> User:
    """校验登录凭证，返回可登录的用户。

    校验顺序（安全考量）：先验证密码，再检查账号是否启用。这样「用户名不存在」
    与「密码错误」返回同一条 401 文案，避免用户名枚举；只有在密码正确的前提下
    才会得知账号被禁用。

    Raises:
        UnauthorizedError: 用户不存在或密码错误（401，文案不区分二者）。
        ForbiddenError: 密码正确但账号已被禁用（403）。
    """
    user = await get_user_by_username(db, payload.username)
    if user is None or not verify_password(payload.password, user.password_hash):
        raise UnauthorizedError("Invalid username or password")
    if not user.is_active:
        raise ForbiddenError("User account is disabled")
    return user
