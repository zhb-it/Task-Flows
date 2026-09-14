"""限流中间件（TASK-046，项目文档 §22）。

## 为什么是中间件而不是路由依赖

§22 要求全站按 `IP / User` 两个维度限流。若做成路由依赖，每个端点都要显式
声明、漏一个就出现无保护的入口；而中间件对所有 `/api/v1` 请求自动生效，不会
因为新增端点忘记加依赖而失效。这也符合 §22 图示「请求进入 → 判定 → 429」
的位置（在路由分发之前）。

## 身份判定为什么不查库

中间件在路由层之前运行，此处的数据库 Session 尚未建立（`get_db` 是端点级
依赖）。若在此查库，则每个请求都会多一次数据库往返，且未认证请求也要连着
数据库——这与「限流是为了保护数据库」的初衷相反。

因此这里只解 JWT 的 `sub`：Token 的**签名与过期**由 `decode_access_token`
校验（这是纯计算，无 IO）。至于「该用户是否仍存在/是否被禁用」，本来就由
端点内的 `get_current_user` 负责——限流不需要这个结论，它只需要一个**稳定的
区分键**。解不出来（未认证/Token 非法）就退化为按 IP 限流，这恰好是 §22
「IP / User」两层维度的自然含义。

## 失败开放（fail-open）与延迟上界

Redis 不可用时**放行**请求而不是全部 429。理由：限流是保护性措施，不应成为
新的单点故障——Redis 一挂就让整个 API 不可用，比「短时限流失效」的代价大得多。
Redis 故障会由 `/health` 暴露，属于可观测的已知状态。

fail-open 还必须**有延迟上界**：限流对每个请求都要访问 Redis，若 Redis 处于
「TCP 连得上但不应答」的状态，每个请求都会阻塞到 socket 超时——比拒绝请求更糟
（请求变慢而非快速失败），且会耗尽 worker。因此这里在客户端 socket 超时
（`app.db.redis`）之外**再加一层 `asyncio.timeout`**，双保险封顶单请求的额外
延迟。Redis 完全没监听时通常是「连接被拒」（毫秒级）；「连接超时」才是需要
这一层兜底的病态情形。本缺陷由 TASK-046 的测试发现（单个用例从 <1s 涨到 27s），
详见 DECISIONS 019。
"""

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import get_settings
from app.core.exceptions import RateLimitExceededError
from app.core.redis_keys import RATE_LIMIT_SCOPE_IP, RATE_LIMIT_SCOPE_USER
from app.core.redis_keys import rate_limit_key
from app.core.security import decode_access_token
from app.db.redis import get_redis_client
from app.services.rate_limit import check_rate_limit

logger = logging.getLogger(__name__)

#: 只有业务 API 受限；`/health`、`/`、`/docs` 等运维/文档端点不限流
#: —— 否则编排器的健康探针或开发者打开文档页就会消耗额度。
RATE_LIMITED_PREFIX = "/api/v1"

#: 单次限流判定的延迟上界（秒）。正常情况下这是一次本地 Redis 往返（<10ms）；
#: 该上界只在 Redis 处于病态状态时生效，保证请求仍能 fail-open 地快速通过。
RATE_LIMIT_CALL_TIMEOUT_SECONDS = 2.0


def _client_ip(request: Request) -> str:
    """取客户端 IP 作为限流标识。

    这里**只**用 `request.client.host`（TCP 连接的来源地址），不解析
    `X-Forwarded-For`：该头可被客户端任意伪造，用它做限流等于让攻击者
    随意切换身份绕过限制。生产环境经 Nginx 反代时，应由 Nginx 覆盖
    （而非追加）真实 IP，届时再按部署拓扑决定是否信任该头——那是部署层
    的信任边界问题，属于 TASK-060 的范围。
    """
    if request.client is None:  # 极少数场景（如 ASGI 直连）没有 client
        return "unknown"
    return request.client.host


def _rate_limit_identity(request: Request) -> tuple[str, str]:
    """返回 ``(scope, identifier)``：已认证按 user，否则按 IP（§22）。"""
    authorization = request.headers.get("Authorization", "")
    if authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
        if token:
            try:
                payload = decode_access_token(token)
                subject = payload.get("sub")
                if subject is not None:
                    return RATE_LIMIT_SCOPE_USER, str(subject)
            except Exception:
                # Token 非法/过期：这不是限流层要报告的错误（那是认证层的 401）。
                # 这里只关心「拿不到可信身份」，退化为 IP 维度即可。
                pass
    return RATE_LIMIT_SCOPE_IP, _client_ip(request)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """对 `/api/v1` 施加滑动窗口限流（§22）。"""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        settings = get_settings()
        if not settings.rate_limit_enabled:
            return await call_next(request)
        if not request.url.path.startswith(RATE_LIMITED_PREFIX):
            return await call_next(request)

        scope, identifier = _rate_limit_identity(request)
        key = rate_limit_key(scope, identifier)
        # member 必须唯一：同一毫秒内的两个并发请求若共用 member，ZADD 会把
        # 它们折叠成一个成员（更新 score 而非新增），使计数偏低而被击穿。
        member = f"{uuid.uuid4().hex}"

        try:
            # 外层 asyncio.timeout 是 socket 超时之外的兜底：即使客户端配置被
            # 改坏（或将来换成不设超时的实现），单请求的额外延迟依然有上界。
            async with asyncio.timeout(RATE_LIMIT_CALL_TIMEOUT_SECONDS):
                result = await check_rate_limit(
                    get_redis_client(),
                    key,
                    limit=settings.rate_limit_requests,
                    window_seconds=settings.rate_limit_window_seconds,
                    member=member,
                )
        except Exception:
            # fail-open：Redis 故障不应让 API 整体不可用（见模块 docstring）。
            logger.warning("rate limit check failed, allowing request", exc_info=True)
            return await call_next(request)

        if not result.allowed:
            # 复用统一异常类型，使 429 的信封与 `Retry-After` 只有一处定义
            # （`app.core.exceptions`）——中间件直接把它渲染成响应，是因为
            # 此时尚未进入路由，异常处理器不会介入。
            exc = RateLimitExceededError(
                f"Rate limit exceeded: {result.limit} requests per "
                f"{settings.rate_limit_window_seconds} seconds",
                retry_after=result.retry_after,
            )
            return JSONResponse(
                status_code=exc.status_code,
                content={"detail": exc.detail},
                headers=exc.headers,
            )

        response = await call_next(request)
        # 让客户端（与测试）能看到配额状态，无需额外端点。
        response.headers["X-RateLimit-Limit"] = str(result.limit)
        response.headers["X-RateLimit-Remaining"] = str(
            max(0, result.limit - result.current)
        )
        return response
