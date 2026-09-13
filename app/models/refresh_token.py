"""RefreshToken ORM model (TASK-018).

字段集取自开发文档 §19「JWT 双 Token」：

    refresh_tokens:
        id
        user_id
        jti
        expires_at
        revoked
        created_at

Refresh Token 本身**不落库**，落在库里的只有它的 `jti`（§55.1「保存 Refresh
Token JTI」）。这样即使数据库泄露也无法直接还原出可用 Token，而服务端依然能凭
`jti` 回答「这个 Refresh Token 是否已撤销」（§19「检查数据库 JTI」）。

`user_id` 上的 `ON DELETE CASCADE` 保证删除用户不会留下孤儿 Token 记录。
"""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    #: JWT ID —— 唯一标识一个 Refresh Token；撤销（TASK-019）与轮换均按此列定位。
    jti: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    revoked: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        return (
            f"<RefreshToken id={self.id} user_id={self.user_id} "
            f"revoked={self.revoked}>"
        )
