"""Notification schemas (TASK-053).

``NotificationRead`` 是通知查询 / 标记已读的出站契约；字段对齐 §18 七字段
（id / user_id / type / title / content / is_read / created_at）。
通知是系统派发的（无创建端点），所以只有读模型，没有入站写模型。
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class NotificationRead(BaseModel):
    id: int
    user_id: int
    type: str
    title: str
    content: str | None
    is_read: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
