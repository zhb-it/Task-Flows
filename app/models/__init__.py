"""ORM models for TaskFlow Pro.

Importing this package registers every model on the shared
:data:`app.db.base.Base` metadata, so Alembic can autogenerate migrations
against the full set of tables.
"""

from app.models.permission import Permission
from app.models.project import Project
from app.models.refresh_token import RefreshToken
from app.models.role import Role
from app.models.role_permission import RolePermission
from app.models.task import Task
from app.models.task_assignee import TaskAssignee
from app.models.team import Team
from app.models.team_member import TeamMember
from app.models.comment import Comment
from app.models.operation_log import OperationLog
from app.models.user import User
from app.models.user_role import UserRole

__all__ = [
    "Permission",
    "Project",
    "RefreshToken",
    "Role",
    "RolePermission",
    "Task",
    "TaskAssignee",
    "Team",
    "TeamMember",
    "Comment",
    "OperationLog",
    "User",
    "UserRole",
]
