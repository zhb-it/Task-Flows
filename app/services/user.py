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

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.crud.user import get_user
from app.models.user import User


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
