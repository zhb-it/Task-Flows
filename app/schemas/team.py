"""Team schemas (TASK-027 / TASK-028).

`TeamCreate` / `TeamUpdate` 是入站契约；`TeamUpdate` 全字段可选，Service 层用
`model_dump(exclude_unset=True)` 只应用请求中显式出现的字段（PATCH 部分更新）。
`TeamRead` 与 `UserRead` 同惯例：只暴露安全字段，永不包含任何敏感信息。

TASK-028 成员管理：邀请请求体携带 `user_id` + 可选 `role`（仅 admin/member，
默认 member——**禁止直接邀请为 OWNER**，owner 只能经创建/转让获得，TASK-028
决策 2）。`TeamMemberRead` 附带 `username` 与可读 `role` 名。
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class TeamCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    description: str | None = Field(default=None, max_length=255)


class TeamUpdate(BaseModel):
    # name 传 null 会被 422 拒绝（可空但受长度约束的仅 description）；
    # description 显式传 null 表示清空描述，未传则保持不变（exclude_unset）。
    name: str | None = Field(default=None, min_length=1, max_length=150)
    description: str | None = Field(default=None, max_length=255)


class TeamMemberInvite(BaseModel):
    user_id: int
    # 仅 admin / member：Literal 在 422 层就挡掉 "owner"——owner 不可被邀请。
    role: Literal["admin", "member"] = "member"


class TeamMemberRead(BaseModel):
    id: int
    team_id: int
    user_id: int
    username: str
    role: str  # "owner" | "admin" | "member"（TeamRole 名小写）
    joined_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TeamRead(BaseModel):
    id: int
    name: str
    description: str | None
    owner_id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
