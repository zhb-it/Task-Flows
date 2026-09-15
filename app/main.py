"""FastAPI application entrypoint.

Wires up the application shell, the `/api/v1` routers and a `/health` endpoint.
The `/health` endpoint probes PostgreSQL and Redis so an orchestrator can tell
whether the app's dependencies are reachable, but it always returns 200 while
the process itself is alive (liveness), reporting dependency status in the body.

Redis 探测复用 ``app/db/redis.py`` 的共享客户端（TASK-045）——原先此处
`Redis.from_url` 一次探测建一个连接池，是资源浪费，也让「应用到底怎么连
Redis」出现第二份真相。
"""

import asyncio
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI
from sqlalchemy import text

from app.api.v1 import api_router
from app.core.config import get_settings
from app.core.exceptions import AppError, app_error_handler
from app.core.logging_config import configure_logging
from app.core.middleware import RateLimitMiddleware, RequestLoggingMiddleware
from app.db.redis import close_redis, get_redis_client
from app.db.session import engine

settings = get_settings()

# 日志在应用创建之前配置（§33）：越早安装 handler，越不容易漏掉启动阶段的日志。
# 幂等，可重复调用（测试会多次 import 本模块）。
configure_logging(settings)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """应用生命周期：启动时无需预热，关闭时释放 Redis 连接池。"""
    yield
    await close_redis()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    debug=settings.debug,
    lifespan=lifespan,
)

# 限流在路由分发之前生效（§22）。用中间件而非路由依赖，是为了让新增端点
# 自动受到保护，不会因为忘记声明依赖而留下无保护入口。
app.add_middleware(RateLimitMiddleware)

# 访问日志放在限流**之后**注册：Starlette 后注册的中间件在更外层，因此本中间件
# 包住限流——duration 才是「客户端实际等待的总时间」（含限流判定的开销）。
app.add_middleware(RequestLoggingMiddleware)

app.include_router(api_router)

app.add_exception_handler(AppError, app_error_handler)


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
    """Return True if Redis answers PING within the timeout.

    复用共享客户端（不关闭它——它属于进程，不属于本次探测）。
    """
    try:
        async with asyncio.timeout(2):
            return bool(await get_redis_client().ping())
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
