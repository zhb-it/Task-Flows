"""User schemas.

`UserRead` deliberately omits `password_hash` (project rule §5: API responses
must never expose the password hash). `UserCreate` carries the plain `password`
field as the inbound contract for registration (TASK-015); the CRUD layer only
ever persists the already-hashed value, so this schema is never persisted as-is.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class UserBase(BaseModel):
    username: str
    email: str


class UserCreate(UserBase):
    password: str


class UserRead(UserBase):
    id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
