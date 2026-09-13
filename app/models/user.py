"""User ORM model.

Field set is taken verbatim from the project spec (docs/PROJECT_SPEC.md and
the development document §5.1):

    users:
        id
        username        UNIQUE
        email           UNIQUE
        password_hash   (never stored in plaintext)
        is_active
        created_at
        updated_at

The `creator_id BIGINT NOT NULL REFERENCES users(id)` constraint used
elsewhere confirms the primary key is a BIGINT. Password hashing helpers are
introduced later (TASK-014); this model only persists the resulting hash.
"""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    username: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username!r}>"
