"""Service 层授权守卫（TASK-024，开发文档 §49 / §50）。

TASK-023 的 `require_permission` 依赖守卫 HTTP 端点入口；当授权判定发生在
业务层内部（Service 之间调用、后台任务、资源归属校验之前）时，由本模块的
`ensure_permission` 承担同一规则——语义（单权限 / AND）与报错文案和依赖
完全一致，客户端看到的 403 无法区分来源。

资源级归属校验（§49 IDOR：User → Team → Project → Task 链）需要 team /
project / task 表，Phase 5 起随 TASK-026/029/031 实装。其契约在本 TASK 定死：
**资源存在但不在调用者归属链上 → `ResourceNotFoundError`(404)**，与「不存在」
不可区分以防 id 枚举；功能级权限缺失（不针对具体资源）仍走 403。

账号状态（is_active）不在此校验——那是认证链 `load_current_user` 的职责，
与 TASK-017/023 的既有分工一致。
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError
from app.crud.permission import get_user_permissions
from app.models.user import User


def validate_permission_name(name: str) -> None:
    """权限名必须是 `resource:action` 格式（TASK-022 决策：单列严格格式）。

    依赖工厂在路由注册时、Service 守卫在调用时各自调用本函数，尽早暴露
    拼写错误而非把坏权限名静默放行为「永不可满足的授权」。
    """
    parts = name.split(":")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise ValueError(
            f"Invalid permission name {name!r}: expected 'resource:action' format"
        )


async def ensure_permission(
    db: AsyncSession, user: User, *permissions: str
) -> None:
    """要求 `user` 持有全部列出的权限，否则抛 `ForbiddenError`(403)。

    语义（TASK-023 决策，本函数保持一致）：单权限或 AND——全部持有才通过；
    OR 语义留给后续 TASK 在需要时扩展。报错文案与依赖相同：
    `Permission denied: <缺失项>`，只列缺失、不误报已持有。
    """
    if not permissions:
        raise ValueError("ensure_permission() needs at least one permission name")
    for name in permissions:
        validate_permission_name(name)

    effective = set(await get_user_permissions(db, user.id))
    missing = sorted(set(permissions) - effective)
    if missing:
        raise ForbiddenError(f"Permission denied: {', '.join(missing)}")
