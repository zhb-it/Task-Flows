"""TASK-050 — 维护异步任务测试（§23 归档操作日志 + 清理过期附件）.

覆盖面
------
1. **注册与接线**：两任务已注册到 Celery App、Worker include 已登记；
2. **归档执行链路**：超期日志迁入归档表、主表对应行删除、内容逐字段一致；
3. **归档幂等**：at-least-once 重投不重复（id 复用 + ON CONFLICT DO NOTHING
   + 同事务删主表）；
4. **归档分批**：batch_size 小值时循环搬完（避免长事务）；
5. **归档参数防御**：retention_days / batch_size 非正 → ValueError（不重试）；
6. **清理执行链路**：孤儿物理文件被删、DB 有记录的文件保留；
7. **清理年龄窗口**：太新的孤儿跳过，改旧后删除；
8. **清理参数防御**：min_age_seconds 负 → ValueError；
9. **重试语义声明**：两任务 autoretry_for 含 SQLAlchemyError/OSError、不含
   ValueError、max_retries=5（规则 §8）。

实现约束（同 tests/test_notification_task.py）
-----------------------------------------
- 任务体内部用 ``asyncio.run``，**测试必须用同步用例**调用任务；
- 归档验证用 asyncpg 直连 5433，与任务写入路径相互独立；
- 归档测试行用 ``action`` 前缀 ``mt_<RUN_TOKEN>_`` 隔离，teardown 精确清理
  两表（operation_logs / operation_logs_archive）；
- 清理任务通过 monkeypatch ``settings.upload_dir`` 指向 ``tmp_path``，隔离
  真实 ``storage/`` 卷，不污染部署文件。
"""

import asyncio
import json
import os
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.tasks.celery_app import TASK_MODULES, celery_app
from app.tasks.maintenance_tasks import (
    TASK_NAME_ARCHIVE_LOGS,
    TASK_NAME_CLEANUP_ATTACHMENTS,
    archive_operation_logs,
    cleanup_expired_attachments,
)

TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@127.0.0.1:5433/taskflow"
POSTGRES_DSN = "postgresql://postgres:postgres@127.0.0.1:5433/taskflow"
RUN_TOKEN = uuid.uuid4().hex[:10]
ACTION_PREFIX = f"mt_{RUN_TOKEN}_"


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# 归档表的 asyncpg 直连辅助（与任务写入路径独立）
# ---------------------------------------------------------------------------


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


async def _fetch_archive_row(log_id: int) -> dict:
    import asyncpg

    conn = await asyncpg.connect(POSTGRES_DSN)
    try:
        row = await conn.fetchrow(
            "SELECT id, user_id, resource_type, resource_id, action, payload, created_at "
            "FROM operation_logs_archive WHERE id = $1",
            log_id,
        )
        if row is None:
            return {}
        d = dict(row)
        # asyncpg 对该连接的 jsonb 解码为 str，归一化为 dict 再比较。
        if isinstance(d["payload"], str):
            d["payload"] = json.loads(d["payload"])
        return d
    finally:
        await conn.close()


async def _delete_logs_by_prefix() -> None:
    """teardown：清本次运行在 operation_logs 与归档表的两表 mt_ 行。"""
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


@pytest.fixture(autouse=True)
def _cleanup_logs():
    yield
    _run(_delete_logs_by_prefix())


# ---------------------------------------------------------------------------
# 1. 注册与接线
# ---------------------------------------------------------------------------


def test_archive_task_registered_on_celery_app():
    assert TASK_NAME_ARCHIVE_LOGS in celery_app.tasks


def test_cleanup_task_registered_on_celery_app():
    assert TASK_NAME_CLEANUP_ATTACHMENTS in celery_app.tasks


def test_worker_include_lists_maintenance_module():
    assert "app.tasks.maintenance_tasks" in TASK_MODULES


# ---------------------------------------------------------------------------
# 2. 归档执行链路：迁移 + 主表删除 + 内容一致
# ---------------------------------------------------------------------------


def test_archive_moves_expired_logs_and_keeps_recent():
    now = datetime.now(timezone.utc)
    old_ids = [
        _run(_insert_log(now - timedelta(days=2), ACTION_PREFIX + "old", {"old": "A"}))
        for _ in range(3)
    ]
    recent_id = _run(_insert_log(now, ACTION_PREFIX + "new", {"new": "B"}))

    result = archive_operation_logs(retention_days=1, batch_size=10)

    # 3 条超期迁入归档表，1 条新日志留在主表。
    assert result["archived"] == 3
    assert _run(_count_archive()) == 3
    assert _run(_count_main()) == 1

    # 主表的新行完好。
    assert _run(_fetch_archive_row(recent_id)) == {}

    # 内容逐字段一致（含 JSONB payload 与原时间戳）。
    row = _run(_fetch_archive_row(old_ids[0]))
    assert row["user_id"] == 1
    assert row["resource_type"] == "task"
    assert row["action"] == ACTION_PREFIX + "old"
    assert row["payload"] == {"old": "A"}
    # created_at 应保留原事件时间（now-2day），而非归档时间。
    assert abs((row["created_at"] - (now - timedelta(days=2))).total_seconds()) < 2


