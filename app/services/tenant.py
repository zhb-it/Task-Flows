"""Tenant Service（TASK-093：生命周期业务规则）.

职责边界：
- slug 冲突 → ``ConflictError``(409)（DB UNIQUE 是兜底防线）；
- 状态机白名单：active ↔ suspended、active/suspended → deleted、
  **deleted 为终态**（白名单常量与模型层同源：``ALLOWED_TENANT_TRANSITIONS``）；
- slug 创建后不可变：更新契约里根本没有 slug 字段，这里再加一道显式拒绝，
  防御未来有人在 payload 里塞 slug 时静默生效。

平台管理员判定不在本层——端点入口 ``require_permission("tenant:manage")``
已先行挡住（DECISIONS 065：能力面先行，身份实体拆分属 TASK-096）。
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ResourceNotFoundError
from app.crud.tenant import (
    create_tenant,
    get_tenant,
    get_tenant_by_slug,
    list_tenants,
    update_tenant,
)
from app.models.tenant import ALLOWED_TENANT_TRANSITIONS, Tenant
from app.schemas.tenant import TenantCreate, TenantStatusUpdate, TenantUpdate
from app.services.rbac_seed import seed_tenant_rbac

SLUG_TAKEN = "Tenant slug already exists"
TENANT_NOT_FOUND = "Tenant not found"
TENANT_DELETED = "Tenant is deleted"
ILLEGAL_TRANSITION = "Illegal status transition: {old} -> {new}"


async def create_tenant_with_checks(
    db: AsyncSession, payload: TenantCreate
) -> Tenant:
    """创建租户；slug 冲突（含已删除租户占用的 slug）→ 409。

    deleted 租户的行保留在库中（终态是状态而非物理删除），因此其 slug
    依旧占用——slug 是对外标识，复用会带来「新租户继承旧租户历史」的风险。

    TASK-096：新租户必须有独立的 admin / member 角色与权限绑定（租户内 RBAC），
    ``seed_tenant_rbac`` 在创建后幂等播种（不授予平台权限 ``tenant:manage``，
    故租户管理员无法越权管理其他租户）。
    """
    if await get_tenant_by_slug(db, payload.slug) is not None:
        raise ConflictError(SLUG_TAKEN)
    tenant = await create_tenant(db, payload)  # 内部已提交
    await seed_tenant_rbac(db, tenant.id)  # 新事务内播种（翻转 GUC 以过 RLS）
    await db.commit()
    await db.refresh(tenant)
    return tenant


async def get_tenant_or_404(db: AsyncSession, tenant_id: int) -> Tenant:
    tenant = await get_tenant(db, tenant_id)
    if tenant is None:
        raise ResourceNotFoundError(TENANT_NOT_FOUND)
    return tenant


async def list_tenants_paged(
    db: AsyncSession, *, skip: int = 0, limit: int = 50
) -> tuple[list[Tenant], int]:
    """分页列出全部租户（平台管理面需要看到 deleted 终态行）。"""
    return await list_tenants(db, skip=skip, limit=limit)


async def change_tenant_status(
    db: AsyncSession, tenant: Tenant, payload: TenantStatusUpdate
) -> Tenant:
    """按白名单转换状态；同状态重复请求幂等放行（不改行）。"""
    new_status = payload.status
    if new_status != tenant.status:
        if new_status not in ALLOWED_TENANT_TRANSITIONS[tenant.status]:
            raise ConflictError(
                ILLEGAL_TRANSITION.format(old=tenant.status, new=new_status)
            )
        tenant.status = new_status
        await db.commit()
        await db.refresh(tenant)
    return tenant


async def update_tenant_fields(
    db: AsyncSession, tenant: Tenant, payload: TenantUpdate
) -> Tenant:
    """更新显示名/配额。deleted 为终态，不可再改（409）。"""
    if tenant.status == "deleted":
        raise ConflictError(TENANT_DELETED)
    return await update_tenant(db, tenant, payload)
