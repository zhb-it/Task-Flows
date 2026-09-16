"""自定义 HTTP 中间件。

本模块含三个中间件，按**运行时的嵌套顺序**（由外到内）列出：

- ``RequestIdMiddleware``（TASK-057，项目文档 §34）——为每个请求确定
  ``request_id``：客户端透传（校验后）或服务端生成；写入 ``ContextVar`` 供
  请求内**所有**日志使用，并随响应头回传；
- ``RequestLoggingMiddleware``（TASK-056，项目文档 §33）——结构化访问日志
  （method/path/status_code/duration/user_id）；
- ``RateLimitMiddleware``（TASK-046，项目文档 §22）——滑动窗口限流。

嵌套顺序由 ``app/main.py`` 的注册顺序决定——Starlette 的 ``add_middleware``
是「后注册者更靠外」。下文按代码顺序逐个说明，每个类都注明了它在嵌套中的位置
与理由。

================================ 限流中间件 ================================

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

## IP 维度在反代之后如何保持有效（§31 / TASK-060）

IP 维度若永远取 TCP 对端地址，则接入 Nginx 之后所有匿名请求的对端都变成
Nginx，「按 IP 限流」退化为「所有匿名用户共享一份配额」——这正是 DECISIONS 018
留下的遗留约束。TASK-060 的解法是「反代覆盖写入 + 应用侧按信任网段判定」：
Nginx 用 `$remote_addr` **覆盖**写入 `X-Forwarded-For`（客户端伪造的值在到达
应用前已被替换），应用只在 `TRUST_PROXY_HEADERS=true` **且**对端落在
`TRUSTED_PROXY_IPS` 网段内时才采信它。判定逻辑集中在 `app.core.client_ip`，
本模块只负责把 `Request` 的原始信息喂给它。

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
import re
import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.client_ip import FORWARDED_FOR_HEADER, parse_trusted_proxies, resolve_client_ip
from app.core.config import get_settings
from app.core.exceptions import RateLimitExceededError
from app.core.logging_config import request_id_var, user_id_var
from app.core.metrics import IN_PROGRESS, REQUEST_COUNT, REQUEST_LATENCY, route_label
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
    """取客户端 IP 作为限流标识 / 日志字段。

    解析规则集中在 ``app.core.client_ip``（TASK-060）：默认只信 TCP 对端地址，
    仅当 ``TRUST_PROXY_HEADERS=true`` **且**对端落在 ``TRUSTED_PROXY_IPS`` 网段
    内时才采信 ``X-Forwarded-For``。之所以不无条件解析该头，是因为它可被客户端
    任意伪造——用它做身份标识等于让攻击者随手换身份绕过限流（DECISIONS 018）。

    反代侧的配合：本项目 Nginx 用 ``$remote_addr`` **覆盖**写入该头
    （``nginx/nginx.conf``），因此「客户端塞进来的值」在到达应用之前就被替换掉了。
    """
    settings = get_settings()
    peer_ip = request.client.host if request.client is not None else None
    return resolve_client_ip(
        peer_ip,
        request.headers.get(FORWARDED_FOR_HEADER),
        trust_proxy=settings.trust_proxy_headers,
        trusted_proxies=parse_trusted_proxies(settings.trusted_proxy_ips),
    )


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


# ===========================================================================
# 请求访问日志（TASK-056，§33）
# ===========================================================================
#
# §33 要求日志至少记录 path / method / status_code / duration，这四个字段只有
# 中间件拿得到（端点内看不到「本次请求的总耗时」与「最终状态码」，异常处理器
# 返回的 4xx/5xx 也不会经过端点代码）。因此访问日志用中间件实现。
#
# 三个设计点：
#
# 1. **user_id 不查库**：与限流中间件同理由——中间件在路由层之前运行，此处
#    没有 ``get_db`` Session；且「用户是谁」的权威判定仍在端点的
#    ``get_current_user``（401/403 由它负责）。这里只解 JWT 的 ``sub`` 作为
#    **日志标识**，解不出来就记 null（未认证请求）。
# 2. **写进 ContextVar**：``user_id`` 不只出现在访问日志上——请求内任何一条
#    业务日志（如 Service/任务里的 warning）都应带上它（§33）。因此中间件把
#    user_id 存进 ``user_id_var``，请求结束还原；formatter 自动读取。
#    ``request_id`` 走同一条通道，但**不由本中间件生成**——它由更外层的
#    ``RequestIdMiddleware``（TASK-057）设置，因此在本中间件写日志时已经在
#    ContextVar 里了，访问日志天然带上它。
# 3. **异常也要记**：``call_next`` 抛异常时先记一条 status_code=500 再向上抛
#    （Starlette 的 ``ServerErrorMiddleware`` 在最外层渲染 500），避免「出错
#    的那次请求恰好没有日志」——那正是最需要日志的一次。


def _user_id_from_request(request: Request) -> int | None:
    """从 ``Authorization: Bearer`` 解出用户 id（纯计算，不查库）。"""
    authorization = request.headers.get("Authorization", "")
    if not authorization.lower().startswith("bearer "):
        return None
    token = authorization[7:].strip()
    if not token:
        return None
    try:
        payload = decode_access_token(token)
    except Exception:
        # Token 非法/过期不是日志层要报告的错误（认证层会给出 401）；
        # 这里只需「拿不到可信身份」，记 null 即可。
        return None
    subject = payload.get("sub")
    try:
        return int(subject)
    except (TypeError, ValueError):
        return None


def _log_request_completed(
    request: Request, status_code: int, started: float, client_ip: str
) -> None:
    """输出一条结构化访问日志（duration 单位为毫秒）。

    ``client_ip`` 记录的是**解析后的真实客户端 IP**（见 ``_client_ip``）：反代
    之后如果只记 TCP 对端地址，日志里全是 Nginx 的地址，排查时无法区分来源。
    """
    logger.info(
        "request completed",
        extra={
            "method": request.method,
            "path": request.url.path,
            "status_code": status_code,
            # duration 用毫秒（float，保留 3 位）——比秒更易读且不丢亚毫秒信息。
            "duration": round((time.perf_counter() - started) * 1000, 3),
            "client_ip": client_ip,
        },
    )


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """为每个请求输出一条结构化访问日志（§33）。

    记录**全部路径**（含 ``/health``、``/``、``/docs``）——TASK-056 用户确认：
    编排器探针与文档页的访问同样有排查价值，日志完整性优先于「不被探针刷屏」。
    需要压缩时可把 ``LOG_REQUESTS=false`` 整体关闭。
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if not get_settings().log_requests:
            return await call_next(request)

        started = time.perf_counter()
        # 提前解析（而不是在写日志时现算）：异常路径也要记日志，先算好可避免
        # 在 except 分支里再做一次可能抛错的解析。
        client_ip = _client_ip(request)
        user_id = _user_id_from_request(request)
        token = user_id_var.set(user_id) if user_id is not None else None
        try:
            response = await call_next(request)
        except Exception:
            _log_request_completed(request, 500, started, client_ip)
            raise
        else:
            # ⚠ 必须在 finally 还原 ContextVar **之前**写日志：访问日志的
            # user_id 来自 user_id_var，若先还原再记录，每个成功请求的日志都会
            # 丢掉 user_id（§33 明确要求日志带 user_id）——此为 TASK-056 实测
            # 发现的缺陷。
            _log_request_completed(request, response.status_code, started, client_ip)
            return response
        finally:
            if token is not None:
                user_id_var.reset(token)


