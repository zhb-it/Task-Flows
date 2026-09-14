"""Attachment CRUD（TASK-042）.

写入只 ``flush`` —— 事务边界在 Service 层（项目规则 §4 / ARCHITECTURE.md）。

列表按 ``created_at`` 升序（先传的在前），join ``users`` 取 ``uploader`` 名
避免 N+1。
"""

from sqlalchemy import asc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attachment import Attachment
from app.models.user import User


async def create_attachment(
    db: AsyncSession,
    *,
    task_id: int,
    uploader_id: int,
    filename: str,
    storage_path: str,
    content_type: str,
    size: int,
) -> Attachment:
    attachment = Attachment(
        task_id=task_id,
        uploader_id=uploader_id,
        filename=filename,
        storage_path=storage_path,
        content_type=content_type,
        size=size,
    )
    db.add(attachment)
    await db.flush()
    await db.refresh(attachment)
    return attachment


async def get_attachment(
    db: AsyncSession, attachment_id: int
) -> Attachment | None:
    result = await db.execute(
        select(Attachment).where(Attachment.id == attachment_id)
    )
    return result.scalar_one_or_none()


async def list_attachments_by_task(
    db: AsyncSession,
    task_id: int,
    *,
    skip: int = 0,
    limit: int = 100,
) -> list[tuple[Attachment, str]]:
    """任务下的附件（时间升序）——返回 ``(Attachment, uploader)`` 元组。"""
    stmt = (
        select(Attachment, User.username)
        .join(User, User.id == Attachment.uploader_id)
        .where(Attachment.task_id == task_id)
        .order_by(asc(Attachment.created_at), asc(Attachment.id))
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(stmt)
    return [(row[0], row[1]) for row in result.all()]


async def delete_attachment(db: AsyncSession, attachment: Attachment) -> None:
    await db.delete(attachment)
    await db.flush()
