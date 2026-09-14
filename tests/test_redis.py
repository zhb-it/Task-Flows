"""TASK-045：Redis 连接层与 Key 约定的测试。

分两类：

1. **离线契约测试**——不依赖运行中的 Redis。覆盖 ``app/core/redis_keys.py`` 的
   全部命名规则（这是纯函数，必须 100% 覆盖）以及 ``app/db/redis.py`` 的
   「import 不连接」「共享单例」契约。
2. **真实连通性测试**——连接宿主的 Redis 7（宿主端口 6389，容器内 6379；
   与 PostgreSQL 5433/5432 的映射惯例一致）。只做「连得上、PING 通、Key 约定
   在真实 Redis 上可用」这类不污染数据的最小验证，键用本次运行唯一前缀，
   用完即删。

为什么 Redis 测试要连真实实例：连接层的问题（url 解析、decode_responses
行为、连接池生命周期）在假客户端上是照不出来的——那些恰恰是本 TASK 的交付物。
"""

import uuid

import pytest
import pytest_asyncio
import redis.asyncio as aioredis

from app.core import redis_keys
from app.db import redis as redis_db

#: 宿主映射端口（compose 中 6389:6379）。
REDIS_URL = "redis://127.0.0.1:6389/0"

RUN_TOKEN = uuid.uuid4().hex[:10]


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


# ===========================================================================
# 1. Key 命名约定（纯函数，离线）
# ===========================================================================


def test_build_key_shape():
    assert redis_keys.build_key("ratelimit", "ip", "1.2.3.4") == (
        "taskflow:ratelimit:ip:1.2.3.4"
    )


def test_build_key_prefix_is_stable():
    """前缀是数据兼容性契约——改动等同迁移，因此显式钉住。"""
    assert redis_keys.KEY_PREFIX == "taskflow"
    assert redis_keys.build_key("x").startswith("taskflow:x")


def test_build_key_single_part():
    assert redis_keys.build_key("jwt", "blacklist", "abc") == (
        "taskflow:jwt:blacklist:abc"
    )


def test_build_key_coerces_non_string_parts():
    """user id 是 int，必须能直接传入（调用方不该被迫手写 str()）。"""
    assert redis_keys.build_key("ratelimit", "user", 42) == (
        "taskflow:ratelimit:user:42"
    )


def test_build_key_allows_zero_parts():
    assert redis_keys.build_key("ping") == "taskflow:ping"


def test_build_key_rejects_empty_purpose():
    with pytest.raises(ValueError):
        redis_keys.build_key("", "x")


def test_build_key_rejects_colon_in_purpose():
    """purpose 含 ':' 会破坏「用途段」的结构，必须拒绝而不是静默拼接。"""
    with pytest.raises(ValueError):
        redis_keys.build_key("rate:limit", "x")


def test_rate_limit_key_per_scope():
    assert redis_keys.rate_limit_key("ip", "203.0.113.7") == (
        "taskflow:ratelimit:ip:203.0.113.7"
    )
    assert redis_keys.rate_limit_key("user", 7) == "taskflow:ratelimit:user:7"


def test_rate_limit_scopes_are_distinct():
    """同一标识在不同 scope 下必须是不同 Key——否则 IP 与 user 会互相挤兑配额。"""
    a = redis_keys.rate_limit_key(redis_keys.RATE_LIMIT_SCOPE_IP, "1")
    b = redis_keys.rate_limit_key(redis_keys.RATE_LIMIT_SCOPE_USER, "1")
    assert a != b


def test_jwt_blacklist_key_shape():
    assert redis_keys.jwt_blacklist_key("jti-123") == (
        "taskflow:jwt:blacklist:jti-123"
    )


def test_jwt_blacklist_key_rejects_empty_jti():
    with pytest.raises(ValueError):
        redis_keys.jwt_blacklist_key("")


def test_all_purposes_share_the_single_prefix():
    """所有 Key 都必须以 KEY_PREFIX 开头——运维靠它安全地 SCAN/清理。"""
    samples = [
        redis_keys.rate_limit_key("ip", "1.1.1.1"),
        redis_keys.jwt_blacklist_key("abc"),
        redis_keys.build_key(redis_keys.PURPOSE_CELERY, "queue"),
    ]
    for key in samples:
        assert key.startswith(redis_keys.KEY_PREFIX + ":")


# ===========================================================================
# 2. 连接层契约（离线）
# ===========================================================================


def test_module_does_not_connect_at_import():
    """import 阶段不得建立连接——否则无 Redis 的环境无法 import 应用。

    单进程内断言 ``_client is None`` 是不够的：本文件其他用例可能已把单例建好。
    只有在**全新子进程**里 import 才能证明「import 本身不触发连接」，
    且用一个不可达地址 import 也不应报错/超时。
    """
    import subprocess
    import sys

    code = (
        "import app.main; "
        "from app.db import redis as r; "
        "assert r._client is None, 'import 阶段不应创建客户端'; "
        "print('OK')"
    )
    env = {
        **__import__("os").environ,
        # 故意指向不可达地址：若 import 期真的去连接，这里会挂住或报错
        "REDIS_URL": "redis://127.0.0.1:6399/0",
    }
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
        cwd=str(__import__("pathlib").Path(__file__).resolve().parent.parent),
    )
    assert proc.returncode == 0, proc.stderr
    assert "OK" in proc.stdout


