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

TASK-036 多人分配（用户确认决策）：

- `POST /tasks/{task_id}/assignees` / `DELETE .../assignees/{user_id}`：
  功能级 `task:update`（分配是更新行为，seed 权限清单不新增项）+
  资源级团队成员即可（协作式，可自领）；目标用户不存在或非任务所属
  团队成员 → 404 `User not found`（同文案防枚举）；重复分配 409；
  目标非该任务负责人 → 404 `Assignee not found`。
- `TaskRead.assignees` 内嵌 `[{user_id, username, assigned_at}]`——
  详情/列表/创建/更新响应统一内嵌，批量 IN 查询避免 N+1。
- `GET /tasks` 增 `assignee_id` 可选过滤（负责人筛选）。

TASK-038 状态流转（用户确认决策）：`POST /tasks/{task_id}/transition`，
请求体 `{"to_status": "<状态>"}`——功能级 `task:transition`（种子仅
admin 持有）+ 资源级**任务所属团队成员即可**（协作式，同更新/分配语义）；
非法流转（相邻回退 / 跨级跳转 / 终态任何出边 / 同状态重复流转）→ 409
`Invalid status transition`（TASK-037 状态机在 Service 层拦截，Decision 005：
普通 PATCH 依然不可触达 status）。
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
    TaskAssigneeCreate,
    TaskAssigneeRead,
    TaskCreate,
    TaskRead,
    TaskSortField,
    TaskSortOrder,
    TaskTransitionCreate,
    TaskUpdate,
)
from app.services import task as task_service

router = APIRouter(prefix="/tasks", tags=["tasks"])


async def _serialize_task(
    db: AsyncSession, task
) -> TaskRead:
    """TaskRead + assignees 内嵌（单任务场景）。"""
    mapping = await task_service.assignees_map(db, [task.id])
    payload = TaskRead.model_validate(task)
    payload.assignees = mapping.get(task.id, [])
    return payload


async def _serialize_tasks(
    db: AsyncSession, tasks: list
) -> list[TaskRead]:
    """TaskRead + assignees 内嵌（列表场景，一次批量查询）。"""
    mapping = await task_service.assignees_map(db, [t.id for t in tasks])
    out = []
    for t in tasks:
        payload = TaskRead.model_validate(t)
        payload.assignees = mapping.get(t.id, [])
        out.append(payload)
    return out


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
    return SuccessResponse(data=await _serialize_task(db, task))


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
    assignee_id: Annotated[
        int | None,
        Query(description="Filter tasks assigned to this user (TASK-036)"),
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
        assignee_id=assignee_id,
        skip=skip,
        limit=limit,
        sort=sort,
        order=order,
    )
    return SuccessResponse(data=await _serialize_tasks(db, tasks))


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
    return SuccessResponse(data=await _serialize_task(db, task))


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
    return SuccessResponse(data=await _serialize_task(db, task))


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


@router.post(
    "/{task_id}/transition",
    response_model=SuccessResponse[TaskRead],
    status_code=status.HTTP_200_OK,
    summary=(
        "Transition a task's status via the state machine "
        "(project team members only; illegal transition → 409)"
    ),
    responses={
        403: {"description": "Missing task:transition permission"},
        404: {"description": "Task not found (or not on caller's team chain)"},
        409: {"description": "Invalid status transition"},
    },
)
async def transition_task(
    task_id: int,
    payload: TaskTransitionCreate,
    user: Annotated[User, Depends(require_permission("task:transition"))],
    db: AsyncSession = Depends(get_db),
) -> SuccessResponse[TaskRead]:
    task = await task_service.transition_task(db, user, task_id, payload)
    return SuccessResponse(data=await _serialize_task(db, task))


@router.post(
    "/{task_id}/assignees",
    response_model=SuccessResponse[TaskAssigneeRead],
    status_code=status.HTTP_201_CREATED,
    summary="Assign a user to a task (project team members only)",
    responses={
        404: {
            "description": (
                "Task not found (or not on caller's team chain) / "
                "User not found (or not a member of the task's team)"
            ),
        },
        409: {"description": "User already assigned to this task"},
    },
)
async def assign_task(
    task_id: int,
    payload: TaskAssigneeCreate,
    user: Annotated[User, Depends(require_permission("task:update"))],
    db: AsyncSession = Depends(get_db),
) -> SuccessResponse[TaskAssigneeRead]:
    assignee = await task_service.assign_task(db, user, task_id, payload)
    return SuccessResponse(data=assignee)


@router.delete(
    "/{task_id}/assignees/{user_id}",
    response_model=SuccessResponse[None],
    status_code=status.HTTP_200_OK,
    summary="Remove an assignee from a task (project team members only)",
    responses={
        404: {
            "description": (
                "Task not found (or not on caller's team chain) / "
                "Assignee not found"
            ),
        },
    },
)
async def unassign_task(
    task_id: int,
    user_id: int,
    user: Annotated[User, Depends(require_permission("task:update"))],
    db: AsyncSession = Depends(get_db),
) -> SuccessResponse[None]:
    await task_service.unassign_task(db, user, task_id, user_id)
    return SuccessResponse(data=None)
