"""OperationLog schemas（TASK-039）.

``OperationLogRead`` 是日志查询响应的出站契约；payload 原样透传为 JSON
对象（§15 示例 ``{old_status, new_status}``），不做形状约束——不同 action
的 payload 字段随业务演进。
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class OperationLogRead(BaseModel):
    id: int
    user_id: int
    resource_type: str
    resource_id: int
    action: str
    payload: dict[str, Any] = {}
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
