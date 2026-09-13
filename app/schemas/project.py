"""Project schemas (TASK-029).

`ProjectCreate` / `ProjectUpdate` 是入站契约；`ProjectUpdate` 全字段可选，
Service 层用 `model_dump(exclude_unset=True)` 只应用请求中显式出现的字段
（PATCH 部分更新）。`ProjectRead` 与 `TeamRead` 同惯例：只暴露安全字段。

注意 `ProjectCreate` 不收 `owner_id` —— 创建者恒为当前调用者（Service 层
从认证链取），不开放客户端指定，杜绝冒名创建。
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ProjectCreate(BaseModel):
    team_id: int
    name: str = Field(min_length=1, max_length=150)
    description: str | None = Field(default=None, max_length=255)


class ProjectUpdate(BaseModel):
    # name 传 null 会被 422 拒绝；description 显式传 null 表示清空描述，
    # 未传则保持不变（exclude_unset）。
    name: str | None = Field(default=None, min_length=1, max_length=150)
    description: str | None = Field(default=None, max_length=255)


class ProjectRead(BaseModel):
    id: int
    name: str
    description: str | None
    team_id: int
    owner_id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
