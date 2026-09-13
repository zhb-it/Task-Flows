"""Project Service (TASK-029).

事务边界与业务规则在本层（项目规则 §4）。TASK-029 三个已确认决策
（docs/DB_SCHEMA.md / DECISIONS 登记）：

1. **双层判定**：功能级权限（`project:create|read|update|delete`，Router
   依赖层）+ 资源级归属（本层）。可见性按规格 §5「用户只能访问其所属
   团队链路下的资源」——项目所属团队的成员（`team_members` 有行）构成
   归属链；不在链上 → 404（§49 IDOR 防枚举契约）。
2. **创建授权 = 团队成员即可**：`project:create` + 调用者是目标团队成员；
   项目 `owner_id` 恒为创建者，不开放客户端指定。
3. **改删授权 = 团队角色 OWNER/ADMIN**：`project:update|delete` + 调用者
   在项目所属团队的角色为 OWNER/ADMIN；团队角色不足 → 403（调用者已在
   归属链上、本就可见该项目，无信息泄露顾虑，与 TASK-028 语义一致）。

Service 层复用 team 服务的归属链原语（`team_membership` 等），不重复实现。
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError, ResourceNotFoundError
from app.crud.project import (
    create_project as create_project_crud,
    delete_project as delete_project_crud,
    get_project,
    is_project_visible,
    list_projects_for_user,
    update_project as update_project_crud,
)
from app.crud.team import get_team, is_team_member
from app.models.project import Project
from app.models.team_member import TeamRole
from app.models.user import User
from app.schemas.project import ProjectCreate, ProjectUpdate
from app.services.team import team_membership

PROJECT_NOT_FOUND = "Project not found"
TEAM_NOT_FOUND = "Team not found"
NOT_MANAGER = "Only team owner or admin can manage projects"


async def create_project(
    db: AsyncSession, user: User, payload: ProjectCreate
) -> Project:
    """在团队下创建项目（决策 2）：须是团队成员，创建者即 owner。

    团队不存在或调用者不是其成员 → 404（同一文案，IDOR 防枚举——
    不向非成员泄露团队是否存在）。
    """
    team = await get_team(db, payload.team_id)
    if team is None or not await is_team_member(
        db, team_id=team.id, user_id=user.id
    ):
        raise ResourceNotFoundError(TEAM_NOT_FOUND)

    project = await create_project_crud(
        db,
        name=payload.name,
        description=payload.description,
        team_id=team.id,
        owner_id=user.id,
    )
    await db.commit()
    return project


async def list_projects(
    db: AsyncSession, user: User, *, skip: int = 0, limit: int = 100
) -> list[Project]:
    """当前用户所在团队下的项目（决策 4），按 id 排序。"""
    return await list_projects_for_user(db, user.id, skip=skip, limit=limit)


async def get_project_for_user(
    db: AsyncSession, user: User, project_id: int
) -> Project:
    """读取单个项目；不存在或调用者不在归属链上 → 404（同一文案）。"""
    project = await get_project(db, project_id)
    if project is None or not await is_project_visible(
        db, project_id=project.id, user_id=user.id
    ):
        raise ResourceNotFoundError(PROJECT_NOT_FOUND)
    return project


async def update_project(
    db: AsyncSession, user: User, project_id: int, payload: ProjectUpdate
) -> Project:
    """部分更新项目字段（决策 3）：须团队角色 OWNER/ADMIN，否则 403/404。

    `exclude_unset=True`：只应用请求体中显式出现的字段——`description`
    显式传 null 即清空，未传保持原值。
    """
    project = await _get_project_for_management(db, user, project_id)
    fields = payload.model_dump(exclude_unset=True)
    for key, value in fields.items():
        setattr(project, key, value)
    updated = await update_project_crud(db, project)
    await db.commit()
    return updated


async def delete_project(db: AsyncSession, user: User, project_id: int) -> None:
    """删除项目（决策 3）：须团队角色 OWNER/ADMIN；未来任务随级联清理。"""
    project = await _get_project_for_management(db, user, project_id)
    await delete_project_crud(db, project)
    await db.commit()


async def _get_project_for_management(
    db: AsyncSession, user: User, project_id: int
) -> Project:
    """管理操作（PATCH/DELETE）的资源级判定：

    - 项目不存在或调用者不在归属链上 → 404（同一文案，IDOR 防枚举）；
    - 在链上但团队角色不足（非 OWNER/ADMIN）→ 403（调用者本就可见，
      明示权限不足无泄露）。
    """
    project = await get_project(db, project_id)
    if project is None or not await is_project_visible(
        db, project_id=project.id, user_id=user.id
    ):
        raise ResourceNotFoundError(PROJECT_NOT_FOUND)

    role = await team_membership(db, project.team_id, user.id)
    if role not in (TeamRole.OWNER, TeamRole.ADMIN):
        raise ForbiddenError(NOT_MANAGER)
    return project
