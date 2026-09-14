"""TASK-046：ZSET + Lua 滑动窗口限流的测试。

分三层，对应交付物的三个部分：

1. **Lua 脚本语义**（连真实 Redis）——「删窗口外 / 统计 / 判超限 / 新增 / 设 TTL」
   这五步的行为，以及 §22 最关键的**原子性**。这一层直接调
   `check_rate_limit`，不经 HTTP。
2. **中间件契约**（连真实 Redis）——`/api/v1` 生效、`/health` 等豁免、
   已认证按 user / 未认证按 IP、429 响应格式与 `Retry-After`、
   Redis 故障时 fail-open。
3. **配额参数校验**（离线）——非法配置显式失败。

为什么不 mock Redis：本 TASK 的交付物就是「Lua 脚本在真实 Redis 上的原子性
与语义」。用假客户端测，等于把「EVAL 真的能跑」「时间取自 Redis」「ZSET 语义
如预期」这些最容易出错的点全部排除在覆盖之外——而它们恰恰是限流被击穿的
常见根因（见 DECISIONS 016）。

窗口时间相关断言尽量不依赖 `sleep`：只在「窗口过期后恢复」这一个用例里睡，
且用很短的窗口（1 秒），把测试时间控制在秒级。
"""

import asyncio
import uuid

import pytest
import pytest_asyncio
import redis.asyncio as aioredis
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.core.redis_keys import RATE_LIMIT_SCOPE_IP, RATE_LIMIT_SCOPE_USER
from app.core.redis_keys import rate_limit_key
from app.db import redis as redis_db
from app.db.session import get_db
from app.main import app
from app.services.rate_limit import check_rate_limit, enforce_rate_limit

#: 宿主映射端口（compose 中 6389:6379）。
REDIS_URL = "redis://127.0.0.1:6389/0"

#: 开发库在宿主 5433（`.env` 的 localhost:5432 是另一台 PostgreSQL）。
#: 认证类用例只有拿到**真实**数据库才能验证「有效 Token + 不存在的用户 = 401」，
#: 否则会在连接阶段就抛错，掩盖真正的中间件行为。
TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@127.0.0.1:5433/taskflow"

_engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
_SessionFactory = async_sessionmaker(_engine, expire_on_commit=False)


async def _override_get_db():
    async with _SessionFactory() as session:
        yield session

#: 本次运行的唯一前缀，保证并发跑多份测试不互相干扰，且便于精确清理。
RUN_TOKEN = uuid.uuid4().hex[:10]


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest_asyncio.fixture
async def redis_client():
    """指向宿主 Redis 的真实异步客户端；不可达则 skip。"""
    client = aioredis.Redis.from_url(REDIS_URL, decode_responses=True)
    try:
        await client.ping()
    except Exception as exc:  # pragma: no cover - 环境缺失时的提示
        await client.aclose()
        pytest.skip(f"Redis not reachable at {REDIS_URL}: {exc}")
    yield client
    await client.aclose()


@pytest_asyncio.fixture
async def rl_key(redis_client):
    """一个本次测试独占的限流键；用完即删。"""
    key = rate_limit_key("ip", f"test-{RUN_TOKEN}-{uuid.uuid4().hex[:8]}")
    yield key
    await redis_client.delete(key)


# ===========================================================================
# 1. Lua 脚本语义（真实 Redis）
# ===========================================================================


async def test_allows_up_to_limit_then_rejects(redis_client, rl_key):
    """窗口内允许恰好 ``limit`` 次，第 ``limit+1`` 次起拒绝（§22 核心行为）。"""
    limit = 5
    results = []
    for _ in range(limit + 3):
        results.append(
            await check_rate_limit(
                redis_client, rl_key, limit=limit, window_seconds=60, member=uuid.uuid4().hex
            )
        )
    assert [r.allowed for r in results] == [True] * limit + [False] * 3
    # current 在额度内递增，超限后停在 limit（不因被拒而虚增）
    assert [r.current for r in results] == [1, 2, 3, 4, 5, 5, 5, 5]