# ===========================================================================
# 请求 ID（TASK-057，§34）
# ===========================================================================
#
# §34：每个 HTTP 请求都要有 ``request_id``，**可由客户端传入，也可以服务端
# 生成**，且**日志中必须带**这个字段——目的是拿到用户报障时能凭一个 id 捞出
# 该次请求的全部日志。
#
# ## 为什么单独一个中间件（不塞进 RequestLoggingMiddleware）
#
# ① **与日志开关解耦**：§34 要求「每一个 HTTP 请求生成 request_id」，这是请求的
#    身份，不是日志格式的一部分。若把生成逻辑写进访问日志中间件，则
#    ``LOG_REQUESTS=false`` 时就不再生成、响应头也没了——§34 的硬要求会被一个
#    日志开关悄悄破坏。
# ② **必须最外层**：request_id 要出现在**本次请求的所有日志**上，包括限流中间件
#    的 ``warning`` 与访问日志中间件自己那条。因此它的 ContextVar 必须在任何
#    其他中间件运行之前就位 —— 在 ``app/main.py`` **最后**注册（后注册者更靠外）。
#
# 嵌套顺序（由外到内）：
#
#     RequestIdMiddleware → RequestLoggingMiddleware → RateLimitMiddleware → 路由
#
# 于是请求的流转是：最外层定 id → 访问日志拿到 id → 限流（其 warning 也带 id）
# → 路由/Service（业务日志全带 id）。
#
# ## 客户端传入值的校验（TASK-057 用户确认）
#
# 只接受 ``^[A-Za-z0-9._-]{1,64}$``，不合法就**丢弃并重新生成**，绝不原样信任：
#
# - **日志注入**：header 值里若含换行/控制字符，可直接伪造一整条日志行——把
#   ``\n`` 塞进来的请求会污染审计记录；
# - **日志膨胀/污染**：超长值（几十 KB）能把每一行日志撑爆，也让聚合器不堪重负；
# - **身份伪造**：id 是可观测性的信任锚，若客户端能随意设定，就能把自己的请求
#   伪装成别人的、或与既有 id 撞车，排查价值归零。
#
# 64 字符足够容纳 UUID(36) 与常见 traceparent 风格 id，也是业界常见的上限；
# 字母数字加 ``. _ -`` 覆盖了 UUID / ulid / ksuid / hex 等所有主流生成方式。
#
# ## 已知边界
#
# 未处理异常会冒泡到 Starlette 的 ``ServerErrorMiddleware``（它在本中间件**之外**）
# 由它渲染 500，那个响应**没有** ``X-Request-ID`` 头。这不影响 §34 的硬要求：
# 该请求的日志（访问日志中间件在向上抛之前已记 ``status_code=500``）仍然带
# request_id。

