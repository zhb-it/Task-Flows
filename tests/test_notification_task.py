"""TASK-049 — 通知异步任务测试（§24 通知异步化）.

覆盖面：
1. **注册与接线**：任务已注册到 Celery App、Worker include 已登记；
2. **执行链路**：直接调用与 eager 派发（经 Celery 任务机）都能落库；
3. **§24 要求 2 可重试**：重试语义已声明（瞬态故障重试、参数错误不重试）；
4. **§24 要求 3 不大量重复**：同一 idempotency_key 的重投递被跳过；
   不同 key 正常各建一条；Redis 完成标记带 TTL；Redis 故障 fail-open；
5. **参数防御**：非法参数 ValueError 快速失败、零副作用；
6. **FK 级联**：删除用户级联清理其通知。

实现约束（与 tests/test_celery_app.py 同理）：
- 任务体内部使用 ``asyncio.run``，**测试必须用同步用例**调用任务——
  async 用例自身跑在 pytest-asyncio 的事件循环里，嵌套 ``asyncio.run``
  会直接 RuntimeError。库内验证同样用 ``asyncio.run`` 包裹的短命连接。
- 沿用项目纪律：本次运行唯一前缀（``ntfy_<RUN_TOKEN>_``）+ teardown
  精确删除；验证用 asyncpg 直连开发库（5433），与任务自身的写入路径
  相互独立，避免「自己验证自己」。
"""

import asyncio
import uuid

import pytest
import redis as redis_lib
from sqlalchemy.exc import SQLAlchemyError

from app.crud.user import create_user
from app.tasks.celery_app import TASK_MODULES, celery_app
from app.tasks.notification_tasks import (
    IDEMPOTENCY_TTL_SECONDS,
    TASK_NAME_CREATE_NOTIFICATION,
    create_notification,
    new_idempotency_key,
)

TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@127.0.0.1:5433/taskflow"
POSTGRES_DSN = "postgresql://postgres:postgres@127.0.0.1:5433/taskflow"
REDIS_HOST, REDIS_PORT = "127.0.0.1", 6389

RUN_TOKEN = uuid.uuid4().hex[:10]
USER_PREFIX = f"ntfy_{RUN_TOKEN}_"
KEY_PREFIX = f"{RUN_TOKEN}_"  # idempotency key 统一带 RUN_TOKEN，便于清理


def _run(coro):
    return asyncio.run(coro)


def _username(tag: str) -> str:
    return f"{USER_PREFIX}{tag}"


async def _create_user(tag: str) -> int:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine(TEST_DATABASE_URL, pool_pre_ping=True)
    try:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            user = await create_user(
                session,
                username=_username(tag),
                email=f"{_username(tag)}@example.com",
                password_hash="h",
            )
            await session.commit()
            return user.id
    finally:
        await engine.dispose()


async def _count_notifications(user_id: int) -> int:
    import asyncpg

    conn = await asyncpg.connect(POSTGRES_DSN)
    try:
        return await conn.fetchval(
            "SELECT count(*) FROM notifications WHERE user_id = $1", user_id
        )
    finally:
        await conn.close()


async def _fetch_notifications(user_id: int) -> list[dict]:
    import asyncpg

    conn = await asyncpg.connect(POSTGRES_DSN)
    try:
        rows = await conn.fetch(
            "SELECT id, user_id, type, title, content, is_read, created_at"
            " FROM notifications WHERE user_id = $1 ORDER BY id",
            user_id,
        )
        return [dict(r) for r in rows]
    finally:
        await conn.close()


async def _delete_users_by_prefix() -> None:
    """删本次运行的用户（FK CASCADE 连带清掉其通知）。"""
    import asyncpg

    conn = await asyncpg.connect(POSTGRES_DSN)
    try:
        await conn.execute(
            "DELETE FROM users WHERE username LIKE $1", USER_PREFIX + "%"
        )
    finally:
        await conn.close()


def _redis() -> redis_lib.Redis:
    return redis_lib.Redis(
        host=REDIS_HOST, port=REDIS_PORT, decode_responses=True, socket_timeout=2
    )


@pytest.fixture(autouse=True)
def _cleanup():
    """teardown：删 Redis 完成标记 + 删本次用户（通知随 FK CASCADE 消失）。"""
    yield
    r = _redis()
    for key in r.scan_iter(match=f"taskflow:notify_done:{KEY_PREFIX}*", count=200):
        r.delete(key)
    _run(_delete_users_by_prefix())
    r.close()


