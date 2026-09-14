"""Comment CRUD（TASK-041）.

写入只 ``flush`` —— 事务边界在 Service 层（项目规则 §4 / ARCHITECTURE.md）。

列表按 ``created_at`` 升序（讨论时间线，最早在前），带 ``skip`` / ``limit``
分页（与项目其它列表同惯例）。返回评论时 join ``users`` 取 ``username``
（评论展示需要作者名），避免 N+1。
"""

from sqlalchemy import asc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.comment import Comment
from app.models.user import User


async def create_comment(
    db: AsyncSession,
    *,
    task_id: int,
    user_id: int,
    content: str,
) -> Comment:
    comment = Comment(task_id=task_id, user_id=user_id, content=content)
    db.add(comment)
    await db.flush()
    await db.refresh(comment)
    return comment


async def get_comment(db: AsyncSession, comment_id: int) -> Comment | None:
    result = await db.execute(select(Comment).where(Comment.id == comment_id))
    return result.scalar_one_or_none()


async def list_comments_by_task(
    db: AsyncSession,
    task_id: int,
    *,
    skip: int = 0,
    limit: int = 100,
) -> list[tuple[Comment, str]]:
    """任务下的评论（时间升序）——返回 ``(Comment, username)`` 元组。"""
    stmt = (
        select(Comment, User.username)
        .join(User, User.id == Comment.user_id)
        .where(Comment.task_id == task_id)
        .order_by(asc(Comment.created_at), asc(Comment.id))
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(stmt)
    return [(row[0], row[1]) for row in result.all()]


async def delete_comment(db: AsyncSession, comment: Comment) -> None:
    await db.delete(comment)
    await db.flush()
