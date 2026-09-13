"""`/api/v1` router aggregation (API_CONTRACT.md：基础路径 `/api/v1`)."""

from fastapi import APIRouter

from app.api.v1 import auth

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
