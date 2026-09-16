"""RBAC 只读服务（TASK-083）。

Router 层不得直接 import CRUD 层（`tests/test_quality_checks.py` 的架构
门禁），`GET /permissions` 的矩阵装配逻辑放在这里——虽然当前只是「查询 +
拼装」，但它决定了 API 契约的输出形状（按角色分组、权限名按字典序），
属于业务语义而非数据访问细节。
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.permission import get_role_permissions
from app.crud.role import get_roles
from app.schemas.role import RoleWithPermissionsRead


async def get_permission_matrix(db: AsyncSession) -> list[RoleWithPermissionsRead]:
    """全部角色 + 各自权限名（字典序）。

    权限名统一按字典序输出：``get_role_permissions`` 按 Permission.id（种子
    插入序）返回，直接透传会让矩阵与 ``/users/me/permissions``（name 序）
    出现两种顺序契约，前端没法做集合比较。角色数是种子量级（2 个），
    逐角色查询不构成 N+1 风险。
    """
    roles = await get_roles(db)
    return [
        RoleWithPermissionsRead(
            id=role.id,
            name=role.name,
            description=role.description,
            permissions=sorted(p.name for p in await get_role_permissions(db, role.id)),
        )
        for role in roles
    ]
