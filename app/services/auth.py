"""Auth services — user registration (TASK-015).

Business rules enforced here (not in the router):

- username / email must be unique → ``ConflictError`` (HTTP 409)
- the plain-text password is hashed exactly once, here, via
  ``app.core.security.hash_password``; only the hash reaches the CRUD layer
- the Service owns the transaction boundary (项目规则 §4 / ARCHITECTURE.md)
"""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError
from app.core.security import hash_password
from app.crud.user import create_user, get_user_by_email, get_user_by_username
from app.models.user import User
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
