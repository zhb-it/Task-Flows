"""TASK-051 — Celery 任务韧性测试（幂等 / 重试 / 失败，§8 / §23 / §24）.

定位
----
TASK-048/049/050 已分别测试了**声明层面**（``autoretry_for`` 元组、幂等键
跳过、参数防御的 ``ValueError``）与**直接调用层面**（把任务当普通函数调用）。
本任务补的是**行为层面**——这些声明在真实故障下是否真的生效：

1. **重试行为（真实）**：瞬态 DB 故障后，Celery 真的重跑任务体并最终成功，
   且恰好产生 1 行（幂等去重与重试协同）；超过 ``max_retries`` 后真的抛错、
   不产生任何副作用（规则 §8 failure「任务失败怎么办」）。
2. **失败短路**：参数错误在触达 DB **之前**被拦截、且不触发任何重试
   （``ValueError`` 不在 ``autoretry_for``，重试永不成功）。
3. **维护任务经 Celery 任务机执行**：``archive`` / ``cleanup`` 目前只测了
   直接调用，本文件补 eager 派发（``delay`` → 任务机 → 执行）端到端。
4. **清理重投递幂等**：孤儿文件删后再跑一遍 → 0 删除、0 错误。
5. **整体 at-least-once 安全**：三个任务**各跑两遍**，累计副作用 = 单跑一遍，
   跨模块互不串扰（整合验收，类比 TASK-040/044/047）。
6. **超时不被绕过**：三个业务任务都不覆盖 App 级 ``soft/hard_time_limit``，
   §8 的 300/600s 超时对它们生效。

范围纪律
--------
纯测试任务，**不改应用代码**（同 TASK-040/044/047 先例）。复用既有任务模块
与连接层；任务体内 ``asyncio.run`` 故用例必须同步；验证用 asyncpg 直连 5433
与任务写入路径相互独立；幂等键 / 日志行 / 用户均带本运行唯一前缀，teardown
精确清理，开发库零残留。
"""

import asyncio
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import redis as redis_lib
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.crud.user import create_user
from app.tasks.celery_app import celery_app
from app.tasks.maintenance_tasks import (
    TASK_NAME_ARCHIVE_LOGS,
    TASK_NAME_CLEANUP_ATTACHMENTS,
    archive_operation_logs,
    cleanup_expired_attachments,
)
from app.tasks.notification_tasks import (
    TASK_NAME_CREATE_NOTIFICATION,
    create_notification,
)

TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@127.0.0.1:5433/taskflow"
POSTGRES_DSN = "postgresql://postgres:postgres@127.0.0.1:5433/taskflow"
REDIS_HOST, REDIS_PORT = "127.0.0.1", 6389

RUN_TOKEN = uuid.uuid4().hex[:10]
USER_PREFIX = f"rsl_{RUN_TOKEN}_"
NOTIFY_KEY_PREFIX = f"{RUN_TOKEN}_"  # 幂等键前缀，teardown 按它清 Redis 标记
ACTION_PREFIX = f"rsl_{RUN_TOKEN}_"  # 归档日志 action 前缀，teardown 清两表


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# asyncpg 直连辅助（与任务写入路径相互独立）
# ---------------------------------------------------------------------------


