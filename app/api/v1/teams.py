"""Team endpoints — 团队 CRUD（TASK-027）.

Router 只做 HTTP ⇄ Service 的翻译（项目规则 §4）。授权分两层：

- 功能级：`require_permission("team:create|read|update|delete")` 依赖在进入
  业务前判定，缺失 → 403（TASK-023 契约）。
- 资源级：Service 层判定归属（PATCH/DELETE 仅 owner；GET 详情需是成员），
  不在归属链 → 404（TASK-024 IDOR 契约，两种 404 文案相同）。
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_permission
from app.models.user import User
from app.db.session import get_db
from app.schemas.common import SuccessResponse
from app.schemas.team import TeamCreate, TeamRead, TeamUpdate
from app.services import team as team_service

router = APIRouter(prefix="/teams", tags=["teams"])


@router.post(
    "",
    response_model=SuccessResponse[TeamRead],
    status_code=status.HTTP_201_CREATED,
    summary="Create a team (creator becomes owner)",
    responses={401: {}, 403: {"description": "Missing team:create permission"}},
)
async def create_team(
    payload: TeamCreate,
    user: Annotated[User, Depends(require_permission("team:create"))],
    db: AsyncSession = Depends(get_db),
) -> SuccessResponse[TeamRead]:
    team = await team_service.create_team(db, user, payload)
    return SuccessResponse(data=TeamRead.model_validate(team))


@router.get(
    "",
    response_model=SuccessResponse[list[TeamRead]],
    status_code=status.HTTP_200_OK,
    summary="List teams the current user participates in",
    responses={401: {}, 403: {"description": "Missing team:read permission"}},
)
async def list_teams(
    user: Annotated[User, Depends(require_permission("team:read"))],
    db: AsyncSession = Depends(get_db),
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
) -> SuccessResponse[list[TeamRead]]:
    teams = await team_service.list_teams(db, user, skip=skip, limit=limit)
    return SuccessResponse(data=[TeamRead.model_validate(t) for t in teams])


@router.get(
    "/{team_id}",
    response_model=SuccessResponse[TeamRead],
    status_code=status.HTTP_200_OK,
    summary="Get a team by id (must participate in it)",
    responses={
        404: {"description": "Team not found (or not on caller's ownership chain)"},
    },
)
async def get_team(
    team_id: int,
    user: Annotated[User, Depends(require_permission("team:read"))],
    db: AsyncSession = Depends(get_db),
) -> SuccessResponse[TeamRead]:
    team = await team_service.get_team_for_user(db, user, team_id)
    return SuccessResponse(data=TeamRead.model_validate(team))


@router.patch(
    "/{team_id}",
    response_model=SuccessResponse[TeamRead],
    status_code=status.HTTP_200_OK,
    summary="Partially update a team (owner only)",
    responses={
        404: {"description": "Team not found (or caller is not the owner)"},
    },
)
async def update_team(
    team_id: int,
    payload: TeamUpdate,
    user: Annotated[User, Depends(require_permission("team:update"))],
    db: AsyncSession = Depends(get_db),
) -> SuccessResponse[TeamRead]:
    team = await team_service.update_team(db, user, team_id, payload)
    return SuccessResponse(data=TeamRead.model_validate(team))


@router.delete(
    "/{team_id}",
    response_model=SuccessResponse[None],
    status_code=status.HTTP_200_OK,
    summary="Delete a team (owner only)",
    responses={
        404: {"description": "Team not found (or caller is not the owner)"},
    },
)
async def delete_team(
    team_id: int,
    user: Annotated[User, Depends(require_permission("team:delete"))],
    db: AsyncSession = Depends(get_db),
) -> SuccessResponse[None]:
    await team_service.delete_team(db, user, team_id)
    return SuccessResponse(data=None)
