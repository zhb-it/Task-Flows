"""Team endpoints — 团队 CRUD（TASK-027）与成员管理（TASK-028）.

Router 只做 HTTP ⇄ Service 的翻译（项目规则 §4）。授权分两层：

- 功能级：`require_permission("team:read|create|update|delete|invite")` 依赖
  在进入业务前判定，缺失 → 403（TASK-023 契约）。
- 资源级：Service 层判定归属（PATCH/DELETE 团队仅 owner；成员管理需团队
  角色 OWNER/ADMIN），不在归属链 → 404（TASK-024 IDOR 契约）。

成员管理（TASK-028）：邀请请求体 `user_id` + `role`（仅 admin/member）；
重复邀请 409；移除层级 OWNER > ADMIN > MEMBER，owner 不可被移除。
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_permission
from app.models.user import User
from app.db.session import get_db
from app.schemas.common import SuccessResponse
from app.schemas.team import (
    TeamCreate,
    TeamMemberInvite,
    TeamMemberRead,
    TeamRead,
    TeamUpdate,
)
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


# --- TASK-028 成员管理 ------------------------------------------------------------


@router.post(
    "/{team_id}/members",
    response_model=SuccessResponse[TeamMemberRead],
    status_code=status.HTTP_201_CREATED,
    summary="Invite a user to a team (team owner/admin only)",
    responses={
        403: {"description": "Missing team:invite permission, or caller role insufficient"},
        404: {"description": "Team not on caller's ownership chain, or target user not found"},
        409: {"description": "Target user is already a team member"},
    },
)
async def invite_member(
    team_id: int,
    payload: TeamMemberInvite,
    user: Annotated[User, Depends(require_permission("team:invite"))],
    db: AsyncSession = Depends(get_db),
) -> SuccessResponse[TeamMemberRead]:
    member = await team_service.invite_member(db, user, team_id, payload)
    return SuccessResponse(data=member)


@router.get(
    "/{team_id}/members",
    response_model=SuccessResponse[list[TeamMemberRead]],
    status_code=status.HTTP_200_OK,
    summary="List team members (visible to team members)",
    responses={
        404: {"description": "Team not found (or not on caller's ownership chain)"},
    },
)
async def list_members(
    team_id: int,
    user: Annotated[User, Depends(require_permission("team:read"))],
    db: AsyncSession = Depends(get_db),
) -> SuccessResponse[list[TeamMemberRead]]:
    members = await team_service.list_members(db, user, team_id)
    return SuccessResponse(data=members)


@router.delete(
    "/{team_id}/members/{user_id}",
    response_model=SuccessResponse[None],
    status_code=status.HTTP_200_OK,
    summary="Remove a member (owner removes anyone, admin removes members only)",
    responses={
        403: {"description": "Caller role insufficient, or target member cannot be removed"},
        404: {"description": "Team not on caller's ownership chain, or member not found"},
    },
)
async def remove_member(
    team_id: int,
    user_id: int,
    user: Annotated[User, Depends(require_permission("team:invite"))],
    db: AsyncSession = Depends(get_db),
) -> SuccessResponse[None]:
    await team_service.remove_member(db, user, team_id, user_id)
    return SuccessResponse(data=None)
