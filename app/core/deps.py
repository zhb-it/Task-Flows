"""可复用的 FastAPI 依赖（ARCHITECTURE.md：core 负责配置、安全、依赖、异常）。

认证依赖是 Router 与 Service 之间的桥：它只做「HTTP 凭证 → 已认证用户」的翻译，
把「取不到凭证 / 凭证不合法」统一表达为 401，真正的账号状态规则交给 Service。

**租户上下文注入（TASK-095）**：``get_current_user`` 加载用户成功后，把
``user.tenant_id`` 写入请求级 ContextVar（``app.core.tenant_context``）并翻转
当前事务的 RLS GUC，请求结束在 ``finally`` 内还原。此后查询作用域
（``do_orm_execute`` 自动过滤）、写入注入（``before_flush``）与 RLS 兜底
（``after_begin`` GUC）三道防线即对整个请求生效——依赖链上的其他依赖
（如 ``require_permission``）复用同一份 FastAPI 缓存结果，注入恰好一次。

权限依赖（TASK-023）`require_permission` 在认证之后判定授权：沿
User → UserRole → Role → RolePermission → Permission 模型链解析用户的有效
权限集合，不满足即 403。它只回答「这个用户能不能进这个端点」；资源归属等
更细的判定属于 Service 资源级权限（TASK-024，`ensure_permission` +
`ResourceNotFoundError`）。
"""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.security import decode_access_token
from app.core.tenant_context import (
    enforce_tenant_guc,
    get_current_tenant_id,
    reset_current_tenant_id,
    set_current_tenant_id,
)
from app.crud.permission import get_user_permissions
from app.db.session import get_db
from app.models.user import User
from app.services.authorization import validate_permission_name
from app.services.user import load_current_user

# `auto_error=False` 是刻意的：FastAPI 的 HTTPBearer 默认在缺少 Authorization 头时
# 抛 403，与本项目「认证失败 → 401 + WWW-Authenticate: Bearer」的规范冲突
# （见 UnauthorizedError）。关闭默认行为后，缺头/非 Bearer 由下方统一转成 401。
bearer_scheme = HTTPBearer(
    auto_error=False,
    scheme_name="AccessToken",
    description="以 /api/v1/auth/login 取得的 access_token 作为 `Bearer <token>` 传入。",
)


async def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(bearer_scheme)
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AsyncIterator[User]:
    """从 `Authorization: Bearer <token>` 解析并返回当前登录用户。

    本依赖是 yield 形式：加载成功后先完成租户上下文注入（ContextVar +
    事务级 RLS GUC，见 TASK-095），再 ``yield`` 用户；请求结束时 ``finally``
    还原 ContextVar。注入恰好发生在「认证查询之后、业务查询之前」——
    认证自身的查询处于无租户事务（bypass GUC），业务查询全程被作用域与
    RLS 约束。

    Raises:
        UnauthorizedError: 凭证缺失、方案不是 Bearer、签名/过期/类别不合法，
            或 Token 的 subject 无法解析为有效用户 id。
        ForbiddenError: 凭证有效但账号已被禁用（由 Service 抛出）。
    """
    if credentials is None or not credentials.credentials:
        raise UnauthorizedError("Not authenticated")

    payload = decode_access_token(credentials.credentials)

    try:
        user_id = int(payload.get("sub"))
    except (TypeError, ValueError) as exc:
        # 签名有效但 subject 非法的 Token（例如换密钥前的旧 Token）不应导致 500。
        raise UnauthorizedError("Invalid or expired token") from exc

    user = await load_current_user(db, user_id)

    # —— TASK-095：请求级租户上下文（认证依赖注入 / finally 还原） ——
    prev_tenant = get_current_tenant_id()
    token = set_current_tenant_id(user.tenant_id)
    # 认证查询所在事务已带 bypass GUC；这里把同一事务翻转为「tenant 过滤 +
    # bypass 关」，保证端点首条查询即受 RLS 约束（而非等下一个事务）。
    await enforce_tenant_guc(db)
    try:
        yield user
    finally:
        try:
            reset_current_tenant_id(token)
        except LookupError:
            # FastAPI 的 yield 依赖退出码可能运行在与进入时不同的 task 中，
            # 跨 context 还原 Token 会抛 LookupError；退化为直接置回进入前的
            # 值（每个请求持有独立 context 副本，不会污染兄弟请求）。
            set_current_tenant_id(prev_tenant)


#: 路由签名中直接使用：`current_user: CurrentUser`
CurrentUser = Annotated[User, Depends(get_current_user)]


def require_permission(*permissions: str):
    """权限依赖工厂：返回一个「要求当前用户持有全部列出权限」的依赖。

    语义（TASK-023 决策）：单权限或 AND——`require_permission("task:read")`
    要求持有 `task:read`；`require_permission("a", "b")` 要求同时持有两者。
    OR 语义留给后续 TASK 在需要时扩展。

    用法::

        @router.get("/tasks", dependencies=[Depends(require_permission("task:read"))])
        async def list_tasks(...): ...

    或需要用户对象时::

        @router.get("/tasks")
        async def list_tasks(user: Annotated[User, Depends(require_permission("task:read"))]): ...

    认证失败（401/账号禁用 403）由链条前端的 `get_current_user` 决定；
    本依赖只在认证通过后追加授权判定，缺权限 → `ForbiddenError`(403)，
    文案列出缺失的权限名便于客户端与服务端定位。业务层内部的等价判定
    （Service 互调、后台任务）用 `app.services.authorization.ensure_permission`，
    两者语义与文案一致（TASK-024）。
    """
    if not permissions:
        raise ValueError("require_permission() needs at least one permission name")
    for name in permissions:
        validate_permission_name(name)

    required = frozenset(permissions)

    async def permission_checker(
        user: Annotated[User, Depends(get_current_user)],
        db: Annotated[AsyncSession, Depends(get_db)],
    ) -> User:
        effective = set(await get_user_permissions(db, user.id))
        missing = sorted(required - effective)
        if missing:
            raise ForbiddenError(f"Permission denied: {', '.join(missing)}")
        return user

    return permission_checker