async def test_rejected_requests_are_not_recorded(redis_client, rl_key):
    """被拒的请求**不写入** ZSET。

    若写入了，攻击者持续打请求会让 ZSET 不断增长、且窗口永远滚动不过去
    （每分钟都有新成员），等于把自己永久锁死——同时 ZSET 也无界膨胀。
    """
    await check_rate_limit(redis_client, rl_key, limit=2, window_seconds=60, member="m1")
    await check_rate_limit(redis_client, rl_key, limit=2, window_seconds=60, member="m2")
    for i in range(10):
        r = await check_rate_limit(
            redis_client, rl_key, limit=2, window_seconds=60, member=f"rejected{i}"
        )
        assert r.allowed is False
    assert await redis_client.zcard(rl_key) == 2


async def test_ttl_is_set_and_bounded_by_window(redis_client, rl_key):
    """§22 第 5 步：设置过期时间，且不超过窗口长度。"""
    await check_rate_limit(redis_client, rl_key, limit=10, window_seconds=30, member="m")
    ttl_ms = await redis_client.pttl(rl_key)
    assert 0 < ttl_ms <= 30_000


async def test_expired_entries_leave_the_window(redis_client, rl_key):
    """窗口滑过之后旧请求不再计数（§22「删除窗口外数据」+「窗口恢复后允许请求」）。"""
    # 1 秒窗口，限 2 次
    assert (await check_rate_limit(redis_client, rl_key, limit=2, window_seconds=1, member="a")).allowed
    assert (await check_rate_limit(redis_client, rl_key, limit=2, window_seconds=1, member="b")).allowed
    assert not (await check_rate_limit(redis_client, rl_key, limit=2, window_seconds=1, member="c")).allowed

    await asyncio.sleep(1.1)  # 跨过一个完整窗口

    after = await check_rate_limit(redis_client, rl_key, limit=2, window_seconds=1, member="d")
    assert after.allowed is True, "窗口滑过后应恢复额度"
    # 旧成员已被 ZREMRANGEBYSCORE 清掉
    assert await redis_client.zcard(rl_key) == 1


async def test_oldest_entry_governs_retry_after(redis_client, rl_key):
    """``Retry-After`` 由窗口内**最早**的请求推算——它最先离开窗口。"""
    await check_rate_limit(redis_client, rl_key, limit=1, window_seconds=30, member="only")
    r = await check_rate_limit(redis_client, rl_key, limit=1, window_seconds=30, member="next")
    assert r.allowed is False
    assert 0 < r.retry_after <= 30


async def test_member_uniqueness_required_for_accurate_counting(redis_client, rl_key):
    """member 必须唯一，否则 ZSET 折叠成员导致计数偏低。

    这是把「并发必须传唯一 member」这条隐式约束显式钉住：若将来有人图省事
    用固定字符串（如 IP）作 member，同毫秒的并发请求会被折叠成一个，限流被击穿。
    """
    for _ in range(3):
        await check_rate_limit(redis_client, rl_key, limit=10, window_seconds=60, member="same")
    assert await redis_client.zcard(rl_key) == 1  # 三次请求折叠成一个成员
    # 而唯一 member 会各自计数
    key2 = rl_key + ":uniq"
    try:
        for _ in range(3):
            await check_rate_limit(redis_client, key2, limit=10, window_seconds=60, member=uuid.uuid4().hex)
        assert await redis_client.zcard(key2) == 3
    finally:
        await redis_client.delete(key2)


async def test_concurrent_requests_do_not_breach_limit(redis_client, rl_key):
    """**原子性**（§22 明确要求）：并发下放行数恰好等于额度，不多不少。

    这正是必须用 Lua 的原因：若「读计数 → 判断 → 写入」拆成多条命令，
    并发的 20 个请求可能都读到「未超限」而全部放行。Lua 在 Redis 内单线程
    执行，判断与写入之间没有竞态。
    """
    limit = 5
    results = await asyncio.gather(
        *[
            check_rate_limit(
                redis_client, rl_key, limit=limit, window_seconds=60, member=uuid.uuid4().hex
            )
            for _ in range(20)
        ]
    )
    allowed = sum(1 for r in results if r.allowed)
    assert allowed == limit, f"并发下放行 {allowed} 次，应为 {limit} 次"
    assert await redis_client.zcard(rl_key) == limit


async def test_rejects_invalid_parameters(redis_client, rl_key):
    with pytest.raises(ValueError):
        await check_rate_limit(redis_client, rl_key, limit=0, window_seconds=60, member="m")
    with pytest.raises(ValueError):
        await check_rate_limit(redis_client, rl_key, limit=10, window_seconds=0, member="m")


