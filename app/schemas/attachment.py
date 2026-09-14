"""Attachment schemas（TASK-042）.

``AttachmentRead`` 是出站契约（内嵌 ``uploader`` 供前端渲染上传者）。

**入站不用 Pydantic 模型**：上传走 ``multipart/form-data``，字段来自
``UploadFile``，且大小校验必须在**流式写入过程中**完成（不能先读进内存再
校验——那样超大文件会先撑爆内存）。因此入站约束在 Service 层按块累计实现，
MIME 与文件名校验也在那里（见 ``app/services/attachment.py``）。
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AttachmentRead(BaseModel):
    id: int
    task_id: int
    uploader_id: int
    uploader: str
    filename: str
    content_type: str
    size: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
