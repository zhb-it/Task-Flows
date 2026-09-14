"""滑动窗口限流（TASK-046，项目文档 §22）。

## 为什么用 ZSET + Lua

§22 指定 `IP / User → Redis ZSET → 滑动时间窗口 → 判断请求数量 → 超限 429`。

固定窗口（`INCR` + `EXPIRE`）有边界突刺问题：若限 60 次/分钟，客户端可以在
第 59 秒发 60 次、第 61 秒再发 60 次，两秒内 120 次全部通过。滑动窗口用
「每个请求的时间戳」判断「过去 N 秒内有多少请求」，从根本上没有这个边界。

ZSET 天然适合：`score` 存请求时刻（毫秒），`member` 是本次请求的唯一标识。
统计窗口内请求数 = 数 `score > now - window` 的成员。用完的旧成员由脚本删除，
避免 ZSET 无限增长。

## 为什么必须用 Lua

§22 明确要求「必须保证 Redis 操作原子性」。这五步
（删除窗口外 → 统计 → 判超限 → 新增 → 设过期）如果拆成多条 Redis 命令，
两个并发请求会交错执行：都读到「窗口内 59 次」→ 都判断「没超限」→ 都写入，
于是限流被击穿（race condition）。Lua 脚本在 Redis 中**单线程原子执行**，
中间不会被其它命令插入，因此判断与写入之间不存在竞态。

## 时间来源

脚本内用 `redis.call('TIME')` 取 Redis 服务器时间，而非客户端时间：

- 多实例部署时各客户端时钟可能不一致，用客户端时间会让同一用户在不同实例
  上落到不同的窗口位置，限流形同虚设；
- 客户端时间可被配置错误影响，而 Redis 时间是唯一的权威。
"""

from dataclasses import dataclass

from redis.asyncio import Redis

from app.core.exceptions import RateLimitExceededError

# ---------------------------------------------------------------------------
# Lua 脚本
# ---------------------------------------------------------------------------

#: 滑动窗口限流脚本。
#:
#: KEYS[1] 限流 ZSET 的 key（由 ``app.core.redis_keys.rate_limit_key`` 构造）
#: ARGV[1] 窗口长度（毫秒）
#: ARGV[2] 窗口内允许的最大请求数
#: ARGV[3] 本次请求的唯一标识（ZSET member）
#:
#: 返回 ``{allowed, current_count, retry_after_seconds}``：
#: - ``allowed``      1 放行 / 0 拒绝
#: - ``current_count`` 判定时的窗口内请求数（用于观测与错误文案）
#: - ``retry_after``  建议重试等待秒数（仅在拒绝时有意义）
#:
#: 注意 ``redis.call('TIME')`` 返回 ``{秒, 微秒}`` 两个字符串，必须显式转数字，
#: 否则 Lua 中的算术会隐式转换——显式写出来更清晰，也避免精度意外。
_RATE_LIMIT_LUA = """
local key = KEYS[1]
local window_ms = tonumber(ARGV[1])
local max_requests = tonumber(ARGV[2])
local member = ARGV[3]

-- 用 Redis 服务器时间，避免多实例客户端时钟漂移
local now_parts = redis.call('TIME')
local now_ms = tonumber(now_parts[1]) * 1000 + math.floor(tonumber(now_parts[2]) / 1000)
local window_start = now_ms - window_ms

-- 1) 删除窗口外的数据（滑动：旧请求不再计入）
redis.call('ZREMRANGEBYSCORE', key, 0, window_start)

-- 2) 统计当前窗口内的请求数
local current = redis.call('ZCARD', key)

-- 3) 判断是否超限：超限则**不写入**本次请求
if current >= max_requests then
    -- 最早的那个成员离开窗口时才会腾出额度，据此算出 Retry-After
    local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
    local retry_after = 0
    if oldest[2] then
        local oldest_ms = tonumber(oldest[2])
        retry_after = math.ceil((oldest_ms + window_ms - now_ms) / 1000)
    end
    return {0, current, retry_after}
end

-- 4) 记录本次请求
redis.call('ZADD', key, now_ms, member)

-- 5) 设置过期时间：窗口内不再有新请求时键自动回收
redis.call('PEXPIRE', key, window_ms)

return {1, current + 1, 0}
"""


@dataclass(frozen=True)
class RateLimitResult:
    """一次限流判定的结果。"""

    allowed: bool
    #: 判定时的窗口内请求数（放行时含本次请求）。
    current: int
    #: 允许的最大请求数（用于错误文案与观测）。
    limit: int
    #: 拒绝时建议的等待秒数；放行时为 0。
    retry_after: int


async def check_rate_limit(
    redis: Redis,
    key: str,
    *,
    limit: int,
    window_seconds: int,
    member: str,
) -> RateLimitResult:
    """在 ``key`` 对应的滑动窗口内判定是否放行，并原子地记录本次请求。

    Args:
        redis: 共享 Redis 客户端（``app.db.redis.get_redis_client``）。
        key: 限流键（``rate_limit_key(scope, identifier)``）。
        limit: 窗口内允许的最大请求数。
        window_seconds: 窗口长度（秒）。
        member: 本次请求的唯一标识。必须唯一，否则 ZSET 会把两次请求折叠成
            一个成员（``ZADD`` 更新已存在成员的 score），导致计数偏低。

    Returns:
        ``RateLimitResult``：``allowed=False`` 时调用方应返回 429。
    """
    if limit <= 0:
        raise ValueError("limit must be positive")
    if window_seconds <= 0:
        raise ValueError("window_seconds must be positive")

    raw = await redis.eval(
        _RATE_LIMIT_LUA,
        1,
        key,
        str(window_seconds * 1000),
        str(limit),
        member,
    )
    allowed_flag, current, retry_after = int(raw[0]), int(raw[1]), int(raw[2])
    return RateLimitResult(
        allowed=bool(allowed_flag),
        current=current,
        limit=limit,
        retry_after=retry_after if not allowed_flag else 0,
    )


def enforce_rate_limit(result: RateLimitResult) -> None:
    """把被拒绝的判定结果转成 ``RateLimitExceededError``（429）。

    与 ``check_rate_limit`` 分开，是为了让「判定」与「怎么表达这个判定」各自
    独立：Service 层关心前者，HTTP 层关心后者（项目规则 §4 分层）。
    """
    if result.allowed:
        return
    raise RateLimitExceededError(
        f"Rate limit exceeded: {result.limit} requests per window",
        retry_after=result.retry_after,
    )
