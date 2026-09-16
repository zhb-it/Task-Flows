"""FastAPI application entrypoint.

Wires up the application shell, the `/api/v1` routers and the health probe
family (`/health`, `/health/live`, `/health/ready`, `/health/db`,
`/health/redis` — TASK-088, 规格 §32).
The `/health` endpoint probes PostgreSQL and Redis so an orchestrator can tell
whether the app's dependencies are reachable, but it always returns 200 while
the process itself is alive (liveness), reporting dependency status in the body.
`/health/live` 与 `/health/ready` 把「进程活着」与「依赖可用」两种语义分开。

Redis 探测复用 ``app/db/redis.py`` 的共享客户端（TASK-045）——原先此处
`Redis.from_url` 一次探测建一个连接池，是资源浪费，也让「应用到底怎么连
Redis」出现第二份真相。
"""

import asyncio
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.v1 import api_router
from app.core.config import get_settings
from app.core.exceptions import AppError, app_error_handler
from app.core.logging_config import configure_logging
from app.core.middleware import (
    RateLimitMiddleware,
    RequestIdMiddleware,
    RequestLoggingMiddleware,
)
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

# Request ID 最后注册，因而位于**最外层**（§34）：它的 ContextVar 必须在限流与
# 访问日志之前就位，这样本次请求的**全部**日志（含限流 warning、访问日志）都带
# request_id。与 LOG_REQUESTS 开关无关——§34 要求每个请求都生成，不受日志开关影响。
app.add_middleware(RequestIdMiddleware)

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
        async with asyncio.timeout(settings.health_probe_timeout):
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
        async with asyncio.timeout(settings.health_probe_timeout):
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


# ---------------------------------------------------------------------------
# 健康探针族（TASK-088，规格 §32）
#
# 「进程活着」（liveness）与「依赖可用」（readiness）是两种语义，混在一个
# 端点里会让编排器无所适从：DB 短暂抖动时把实例杀掉重启（liveness 误判），
# 或者依赖挂了还继续往里导流量（readiness 误判）。拆开之后：
#
#   /health/live   → liveness：进程在就 200，永不探测依赖。重启决策用它。
#   /health/ready  → readiness：依赖不可用返回 503，编排器摘除流量但不重启。
#   /health/db     → 单依赖明细：定位「到底是谁挂了」。
#   /health/redis  → 同上。
#   /health        → 兼容端点（恒 200，body 报依赖状态）：既有测试、
#                    compose healthcheck 和外部监控都依赖它的行为，不变。
#
# 全部免认证、不限流（限流只作用于 /api/v1 前缀，见 RateLimitMiddleware）。
# 探测函数是模块级函数，测试通过 monkeypatch 替换即可打桩，不必真停容器。
# ---------------------------------------------------------------------------


@app.get("/health/live")
async def health_live() -> dict:
    """Liveness：进程活着即 200。刻意不探测任何依赖。"""
    return {"status": "ok"}


@app.get("/health/ready")
async def health_ready() -> JSONResponse:
    """Readiness：依赖全部可用 200；任一不可用 503，body 给各项明细。"""
    db_up = await _check_database()
    redis_up = await _check_redis()
    body = {
        "status": "ok" if (db_up and redis_up) else "not_ready",
        "database": "up" if db_up else "down",
        "redis": "up" if redis_up else "down",
    }
    if db_up and redis_up:
        return JSONResponse(status_code=200, content=body)
    return JSONResponse(status_code=503, content=body)


@app.get("/health/db")
async def health_db() -> JSONResponse:
    """PostgreSQL 单依赖明细：可用 200，不可用 503。"""
    db_up = await _check_database()
    return JSONResponse(
        status_code=200 if db_up else 503,
        content={"database": "up" if db_up else "down"},
    )


@app.get("/health/redis")
async def health_redis() -> JSONResponse:
    """Redis 单依赖明细：可用 200，不可用 503。"""
    redis_up = await _check_redis()
    return JSONResponse(
        status_code=200 if redis_up else 503,
        content={"redis": "up" if redis_up else "down"},
    )