@pytest.fixture
def redis_available():
    try:
        _redis().ping()
    except Exception:
        pytest.skip("Redis 不可用（6389），跳过依赖 Redis 的幂等测试")


def _call(user_id: int, **kwargs):
    """同步调用任务（任务内部 asyncio.run，禁止在事件循环内嵌套调用）。

    默认补上带 RUN_TOKEN 前缀的幂等键：teardown 按前缀清 Redis 标记，
    无前缀的自动生成键会绕过清理在开发 Redis 里滞留 7 天（首轮全量
    回归实测留下 16 个无前缀键，本写法即为此修复）。
    """
    if "idempotency_key" not in kwargs or kwargs["idempotency_key"] is None:
        kwargs["idempotency_key"] = KEY_PREFIX + uuid.uuid4().hex
    return create_notification(
        user_id,
        kwargs.get("ntype", "task_assigned"),
        kwargs.get("title", "你被分配了新任务"),
        kwargs.get("content"),
        kwargs["idempotency_key"],
    )


# ---------------------------------------------------------------------------
# 1. 注册与接线
# ---------------------------------------------------------------------------

def test_task_is_registered_on_celery_app():
    assert TASK_NAME_CREATE_NOTIFICATION in celery_app.tasks


def test_worker_include_lists_notification_module():
    assert "app.tasks.notification_tasks" in TASK_MODULES


# ---------------------------------------------------------------------------
# 2. 执行链路：直接调用落库
# ---------------------------------------------------------------------------

def test_creates_notification_row(redis_available):
    user_id = _run(_create_user("main"))

    result = _call(user_id, ntype="task_assigned", title="任务 X 分配给你", content="详情略")

    assert result == {"status": "created", "notification_id": result["notification_id"]}
    assert result["notification_id"] is not None
    rows = _run(_fetch_notifications(user_id))
    assert len(rows) == 1
    row = rows[0]
    assert row["type"] == "task_assigned"
    assert row["title"] == "任务 X 分配给你"
    assert row["content"] == "详情略"
    assert row["is_read"] is False  # §18：通知产生时必然未读
    assert row["created_at"] is not None


def test_content_is_nullable(redis_available):
    user_id = _run(_create_user("nocontent"))

    result = _call(user_id, content=None)

    assert result["status"] == "created"
    rows = _run(_fetch_notifications(user_id))
    assert len(rows) == 1
    assert rows[0]["content"] is None


def test_eager_dispatch_through_celery_machinery(redis_available):
    """经 Celery 任务机（eager）端到端：delay → 执行 → 落库。"""
    celery_app.conf.task_always_eager = True
    try:
        user_id = _run(_create_user("eager"))
        key = KEY_PREFIX + uuid.uuid4().hex
        result = create_notification.delay(
            user_id, "task_status_changed", "任务状态已更新", None, key
        )
        assert result.get()["status"] == "created"
        assert _run(_count_notifications(user_id)) == 1
    finally:
        celery_app.conf.task_always_eager = False


# ---------------------------------------------------------------------------
# 3. §24 要求 3：重试/重投递不大量重复
# ---------------------------------------------------------------------------

def test_same_idempotency_key_creates_only_one_row(redis_available):
    user_id = _run(_create_user("dup"))
    key = KEY_PREFIX + uuid.uuid4().hex

    first = _call(user_id, idempotency_key=key)
    second = _call(user_id, idempotency_key=key)

    assert first["status"] == "created"
    assert second["status"] == "skipped"
    assert second["notification_id"] is None
    assert _run(_count_notifications(user_id)) == 1


def test_different_keys_create_independent_rows(redis_available):
    """幂等键不同 = 不同业务事件，各建一条（去重不能误伤）。"""
    user_id = _run(_create_user("multi"))

    r1 = _call(user_id, idempotency_key=KEY_PREFIX + uuid.uuid4().hex)
    r2 = _call(user_id, idempotency_key=KEY_PREFIX + uuid.uuid4().hex)

    assert r1["status"] == "created"
    assert r2["status"] == "created"
    assert r1["notification_id"] != r2["notification_id"]
    assert _run(_count_notifications(user_id)) == 2


def test_done_marker_has_ttl_and_project_prefix(redis_available):
    """完成标记：taskflow:notify_done:<key>，且带 TTL（不无界占用 Redis）。"""
    user_id = _run(_create_user("ttl"))
    key = KEY_PREFIX + uuid.uuid4().hex

    _call(user_id, idempotency_key=key)

    r = _redis()
    redis_key = f"taskflow:notify_done:{key}"
    assert r.exists(redis_key) == 1
    ttl = r.ttl(redis_key)
    assert 0 < ttl <= IDEMPOTENCY_TTL_SECONDS
    r.close()


