"""Permission / RolePermission CRUD operations (TASK-022，开发文档 §6).

Write helpers persist rows via `flush` only — the transaction boundary stays
with the Service layer (项目规则 §4 / ARCHITECTURE.md). The composite UNIQUE
on `role_permissions` is the DB-level backstop against duplicate bindings.

`get_user_permissions` resolves the full model chain
User → UserRole → Role → RolePermission → Permission and returns the
`resource:action` name strings — the exact form TASK-023's permission
dependency will consume.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.permission import Permission
from app.models.role_permission import RolePermission
from app.models.user_role import UserRole


async def create_permission(
    db: AsyncSession, *, name: str, description: str | None = None
) -> Permission:
    permission = Permission(name=name, description=description)
    db.add(permission)
    await db.flush()
    await db.refresh(permission)
    return permission


async def get_permission(db: AsyncSession, permission_id: int) -> Permission | None:
    result = await db.execute(
        select(Permission).where(Permission.id == permission_id)
    )
    return result.scalar_one_or_none()


async def get_permission_by_name(
    db: AsyncSession, name: str
) -> Permission | None:
    result = await db.execute(select(Permission).where(Permission.name == name))
    return result.scalar_one_or_none()


async def get_permissions(
    db: AsyncSession, *, skip: int = 0, limit: int = 100
) -> list[Permission]:
    result = await db.execute(
        select(Permission).order_by(Permission.id).offset(skip).limit(limit)
    )
    return list(result.scalars().all())


async def bind_permission_to_role(
    db: AsyncSession, *, role_id: int, permission_id: int
) -> RolePermission:
    """Bind a permission to a role. Flushes so UNIQUE violations surface here."""
    binding = RolePermission(role_id=role_id, permission_id=permission_id)
    db.add(binding)
    await db.flush()
    await db.refresh(binding)
    return binding


async def unbind_permission_from_role(
    db: AsyncSession, *, role_id: int, permission_id: int
) -> bool:
    """Remove a binding. Returns True if a row was deleted (idempotent)."""
    result = await db.execute(
        select(RolePermission).where(
            RolePermission.role_id == role_id,
            RolePermission.permission_id == permission_id,
        )
    )
    binding = result.scalar_one_or_none()
    if binding is None:
        return False
    await db.delete(binding)
    await db.flush()
    return True


async def get_role_permissions(db: AsyncSession, role_id: int) -> list[Permission]:
    result = await db.execute(
        select(Permission)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .where(RolePermission.role_id == role_id)
        .order_by(Permission.id)
    )
    return list(result.scalars().all())


async def get_user_permissions(db: AsyncSession, user_id: int) -> list[str]:
    """All `resource:action` permission names effective for the user.

    Rows are de-duplicated by name: the same permission bound to two roles the
    user holds must appear once (the permission check is set membership, not a
    count).
    """
    result = await db.execute(
        select(Permission.name)
        .distinct()
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(UserRole, UserRole.role_id == RolePermission.role_id)
        .where(UserRole.user_id == user_id)
        .order_by(Permission.name)
    )
    return list(result.scalars().all())