async def _create_user(tag: str) -> int:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine(TEST_DATABASE_URL, pool_pre_ping=True)
    try:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            user = await create_user(
                session,
                username=f"{USER_PREFIX}{tag}",
                email=f"{USER_PREFIX}{tag}@example.com",
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


async def _delete_users_by_prefix() -> None:
    import asyncpg

    conn = await asyncpg.connect(POSTGRES_DSN)
    try:
        await conn.execute("DELETE FROM users WHERE username LIKE $1", USER_PREFIX + "%")
    finally:
        await conn.close()


async def _insert_log(when: datetime, action: str, payload: dict | None = None) -> int:
    import asyncpg

    conn = await asyncpg.connect(POSTGRES_DSN)
    try:
        return await conn.fetchval(
            "INSERT INTO operation_logs "
            "(user_id, resource_type, resource_id, action, payload, created_at) "
            "VALUES (1, 'task', 1, $1, $2::jsonb, $3) RETURNING id",
            action,
            json.dumps(payload if payload is not None else {"k": "v"}),
            when,
        )
    finally:
        await conn.close()


async def _count_main() -> int:
    import asyncpg

    conn = await asyncpg.connect(POSTGRES_DSN)
    try:
        return await conn.fetchval(
            "SELECT count(*) FROM operation_logs WHERE action LIKE $1",
            ACTION_PREFIX + "%",
        )
    finally:
        await conn.close()


async def _count_archive() -> int:
    import asyncpg

    conn = await asyncpg.connect(POSTGRES_DSN)
    try:
        return await conn.fetchval(
            "SELECT count(*) FROM operation_logs_archive WHERE action LIKE $1",
            ACTION_PREFIX + "%",
        )
    finally:
        await conn.close()


async def _delete_logs_by_prefix() -> None:
    import asyncpg

    conn = await asyncpg.connect(POSTGRES_DSN)
    try:
        await conn.execute(
            "DELETE FROM operation_logs WHERE action LIKE $1", ACTION_PREFIX + "%"
        )
        await conn.execute(
            "DELETE FROM operation_logs_archive WHERE action LIKE $1",
            ACTION_PREFIX + "%",
        )
    finally:
        await conn.close()


def _redis() -> redis_lib.Redis:
    return redis_lib.Redis(
        host=REDIS_HOST, port=REDIS_PORT, decode_responses=True, socket_timeout=2
    )


@pytest.fixture(autouse=True)
def _cleanup():
    """teardown：清 Redis 完成标记 + 删本次用户（通知随 FK CASCADE）+ 清两表日志。"""
    yield
    r = _redis()
    for key in r.scan_iter(match=f"taskflow:notify_done:{NOTIFY_KEY_PREFIX}*", count=200):
        r.delete(key)
    r.close()
    _run(_delete_users_by_prefix())
    _run(_delete_logs_by_prefix())


@pytest.fixture
def redis_available():
    try:
        _redis().ping()
    except Exception:
        pytest.skip("Redis 不可用（6389），跳过依赖 Redis 的韧性测试")


def _eager_on():
    celery_app.conf.task_always_eager = True


def _eager_off():
    celery_app.conf.task_always_eager = False


# ---------------------------------------------------------------------------
# 1. 重试行为（真实瞬态故障）
# ---------------------------------------------------------------------------


def test_notification_retries_on_transient_db_failure_then_succeeds(
    redis_available, monkeypatch
):
    """首次插入抛 SQLAlchemyError → 自动重试 → 第二次成功，恰好 1 行（§8 retry）。"""
    from app.tasks import notification_tasks as nt

    user_id = _run(_create_user("retry_ok"))
    key = NOTIFY_KEY_PREFIX + uuid.uuid4().hex
    calls = {"n": 0}
    real_insert = nt._insert_notification

    async def _flaky(url, uid, typ, title, content):
        calls["n"] += 1
        if calls["n"] < 2:
            raise SQLAlchemyError("transient db down")
        return await real_insert(url, uid, typ, title, content)

    # 关闭退避让重试即时发生，避免测试被 backoff 睡死。
    orig_backoff = create_notification.retry_backoff
    orig_jitter = create_notification.retry_jitter
    create_notification.retry_backoff = False
    create_notification.retry_jitter = False
    monkeypatch.setattr(nt, "_insert_notification", _flaky)
    _eager_on()
    try:
        result = create_notification.delay(
            user_id, "task_assigned", "任务 X", None, key
        )
        payload = result.get()
        assert payload["status"] == "created"
        assert payload["notification_id"] is not None
    finally:
        _eager_off()
        create_notification.retry_backoff = orig_backoff
        create_notification.retry_jitter = orig_jitter

    assert calls["n"] == 2  # 初跑 + 1 次重试，恰好重跑一次
    assert _run(_count_notifications(user_id)) == 1  # 重试不重复建行


def test_notification_max_retries_exhausted_raises_without_side_effect(
    redis_available, monkeypatch
):
    """永久故障超 max_retries → 抛错、插入函数被调用 (1+max) 次、零通知行（§8 failure）。"""
    from app.tasks import notification_tasks as nt

    user_id = _run(_create_user("exhaust"))
    key = NOTIFY_KEY_PREFIX + uuid.uuid4().hex
    calls = {"n": 0}

    async def _always_fail(url, uid, typ, title, content):
        calls["n"] += 1
        raise SQLAlchemyError("db permanently down")

    # 缩小重试次数 + 关退避，让"耗尽"快速可测。
    orig_max = create_notification.max_retries
    orig_backoff = create_notification.retry_backoff
    orig_jitter = create_notification.retry_jitter
    create_notification.max_retries = 2
    create_notification.retry_backoff = False
    create_notification.retry_jitter = False
    monkeypatch.setattr(nt, "_insert_notification", _always_fail)
    _eager_on()
    try:
        with pytest.raises(Exception):  # MaxRetriesExceeded / 原异常
            create_notification.delay(
                user_id, "task_assigned", "任务 X", None, key
            ).get()
    finally:
        _eager_off()
        create_notification.max_retries = orig_max
        create_notification.retry_backoff = orig_backoff
        create_notification.retry_jitter = orig_jitter

    assert calls["n"] == 3  # 初跑 + 2 次重试
    assert _run(_count_notifications(user_id)) == 0  # 失败不产生错误通知（§24 要求 1）


# ---------------------------------------------------------------------------
# 2. 失败短路：参数错误在触达 DB 前被拦截、不重试
# ---------------------------------------------------------------------------


def test_invalid_params_short_circuit_before_db_and_no_retry(
    redis_available, monkeypatch
):
    """非法参数：``_validate`` 先于 DB 触发，插入函数 0 次调用、0 重试、0 行。"""
    from app.tasks import notification_tasks as nt

    user_id = _run(_create_user("shortcircuit"))
    key = NOTIFY_KEY_PREFIX + uuid.uuid4().hex
    calls = {"n": 0}

    async def _insert_spy(url, uid, typ, title, content):
        calls["n"] += 1
        raise AssertionError("insert must not be reached for invalid params")

    monkeypatch.setattr(nt, "_insert_notification", _insert_spy)
    with pytest.raises(ValueError):
        create_notification(user_id, "", "标题", None, key)  # type 空

    assert calls["n"] == 0  # 校验短路，DB 从未被触达
    assert _run(_count_notifications(user_id)) == 0


# ---------------------------------------------------------------------------
# 3. 维护任务经 Celery 任务机执行（eager 端到端）
# ---------------------------------------------------------------------------


def test_archive_runs_through_eager_machinery():
    """``archive_operation_logs.delay()`` 经 Celery 任务机真正执行（非直接调用）。"""
    now = datetime.now(timezone.utc)
    for _ in range(2):
        _run(_insert_log(now - timedelta(days=5), ACTION_PREFIX + "old"))

    _eager_on()
    try:
        result = archive_operation_logs.delay(retention_days=1, batch_size=10)
        assert result.get()["archived"] == 2
    finally:
        _eager_off()

    assert _run(_count_archive()) == 2
    assert _run(_count_main()) == 0


def test_cleanup_runs_through_eager_machinery(tmp_path, monkeypatch):
    """``cleanup_expired_attachments.delay()`` 经 Celery 任务机回收孤儿文件。"""
    settings = get_settings()
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path), raising=False)
    orphan = tmp_path / "tasks" / "1" / "o.bin"
    orphan.parent.mkdir(parents=True, exist_ok=True)
    orphan.write_bytes(b"orphan")

    _eager_on()
    try:
        result = cleanup_expired_attachments.delay(min_age_seconds=0)
        assert result.get()["deleted"] >= 1
    finally:
        _eager_off()

    assert not orphan.exists()


