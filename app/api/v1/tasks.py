"""Task endpoints — 任务 CRUD（TASK-034）.

Router 只做 HTTP ⇄ Service 的翻译（项目规则 §4）。授权分两层（TASK-033
决策，docs/API_CONTRACT.md Task 注已登记）：

- 功能级：`require_permission("task:create|read|update|delete")` 依赖在
  进入业务前判定，缺失 → 403（TASK-023 契约）。
- 资源级：Service 层判定归属链（任务 → 项目 → 团队 → `team_members`）。
  不在链上 → 404（IDOR 防枚举）；已在链上但角色不足（删除需团队
  OWNER/ADMIN）→ 403 明示。

TASK-032 决策：创建请求体不含 `status`——新任务一律 TODO 起步。

TASK-035 列表查询（用户确认决策）：`GET /tasks?project_id={id}` 演进为
多条件查询——`status` / `priority` 精确过滤、`keyword` 标题模糊搜索、
`skip`/`limit` 分页（与 teams/projects 同惯例，响应仍为纯列表）、
`sort`（id/created_at/due_at/priority 白名单）+ `order`（asc/desc），
默认 id 升序。`project_id` 保持必填（跨项目「我的任务」视图留待
TASK-036 assignee 后再议）。
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_permission
from app.db.session import get_db
from app.models.task import TaskPriority, TaskStatus
from app.models.user import User
from app.schemas.common import SuccessResponse
from app.schemas.task import (
    TaskCreate,
    TaskRead,
    TaskSortField,
    TaskSortOrder,
    TaskUpdate,
)
from app.services import task as task_service

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post(
    "",
    response_model=SuccessResponse[TaskRead],
    status_code=status.HTTP_201_CREATED,
    summary="Create a task under a project (creator = caller, TODO start)",
    responses={
        403: {"description": "Missing task:create permission"},
        404: {"description": "Project not found (or caller is not a member)"},
    },
)
async def create_task(
    payload: TaskCreate,
    user: Annotated[User, Depends(require_permission("task:create"))],
    db: AsyncSession = Depends(get_db),
) -> SuccessResponse[TaskRead]:
    task = await task_service.create_task(db, user, payload)
    return SuccessResponse(data=TaskRead.model_validate(task))


@router.get(
    "",
    response_model=SuccessResponse[list[TaskRead]],
    status_code=status.HTTP_200_OK,
    summary=(
        "List tasks of a project with filtering / paging / ordering "
        "(project team members only)"
    ),
    responses={
        403: {"description": "Missing task:read permission"},
        404: {"description": "Project not found (or not on caller's team chain)"},
    },
)
async def list_tasks(
    user: Annotated[User, Depends(require_permission("task:read"))],
    project_id: Annotated[int, Query(description="Filter tasks by project")],
    status_filter: Annotated[
        TaskStatus | None, Query(alias="status", description="Exact status match")
    ] = None,
    priority: Annotated[
        TaskPriority | None, Query(description="Exact priority match")
    ] = None,
    keyword: Annotated[
        str | None,
        Query(max_length=200, description="Case-insensitive title substring"),
    ] = None,
    skip: Annotated[int, Query(ge=0, description="Pagination offset")] = 0,
    limit: Annotated[int, Query(ge=1, le=100, description="Page size")] = 100,
    sort: TaskSortField = TaskSortField.ID,
    order: TaskSortOrder = "asc",
    db: AsyncSession = Depends(get_db),
) -> SuccessResponse[list[TaskRead]]:
    tasks = await task_service.list_tasks(
        db,
        user,
        project_id,
        status=status_filter,
        priority=priority,
        keyword=keyword,
        skip=skip,
        limit=limit,
        sort=sort,
        order=order,
    )
    return SuccessResponse(data=[TaskRead.model_validate(t) for t in tasks])


@router.get(
    "/{task_id}",
    response_model=SuccessResponse[TaskRead],
    status_code=status.HTTP_200_OK,
    summary="Get a task by id (project team members only)",
    responses={
        404: {"description": "Task not found (or not on caller's team chain)"},
    },
)
async def get_task(
    task_id: int,
    user: Annotated[User, Depends(require_permission("task:read"))],
    db: AsyncSession = Depends(get_db),
) -> SuccessResponse[TaskRead]:
    task = await task_service.get_task_for_user(db, user, task_id)
    return SuccessResponse(data=TaskRead.model_validate(task))


@router.patch(
    "/{task_id}",
    response_model=SuccessResponse[TaskRead],
    status_code=status.HTTP_200_OK,
    summary="Partially update a task (project team members; status immutable)",
    responses={
        404: {"description": "Task not found (or not on caller's team chain)"},
    },
)
async def update_task(
    task_id: int,
    payload: TaskUpdate,
    user: Annotated[User, Depends(require_permission("task:update"))],
    db: AsyncSession = Depends(get_db),
) -> SuccessResponse[TaskRead]:
    task = await task_service.update_task(db, user, task_id, payload)
    return SuccessResponse(data=TaskRead.model_validate(task))


@router.delete(
    "/{task_id}",
    response_model=SuccessResponse[None],
    status_code=status.HTTP_200_OK,
    summary="Delete a task (team owner/admin only)",
    responses={
        403: {"description": "Caller team role insufficient (need OWNER/ADMIN)"},
        404: {"description": "Task not found (or not on caller's team chain)"},
    },
)
async def delete_task(
    task_id: int,
    user: Annotated[User, Depends(require_permission("task:delete"))],
    db: AsyncSession = Depends(get_db),
) -> SuccessResponse[None]:
    await task_service.delete_task(db, user, task_id)
    return SuccessResponse(data=None)
