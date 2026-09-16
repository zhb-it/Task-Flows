"""User schemas.

`UserRead` deliberately omits `password_hash` (project rule §5: API responses
must never expose the password hash). `UserCreate` carries the plain `password`
field as the inbound contract for registration (TASK-015); the CRUD layer only
ever persists the already-hashed value, so this schema is never persisted as-is.

TASK-082/083 adds the RBAC admin contracts: roles are exchanged as **name**
strings (the seed guarantees `admin` / `member` exist; names are stable and
human-readable, ids are not part of any contract).
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


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


class UserWithRolesRead(UserRead):
    """`UserRead` + 该用户的角色名列表（GET /users 列表用）。"""

    roles: list[str] = []


class UserRolesRead(BaseModel):
    """GET/PUT `/users/{user_id}/roles` 的契约体。"""

    user_id: int
    roles: list[str]


class RoleNamesUpdate(BaseModel):
    """PUT `/users/{user_id}/roles` 的请求体：全量替换语义（PUT，非 patch）。"""

    roles: list[str] = Field(max_length=50)


class MePermissionsRead(BaseModel):
    """GET `/users/me/permissions`：当前用户的有效权限名集合（去重、有序）。"""

    permissions: list[str]
