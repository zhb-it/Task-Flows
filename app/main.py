"""FastAPI application entrypoint.

Wires up the application shell, the `/api/v1` routers and a `/health` endpoint.
The `/health` endpoint probes PostgreSQL and Redis so an orchestrator can tell
whether the app's dependencies are reachable, but it always returns 200 while
the process itself is alive (liveness), reporting dependency status in the body.
"""

import asyncio

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from sqlalchemy import text

from app.api.v1 import api_router
from app.core.config import get_settings
from app.core.exceptions import AppError
from app.db.session import engine

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    debug=settings.debug,
)

app.include_router(api_router)


@app.exception_handler(AppError)
async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
    """Render domain errors with the project error envelope (项目文档 §26)."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=exc.headers,
    )


@app.get("/")
def root() -> dict:
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "env": settings.app_env,
    }


async def _check_database() -> bool:
    """Return True if PostgreSQL answers a trivial query within the timeout."""
    try:
        async with asyncio.timeout(2):
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


async def _check_redis() -> bool:
    """Return True if Redis answers PING within the timeout."""
    try:
        async with asyncio.timeout(2):
            client = Redis.from_url(settings.redis_url)
            try:
                return bool(await client.ping())
            finally:
                await client.aclose()
    except Exception:
        return False


@app.get("/health")
async def health() -> dict:
    db_up = await _check_database()
    redis_up = await _check_redis()
    status = "ok" if (db_up and redis_up) else "degraded"
    return {
        "status": status,
        "app": settings.app_name,
        "version": settings.app_version,
        "env": settings.app_env,
        "database": "up" if db_up else "down",
        "redis": "up" if redis_up else "down",
    }