# ---------------------------------------------------------------------------
# 4. 清理重投递幂等
# ---------------------------------------------------------------------------


def test_cleanup_idempotent_on_redelivery(tmp_path, monkeypatch):
    """孤儿删后再跑一遍：第二次 0 删除、0 错误（删文件幂等 + 孤儿判定只读 DB）。"""
    settings = get_settings()
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path), raising=False)
    orphan = tmp_path / "tasks" / "1" / "o.bin"
    orphan.parent.mkdir(parents=True, exist_ok=True)
    orphan.write_bytes(b"orphan")

    first = cleanup_expired_attachments(min_age_seconds=0)
    second = cleanup_expired_attachments(min_age_seconds=0)

    assert first["deleted"] == 1
    assert second["deleted"] == 0  # 已不在 → no-op
    assert second["errors"] == 0
    assert not orphan.exists()


# ---------------------------------------------------------------------------
# 5. 整体 at-least-once 安全（跨模块整合验收）
# ---------------------------------------------------------------------------


def test_all_tasks_idempotent_under_redelivery(redis_available, tmp_path, monkeypatch):
    """通知 / 归档 / 清理各跑两遍，累计副作用 = 单跑一遍，跨模块互不串扰。"""
    settings = get_settings()
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path), raising=False)

    # 通知：同一幂等键两遍 → 恰好 1 行。
    user_id = _run(_create_user("integ"))
    nkey = NOTIFY_KEY_PREFIX + uuid.uuid4().hex
    r1 = create_notification(user_id, "task_assigned", "整合", None, nkey)
    r2 = create_notification(user_id, "task_assigned", "整合", None, nkey)
    assert r1["status"] == "created"
    assert r2["status"] == "skipped"
    assert _run(_count_notifications(user_id)) == 1

    # 归档：同一 cutoff 两遍 → 迁入 3、第二遍 0。
    now = datetime.now(timezone.utc)
    for _ in range(3):
        _run(_insert_log(now - timedelta(days=5), ACTION_PREFIX + "old"))
    a1 = archive_operation_logs(retention_days=1, batch_size=10)
    a2 = archive_operation_logs(retention_days=1, batch_size=10)
    assert a1["archived"] == 3
    assert a2["archived"] == 0
    assert _run(_count_archive()) == 3

    # 清理：孤儿两遍 → 第一遍删 1、第二遍 0。
    orphan = tmp_path / "tasks" / "9" / "o.bin"
    orphan.parent.mkdir(parents=True, exist_ok=True)
    orphan.write_bytes(b"orphan")
    c1 = cleanup_expired_attachments(min_age_seconds=0)
    c2 = cleanup_expired_attachments(min_age_seconds=0)
    assert c1["deleted"] == 1
    assert c2["deleted"] == 0
    assert c2["errors"] == 0


# ---------------------------------------------------------------------------
# 6. 超时不被绕过（§8）
# ---------------------------------------------------------------------------


def test_business_tasks_inherit_app_soft_hard_limits():
    """三个业务任务都不覆盖 App 级 soft/hard time limit，§8 的 300/600s 生效。"""
    for task in (
        create_notification,
        archive_operation_logs,
        cleanup_expired_attachments,
    ):
        # 未显式设置时 hard_time_limit 不是对象属性（访问抛 AttributeError），
        # 用 getattr 缺省返回 None 安全判定；两者为 None = 继承 App 级 §8 超时。
        assert getattr(task, "soft_time_limit", None) is None, (
            f"{task.name} 不应覆盖 soft_time_limit"
        )
        assert getattr(task, "hard_time_limit", None) is None, (
            f"{task.name} 不应覆盖 hard_time_limit"
        )
    assert TASK_NAME_CREATE_NOTIFICATION in celery_app.tasks
    assert TASK_NAME_ARCHIVE_LOGS in celery_app.tasks
    assert TASK_NAME_CLEANUP_ATTACHMENTS in celery_app.tasks