def test_redis_down_fails_open_notification_still_created(monkeypatch):
    """Redis 故障 fail-open：只损失去重，不丢通知（§8 failure）。"""
    from app.tasks import notification_tasks as nt

    def _boom():
        raise redis_lib.ConnectionError("redis down")

    monkeypatch.setattr(nt, "get_sync_redis_client", _boom)

    user_id = _run(_create_user("failopen"))
    result = _call(user_id, idempotency_key=KEY_PREFIX + uuid.uuid4().hex)

    assert result["status"] == "created"
    assert _run(_count_notifications(user_id)) == 1


def test_sync_redis_client_has_socket_timeouts():
    """同步客户端沿用 TASK-046 的超时纪律（否则 Redis 故障挂死 worker）。"""
    from app.db.redis import REDIS_SOCKET_TIMEOUT_SECONDS, get_sync_redis_client

    client = get_sync_redis_client()
    kwargs = client.connection_pool.connection_kwargs
    assert kwargs["host"] == "127.0.0.1"
    assert kwargs["port"] == REDIS_PORT
    assert kwargs["socket_timeout"] == REDIS_SOCKET_TIMEOUT_SECONDS
    assert kwargs["socket_connect_timeout"] == REDIS_SOCKET_TIMEOUT_SECONDS


# ---------------------------------------------------------------------------
# 4. 参数防御：快速失败、零副作用
# ---------------------------------------------------------------------------

def test_invalid_parameters_raise_without_side_effects(redis_available):
    user_id = _run(_create_user("invalid"))
    key = KEY_PREFIX + uuid.uuid4().hex

    with pytest.raises(ValueError):
        _call(0, idempotency_key=key)  # user_id 非正
    with pytest.raises(ValueError):
        _call(user_id, ntype="", idempotency_key=key)  # type 空
    with pytest.raises(ValueError):
        _call(user_id, ntype="x" * 51, idempotency_key=key)  # type 超长
    with pytest.raises(ValueError):
        _call(user_id, title="   ", idempotency_key=key)  # title 空白
    with pytest.raises(ValueError):
        _call(user_id, title="x" * 256, idempotency_key=key)  # title 超长

    assert _run(_count_notifications(user_id)) == 0


def test_missing_idempotency_key_generates_one(redis_available):
    """缺省幂等键时任务自行生成（手动调用场景；重试不去重已在 docstring 声明）。

    自动生成的键不带 RUN_TOKEN 前缀，teardown 删不到——本用例用 SCAN
    差集自行清理自己产生的标记。
    """
    user_id = _run(_create_user("nokey"))
    r = _redis()
    before = set(r.scan_iter(match="taskflow:notify_done:*", count=500))

    result = _call(user_id, idempotency_key=None)

    assert result["status"] == "created"
    after = set(r.scan_iter(match="taskflow:notify_done:*", count=500))
    for key in after - before:
        r.delete(key)
    r.close()


# ---------------------------------------------------------------------------
# 5. §24 要求 2：可重试语义已声明
# ---------------------------------------------------------------------------

def test_retry_semantics_declared():
    """瞬态故障（DB/网络）自动重试；参数错误不重试（§8 retry/failure）。"""
    options = create_notification.autoretry_for
    assert SQLAlchemyError in options
    assert OSError in options
    assert ValueError not in options
    assert create_notification.max_retries == 5
    assert create_notification.retry_backoff is True
    assert create_notification.retry_backoff_max == 600
    assert create_notification.retry_jitter is True


def test_new_idempotency_key_is_unique_and_hex():
    keys = {new_idempotency_key() for _ in range(100)}
    assert len(keys) == 100
    assert all(len(k) == 32 for k in keys)  # uuid4().hex


# ---------------------------------------------------------------------------
# 6. FK 级联
# ---------------------------------------------------------------------------

def test_deleting_user_cascades_notifications(redis_available):
    """通知写给某个用户：用户删除，通知随之清理（DECISIONS 029）。"""
    user_id = _run(_create_user("cascade"))
    assert _call(user_id)["status"] == "created"
    assert _run(_count_notifications(user_id)) == 1

    _run(_delete_users_by_prefix())

    assert _run(_count_notifications(user_id)) == 0
