"""Auth services — registration (TASK-015), login (TASK-016), refresh (TASK-018)
and logout (TASK-019).

Business rules enforced here (not in the router):

- username / email must be unique → ``ConflictError`` (HTTP 409)
- the plain-text password is hashed exactly once, here, via
  ``app.core.security.hash_password``; only the hash reaches the CRUD layer
- login verifies the password before the account state, and rejects disabled
  accounts → ``UnauthorizedError`` (401) / ``ForbiddenError`` (403)
- login issues the双 Token pair and persists only the Refresh Token's ``jti``
  （开发文档 §55.1）
- refresh validates the token, then the **database** jti（§19「检查数据库
  JTI」）, then rotates it: 旧 jti 立即置 revoked，新 Token 对重新落库
- logout revokes the caller's own Refresh Token（§19「登出：撤销 Refresh
  Token」）with idempotent semantics: 任何「Token 本来就不可用」的情形都静默
  成功，仅出示他人 Token 时显式 403
- the Service owns the transaction boundary (项目规则 §4 / ARCHITECTURE.md)：
  签发 Token 与登记 jti 必须同生共死
"""

from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ForbiddenError, UnauthorizedError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    hash_password,
    verify_password,
)
from app.crud.refresh_token import (
    create_refresh_token as store_refresh_token,
    get_refresh_token_by_jti,
    revoke_refresh_token,
)
from app.crud.user import create_user, get_user_by_email, get_user_by_username
from app.models.user import User
from app.schemas.auth import LoginRequest
from app.schemas.user import UserCreate
from app.services.user import load_current_user


async def register_user(db: AsyncSession, payload: UserCreate) -> User:
    """Register a new active user and return the persisted row.

    Raises:
        ConflictError: if the username or the email is already taken.
    """
    if await get_user_by_username(db, payload.username) is not None:
        raise ConflictError("Username is already registered")
    if await get_user_by_email(db, payload.email) is not None:
        raise ConflictError("Email is already registered")

    # ⚠ The try must wrap `create_user`, not just `commit`: the unique violation
    # is raised by the `flush()` inside `create_user` (session-bound INSERT), so a
    # guard starting at `commit` is unreachable and the losing side of a race gets
    # a 500 instead of a 409. Found by TASK-062's real-concurrency registration
    # test — see DECISIONS 044.
    try:
        user = await create_user(
            db,
            username=payload.username,
            email=payload.email,
            password_hash=hash_password(payload.password),
        )
        await db.commit()
    except IntegrityError as exc:
        # Two concurrent registrations can both pass the checks above; the DB
        # unique constraints are the real guard, so translate the violation.
        await db.rollback()
        raise ConflictError("Username or email is already registered") from exc

    await db.refresh(user)
    return user


async def authenticate_user(db: AsyncSession, payload: LoginRequest) -> User:
    """校验登录凭证，返回可登录的用户。

    校验顺序（安全考量）：先验证密码，再检查账号是否启用。这样「用户名不存在」
    与「密码错误」返回同一条 401 文案，避免用户名枚举；只有在密码正确的前提下
    才会得知账号被禁用。

    Raises:
        UnauthorizedError: 用户不存在或密码错误（401，文案不区分二者）。
        ForbiddenError: 密码正确但账号已被禁用（403）。
    """
    user = await get_user_by_username(db, payload.username)
    if user is None or not verify_password(payload.password, user.password_hash):
        raise UnauthorizedError("Invalid username or password")
    if not user.is_active:
        raise ForbiddenError("User account is disabled")
    return user


def _build_pair(user_id: int) -> tuple[str, str, str, datetime]:
    """签发一对新 Token，返回 ``(access, refresh, refresh_jti, refresh_expires_at)``。"""
    access_token = create_access_token(user_id)
    refresh_token, jti, expires_at = create_refresh_token(user_id)
    return access_token, refresh_token, jti, expires_at


