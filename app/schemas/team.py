"""Team schemas (TASK-027).

`TeamCreate` / `TeamUpdate` 是入站契约；`TeamUpdate` 全字段可选，Service 层用
`model_dump(exclude_unset=True)` 只应用请求中显式出现的字段（PATCH 部分更新）。
`TeamRead` 与 `UserRead` 同惯例：只暴露安全字段，永不包含任何敏感信息。
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TeamCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    description: str | None = Field(default=None, max_length=255)


class TeamUpdate(BaseModel):
    # name 传 null 会被 422 拒绝（可空但受长度约束的仅 description）；
    # description 显式传 null 表示清空描述，未传则保持不变（exclude_unset）。
    name: str | None = Field(default=None, min_length=1, max_length=150)
    description: str | None = Field(default=None, max_length=255)


class TeamRead(BaseModel):
    id: int
    name: str
    description: str | None
    owner_id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