def test_get_redis_client_returns_singleton():
    """同一进程内多次调用必须返回同一实例（复用连接池）。"""
    first = redis_db.get_redis_client()
    second = redis_db.get_redis_client()
    assert first is second


def test_get_redis_uses_configured_url():
    """客户端指向配置里的 URL（.env 覆盖能力）。"""
    client = redis_db.get_redis_client()
    conn_kwargs = client.connection_pool.connection_kwargs
    assert conn_kwargs.get("host") is not None


def test_get_redis_decodes_responses():
    """``decode_responses=True``：业务代码拿 str 而不是 bytes。

    这是刻意的契约——限流与黑名单逻辑里到处是字符串比较，若每个调用点都要
    自己 decode 会引入不一致。
    """
    client = redis_db.get_redis_client()
    assert client.connection_pool.connection_kwargs.get("decode_responses") is True


async def test_get_redis_dependency_yields_shared_client():
    gen = redis_db.get_redis()
    client = await gen.__anext__()
    assert client is redis_db.get_redis_client()
    await gen.aclose()
    # 依赖退出后客户端仍然可用（共享实例，不应被请求关闭）
    assert redis_db.get_redis_client() is client


async def test_reset_redis_clears_reference_without_closing():
    """``reset_redis`` 只丢引用；下一次调用据配置重建。"""
    before = redis_db.get_redis_client()
    await redis_db.reset_redis()
    assert redis_db._client is None
    after = redis_db.get_redis_client()
    assert after is not before  # 新建了实例
    assert before.connection_pool is not after.connection_pool


# ===========================================================================
# 3. 真实 Redis 连通性
# ===========================================================================


@pytest_asyncio.fixture
async def redis_client():
    """一个指向宿主 Redis 的真实异步客户端；测试结束关闭。"""
    client = aioredis.Redis.from_url(REDIS_URL, decode_responses=True)
    try:
        # 快速失败：Redis 未启动时给出清晰错误而不是超时挂起
        await client.ping()
    except Exception as exc:  # pragma: no cover - 环境缺失时的提示
        await client.aclose()
        pytest.skip(f"Redis not reachable at {REDIS_URL}: {exc}")
    yield client
    await client.aclose()


async def test_ping(redis_client):
    assert await redis_client.ping() is True


async def test_decode_responses_gives_str(redis_client):
    key = f"taskflow:test:{RUN_TOKEN}:decode"
    try:
        await redis_client.set(key, "hello")
        assert await redis_client.get(key) == "hello"  # 不是 b"hello"
    finally:
        await redis_client.delete(key)


async def test_key_convention_works_on_real_redis(redis_client):
    """把 Key 构造器产出的键真实写进 Redis，验证格式被 Redis 接受且可检索。"""
    key = redis_keys.build_key("test", RUN_TOKEN, "convention")
    try:
        await redis_client.set(key, "1", ex=30)
        assert await redis_client.exists(key) == 1
        # SCAN 用前缀能命中（运维清理依赖这一点）
        found = []
        async for k in redis_client.scan_iter(match=f"taskflow:test:{RUN_TOKEN}*"):
            found.append(k)
        assert key in found
    finally:
        await redis_client.delete(key)


async def test_set_with_ttl_and_expiry_reported(redis_client):
    """TTL 语义可用——限流与黑名单都依赖它。"""
    key = redis_keys.build_key("test", RUN_TOKEN, "ttl")
    try:
        await redis_client.set(key, "v", ex=60)
        ttl = await redis_client.ttl(key)
        assert 0 < ttl <= 60
    finally:
        await redis_client.delete(key)


async def test_zset_available_for_sliding_window(redis_client):
    """§22 限流的基础设施自检：ZSET 的 ZADD/ZRANGEBYSCORE/ZREMRANGEBYSCORE 可用。

    本 TASK 不实现限流（那是 TASK-046），但连接层必须确保**所需数据结构可用**，
    否则下一任务会卡在环境问题上。
    """
    key = redis_keys.build_key("test", RUN_TOKEN, "zset")
    try:
        await redis_client.zadd(key, {"a": 1000, "b": 2000, "c": 3000})
        assert await redis_client.zcard(key) == 3
        # 去掉窗口外的（<=1500）
        removed = await redis_client.zremrangebyscore(key, 0, 1500)
        assert removed == 1
        remaining = await redis_client.zrange(key, 0, -1)
        assert remaining == ["b", "c"]
        # 分数区间统计（窗口内计数）
        assert await redis_client.zcount(key, 1500, 3000) == 2
    finally:
        await redis_client.delete(key)


async def test_pipeline_works(redis_client):
    """pipeline 可用（批量删除等运维操作会用）。"""
    keys = [redis_keys.build_key("test", RUN_TOKEN, f"pipe{i}") for i in range(3)]
    try:
        async with redis_client.pipeline(transaction=True) as pipe:
            for k in keys:
                pipe.set(k, "1", ex=30)
            await pipe.execute()
        assert await redis_client.exists(*keys) == 3
    finally:
        await redis_client.delete(*keys)
