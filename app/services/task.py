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

from sqlalchemy import case
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    ConflictError,
    ForbiddenError,
    ResourceNotFoundError,
)
from app.crud.project import get_project, is_project_visible
from app.crud.task import (
    create_task as create_task_crud,
    delete_task as delete_task_crud,
    get_task,
    list_tasks_by_project,
    update_task as update_task_crud,
)
from app.crud.task_assignee import (
    add_task_assignee,
    is_task_assignee,
    list_assignees_for_tasks,
    remove_task_assignee,
)
from app.crud.user import get_user
from app.models.task import Task, TaskStatus
from app.models.team_member import TeamRole
from app.models.user import User
from app.schemas.task import (
    TaskAssigneeCreate,
    TaskAssigneeRead,
    TaskCreate,
    TaskSortField,
    TaskTransitionCreate,
    TaskUpdate,
)
from app.services.state_machine import validate_transition
from app.services.team import team_membership

TASK_NOT_FOUND = "Task not found"
PROJECT_NOT_FOUND = "Project not found"  # 与项目创建同一文案模式：目标不可见
NOT_MANAGER = "Only team owner or admin can delete tasks"
USER_NOT_FOUND = "User not found"  # 目标用户不存在或非任务所属团队成员（同文案防枚举）
ASSIGNEE_NOT_FOUND = "Assignee not found"
ALREADY_ASSIGNED = "User already assigned to this task"

#: priority 业务权重（URGENT > HIGH > MEDIUM > LOW）——sort=priority 时
#: 按业务序而非字母序排（TASK-035 决策）。
_PRIORITY_WEIGHT = case(
    (Task.priority == "URGENT", 4),
    (Task.priority == "HIGH", 3),
    (Task.priority == "MEDIUM", 2),
    else_=1,
)

#: sort 白名单 -> 排序列/表达式映射（TASK-035）。
_SORT_COLUMNS = {
    TaskSortField.ID: Task.id,
    TaskSortField.CREATED_AT: Task.created_at,
    TaskSortField.DUE_AT: Task.due_at,
    TaskSortField.PRIORITY: _PRIORITY_WEIGHT,
}


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
    db: AsyncSession,
    user: User,
    project_id: int,
    *,
    status: str | None = None,
    priority: str | None = None,
    keyword: str | None = None,
    assignee_id: int | None = None,
    skip: int = 0,
    limit: int = 100,
    sort: TaskSortField = TaskSortField.ID,
    order: str = "asc",
) -> list[Task]:
    """项目下任务列表（TASK-035：多条件过滤 + 分页 + 排序；TASK-036 增
    assignee_id 负责人筛选——存在子查询，不校验目标用户可见性，无行即空列表）。

    - 项目不可见 / 不存在 → 404（沿用 TASK-034 契约，IDOR 防枚举）；
    - 过滤：status / priority 精确匹配 + keyword 标题 ILIKE——通配符
      （% _ \\）转义后按字面匹配，纯空白 keyword 视为未传；assignee_id
      精确匹配某负责人（TASK-036）；
    - 分页：skip/limit（与 teams/projects 同惯例，边界由 Router 校验）；
    - 排序：sort 白名单（TaskSortField）+ order（asc/desc）；priority
      按业务权重而非字母序。
    """
    project = await get_project(db, project_id)
    if project is None or not await is_project_visible(
        db, project_id=project.id, user_id=user.id
    ):
        raise ResourceNotFoundError(TASK_NOT_FOUND)

    cleaned = keyword.strip() if keyword else None
    if cleaned:
        escaped = (
            cleaned.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        )
        keyword_clause = f"%{escaped}%"
    else:
        keyword_clause = None

    column = _SORT_COLUMNS[sort]
    order_clause = column.desc() if order == "desc" else column.asc()
    return await list_tasks_by_project(
        db,
        project.id,
        status=status,
        priority=priority,
        keyword=keyword_clause,
        assignee_id=assignee_id,
        skip=skip,
        limit=limit,
        order_by=order_clause,
    )


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


