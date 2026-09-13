"""Project endpoints — 项目 CRUD（TASK-029）.

Router 只做 HTTP ⇄ Service 的翻译（项目规则 §4）。授权分两层：

- 功能级：`require_permission("project:create|read|update|delete")` 依赖
  在进入业务前判定，缺失 → 403（TASK-023 契约）。
- 资源级：Service 层判定归属链（项目所属团队成员可见；改删需团队角色
  OWNER/ADMIN），不在链上 → 404（TASK-024 IDOR 契约，两种 404 文案相同）。

TASK-029 决策：创建 = 团队成员即可（owner_id 恒为创建者）；改删 = 团队
OWNER/ADMIN；列表 = 我所在团队下的项目。
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_permission
from app.db.session import get_db
from app.models.user import User
from app.schemas.common import SuccessResponse
from app.schemas.project import ProjectCreate, ProjectRead, ProjectUpdate
from app.services import project as project_service

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post(
    "",
    response_model=SuccessResponse[ProjectRead],
    status_code=status.HTTP_201_CREATED,
    summary="Create a project under a team (creator becomes owner)",
    responses={
        403: {"description": "Missing project:create permission"},
        404: {"description": "Team not found (or caller is not a member)"},
    },
)
async def create_project(
    payload: ProjectCreate,
    user: Annotated[User, Depends(require_permission("project:create"))],
    db: AsyncSession = Depends(get_db),
) -> SuccessResponse[ProjectRead]:
    project = await project_service.create_project(db, user, payload)
    return SuccessResponse(data=ProjectRead.model_validate(project))


@router.get(
    "",
    response_model=SuccessResponse[list[ProjectRead]],
    status_code=status.HTTP_200_OK,
    summary="List projects under teams the current user belongs to",
    responses={403: {"description": "Missing project:read permission"}},
)
async def list_projects(
    user: Annotated[User, Depends(require_permission("project:read"))],
    db: AsyncSession = Depends(get_db),
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
) -> SuccessResponse[list[ProjectRead]]:
    projects = await project_service.list_projects(
        db, user, skip=skip, limit=limit
    )
    return SuccessResponse(
        data=[ProjectRead.model_validate(p) for p in projects]
    )


@router.get(
    "/{project_id}",
    response_model=SuccessResponse[ProjectRead],
    status_code=status.HTTP_200_OK,
    summary="Get a project by id (team members only)",
    responses={
        404: {"description": "Project not found (or not on caller's team chain)"},
    },
)
async def get_project(
    project_id: int,
    user: Annotated[User, Depends(require_permission("project:read"))],
    db: AsyncSession = Depends(get_db),
) -> SuccessResponse[ProjectRead]:
    project = await project_service.get_project_for_user(db, user, project_id)
    return SuccessResponse(data=ProjectRead.model_validate(project))


@router.patch(
    "/{project_id}",
    response_model=SuccessResponse[ProjectRead],
    status_code=status.HTTP_200_OK,
    summary="Partially update a project (team owner/admin only)",
    responses={
        403: {"description": "Caller team role insufficient"},
        404: {"description": "Project not found (or not on caller's team chain)"},
    },
)
async def update_project(
    project_id: int,
    payload: ProjectUpdate,
    user: Annotated[User, Depends(require_permission("project:update"))],
    db: AsyncSession = Depends(get_db),
) -> SuccessResponse[ProjectRead]:
    project = await project_service.update_project(
        db, user, project_id, payload
    )
    return SuccessResponse(data=ProjectRead.model_validate(project))


@router.delete(
    "/{project_id}",
    response_model=SuccessResponse[None],
    status_code=status.HTTP_200_OK,
    summary="Delete a project (team owner/admin only)",
    responses={
        403: {"description": "Caller team role insufficient"},
        404: {"description": "Project not found (or not on caller's team chain)"},
    },
)
async def delete_project(
    project_id: int,
    user: Annotated[User, Depends(require_permission("project:delete"))],
    db: AsyncSession = Depends(get_db),
) -> SuccessResponse[None]:
    await project_service.delete_project(db, user, project_id)
    return SuccessResponse(data=None)
