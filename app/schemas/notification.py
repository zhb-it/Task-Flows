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


class NotificationMarkAllRead(BaseModel):
    """``PATCH /notifications/read-all``（TASK-054）的出站契约。

    ``marked`` = 本次真正从已读翻转为已读的条数（已是已读的不计入），
    前端据此更新未读角标；重复调用幂等返回 0。
    """

    marked: int
