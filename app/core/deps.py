"""可复用的 FastAPI 依赖（ARCHITECTURE.md：core 负责配置、安全、依赖、异常）。

认证依赖是 Router 与 Service 之间的桥：它只做「HTTP 凭证 → 已认证用户」的翻译，
把「取不到凭证 / 凭证不合法」统一表达为 401，真正的账号状态规则交给 Service。

后续 TASK-023 的权限依赖与各资源路由都应复用 `CurrentUser`，避免在每个
Router 里重复解析 Token。
"""

from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import UnauthorizedError
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.user import User
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
) -> User:
    """从 `Authorization: Bearer <token>` 解析并返回当前登录用户。

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

    return await load_current_user(db, user_id)


#: 路由签名中直接使用：`current_user: CurrentUser`
CurrentUser = Annotated[User, Depends(get_current_user)]
