"""TaskAssignee CRUD operations (TASK-036).

Write helpers persist rows via `flush` only — the transaction boundary stays
with the Service layer (项目规则 §4 / ARCHITECTURE.md).

读取侧提供两种形态：

- ``list_assignees``：单任务的负责人明细（join users 取 username）；
- ``list_assignees_for_tasks``：多任务批量（IN 查询），供 Service 组装
  TaskRead.assignees 内嵌字段——列表场景一次查询避免 N+1。
"""


from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import Task
from app.models.task_assignee import TaskAssignee
from app.models.user import User


async def add_task_assignee(
    db: AsyncSession,
    *,
    task_id: int,
    user_id: int,
    assigned_by_id: int,
) -> TaskAssignee:
    """Insert an assignee row. Duplicate (task_id, user_id) hits the
    composite PK — callers (Service) check existence first for a clean 409."""
    row = TaskAssignee(
        task_id=task_id, user_id=user_id, assigned_by_id=assigned_by_id
    )
    db.add(row)
    await db.flush()
    await db.refresh(row)
    return row


async def remove_task_assignee(
    db: AsyncSession, *, task_id: int, user_id: int
) -> bool:
    """Delete the assignee row if present. Returns whether a row was removed."""
    result = await db.execute(
        select(TaskAssignee).where(
            TaskAssignee.task_id == task_id, TaskAssignee.user_id == user_id
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        return False
    await db.delete(row)
    await db.flush()
    return True


async def is_task_assignee(
    db: AsyncSession, *, task_id: int, user_id: int
) -> bool:
    result = await db.execute(
        select(
            exists().where(
                TaskAssignee.task_id == task_id,
                TaskAssignee.user_id == user_id,
            )
        )
    )
    return bool(result.scalar())


async def list_assignees(
    db: AsyncSession, task_id: int
) -> list[tuple[TaskAssignee, str]]:
    """Assignees of one task as (row, username) pairs, oldest assignment first."""
    result = await db.execute(
        select(TaskAssignee, User.username)
        .join(User, User.id == TaskAssignee.user_id)
        .where(TaskAssignee.task_id == task_id)
        .order_by(TaskAssignee.assigned_at, TaskAssignee.user_id)
    )
    return [(row, username) for row, username in result.all()]


async def list_assignees_for_tasks(
    db: AsyncSession, task_ids: list[int]
) -> dict[int, list[tuple[TaskAssignee, str]]]:
    """Batched assignee lookup grouped by task_id (list rendering, no N+1)."""
    if not task_ids:
        return {}
    result = await db.execute(
        select(TaskAssignee, User.username)
        .join(User, User.id == TaskAssignee.user_id)
        .where(TaskAssignee.task_id.in_(task_ids))
        .order_by(TaskAssignee.assigned_at, TaskAssignee.user_id)
    )
    grouped: dict[int, list[tuple[TaskAssignee, str]]] = {}
    for row, username in result.all():
        grouped.setdefault(row.task_id, []).append((row, username))
    return grouped


async def filter_tasks_by_assignee(
    db: AsyncSession, user_id: int, *, skip: int = 0, limit: int = 100
) -> list[Task]:
    """Tasks the user is assigned to (「我的任务」数据原语，跨项目）。"""
    result = await db.execute(
        select(Task)
        .where(
            exists().where(
                TaskAssignee.task_id == Task.id,
                TaskAssignee.user_id == user_id,
            )
        )
        .order_by(Task.id)
        .offset(skip)
        .limit(limit)
    )
    return list(result.scalars().all())