async def test_enforce_raises_only_when_rejected(redis_client, rl_key):
    """``enforce_rate_limit`` 把判定翻译成 429，放行时什么都不做。"""
    from app.core.exceptions import RateLimitExceededError

    await check_rate_limit(redis_client, rl_key, limit=1, window_seconds=60, member="a")
    rejected = await check_rate_limit(redis_client, rl_key, limit=1, window_seconds=60, member="b")
    with pytest.raises(RateLimitExceededError) as exc_info:
        enforce_rate_limit(rejected)
    assert exc_info.value.status_code == 429
    assert exc_info.value.headers is not None
    assert int(exc_info.value.headers["Retry-After"]) >= 1

    ok = await check_rate_limit(redis_client, rl_key, limit=100, window_seconds=60, member="c")
    enforce_rate_limit(ok)  # 不抛


# ===========================================================================
# 2. 中间件契约（真实 Redis）
# ===========================================================================


def _isolated_transport() -> tuple[ASGITransport, str]:
    """每个用例一个**独占的客户端 IP**，因此 IP 维度的限流键互不干扰。

    这是关键的测试隔离手段：中间件按 `request.client.host` 取 IP 维度标识，
    而 `ASGITransport` 默认所有用例都是 `127.0.0.1` —— 那样前一个用例消耗的
    额度会泄漏到后一个用例，产生「莫名其妙先到 429」的假失败（本文件首轮
    开发时就踩到过）。

    返回 ``(transport, ip)``，IP 供清理该维度的 Redis 键使用。
    """
    ip = f"10.99.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}"
    return ASGITransport(app=app, client=(ip, 0)), ip


@pytest_asyncio.fixture
async def isolated_client():
    """带独占 IP 的客户端；用完清理该 IP 的限流键。

    同时把 `get_db` 指向真实开发库：认证类用例需要走到「查用户」这一步才能
    观察到正确的 401，而不是在错误的端口上连接失败。
    """
    original = redis_db._client
    redis_db._client = aioredis.Redis.from_url(REDIS_URL, decode_responses=True)
    app.dependency_overrides[get_db] = _override_get_db
    transport, ip = _isolated_transport()
    try:
        async with AsyncClient(transport=transport, base_url="http://testserver") as c:
            yield c, ip
    finally:
        app.dependency_overrides.pop(get_db, None)
        await redis_db._client.delete(rate_limit_key(RATE_LIMIT_SCOPE_IP, ip))
        await redis_db._client.aclose()
        redis_db._client = original


@pytest_asyncio.fixture(autouse=True)
async def _reset_settings_cache():
    """配置项在测试里被 monkeypatch 后，清掉 lru_cache 以免污染后续用例。"""
    yield
    get_settings.cache_clear()


async def test_non_api_paths_are_exempt(isolated_client, monkeypatch):
    """/health 不限流——否则编排器探针会消耗额度甚至被拒。"""
    client, _ = isolated_client
    settings = get_settings()
    monkeypatch.setattr(settings, "rate_limit_requests", 1)
    monkeypatch.setattr(settings, "rate_limit_window_seconds", 60)

    for _ in range(5):
        r = await client.get("/health")
        assert r.status_code == 200


async def test_api_is_rate_limited(isolated_client, monkeypatch):
    """`/api/v1` 超限返回 429（§22）。"""
    client, _ = isolated_client
    settings = get_settings()
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_requests", 2)
    monkeypatch.setattr(settings, "rate_limit_window_seconds", 60)

    # 用未认证请求避免建库造数：401 也会经过中间件（限流先于认证）
    codes = []
    for _ in range(4):
        r = await client.get("/api/v1/users/me")
        codes.append(r.status_code)
    assert codes[:2] == [401, 401], "前两次额度内：应到达认证层得到 401"
    assert codes[2:] == [429, 429], "超出额度：应被限流拦下得到 429"