async def issue_token_pair(db: AsyncSession, user: User) -> tuple[str, str]:
    """为已认证用户签发 ``(access_token, refresh_token)``。

    Refresh Token 只把它的 ``jti`` / ``expires_at`` 落库，Token 本体不持久化
    （开发文档 §55.1「保存 Refresh Token JTI」）。签发与登记在同一个事务里提交，
    避免出现「客户端拿到 Refresh Token 但服务端查不到 jti」的中间态。
    """
    access_token, refresh_token, jti, expires_at = _build_pair(user.id)
    await store_refresh_token(db, user_id=user.id, jti=jti, expires_at=expires_at)
    await db.commit()
    return access_token, refresh_token


async def rotate_tokens(db: AsyncSession, refresh_token: str) -> tuple[str, str]:
    """用 Refresh Token 换取全新的 Token 对（轮换策略）。

    校验顺序（每一步失败即拒绝，文案统一，不向客户端透露失败细节）：

    1. 签名 / 过期 / 类别（`core.security`）→ 401
    2. jti 是否登记在库（开发文档 §19「检查数据库 JTI」）→ 401
    3. 该 jti 是否已被撤销 → 401。轮换后旧 Token 再次出现，意味着它可能在
       客户端之外被复制使用，故一律拒绝。
    4. 数据库中的 ``expires_at`` 是否已过期 → 401
    5. 账号是否存在 / 是否启用 → 401 / 403，与 `/users/me`（TASK-017）保持一致
    6. 轮换：旧 jti 置 ``revoked=true``，签发并登记新的 Refresh Token，
       全部动作在同一事务内提交。

    Raises:
        UnauthorizedError: Token 不可用（签名/过期/类别/jti 未知/已撤销/账号不存在）。
        ForbiddenError: Token 有效但账号已被禁用。
    """
    payload = decode_refresh_token(refresh_token)

    try:
        user_id = int(payload.get("sub"))
    except (TypeError, ValueError) as exc:
        raise UnauthorizedError("Invalid or expired token") from exc

    jti = payload.get("jti")
    if not isinstance(jti, str) or not jti:
        raise UnauthorizedError("Invalid or expired token")

    stored = await get_refresh_token_by_jti(db, jti)
    if stored is None or stored.revoked or stored.user_id != user_id:
        raise UnauthorizedError("Invalid or expired token")
    if stored.expires_at <= datetime.now(timezone.utc):
        raise UnauthorizedError("Invalid or expired token")

    user = await load_current_user(db, user_id)

    await revoke_refresh_token(db, jti)
    access_token, new_refresh_token, new_jti, new_expires_at = _build_pair(user.id)
    await store_refresh_token(
        db, user_id=user.id, jti=new_jti, expires_at=new_expires_at
    )
    await db.commit()
    return access_token, new_refresh_token


async def logout_user(db: AsyncSession, user: User, refresh_token: str) -> None:
    """撤销当前用户的 Refresh Token（TASK-019，开发文档 §19「登出：撤销
    Refresh Token」）。

    幂等语义（TASK-019 决策）：登出的目标是「让这个 Refresh Token 不可用」，
    因此签名/过期/类别不合法、jti 未登记、jti 已撤销等「Token 本来就不可用」
    的情形一律静默返回（不报错、不产生副作用），客户端可以无条件清理本地
    凭证。

    唯一的显式拒绝：出示的 Refresh Token 有效但属于**其他用户** —— 归属校验
    防止越权撤销他人凭证（项目规则 §9 IDOR），返回 403 且不产生任何撤销动作。

    Raises:
        ForbiddenError: Refresh Token 有效但归属其他用户。
    """
    try:
        payload = decode_refresh_token(refresh_token)
    except UnauthorizedError:
        return  # 不可用的 Token：幂等成功，无需操作

    jti = payload.get("jti")
    if not isinstance(jti, str) or not jti:
        return

    stored = await get_refresh_token_by_jti(db, jti)
    if stored is None or stored.revoked:
        return
    if stored.user_id != user.id:
        raise ForbiddenError("Refresh token does not belong to current user")

    await revoke_refresh_token(db, jti)
    await db.commit()
