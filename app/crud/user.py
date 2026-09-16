"""User CRUD operations.

The write helper persists the *already hashed* `password_hash`. Hashing itself
is the responsibility of the security module / Service layer (TASK-014/015),
keeping this layer free of auth concerns.
"""

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


async def create_user(
    db: AsyncSession, *, username: str, email: str, password_hash: str
) -> User:
    user = User(username=username, email=email, password_hash=password_hash)
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user


async def get_user(db: AsyncSession, user_id: int) -> User | None:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def get_user_by_username(db: AsyncSession, username: str) -> User | None:
    result = await db.execute(select(User).where(User.username == username))
    return result.scalar_one_or_none()


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def get_users(
    db: AsyncSession, *, skip: int = 0, limit: int = 100, q: str | None = None
) -> list[User]:
    """分页列出用户；``q`` 非空时按用户名/邮箱做大小写不敏感的子串过滤。

    邀请成员（前端选择器）与权限页找人都要「按名字找人再拿 id」，纯自增
    id 列表无法定位目标（TASK-085）。`ILIKE '%q%'` 与任务搜索同款实现
    （pg_trgm/ILIKE 口径，见 DECISIONS 036）；结果仍按 id 升序，分页语义不变。
    """
    stmt = select(User).order_by(User.id).offset(skip).limit(limit)
    if q:
        pattern = f"%{q}%"
        stmt = stmt.where(or_(User.username.ilike(pattern), User.email.ilike(pattern)))
    result = await db.execute(stmt)
    return list(result.scalars().all())
