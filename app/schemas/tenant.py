"""Tenant Pydantic 契约（TASK-093）.

租户是平台管理面对象：创建/读取/更新/状态变更全部走
``require_permission("tenant:manage")``（平台管理员，DECISIONS 065）。

口径：
- ``slug`` 仅在创建时出现，且**不可变更**（对外标识，未来是子域/域名基础，
  改名等于换门牌；改名需求出现时走显式新任务）。
- 配额字段可选；``None`` = 未设限（DB 列可空，CHECK 保证 > 0 / >= 0）。
- 状态变更走独立端点（PATCH /tenants/{id}/status），白名单语义在 Service；
  普通更新端点不接受 status，避免「部分更新」与「状态机」两套语义打架。
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.tenant import TENANT_SLUG_PATTERN


class TenantCreate(BaseModel):
    """POST /tenants 请求体。"""

    name: str = Field(min_length=1, max_length=150)
    slug: str = Field(
        min_length=2,
        max_length=63,
        pattern=TENANT_SLUG_PATTERN,
        description="全局唯一标识（小写字母/数字与连字符）",
    )
    member_limit: int | None = Field(default=None, gt=0)
    storage_limit_bytes: int | None = Field(default=None, ge=0)


class TenantUpdate(BaseModel):
    """PATCH /tenants/{id} 请求体（部分更新，exclude_unset）。"""

    name: str | None = Field(default=None, min_length=1, max_length=150)
    member_limit: int | None = Field(default=None, gt=0)
    storage_limit_bytes: int | None = Field(default=None, ge=0)


class TenantStatusUpdate(BaseModel):
    """PATCH /tenants/{id}/status 请求体（状态机白名单在 Service 执行）。"""

    status: Literal["active", "suspended", "deleted"]


class TenantRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    status: str
    member_limit: int | None
    storage_limit_bytes: int | None
    created_at: datetime
    updated_at: datetime


class TenantListRead(BaseModel):
    """GET /tenants 分页信封：显式 COUNT(*) + total（企业化已拍板口径）。"""

    items: list[TenantRead]
    total: int
