"""Task CRUD operations (TASK-032, list query extended in TASK-035).

Write helpers persist rows via `flush` only — the transaction boundary stays
with the Service layer (项目规则 §4 / ARCHITECTURE.md).

TASK-032 决策（用户确认）：本层只提供基础 CRUD —— `get_task` /
`list_tasks_by_project` / create / update / delete；状态值校验在 Schema
与状态机（TASK-037/038），本层不做。

TASK-035（用户确认决策）：`list_tasks_by_project` 演进为多条件查询——
`status` / `priority` 精确过滤 + `keyword` 标题 ILIKE（通配符转义，按
字面匹配）+ skip/limit 分页（与 teams/projects 同惯例）+ 排序子句由
Service 层传入（白名单映射与 priority 业务权重在 Service，本层保持
纯数据操作，不解释业务含义）。
"""

from datetime import datetime

from sqlalchemy import asc, select
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
    db: AsyncSession,
    project_id: int,
    *,
    status: str | None = None,
    priority: str | None = None,
    keyword: str | None = None,
    skip: int = 0,
    limit: int = 100,
    order_by=None,
) -> list[Task]:
    """Tasks of a project with optional filtering / paging / ordering.

    `order_by` 是完整的排序子句（Service 层传入 `Task.col.asc()/desc()`，
    默认 id 升序）；keyword 已由 Service 层做通配符转义。
    """
    stmt = select(Task).where(Task.project_id == project_id)
    if status is not None:
        stmt = stmt.where(Task.status == status)
    if priority is not None:
        stmt = stmt.where(Task.priority == priority)
    if keyword:
        stmt = stmt.where(Task.title.ilike(keyword))
    stmt = stmt.order_by(order_by if order_by is not None else asc(Task.id))
    result = await db.execute(stmt.offset(skip).limit(limit))
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
