"""Refresh token CRUD operations.

Token 的签名/过期/类别校验属于 `app/core/security.py`；本层只负责
`refresh_tokens` 表的读写。撤销与轮换都按 `jti` 定位，事务边界由 Service 持有
（与 `crud/user.py` 的分工一致）。
"""

from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.refresh_token import RefreshToken


async def create_refresh_token(
    db: AsyncSession, *, user_id: int, jti: str, expires_at: datetime
) -> RefreshToken:
    """登记一个已签发的 Refresh Token 的 jti（Token 本体不入库）。"""
    token = RefreshToken(user_id=user_id, jti=jti, expires_at=expires_at)
    db.add(token)
    await db.flush()
    await db.refresh(token)
    return token


async def get_refresh_token_by_jti(db: AsyncSession, jti: str) -> RefreshToken | None:
    result = await db.execute(select(RefreshToken).where(RefreshToken.jti == jti))
    return result.scalar_one_or_none()


async def revoke_refresh_token(db: AsyncSession, jti: str) -> None:
    """把指定 jti 标记为已撤销。

    幂等：对同一个 jti 重复调用不会改变结果；不 commit，交由 Service 决定事务。
    """
    await db.execute(
        update(RefreshToken).where(RefreshToken.jti == jti).values(revoked=True)
    )