# ===========================================================================
# 指标与 5xx 统一信封（TASK-090，§1「日志与指标」/ §26 / B9）
# ===========================================================================


class MetricsErrorMiddleware(BaseHTTPMiddleware):
    """请求计数/延迟指标 + 未处理异常的统一信封（双重职责，见下）.

    嵌套位置：注册在 ``RequestIdMiddleware`` 之内、``RequestLoggingMiddleware``
    之外——必须**包住**访问日志（才能观测到限流判定的时间）又**被** request_id
    包住（异常日志才有 request_id 关联，§34）。

    ## 职责 1：指标（§1「日志与指标」）

    请求计数与延迟按 ``method + 路由模板 + status`` 打标签。路由模板在
    ``call_next`` 返回后从 ``scope["route"]`` 读取（Starlette 路由分发成功后
    写入）——必须是模板而不是原始路径，否则每个 UUID 一个标签序列，基数打爆
    监控存储（见 ``app/core/metrics`` 标签纪律）。未命中路由（404）统一落
    ``unmatched``。两条同模板不同 id 的请求因此产生**同一个**标签值——这是
    TASK-090 验收标准之一。

    ## 职责 2：未处理异常 → §26 统一信封（B9）

    此前未处理异常一路冒泡到 Starlette 的 ``ServerErrorMiddleware``，渲染出的
    500 既不是 ``{"detail": ...}`` 信封、又带框架默认 HTML（debug 时是堆栈页），
    也没有 request_id 头。在这里捕获并渲染 §26 信封：

    - **对外不含堆栈**：body 只有 ``{"detail": "Internal server error"}``，
      异常细节只进日志（``exc_info`` 全量堆栈，JSON formatter 落 ``exception``
      字段）——堆栈里的路径/版本信息是攻击者的侦察素材（§9 敏感信息）；
    - **日志带 request_id**：本中间件在 request_id ContextVar 存活期内记日志，
      关联天然成立；``ServerErrorMiddleware`` 在最外层，ContextVar 已还原，
      这是把信封放中间件而非异常处理器的决定性原因；
    - **X-Request-ID 头得以回传**：信封响应正常返回给 ``RequestIdMiddleware``，
      它会把 id 写进响应头——用户报障时手里有 id 可捞日志。

    计数必须含异常路径（status=500），否则 5xx 率这一最重要的告警信号会失真。
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        method = request.method
        in_progress = IN_PROGRESS.labels(method)
        in_progress.inc()
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            # 路由模板取不到（异常发生在路由分发中）——落 unmatched，
            # 原始路径绝不能进标签（标签纪律）。
            route = route_label(request.scope)
            REQUEST_COUNT.labels(method, route, "500").inc()
            REQUEST_LATENCY.labels(method, route).observe(
                time.perf_counter() - started
            )
            # exc_info 全量堆栈只进日志；request_id 由 ContextVar 提供。
            logger.error(
                "unhandled exception",
                exc_info=True,
                extra={"method": method, "path": request.url.path},
            )
            return JSONResponse(
                status_code=500,
                content={"detail": "Internal server error"},
            )
        finally:
            in_progress.dec()

        route = route_label(request.scope)
        status = str(response.status_code)
        REQUEST_COUNT.labels(method, route, status).inc()
        REQUEST_LATENCY.labels(method, route).observe(time.perf_counter() - started)
        return response


# ===========================================================================
# 请求 ID（TASK-057，§34）
# ===========================================================================

#: 客户端传入 / 服务端回传 request_id 的 HTTP 头名。
REQUEST_ID_HEADER = "X-Request-ID"

#: 接受的 request_id 长度上限（见上文「客户端传入值的校验」）。
_REQUEST_ID_MAX_LENGTH = 64

#: 白名单正则：仅字母数字与 ``. _ -``。``\Z`` 表示字符串末尾（拒绝尾部换行）。
_SAFE_REQUEST_ID_RE = re.compile(rf"[A-Za-z0-9._-]{{1,{_REQUEST_ID_MAX_LENGTH}}}\Z")


def resolve_request_id(request: Request) -> str:
    """确定本次请求的 ``request_id``：客户端传入（校验通过）否则服务端生成。"""
    candidate = request.headers.get(REQUEST_ID_HEADER)
    if candidate:
        candidate = candidate.strip()
        if _SAFE_REQUEST_ID_RE.fullmatch(candidate):
            return candidate
    # uuid4().hex（32 位十六进制）字符集落在白名单内，长度也远小于上限。
    return uuid.uuid4().hex


class RequestIdMiddleware(BaseHTTPMiddleware):
    """为每个请求确定 request_id 并回传响应头（§34）。

    注册在**最外层**（``app/main.py`` 中最后 add）：这样它的 ContextVar 在任何
    其他中间件运行之前就已就位，本次请求的**全部**日志（含访问日志与限流
    warning）都能带上 request_id。
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = resolve_request_id(request)
        token = request_id_var.set(request_id)
        try:
            response = await call_next(request)
        finally:
            # 请求结束必须还原，避免 id 泄漏到下一个请求（同一 worker 会复用
            # 上下文；ContextVar 不还原就会串号）。
            request_id_var.reset(token)

        # 用局部变量而非 ContextVar 读取：此时 ContextVar 已还原（TASK-056 的
        # 教训——先还原再读会拿到 null），而响应头必须回传服务端最终认定的 id，
        # 客户端才能凭它报障。客户端传入了合法值就回传它自己传的那个（链路可串联）。
        response.headers[REQUEST_ID_HEADER] = request_id
        return response
