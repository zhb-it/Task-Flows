"""Comment schemas（TASK-041）.

``CommentCreate`` 是入站契约（仅 content；task_id 在路径，user_id 取调用者）；
``CommentRead`` 是出站契约（内嵌 ``username`` 供前端渲染作者名）。
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CommentCreate(BaseModel):
    content: str = Field(min_length=1, max_length=2000)


class CommentRead(BaseModel):
    id: int
    task_id: int
    user_id: int
    username: str
    content: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
