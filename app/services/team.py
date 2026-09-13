"""Team Service (TASK-027，开发文档 §7 / §49).

事务边界与业务规则在本层（项目规则 §4）。TASK-027 三个已确认决策：

1. **创建团队自动写 OWNER 成员行**：`create_team` 在同一事务内写 `teams` 行 +
   `team_members(owner_id, role=OWNER)`，成员归属链统一以 `team_members` 为准。
2. **PATCH / DELETE 仅 owner**：功能级权限（`team:update` / `team:delete`，
   Router 依赖层）之外，资源级要求 `team.owner_id == user.id`；不满足时与
   「资源不存在」统一 404（§49 IDOR 防枚举，TASK-024 契约）。
3. **可见范围 = 我参与的团队**：列表与详情的归属链判定为 owner 或
   `team_members` 成员；他人团队一律 404。

功能级权限缺失（403）不在此层判定——Router 的 `require_permission` 依赖承担；
Service 层等价场景用 `ensure_permission`（app/services/authorization.py）。
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ResourceNotFoundError
from app.crud.team import (
    add_team_member,
    create_team as create_team_crud,
    delete_team as delete_team_crud,
    get_team,
    get_team_member,
    is_team_member,
    list_teams_for_user,
    update_team as update_team_crud,
)
from app.models.team import Team
from app.models.team_member import TeamRole
from app.models.user import User
from app.schemas.team import TeamCreate, TeamUpdate

NOT_FOUND = "Team not found"


async def create_team(db: AsyncSession, owner: User, payload: TeamCreate) -> Team:
    """创建团队并自动写入 OWNER 成员行（同一事务，决策 1）。"""
    team = await create_team_crud(
        db, name=payload.name, description=payload.description, owner_id=owner.id
    )
    await add_team_member(
        db, team_id=team.id, user_id=owner.id, role_id=TeamRole.OWNER.value
    )
    await db.commit()
    return team


async def list_teams(
    db: AsyncSession, user: User, *, skip: int = 0, limit: int = 100
) -> list[Team]:
    """当前用户参与的团队（owner 或成员），按 id 排序（决策 3）。"""
    return await list_teams_for_user(db, user.id, skip=skip, limit=limit)


async def get_team_for_user(
    db: AsyncSession, user: User, team_id: int
) -> Team:
    """读取单个团队；不存在或调用者不在归属链上 → 404（同一文案）。"""
    team = await get_team(db, team_id)
    if team is None:
        raise ResourceNotFoundError(NOT_FOUND)
    if team.owner_id != user.id and not await is_team_member(
        db, team_id=team.id, user_id=user.id
    ):
        raise ResourceNotFoundError(NOT_FOUND)
    return team


async def update_team(
    db: AsyncSession, user: User, team_id: int, payload: TeamUpdate
) -> Team:
    """部分更新团队字段；仅 owner 可改（决策 2），否则 404。

    `exclude_unset=True`：只应用请求体中显式出现的字段——`description` 显式
    传 null 即清空，未传保持原值。
    """
    team = await get_team(db, team_id)
    if team is None or team.owner_id != user.id:
        raise ResourceNotFoundError(NOT_FOUND)
    fields = payload.model_dump(exclude_unset=True)
    for key, value in fields.items():
        setattr(team, key, value)
    updated = await update_team_crud(db, team)
    await db.commit()
    return updated


async def delete_team(db: AsyncSession, user: User, team_id: int) -> None:
    """删除团队；仅 owner 可删（决策 2），否则 404。

    成员行随团队级联清理（TASK-026 迁移的 ON DELETE CASCADE）；若未来有成员
    仍依赖此团队的数据（项目/任务），由 `teams.owner_id` RESTRICT 之外的字段
    约束在后续 TASK 处理。
    """
    team = await get_team(db, team_id)
    if team is None or team.owner_id != user.id:
        raise ResourceNotFoundError(NOT_FOUND)
    await delete_team_crud(db, team)
    await db.commit()


async def team_membership(
    db: AsyncSession, team_id: int, user_id: int
) -> TeamRole | None:
    """调用者在团队中的团队角色（TASK-028 成员管理的基石，此任务先暴露）。"""
    member = await get_team_member(db, team_id=team_id, user_id=user_id)
    return TeamRole(member.role_id) if member else None