async def test_429_body_and_headers_follow_project_contract(isolated_client, monkeypatch):
    """429 响应体用项目统一错误信封（§26），并带 Retry-After。"""
    client, _ = isolated_client
    settings = get_settings()
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_requests", 1)
    monkeypatch.setattr(settings, "rate_limit_window_seconds", 60)

    await client.get("/api/v1/users/me")
    r = await client.get("/api/v1/users/me")
    assert r.status_code == 429
    body = r.json()
    assert set(body.keys()) == {"detail"}, body
    assert "Rate limit exceeded" in body["detail"]
    assert r.headers.get("Retry-After") is not None
    assert int(r.headers["Retry-After"]) >= 1


async def test_successful_response_reports_quota(isolated_client, monkeypatch):
    """放行的响应带配额头，客户端可据此自我调节。"""
    client, _ = isolated_client
    settings = get_settings()
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_requests", 10)
    monkeypatch.setattr(settings, "rate_limit_window_seconds", 60)

    r = await client.get("/api/v1/users/me")
    assert r.status_code == 401
    assert r.headers["X-RateLimit-Limit"] == "10"
    assert r.headers["X-RateLimit-Remaining"] == "9"


async def test_authenticated_requests_are_limited_per_user_not_ip(
    isolated_client, monkeypatch
):
    """已认证请求按 **user** 维度计数，而非 IP（§22「IP / User」两层）。

    否则同一 NAT 后的两个用户会互相挤兑额度；反之，一个用户换 IP 就能绕过限制。
    """
    client, ip = isolated_client
    settings = get_settings()
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_requests", 1)
    monkeypatch.setattr(settings, "rate_limit_window_seconds", 60)

    from app.core.security import create_access_token

    # 用一个**不存在**的 user id：中间件只解 `sub` 拿区分键，不查库。
    # 第一个请求到达业务层得到 401（用户不存在），第二个请求被 user 维度拦下。
    user_id = uuid.uuid4().int % 1_000_000 + 10_000_000
    headers = {"Authorization": f"Bearer {create_access_token(user_id)}"}

    r1 = await client.get("/api/v1/users/me", headers=headers)
    assert r1.status_code != 429, "第一次应在额度内"
    r2 = await client.get("/api/v1/users/me", headers=headers)
    assert r2.status_code == 429, "同一 user 第二次应超限"

    key = rate_limit_key(RATE_LIMIT_SCOPE_USER, user_id)
    try:
        assert await redis_db._client.exists(key) == 1, "应存在 user 维度的键"
    finally:
        await redis_db._client.delete(key)

    # IP 维度未被这个 user 消耗（未认证请求仍能到达业务层）
    anon = await client.get("/api/v1/users/me")
    assert anon.status_code != 429, "IP 维度额度不应被该 user 消耗"


async def test_invalid_token_falls_back_to_ip_scope(isolated_client, monkeypatch):
    """非法 Token 退化为 IP 维度，而不是报错或完全放行。"""
    client, _ = isolated_client
    settings = get_settings()
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_requests", 1)
    monkeypatch.setattr(settings, "rate_limit_window_seconds", 60)

    headers = {"Authorization": "Bearer not-a-real-token"}
    r1 = await client.get("/api/v1/users/me", headers=headers)
    r2 = await client.get("/api/v1/users/me", headers=headers)
    assert r1.status_code == 401, "认证层应给出 401（限流不改变认证语义）"
    assert r2.status_code == 429, "非法 Token 仍应按 IP 维度受限"


async def test_disabled_flag_bypasses_limit(isolated_client, monkeypatch):
    """`rate_limit_enabled=False` 时完全不限流（便于本地调试/压测）。"""
    client, _ = isolated_client
    settings = get_settings()
    monkeypatch.setattr(settings, "rate_limit_enabled", False)
    monkeypatch.setattr(settings, "rate_limit_requests", 1)

    for _ in range(5):
        r = await client.get("/api/v1/users/me")
        assert r.status_code == 401


async def test_redis_failure_fails_open(isolated_client, monkeypatch):
    """Redis 故障时放行（fail-open），不把限流变成新的单点故障。

    构造方式：把 `check_rate_limit` 换成必抛的函数，模拟 Redis 不可用。
    """
    client, _ = isolated_client
    settings = get_settings()
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_requests", 1)

    import app.core.middleware as mw

    async def _boom(*args, **kwargs):
        raise ConnectionError("redis is down")

    monkeypatch.setattr(mw, "check_rate_limit", _boom)

    for _ in range(5):
        r = await client.get("/api/v1/users/me")
        assert r.status_code == 401, "Redis 故障时不应返回 429，而应放行到业务层"


