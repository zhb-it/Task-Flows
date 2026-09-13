"""Role / UserRole CRUD operations (TASK-022，开发文档 §6).

Write helpers persist rows via `flush` only — the transaction boundary stays
with the Service layer (项目规则 §4 / ARCHITECTURE.md). The composite UNIQUE
constraints on `user_roles` are the DB-level backstop against duplicate
grants; CRUD callers see the `IntegrityError` on flush.

The seed migration (0de65c197efc) guarantees `admin` / `member` exist in every
environment upgraded through Alembic head.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.role import Role
from app.models.user_role import UserRole


async def create_role(
    db: AsyncSession, *, name: str, description: str | None = None
) -> Role:
    role = Role(name=name, description=description)
    db.add(role)
    await db.flush()
    await db.refresh(role)
    return role


async def get_role(db: AsyncSession, role_id: int) -> Role | None:
    result = await db.execute(select(Role).where(Role.id == role_id))
    return result.scalar_one_or_none()


async def get_role_by_name(db: AsyncSession, name: str) -> Role | None:
    result = await db.execute(select(Role).where(Role.name == name))
    return result.scalar_one_or_none()


async def get_roles(db: AsyncSession, *, skip: int = 0, limit: int = 100) -> list[Role]:
    result = await db.execute(
        select(Role).order_by(Role.id).offset(skip).limit(limit)
    )
    return list(result.scalars().all())


async def assign_role_to_user(
    db: AsyncSession, *, user_id: int, role_id: int
) -> UserRole:
    """Grant a role to a user. Flushes so UNIQUE violations surface here."""
    user_role = UserRole(user_id=user_id, role_id=role_id)
    db.add(user_role)
    await db.flush()
    await db.refresh(user_role)
    return user_role


async def revoke_role_from_user(
    db: AsyncSession, *, user_id: int, role_id: int
) -> bool:
    """Remove a role grant. Returns True if a row was deleted (idempotent)."""
    result = await db.execute(
        select(UserRole).where(
            UserRole.user_id == user_id, UserRole.role_id == role_id
        )
    )
    grant = result.scalar_one_or_none()
    if grant is None:
        return False
    await db.delete(grant)
    await db.flush()
    return True


async def get_user_roles(db: AsyncSession, user_id: int) -> list[Role]:
    result = await db.execute(
        select(Role)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user_id)
        .order_by(Role.id)
    )
    return list(result.scalars().all())