def test_archive_is_idempotent_on_redelivery():
    """at-least-once 重投：已归档行被 ON CONFLICT 跳过、主表已无可搬行。"""
    now = datetime.now(timezone.utc)
    for _ in range(3):
        _run(_insert_log(now - timedelta(days=5), ACTION_PREFIX + "old"))

    first = archive_operation_logs(retention_days=1, batch_size=10)
    second = archive_operation_logs(retention_days=1, batch_size=10)

    assert first["archived"] == 3
    # 重投时无更多 cutoff 前日志 → 0，且归档表行数不变（无重复）。
    assert second["archived"] == 0
    assert _run(_count_archive()) == 3


def test_archive_batches_small_batch_size():
    """batch_size=2 时分批循环搬完 5 条（每批独立事务）。"""
    now = datetime.now(timezone.utc)
    for _ in range(5):
        _run(_insert_log(now - timedelta(days=3), ACTION_PREFIX + "old"))

    result = archive_operation_logs(retention_days=1, batch_size=2)

    assert result["archived"] == 5
    assert _run(_count_archive()) == 5
    assert _run(_count_main()) == 0


def test_archive_invalid_params_raise_without_side_effects():
    now = datetime.now(timezone.utc)
    _run(_insert_log(now - timedelta(days=3), ACTION_PREFIX + "old"))

    with pytest.raises(ValueError):
        archive_operation_logs(retention_days=0)
    with pytest.raises(ValueError):
        archive_operation_logs(batch_size=0)

    # 参数错误快速失败，不应有任何迁移发生。
    assert _run(_count_archive()) == 0
    assert _run(_count_main()) == 1


# ---------------------------------------------------------------------------
# 3. 清理过期附件：孤儿回收 + 年龄窗口
# ---------------------------------------------------------------------------


def test_cleanup_removes_orphan_files(tmp_path, monkeypatch):
    """真实 existing 查询（库无对应记录）→ storage 卷中的孤儿文件被删。"""
    settings = get_settings()
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path), raising=False)

    orphan = tmp_path / "tasks" / "1" / "orphan_a.bin"
    orphan.parent.mkdir(parents=True, exist_ok=True)
    orphan.write_bytes(b"orphan-data")

    result = cleanup_expired_attachments(min_age_seconds=0)

    assert not orphan.exists()
    assert result["deleted"] >= 1
    assert result["scanned"] >= 1
    assert result["errors"] == 0


def test_cleanup_keeps_db_referenced_files(tmp_path, monkeypatch):
    """DB 有记录的 storage_path 不被删，仅孤儿被回收。"""
    from app.tasks import maintenance_tasks as mt

    async def _fake_existing(_url: str) -> set[str]:
        return {"tasks/1/keep.bin"}

    monkeypatch.setattr(mt, "_fetch_existing_storage_paths", _fake_existing)

    settings = get_settings()
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path), raising=False)

    keep = tmp_path / "tasks" / "1" / "keep.bin"
    keep.parent.mkdir(parents=True, exist_ok=True)
    keep.write_bytes(b"keep-me")
    orphan = tmp_path / "tasks" / "2" / "orphan.bin"
    orphan.parent.mkdir(parents=True, exist_ok=True)
    orphan.write_bytes(b"delete-me")

    result = cleanup_expired_attachments(min_age_seconds=0)

    assert keep.exists()  # DB 有记录 → 保留
    assert not orphan.exists()  # 孤儿 → 删除
    assert result["skipped_referenced"] >= 1
    assert result["deleted"] == 1


def test_cleanup_respects_min_age_window(tmp_path, monkeypatch):
    """太新的孤儿跳过（给正常删除流程留竞争缓冲），改旧后删除。"""
    settings = get_settings()
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path), raising=False)

    recent = tmp_path / "tasks" / "3" / "recent.bin"
    recent.parent.mkdir(parents=True, exist_ok=True)
    recent.write_bytes(b"recent")

    # 年龄窗口 1h：刚写入的文件 mtime ≈ now，太新 → 跳过。
    result_young = cleanup_expired_attachments(min_age_seconds=3600)
    assert recent.exists()
    assert result_young["deleted"] == 0

    # 把 mtime 改到 2h 前，再用 min_age=0 → 删除。
    old = time.time() - 7200
    os.utime(recent, (old, old))
    result_old = cleanup_expired_attachments(min_age_seconds=0)
    assert not recent.exists()
    assert result_old["deleted"] == 1


def test_cleanup_invalid_params_raise():
    with pytest.raises(ValueError):
        cleanup_expired_attachments(min_age_seconds=-1)


# ---------------------------------------------------------------------------
# 4. 重试语义声明（规则 §8）
# ---------------------------------------------------------------------------


def test_archive_retry_semantics_declared():
    opts = archive_operation_logs.autoretry_for
    assert SQLAlchemyError in opts
    assert OSError in opts
    assert ValueError not in opts  # 参数错误不重试
    assert archive_operation_logs.max_retries == 5
    assert archive_operation_logs.retry_backoff is True
    assert archive_operation_logs.retry_backoff_max == 600
    assert archive_operation_logs.retry_jitter is True


def test_cleanup_retry_semantics_declared():
    opts = cleanup_expired_attachments.autoretry_for
    assert SQLAlchemyError in opts
    assert OSError in opts
    assert ValueError not in opts
    assert cleanup_expired_attachments.max_retries == 5
    assert cleanup_expired_attachments.retry_backoff is True
    assert cleanup_expired_attachments.retry_jitter is True