async def test_ip_and_user_scopes_do_not_share_quota(isolated_client, monkeypatch):
    """IP 与 user 是两把独立的键，互不消耗（§22 两层维度的隔离性）。"""
    client, _ = isolated_client
    settings = get_settings()
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_requests", 1)
    monkeypatch.setattr(settings, "rate_limit_window_seconds", 60)

    from app.core.security import create_access_token

    user_id = uuid.uuid4().int % 1_000_000 + 20_000_000
    headers = {"Authorization": f"Bearer {create_access_token(user_id)}"}
    try:
        assert (await client.get("/api/v1/users/me", headers=headers)).status_code != 429
        # 该 user 已用尽额度；同一 IP 的匿名请求走 IP 键，仍有额度
        anon = await client.get("/api/v1/users/me")
        assert anon.status_code != 429
    finally:
        await redis_db._client.delete(rate_limit_key(RATE_LIMIT_SCOPE_USER, user_id))


# ===========================================================================
# 3. 配额配置与延迟上界（离线）
# ===========================================================================


def test_default_settings_expose_rate_limit_config():
    """限流配置有可用的默认值（§22 未给数值，采用可覆盖的默认，见 DECISIONS 015）。"""
    get_settings.cache_clear()
    s = get_settings()
    assert s.rate_limit_requests > 0
    assert s.rate_limit_window_seconds > 0
    assert isinstance(s.rate_limit_enabled, bool)
    get_settings.cache_clear()


def test_redis_client_has_socket_timeouts():
    """Redis 客户端必须设置 socket 超时（DECISIONS 019）。

    这是本 TASK 期间由测试暴露的真实缺陷：`.env` 曾指向一个需要 AUTH 的
    Redis，客户端不带密码 → NOAUTH → 默认重试直到宽松的默认超时，实测单次
    PING 失败要 5 秒。限流对**每个** `/api/v1` 请求都访问 Redis，于是
    「每请求 +5s」被乘到全站，全量测试从 5 分钟劣化到卡死。

    没有这个超时，fail-open 就退化为「让所有请求变慢」。
    """
    client = redis_db.get_redis_client()
    kwargs = client.connection_pool.connection_kwargs
    assert kwargs.get("socket_timeout") is not None, "缺少 socket_timeout"
    assert kwargs.get("socket_connect_timeout") is not None, (
        "缺少 socket_connect_timeout"
    )


def test_middleware_declares_call_timeout_bound():
    """中间件必须声明单次限流调用的延迟上界（DECISIONS 019 的第二层保险）。"""
    from app.core import middleware as mw

    assert isinstance(mw.RATE_LIMIT_CALL_TIMEOUT_SECONDS, (int, float))
    assert 0 < mw.RATE_LIMIT_CALL_TIMEOUT_SECONDS <= 5, (
        "上界过大等于没有上界；限流的价值远小于让每个请求慢数秒的代价"
    )


async def test_unreachable_redis_fails_open_within_bound(monkeypatch):
    """Redis 不可达时：放行，且单请求延迟有上界（不是无限等待）。

    与 `test_redis_failure_fails_open` 的区别：那个用例测「抛错后放行」的逻辑
    分支，这个用例连**真实**不可达地址，测「延迟上界」确实起作用。
    """
    import time

    settings = get_settings()
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_requests", 1)

    # 指向一个没有服务监听的地址（连接被拒 → 毫秒级失败，仍走 fail-open）
    bad = aioredis.Redis.from_url(
        "redis://127.0.0.1:1/0",
        decode_responses=True,
        socket_connect_timeout=0.3,
        socket_timeout=0.3,
    )
    original = redis_db._client
    redis_db._client = bad
    app.dependency_overrides[get_db] = _override_get_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as c:
            start = time.monotonic()
            r = await c.get("/api/v1/users/me")
            elapsed = time.monotonic() - start
        assert r.status_code == 401, "Redis 不可达应 fail-open 到业务层，而非 429/500"
        assert elapsed < 5, f"单请求耗时 {elapsed:.2f}s，超出可接受上界"
    finally:
        app.dependency_overrides.pop(get_db, None)
        await bad.aclose()
        redis_db._client = original
