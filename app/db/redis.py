"""Async Redis connection layer（TASK-045）.

开发文档 §21 列出 Redis 的五项用途——JWT 黑名单、API 限流、Celery Broker、
Celery Backend、后续缓存。本模块提供**唯一的连接入口**：所有需要 Redis 的
代码都通过这里拿客户端，而不是各自 ``Redis.from_url``。

设计取舍（与 ``app/db/session.py`` 保持一致）：

1. **import 时不建立连接**：Redis 客户端是懒连接的（``redis.asyncio`` 在首次
   命令时才握手），因此本模块可以在没有 Redis 的环境里被 import——测试与
   离线工具因此不必依赖运行中的 Redis。
2. **连接池单例**：``redis.asyncio.Redis`` 内部持有 ``ConnectionPool``，进程内
   复用一个实例即可复用连接。每次请求新建 client（哪怕指向同一 URL）都会
   新建连接池，是常见的资源泄漏来源。
3. **不在本层做业务判断**：这里只负责「给我一个可用的客户端」。限流、黑名单
   等语义属于调用方（TASK-046 及后续）。

为什么不用 ``app.state`` 或全局变量？FastAPI 依赖注入（``Depends(get_redis)``）
让调用方声明依赖、测试可覆盖（``app.dependency_overrides``），与 ``get_db``
的既有惯例一致。
"""

from collections.abc import AsyncGenerator

from redis import Redis as SyncRedis
from redis.asyncio import Redis

from app.core.config import get_settings

settings = get_settings()

#: 进程内共享的客户端。``None`` 表示尚未创建（或已关闭）——见 ``get_redis_client``。
_client: Redis | None = None

#: Celery worker（同步上下文）专用的共享客户端，见 ``get_sync_redis_client``。
_sync_client: SyncRedis | None = None

#: Redis 调用的硬超时（秒）。
#:
#: 为什么必须显式设置：``redis.asyncio`` 的默认 socket 超时很宽松，而 Redis
#: 不可达时（TCP 连上但不应答、或跨网络黑洞）每个命令会**阻塞到默认超时**。
#: 限流中间件对每个请求都要访问 Redis，若不设超时，Redis 一挂就会让**所有
#: API 请求**各自多等数秒——远超限流本身的价值。这是 TASK-046 期间由测试
#: 暴露的真实缺陷（单个用例因此从 <1s 涨到 27s）。
#:
#: 取值理由：健康的 Redis 在同一机房/本机应 <10ms；1 秒给足余量，又能把故障
#: 时的单请求额外延迟封顶在 1 秒。配合中间件的 fail-open，Redis 故障表现为
#:「限流暂时失效 + 每请求最多 1 秒额外延迟」，而不是「服务不可用」。
REDIS_SOCKET_TIMEOUT_SECONDS = 1.0


def get_redis_client() -> Redis:
    """返回进程内共享的 Redis 客户端（惰性创建）。

    注意：返回的是**共享实例**，调用方**不得**关闭它（否则会影响其它调用方）。
    进程退出时由 ``close_redis`` 统一释放。
    """
    global _client
    if _client is None:
        _client = Redis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            socket_timeout=REDIS_SOCKET_TIMEOUT_SECONDS,
            socket_connect_timeout=REDIS_SOCKET_TIMEOUT_SECONDS,
        )
    return _client


async def get_redis() -> AsyncGenerator[Redis, None]:
    """FastAPI 依赖：yield 共享客户端，请求结束后**不关闭**它。

    与 ``get_db`` 的差异是刻意的：数据库 Session 是每请求一份的有状态工作单元，
    必须关闭；而 Redis 客户端是无状态的连接池句柄，应当跨请求复用。
    """
    yield get_redis_client()


def get_sync_redis_client() -> SyncRedis:
    """返回 Celery worker **同步上下文**专用的共享客户端（惰性创建）。

    为什么需要第二个客户端：``get_redis_client`` 返回 ``redis.asyncio`` 客户端，
    每个命令返回协程、必须 await；而 Celery 任务运行在 prefork 池的**同步**
    上下文里，没有事件循环可用（TASK-049 通知任务的幂等标记需要 Redis）。
    与其把 async 客户端硬凑进同步代码，不如在连接层提供同构的同步入口——
    同一 URL、同一超时纪律（见 ``REDIS_SOCKET_TIMEOUT_SECONDS``，TASK-046
    的教训对 worker 同样适用）。

    注意：与 async 客户端一样是**共享实例**，调用方不得关闭它。
    """
    global _sync_client
    if _sync_client is None:
        _sync_client = SyncRedis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            socket_timeout=REDIS_SOCKET_TIMEOUT_SECONDS,
            socket_connect_timeout=REDIS_SOCKET_TIMEOUT_SECONDS,
        )
    return _sync_client


async def close_redis() -> None:
    """关闭共享客户端并释放连接池（应用 shutdown / worker 退出时调用）。

    幂等：重复调用安全。关闭后下一次 ``get_redis_client`` /
    ``get_sync_redis_client`` 会重新创建。
    """
    global _client, _sync_client
    if _client is not None:
        await _client.aclose()
        _client = None
    if _sync_client is not None:
        _sync_client.close()
        _sync_client = None


async def reset_redis() -> None:
    """丢弃当前客户端引用而不关闭连接池（测试用）。

    存在的理由：测试可能用 monkeypatch 把 ``_client`` 换成指向临时库的实例，
    但**不应**关闭被替换掉的那个（它不属于本测试）。``reset_redis`` 只清引用，
    让下一次 ``get_redis_client`` 重新按配置创建。
    """
    global _client
    _client = None
