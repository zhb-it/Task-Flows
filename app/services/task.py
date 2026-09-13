"""Task Service (TASK-033).

事务边界与业务规则在本层（项目规则 §4）。TASK-033 两项已确认决策：

1. **创建授权 = 团队成员即可**：`task:create`（功能级，Router 依赖层）+
   调用者是目标任务所属团队的成员（资源级，本层）。项目不存在或调用者
   非成员 → 404（同一文案，IDOR 防枚举）。新任务一律 TODO 起步
   （TASK-032 决策，本层不接收 status）。
2. **更新 = 团队成员即可；删除 = 团队角色 OWNER/ADMIN**（与种子设计
   对齐——member 全局角色有 task:update 无 task:delete）：更新在归属链上
   即可；删除时团队角色不足 → 403（调用者本就可见该任务，明示权限不足
   无泄露）；不在归属链 → 404（§49 IDOR 契约）。

归属链 = 任务 → 项目 → 团队 → `team_members`（规格 §5「用户只能访问其
所属团队链路下的资源」）。复用 project 服务的可见性原语，不重复实现。
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError, ResourceNotFoundError
from app.crud.project import get_project, is_project_visible
from app.crud.task import (
    create_task as create_task_crud,
    delete_task as delete_task_crud,
    get_task,
    list_tasks_by_project,
    update_task as update_task_crud,
)
from app.models.task import Task
from app.models.team_member import TeamRole
from app.models.user import User
from app.schemas.task import TaskCreate, TaskUpdate
from app.services.team import team_membership

TASK_NOT_FOUND = "Task not found"
PROJECT_NOT_FOUND = "Project not found"  # 与项目创建同一文案模式：目标不可见
NOT_MANAGER = "Only team owner or admin can delete tasks"


async def create_task(db: AsyncSession, user: User, payload: TaskCreate) -> Task:
    """在项目下创建任务（决策 1）：须是项目所属团队成员，创建者即 creator。

    项目不存在或调用者不是其团队成员 → 404（同一文案，IDOR 防枚举——
    不向非成员泄露项目是否存在；类比 POST /projects 对不可见团队报
    "Team not found" 的先例）。
    """
    project = await get_project(db, payload.project_id)
    if project is None or not await is_project_visible(
        db, project_id=project.id, user_id=user.id
    ):
        raise ResourceNotFoundError(PROJECT_NOT_FOUND)

    task = await create_task_crud(
        db,
        project_id=project.id,
        title=payload.title,
        description=payload.description,
        priority=payload.priority.value,
        creator_id=user.id,
        due_at=payload.due_at,
    )
    await db.commit()
    return task


async def get_task_for_user(db: AsyncSession, user: User, task_id: int) -> Task:
    """读取单个任务；不存在或调用者不在归属链上 → 404（同一文案）。"""
    task = await get_task(db, task_id)
    if task is None or not await _is_task_visible(db, task, user.id):
        raise ResourceNotFoundError(TASK_NOT_FOUND)
    return task


async def list_tasks(
    db: AsyncSession, user: User, project_id: int
) -> list[Task]:
    """项目下全部任务（id 升序）；项目不可见 → 404（TASK-035 再做过滤分页）。"""
    project = await get_project(db, project_id)
    if project is None or not await is_project_visible(
        db, project_id=project.id, user_id=user.id
    ):
        raise ResourceNotFoundError(TASK_NOT_FOUND)
    return await list_tasks_by_project(db, project.id)


async def update_task(
    db: AsyncSession, user: User, task_id: int, payload: TaskUpdate
) -> Task:
    """部分更新任务字段（决策 2）：归属链上的团队成员即可。

    `exclude_unset=True`：只应用请求体中显式出现的字段——`description`
    显式传 null 即清空，未传保持原值。status 不在 TaskUpdate 中，无法经
    此修改（流转走 transition API，TASK-038）。
    """
    task = await _get_task_on_chain(db, user, task_id)
    fields = payload.model_dump(exclude_unset=True)
    for key, value in fields.items():
        setattr(task, key, value)
    updated = await update_task_crud(db, task)
    await db.commit()
    return updated


async def delete_task(db: AsyncSession, user: User, task_id: int) -> None:
    """删除任务（决策 2）：须团队角色 OWNER/ADMIN；未来分配行随级联清理。"""
    task = await _get_task_on_chain(db, user, task_id)
    # Task 模型未建 relationship（TASK-031 决策），显式取项目拿 team_id
    project = await get_project(db, task.project_id)
    assert project is not None  # 归属链判定已通过，项目必然存在
    role = await team_membership(db, project.team_id, user.id)
    if role not in (TeamRole.OWNER, TeamRole.ADMIN):
        raise ForbiddenError(NOT_MANAGER)
    await delete_task_crud(db, task)
    await db.commit()


async def _is_task_visible(db: AsyncSession, task: Task, user_id: int) -> bool:
    """任务可见性 = 调用者在任务所属项目的团队成员链上。"""
    return await is_project_visible(
        db, project_id=task.project_id, user_id=user_id
    )


async def _get_task_on_chain(
    db: AsyncSession, user: User, task_id: int
) -> Task:
    """写操作共用的资源级判定第一步：

    任务不存在或调用者不在归属链上 → 404（同一文案，IDOR 防枚举）。
    进一步的角色判定由调用方（update 免、delete 做）完成。
    """
    task = await get_task(db, task_id)
    if task is None or not await _is_task_visible(db, task, user.id):
        raise ResourceNotFoundError(TASK_NOT_FOUND)
    return task
