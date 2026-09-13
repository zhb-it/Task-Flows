"""Project CRUD operations (TASK-029).

Write helpers persist rows via `flush` only — the transaction boundary stays
with the Service layer (项目规则 §4 / ARCHITECTURE.md).

`list_projects_for_user` implements the TASK-029 visibility decision: a user
sees the projects belonging to the teams they participate in (`team_members`
row) —「用户只能访问其所属团队链路下的资源」(PROJECT_SPEC §5).
"""

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project
from app.models.team_member import TeamMember


async def create_project(
    db: AsyncSession,
    *,
    name: str,
    description: str | None,
    team_id: int,
    owner_id: int,
) -> Project:
    project = Project(
        name=name, description=description, team_id=team_id, owner_id=owner_id
    )
    db.add(project)
    await db.flush()
    await db.refresh(project)
    return project


async def get_project(db: AsyncSession, project_id: int) -> Project | None:
    result = await db.execute(select(Project).where(Project.id == project_id))
    return result.scalar_one_or_none()


async def is_project_visible(
    db: AsyncSession, *, project_id: int, user_id: int
) -> bool:
    """调用者是否在项目所属团队的成员链上（可见性判定）。"""
    project = await get_project(db, project_id)
    if project is None:
        return False
    result = await db.execute(
        select(
            exists().where(
                TeamMember.team_id == project.team_id,
                TeamMember.user_id == user_id,
            )
        )
    )
    return bool(result.scalar())


async def list_projects_for_user(
    db: AsyncSession, user_id: int, *, skip: int = 0, limit: int = 100
) -> list[Project]:
    """Projects under teams the user is a member of, ordered by id."""
    member_subq = select(TeamMember.id).where(
        TeamMember.team_id == Project.team_id, TeamMember.user_id == user_id
    )
    result = await db.execute(
        select(Project)
        .where(exists(member_subq))
        .order_by(Project.id)
        .offset(skip)
        .limit(limit)
    )
    return list(result.scalars().all())


async def update_project(db: AsyncSession, project: Project) -> Project:
    """Persist in-place attribute mutations made by the Service layer."""
    await db.flush()
    await db.refresh(project)
    return project


async def delete_project(db: AsyncSession, project: Project) -> None:
    """Delete the project. Future child rows (tasks) cascade with it."""
    await db.delete(project)
    await db.flush()
