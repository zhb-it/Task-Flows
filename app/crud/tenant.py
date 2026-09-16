"""Tenant CRUD（TASK-093，架构分层：Router → Service → CRUD → Model）.

本层只做数据库操作与精确异常翻译（UNIQUE 冲突 → ``IntegrityError`` 由
Service 语义化为 409）；业务规则（状态机、slug 不可变）在 Service。
"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import Tenant
from app.schemas.tenant import TenantCreate, TenantUpdate


async def get_tenant(db: AsyncSession, tenant_id: int) -> Tenant | None:
    return await db.get(Tenant, tenant_id)


async def get_tenant_by_slug(db: AsyncSession, slug: str) -> Tenant | None:
    result = await db.scalars(select(Tenant).where(Tenant.slug == slug))
    return result.first()


async def list_tenants(
    db: AsyncSession, *, skip: int = 0, limit: int = 50
) -> tuple[list[Tenant], int]:
    """分页列出租户，返回 ``(rows, total)``——显式 COUNT(*)（企业化口径）。"""
    total = await db.scalar(select(func.count()).select_from(Tenant))
    result = await db.scalars(
        select(Tenant).order_by(Tenant.id).offset(skip).limit(limit)
    )
    rows = list(result)
    return rows, int(total or 0)


async def create_tenant(db: AsyncSession, payload: TenantCreate) -> Tenant:
    tenant = Tenant(
        name=payload.name,
        slug=payload.slug,
        member_limit=payload.member_limit,
        storage_limit_bytes=payload.storage_limit_bytes,
    )
    db.add(tenant)
    await db.commit()
    await db.refresh(tenant)
    return tenant


async def update_tenant(
    db: AsyncSession, tenant: Tenant, payload: TenantUpdate
) -> Tenant:
    """部分更新（调用方用 ``exclude_unset`` 传入已提供的字段）。

    注意 ``None`` 显式传入表示「取消配额限制」，与「未提供」不同。
    """
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(tenant, field, value)
    await db.commit()
    await db.refresh(tenant)
    return tenant
