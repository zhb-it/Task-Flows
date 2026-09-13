"""Task endpoints — 任务 CRUD（TASK-034）.

Router 只做 HTTP ⇄ Service 的翻译（项目规则 §4）。授权分两层（TASK-033
决策，docs/API_CONTRACT.md Task 注已登记）：

- 功能级：`require_permission("task:create|read|update|delete")` 依赖在
  进入业务前判定，缺失 → 403（TASK-023 契约）。
- 资源级：Service 层判定归属链（任务 → 项目 → 团队 → `team_members`）。
  不在链上 → 404（IDOR 防枚举）；已在链上但角色不足（删除需团队
  OWNER/ADMIN）→ 403 明示。

TASK-032 决策：创建请求体不含 `status`——新任务一律 TODO 起步。
列表按项目过滤：`GET /tasks?project_id={id}`（TASK-035 再做过滤/分页/
排序专项）。
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_permission
from app.db.session import get_db
from app.models.user import User
from app.schemas.common import SuccessResponse
from app.schemas.task import TaskCreate, TaskRead, TaskUpdate
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
    summary="List tasks of a project (project team members only)",
    responses={
        403: {"description": "Missing task:read permission"},
        404: {"description": "Project not found (or not on caller's team chain)"},
    },
)
async def list_tasks(
    user: Annotated[User, Depends(require_permission("task:read"))],
    project_id: Annotated[int, Query(description="Filter tasks by project")],
    db: AsyncSession = Depends(get_db),
) -> SuccessResponse[list[TaskRead]]:
    tasks = await task_service.list_tasks(db, user, project_id)
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
