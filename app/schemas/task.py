"""Task schemas (TASK-032).

`TaskCreate` / `TaskUpdate` 是入站契约；`TaskUpdate` 全字段可选，Service 层用
`model_dump(exclude_unset=True)` 只应用请求中显式出现的字段（PATCH 部分更新）。
`TaskRead` 与 `ProjectRead` 同惯例：只暴露安全字段。

TASK-032 决策（用户确认）：

- **`TaskCreate` 不收 `status`** —— 新任务一律 `TODO` 起步，状态流转只能走
  transition API（TASK-038），杜绝绕过状态机直接建出 DONE 任务
  （Decision 005：状态流转由状态机管，普通 PATCH 也不允许改 status）。
- `status` / `priority` 用 `TaskStatus` / `TaskPriority` StrEnum 校验，
  字面字符串与 DB CHECK 值集一一对应。
- `TaskUpdate` 同样不含 `status`（更新走 transition），也不含 `project_id`
  / `creator_id`（任务跨项目移动与冒名创建均不在契约内）。
"""

import enum
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.task import TaskPriority, TaskStatus


class TaskSortField(enum.StrEnum):
    """列表排序白名单（TASK-035）：仅允许这四列作为 sort 参数。

    priority 按业务权重排序（URGENT > HIGH > MEDIUM > LOW），非字母序，
    权重映射在 Service 层完成。
    """

    ID = "id"
    CREATED_AT = "created_at"
    DUE_AT = "due_at"
    PRIORITY = "priority"


#: 排序方向（TASK-035）；非法值由 FastAPI 422 拒绝。
TaskSortOrder = Literal["asc", "desc"]


class TaskCreate(BaseModel):
    project_id: int
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    priority: TaskPriority = TaskPriority.MEDIUM
    due_at: datetime | None = None


class TaskUpdate(BaseModel):
    # title 传 null 会被 422 拒绝；description 显式传 null 表示清空描述，
    # 未传则保持不变（exclude_unset）。
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    priority: TaskPriority | None = None
    due_at: datetime | None = None


class TaskRead(BaseModel):
    id: int
    project_id: int
    title: str
    description: str | None
    status: TaskStatus
    priority: TaskPriority
    creator_id: int
    due_at: datetime | None
    created_at: datetime
    updated_at: datetime
    #: 负责人列表（TASK-036 内嵌决策）——Service 层批量查询组装；
    # 新建任务恒空列表，不缺省为 None 以稳定前端渲染。
    assignees: list["TaskAssigneeRead"] = []

    model_config = ConfigDict(from_attributes=True)


class TaskAssigneeCreate(BaseModel):
    """POST /tasks/{task_id}/assignees 请求体：仅目标用户 id。

    合法性（用户存在且是任务所属团队成员）由 Service 层校验——
    不合法 404 同文案（TASK-036 决策），Schema 只做形状校验。
    """

    user_id: int


class TaskAssigneeRead(BaseModel):
    """任务负责人条目（TaskRead.assignees 内嵌项）。"""

    user_id: int
    username: str
    assigned_at: datetime


TaskRead.model_rebuild()
