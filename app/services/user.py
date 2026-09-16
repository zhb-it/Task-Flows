"""User services — resolving the authenticated user (TASK-017).

`load_current_user` 把「已通过 JWT 校验的 subject」翻译成一个真实可用的用户，
并在此强制两条账号状态规则（项目规则 §4：业务规则属于 Service，不属于 Router）：

- subject 指向的用户不存在 → 401：Token 签名虽有效，但它指向的账号已不存在，
  凭证事实上已失效，客户端应当重新登录。
- 用户存在但 `is_active=false` → 403：凭证有效且账号可识别，只是已被禁用，
  与 `authenticate_user` 对禁用账号的处理保持同一语义（决策见 API_CONTRACT.md）。

401 的文案与 `decode_access_token` 保持一致，不向客户端区分「Token 坏」与
「账号不存在」，避免通过响应差异探测账号是否存在。
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError, ResourceNotFoundError, UnauthorizedError
from app.crud.role import assign_role_to_user, get_role_by_name, revoke_role_from_user
from app.crud.user import get_user, get_users
from app.crud.permission import get_user_permissions
from app.models.role import Role
from app.models.user import User
from app.models.user_role import UserRole


async def load_current_user(db: AsyncSession, user_id: int) -> User:
    """返回 ``user_id`` 对应的当前登录用户，或拒绝该请求。

    Raises:
        UnauthorizedError: 用户不存在（401）。
        ForbiddenError: 用户存在但账号已被禁用（403）。
    """
    user = await get_user(db, user_id)
    if user is None:
        raise UnauthorizedError("Invalid or expired token")
    if not user.is_active:
        raise ForbiddenError("User account is disabled")
    return user


# ---------------------------------------------------------------------------
# RBAC 管理服务（TASK-082/083）
# ---------------------------------------------------------------------------


async def _load_roles_map(
    db: AsyncSession, user_ids: list[int]
) -> dict[int, list[str]]:
    """批量解析 user_id → 角色名列表（单查询，避免列表接口 N+1）。"""
    if not user_ids:
        return {}
    result = await db.execute(
        select(UserRole.user_id, Role.name)
        .join(Role, Role.id == UserRole.role_id)
        .where(UserRole.user_id.in_(user_ids))
        .order_by(UserRole.user_id, Role.id)
    )
    roles_map: dict[int, list[str]] = {uid: [] for uid in user_ids}
    for uid, name in result.all():
        roles_map.setdefault(uid, []).append(name)
    return roles_map


async def list_users_with_roles(
    db: AsyncSession, *, skip: int = 0, limit: int = 100, q: str | None = None
) -> list[tuple[User, list[str]]]:
    """分页列出用户并附带各自角色名（GET /users，TASK-082/085）。"""
    users = await get_users(db, skip=skip, limit=limit, q=q)
    roles_map = await _load_roles_map(db, [u.id for u in users])
    return [(u, roles_map.get(u.id, [])) for u in users]


async def get_user_role_names(db: AsyncSession, user_id: int) -> list[str]:
    """返回用户的角色名列表；用户不存在 → 404（GET /users/{id}/roles）。"""
    user = await get_user(db, user_id)
    if user is None:
        raise ResourceNotFoundError("User not found")
    roles = await _load_roles_map(db, [user_id])
    return roles.get(user_id, [])


async def replace_user_roles(
    db: AsyncSession, *, operator: User, user_id: int, role_names: list[str]
) -> list[str]:
    """全量替换用户角色（PUT /users/{user_id}/roles，TASK-082）。

    语义：PUT 全量替换——不在 ``role_names`` 里的既有授权被撤销，缺失的补授
    （幂等，重复授权由 uq 约束兜底）。

    守卫：
    - 目标用户不存在 → 404（防 id 枚举与「给幽灵用户授权」的歧义）；
    - 角色名不存在 → 404（角色是种子配置数据，不是可创建资源）；
    - **禁止操作自己的角色**（403）：当前没有「至少保留一个 admin」的全局
      不变量可依赖，允许自我降权等于给了把唯一管理员锁在门外的一键按钮。

    Returns:
        替换后的角色名列表（按 Role.id 排序，与 GET 一致）。
    """
    if operator.id == user_id:
        raise ForbiddenError("Cannot modify your own roles")

    user = await get_user(db, user_id)
    if user is None:
        raise ResourceNotFoundError("User not found")

    # 先整体校验再动手：任何名字非法都不产生半套变更。
    roles: list[Role] = []
    for name in dict.fromkeys(role_names):  # 去重且保序
        role = await get_role_by_name(db, name)
        if role is None:
            raise ResourceNotFoundError(f"Role not found: {name}")
        roles.append(role)

    result = await db.execute(
        select(UserRole.role_id, Role.name)
        .join(Role, Role.id == UserRole.role_id)
        .where(UserRole.user_id == user_id)
    )
    current = {name: rid for rid, name in result.all()}

    for name, rid in current.items():
        if name not in {r.name for r in roles}:
            await revoke_role_from_user(db, user_id=user_id, role_id=rid)
    for role in roles:
        if role.id not in current.values():
            await assign_role_to_user(db, user_id=user_id, role_id=role.id)

    # 写路径的事务边界在 Service 层（项目规则 §4，与 team/comment 等服务一致）：
    # 不提交则 flush 的变更随会话关闭回滚，PUT 会「响应成功、实际未生效」。
    await db.commit()

    result = await _load_roles_map(db, [user_id])
    return result.get(user_id, [])


async def get_my_permission_names(db: AsyncSession, user: User) -> list[str]:
    """当前用户的有效权限名集合（GET /users/me/permissions，TASK-083）。

    CRUD 层已去重并按 name 排序，这里只做透传——语义与
    ``require_permission`` 的判定数据源完全一致（同一 ``get_user_permissions``），
    前端拿它做按钮级显隐不会与后端守卫产生两套真相。
    """
    return await get_user_permissions(db, user.id)
