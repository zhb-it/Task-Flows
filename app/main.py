"""FastAPI application entrypoint.

This module only wires up the application shell. Database sessions, Redis
connections, routers and middleware are introduced in later tasks, so the
app can be imported and tested without external services.
"""

from fastapi import FastAPI

from app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    debug=settings.debug,
)


@app.get("/")
def root() -> dict:
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "env": settings.app_env,
    }
