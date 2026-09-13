"""Team CRUD operations (TASK-027).

Write helpers persist rows via `flush` only — the transaction boundary stays
with the Service layer (项目规则 §4 / ARCHITECTURE.md).

`list_teams_for_user` implements the TASK-027 visibility decision: a user sees
the teams they *participate in* — either as owner (`teams.owner_id`) or as a
`team_members` row. With the create-time OWNER member row (TASK-027 decision)
the member-row branch alone would usually suffice, but the owner branch keeps
the query correct even for teams created before that rule or manipulated
directly.
"""

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.team import Team
from app.models.team_member import TeamMember


async def create_team(
    db: AsyncSession, *, name: str, description: str | None, owner_id: int
) -> Team:
    team = Team(name=name, description=description, owner_id=owner_id)
    db.add(team)
    await db.flush()
    await db.refresh(team)
    return team


async def add_team_member(
    db: AsyncSession, *, team_id: int, user_id: int, role_id: int
) -> TeamMember:
    """Insert a `team_members` row. Flushes so UNIQUE violations surface here."""
    member = TeamMember(team_id=team_id, user_id=user_id, role_id=role_id)
    db.add(member)
    await db.flush()
    await db.refresh(member)
    return member


async def get_team(db: AsyncSession, team_id: int) -> Team | None:
    result = await db.execute(select(Team).where(Team.id == team_id))
    return result.scalar_one_or_none()


async def get_team_member(
    db: AsyncSession, *, team_id: int, user_id: int
) -> TeamMember | None:
    result = await db.execute(
        select(TeamMember).where(
            TeamMember.team_id == team_id, TeamMember.user_id == user_id
        )
    )
    return result.scalar_one_or_none()


async def is_team_member(db: AsyncSession, *, team_id: int, user_id: int) -> bool:
    result = await db.execute(
        select(exists().where(
            TeamMember.team_id == team_id, TeamMember.user_id == user_id
        ))
    )
    return bool(result.scalar())


async def list_teams_for_user(
    db: AsyncSession, user_id: int, *, skip: int = 0, limit: int = 100
) -> list[Team]:
    """Teams the user participates in (owner or member), ordered by id."""
    member_subq = select(TeamMember.id).where(
        TeamMember.team_id == Team.id, TeamMember.user_id == user_id
    )
    result = await db.execute(
        select(Team)
        .where((Team.owner_id == user_id) | exists(member_subq))
        .order_by(Team.id)
        .offset(skip)
        .limit(limit)
    )
    return list(result.scalars().all())


async def update_team(db: AsyncSession, team: Team) -> Team:
    """Persist in-place attribute mutations made by the Service layer."""
    await db.flush()
    await db.refresh(team)
    return team


async def delete_team(db: AsyncSession, team: Team) -> None:
    """Delete the team. `team_members` rows go with it (ON DELETE CASCADE)."""
    await db.delete(team)
    await db.flush()
