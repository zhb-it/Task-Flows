"""Task CRUD operations (TASK-032).

Write helpers persist rows via `flush` only — the transaction boundary stays
with the Service layer (项目规则 §4 / ARCHITECTURE.md).

TASK-032 决策（用户确认）：本层只提供基础 CRUD —— `get_task` /
`list_tasks_by_project`（简单 id 升序）/ create / update / delete；过滤、
分页、排序是 TASK-035 专项，不在本层超前实现。

`create_task` 不收 `status`：新任务一律依赖模型默认值 TODO 起步。
`update_task` 只持久化 Service 层对属性的就地修改（含 status 的修改
由 TASK-037 状态机 / TASK-038 transition API 在 Service 层执行后落库，
本层不做 status 值校验 —— 校验在 Schema 与状态机）。
"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import Task


async def create_task(
    db: AsyncSession,
    *,
    project_id: int,
    title: str,
    description: str | None,
    priority: str,
    creator_id: int,
    due_at: datetime | None = None,
) -> Task:
    task = Task(
        project_id=project_id,
        title=title,
        description=description,
        priority=priority,
        creator_id=creator_id,
        due_at=due_at,
    )
    db.add(task)
    await db.flush()
    await db.refresh(task)
    return task


async def get_task(db: AsyncSession, task_id: int) -> Task | None:
    result = await db.execute(select(Task).where(Task.id == task_id))
    return result.scalar_one_or_none()


async def list_tasks_by_project(
    db: AsyncSession, project_id: int
) -> list[Task]:
    """All tasks of a project, ordered by id (TASK-035 adds filtering)."""
    result = await db.execute(
        select(Task).where(Task.project_id == project_id).order_by(Task.id)
    )
    return list(result.scalars().all())


async def update_task(db: AsyncSession, task: Task) -> Task:
    """Persist in-place attribute mutations made by the Service layer."""
    await db.flush()
    await db.refresh(task)
    return task


async def delete_task(db: AsyncSession, task: Task) -> None:
    """Delete the task. Assignee rows (TASK-036) will cascade with it."""
    await db.delete(task)
    await db.flush()
