"""租户 RBAC 播种服务（TASK-096，§61.3.4 租户内 RBAC）.

每个新创建的租户都应有自己独立的 admin / member 角色与权限绑定——权限是全局
目录（permissions 表不复制），但角色与授权关系是**租户内**实体（带 tenant_id，
由 RLS 兜底）。`:func:`seed_tenant_rbac` 在指定租户内幂等播种，被
``tenant_service.create_tenant_with_checks`` 在创建租户后调用。

设计要点：

- **写入靠租户上下文注入**：本函数先把 ContextVar 置为 ``tenant_id``，于是
  ``before_flush`` 把新角色/绑定行的 ``tenant_id`` 自动注入为该租户；查询经
  ``do_orm_execute`` 自动限定到该租户。
- **RLS 兜底同步**：运行时角色（taskflow_app）受 RLS 约束，WITH CHECK 要求
  写入行的 ``tenant_id == 当前事务 GUC``。本函数确保事务已开启并把 GUC 翻转为
  该租户（``enforce_tenant_guc``），写入才不会被策略拒绝。
- **平台权限隔离**：只播种 ``rbac_data.ALL_PERMISSIONS``（22 项），**不含**
  ``tenant:manage``——租户管理员因此永远无法跨租户管理（DECISIONS 062）。
- **幂等**：先按 name 查租户内角色，缺失才建；重放（升级 / 重试）零副作用。
- **不提交**：flush-only，事务边界交给调用方（创建租户的同一次请求内提交）。
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rbac_data import (
    ADMIN_ROLE_NAME,
    MEMBER_ROLE_NAME,
    ROLE_DESCRIPTIONS,
    ROLE_PERMISSIONS,
)
from app.core.tenant_context import (
    enforce_tenant_guc,
    reset_current_tenant_id,
    set_current_tenant_id,
)
from app.crud.permission import bind_permission_to_role, get_permission_by_name
from app.crud.role import create_role, get_role_by_name


async def seed_tenant_rbac(db: AsyncSession, tenant_id: int) -> None:
    """在 ``tenant_id`` 租户内幂等播种 admin / member 角色及其权限绑定。

    Args:
        db: 异步会话（事务边界由调用方管理）。
        tenant_id: 目标租户主键。

    Returns:
        无；写入经 ``db.flush()`` 落库，不提交。
    """
    token = set_current_tenant_id(tenant_id)
    try:
        # 确保事务已开启，以便把 RLS 事务级 GUC 翻转为本租户（非超管运行时
        # 角色写入受 WITH CHECK 约束，GUC 必须匹配否则被拒）。
        if not db.in_transaction():
            await db.begin()
        await enforce_tenant_guc(db)

        role_ids: dict[str, int] = {}
        for role_name in (ADMIN_ROLE_NAME, MEMBER_ROLE_NAME):
            existing = await get_role_by_name(db, role_name)
            if existing is not None:
                role_ids[role_name] = existing.id
                continue
            role = await create_role(
                db,
                name=role_name,
                description=ROLE_DESCRIPTIONS.get(role_name),
            )
            role_ids[role_name] = role.id
            for perm_name in ROLE_PERMISSIONS[role_name]:
                perm = await get_permission_by_name(db, perm_name)
                if perm is not None:
                    await bind_permission_to_role(
                        db, role_id=role.id, permission_id=perm.id
                    )
        await db.flush()
    finally:
        reset_current_tenant_id(token)
