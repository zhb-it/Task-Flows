"""`/api/v1` router aggregation (API_CONTRACT.md：基础路径 `/api/v1`)."""

from fastapi import APIRouter

from app.api.v1 import (
    attachments,
    auth,
    comments,
    logs,
    notifications,
    permissions,
    projects,
    tasks,
    teams,
    tenants,
    users,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(permissions.router)
api_router.include_router(teams.router)
api_router.include_router(projects.router)
api_router.include_router(tasks.router)
api_router.include_router(comments.router)
api_router.include_router(attachments.router)
api_router.include_router(logs.router)
api_router.include_router(notifications.router)
api_router.include_router(tenants.router)