async def assign_task(
    db: AsyncSession, user: User, task_id: int, payload: TaskAssigneeCreate
) -> TaskAssigneeRead:
    """分配任务负责人（TASK-036 决策，用户确认）：

    - 功能级 task:update（Router 依赖）+ 资源级：调用者与目标都必须是
      任务所属团队成员——协作式分配，member 可分、可自领；
    - 任务不在归属链 → 404 Task not found（IDOR 防枚举）；
    - 目标用户不存在或不是任务所属团队成员 → 404 User not found
      （同文案，不向调用者区分两种失败，防用户 id 枚举；目标用户表
      无团队信息本身不构成资源泄露）；
    - 目标已是负责人 → 409（复合主键兜底，Service 先查给干净文案）；
    - ``assigned_by_id`` = 调用者（最小审计，删用户随 CASCADE 清理，
      追溯由 OperationLog TASK-039 承担）。
    """
    task = await _get_task_on_chain(db, user, task_id)
    project = await get_project(db, task.project_id)
    assert project is not None  # 归属链判定已通过，项目必然存在

    target = await get_user(db, payload.user_id)
    if target is None or await team_membership(
        db, project.team_id, payload.user_id
    ) is None:
        raise ResourceNotFoundError(USER_NOT_FOUND)

    if await is_task_assignee(db, task_id=task.id, user_id=payload.user_id):
        raise ConflictError(ALREADY_ASSIGNED)

    row = await add_task_assignee(
        db, task_id=task.id, user_id=payload.user_id, assigned_by_id=user.id
    )
    await db.commit()
    return TaskAssigneeRead(
        user_id=payload.user_id, username=target.username, assigned_at=row.assigned_at
    )


async def unassign_task(
    db: AsyncSession, user: User, task_id: int, target_user_id: int
) -> None:
    """移除任务负责人：授权同分配（团队成员即可）。

    目标不是该任务的负责人 → 404 Assignee not found（任务不在归属链
    仍为 404 Task not found，见 _get_task_on_chain）。
    """
    task = await _get_task_on_chain(db, user, task_id)
    removed = await remove_task_assignee(
        db, task_id=task.id, user_id=target_user_id
    )
    if not removed:
        raise ResourceNotFoundError(ASSIGNEE_NOT_FOUND)
    await db.commit()


async def transition_task(
    db: AsyncSession, user: User, task_id: int, payload: TaskTransitionCreate
) -> Task:
    """状态流转（TASK-038 决策，用户确认）：

    - 功能级 ``task:transition``（Router 依赖层）+ 资源级**任务所属团队
      成员即可**（协作式，与更新/分配同语义；区别于删除的 OWNER/ADMIN）；
    - 任务不在归属链 / 不存在 → 404 Task not found（IDOR 防枚举）；
    - 非法流转——相邻回退、跨级跳转、终态（DONE/CANCELLED）任何出边、
      同状态重复流转——→ 409 ``Invalid status transition``（TASK-037 决策；
      规格 §11「非法状态流转必须在 Service 层拦截」，状态机
      ``validate_transition`` 在此被 API 消费）；
    - 成功 → 更新 status 并返回任务（Router 组装 TaskRead + assignees）。
    """
    task = await _get_task_on_chain(db, user, task_id)
    validate_transition(TaskStatus(task.status), payload.to_status)
    task.status = payload.to_status.value
    updated = await update_task_crud(db, task)
    await db.commit()
    return updated


async def assignees_map(
    db: AsyncSession, task_ids: list[int]
) -> dict[int, list[TaskAssigneeRead]]:
    """批量取任务负责人明细（Router 组装 TaskRead.assignees 内嵌字段）。

    列表场景一次 IN 查询（无 relationship，TASK-031 决策延续）；
    不在结果中的任务 id 恒为空列表（新任务/未分配）。
    """
    grouped = await list_assignees_for_tasks(db, task_ids)
    return {
        task_id: [
            TaskAssigneeRead(
                user_id=row.user_id, username=username, assigned_at=row.assigned_at
            )
            for row, username in rows
        ]
        for task_id, rows in grouped.items()
    }


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
