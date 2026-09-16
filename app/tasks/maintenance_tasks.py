"""Maintenance async tasks（§23 / TASK-050）.

开发文档 §23 列出两类后台维护任务：

- 归档操作日志（``archive_operation_logs``）
- 清理过期附件（``cleanup_expired_attachments``）

两个任务都是**批量、可重复执行、对失败不敏感**的运维操作，因此：

- 全部在 Celery 同步上下文里跑（worker 默认 prefork），DB 写入沿用
  notification_tasks 的「每次调用独立事件循环 + 短命 engine」模式
  （asyncpg 连接池绑定事件循环，不能复用 API 进程 engine 单例）。
- 都声明 ``autoretry_for=(SQLAlchemyError, OSError)`` 指数退避重试
  （规则 §8 retry/failure）：归档遇 DB 抖动重试、清理遇磁盘 IO 错误重试。
- 都**天然幂等**（规则 §8 idempotency）：重投递不产生重复副作用——
  归档靠「id 复用 + ON CONFLICT DO NOTHING + 同事务删主表」，清理靠
  「删文件幂等 + 孤儿判定只读 DB」。

TASK-089（§61）：两项任务由 celery_app 的 ``beat_schedule`` 周期投递
（此前生产永远不会执行——beat 缺位）；归档任务在迁移完成后追加归档表
**终态清理**（``archived_at`` 超过 ``archive_final_retention_days`` 的行
删除，存储期限最小化）。任务名常量收敛到 ``celery_app`` 声明，
本模块从那里引用，调度侧与注册侧共用同一份名字。

TASK-090（§1）：任务成功结束时把 Unix 时间戳写入 Redis
（``redis_keys.maintenance_last_success_key`` 的 Hash），由 API 进程的
``/metrics`` 暴露为 ``taskflow_maintenance_last_success_timestamp{task}``
——监控据此告警「维护任务超过预期周期没跑成」。写入是尽力而为：
观测失败只记 warning，绝不把已成功的任务拖成失败。
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.db.base import Base
from app.models.operation_log import OperationLog
from app.models.operation_log_archive import OperationLogArchive
from app.services.storage import (
    LocalStorageBackend,
    StorageBackend,
    UnsafeStorageKeyError,
    validate_key,
)
from app.tasks.celery_app import (
    TASK_NAME_ARCHIVE_LOGS,
    TASK_NAME_CLEANUP_ATTACHMENTS,
    celery_app,
)

logger = logging.getLogger(__name__)


def _record_success(task) -> None:
    """记录维护任务最后成功时间戳（TASK-090）：HSET 进共享 Hash。

    :param task: 任务实例（用 ``task.name`` 做字段名）。eager 模式（测试直接
        调用任务体）跳过——eager 调用不构成真实的周期执行，且测试环境未必有
        Redis；与 ``celery_app._bump_task_stat`` 的口径一致。

    worker 进程写、API 进程读——跨进程状态只能走共享存储（Redis），与
    ``celery_app`` 的任务计数同一通道。尽力而为：Redis 抖动只记 warning，
    不影响任务本身的成功。
    """
    request = getattr(task, "request", None)
    if request is not None and getattr(request, "is_eager", False):
        return
    try:
        from app.core.redis_keys import maintenance_last_success_key
        from app.db.redis import get_sync_redis_client

        get_sync_redis_client().hset(
            maintenance_last_success_key(), task.name, time.time()
        )
    except Exception:  # noqa: BLE001 — 观测失败不能把成功任务拖成失败
        logger.warning(
            "failed to record maintenance success timestamp for %s",
            task.name,
            exc_info=True,
        )


# ---------------------------------------------------------------------------
# 1. 归档操作日志
# ---------------------------------------------------------------------------


async def _archive_one_batch(
    database_url: str, cutoff: datetime, batch_size: int
) -> int:
    """把主表中 ``created_at < cutoff`` 的一批日志迁入归档表，返回本批行数。

    单事务内完成「插归档 + 删主表」：

    - 归档用 ``pg_insert ... ON CONFLICT (id) DO NOTHING``——id 复用原日志 id，
      已归档行被跳过（at-least-once 重投安全，不会因重复 INSERT 报错）；
    - 删主表只针对本批已选中的 id，且本批已确认写入归档表；
    - 事务原子：要么「归档+删除」一起成功，要么一起回滚。崩溃重投时主表
      对应行仍在（若上次回滚）或已不在（若上次提交）——前者会重新搬、后者
      为 no-op，都不会丢日志也不会重复。
    """
    engine = create_async_engine(database_url, pool_pre_ping=True)
    try:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            rows = (
                await session.execute(
                    select(OperationLog)
                    .where(OperationLog.created_at < cutoff)
                    .order_by(OperationLog.id)
                    .limit(batch_size)
                )
            ).scalars().all()
            if not rows:
                return 0

            values = [
                {
                    "id": r.id,
                    "user_id": r.user_id,
                    "resource_type": r.resource_type,
                    "resource_id": r.resource_id,
                    "action": r.action,
                    "payload": r.payload,
                    "created_at": r.created_at,
                }
                for r in rows
            ]
            ids = [r.id for r in rows]

            # 先插归档（冲突跳过），再删主表——同事务。
            await session.execute(
                pg_insert(OperationLogArchive)
                .values(values)
                .on_conflict_do_nothing(index_elements=["id"])
            )
            await session.execute(
                delete(OperationLog).where(OperationLog.id.in_(ids))
            )
            await session.commit()
            return len(ids)
    finally:
        await engine.dispose()


async def _purge_expired_archive_batch(
    database_url: str, cutoff: datetime, batch_size: int
) -> int:
    """删除归档表中 ``archived_at < cutoff`` 的一批行，返回本批行数。

    TASK-089（§61 存储期限最小化）：归档表在 TASK-050 落地时**只进不出**——
    主表 90 天迁出后，归档表按 id 只增不减，审计数据没有保留上限，与合规
    口径（个保法 / GDPR 的存储期限最小化）相悖。这里补上终态：归档行保留
    ``archive_final_retention_days`` 天（按 ``archived_at`` 计），到期删除。

    与迁移同样的分批事务模式：每批先选 id 再按 id 删、独立事务提交，长事务
    与 soft timeout 都不会出现；按 id 删天然幂等（重投时行已不在 → 0 行）。
    """
    engine = create_async_engine(database_url, pool_pre_ping=True)
    try:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            ids = (
                (
                    await session.execute(
                        select(OperationLogArchive.id)
                        .where(OperationLogArchive.archived_at < cutoff)
                        .order_by(OperationLogArchive.id)
                        .limit(batch_size)
                    )
                )
                .scalars()
                .all()
            )
            if not ids:
                return 0
            await session.execute(
                delete(OperationLogArchive).where(OperationLogArchive.id.in_(ids))
            )
            await session.commit()
            return len(ids)
    finally:
        await engine.dispose()


@celery_app.task(
    bind=False,
    name=TASK_NAME_ARCHIVE_LOGS,
    autoretry_for=(SQLAlchemyError, OSError),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
    max_retries=5,
)
def archive_operation_logs(
    retention_days: int | None = None,
    batch_size: int | None = None,
    final_retention_days: int | None = None,
) -> dict:
    """把超过保留期的 operation_logs 迁入 operation_logs_archive（§23 / TASK-050）。

    :param retention_days: 保留期（天）；缺省用 ``log_archive_retention_days``。
    :param batch_size: 每批行数；缺省用 ``maintenance_batch_size``。
    :param final_retention_days: 归档表终态保留期（天，按 ``archived_at`` 计）；
        缺省用 ``archive_final_retention_days``（TASK-089）。迁移完成后执行
        终态清理——归档不是数据的终点，审计数据同样有保留上限。
    :returns: ``{"archived": int, "purged": int}``——本次迁入主表->归档表的
        行数，与从归档表删除的行数。

    分批循环：每批独立事务，批大小远小于 soft timeout（300s），避免长事务
    锁主表；数据量巨大导致总时长超 hard limit（600s）被杀死时，已归档行被
    ON CONFLICT 跳过、主表已删行不再出现，重投从 cutoff 继续即可，无副作用。
    """
    settings = get_settings()
    retain = retention_days if retention_days is not None else settings.log_archive_retention_days
    batch = batch_size if batch_size is not None else settings.maintenance_batch_size
    final_retain = (
        final_retention_days
        if final_retention_days is not None
        else settings.archive_final_retention_days
    )
    if retain <= 0:
        raise ValueError("retention_days must be positive")
    if batch <= 0:
        raise ValueError("batch_size must be positive")
    if final_retain <= 0:
        raise ValueError("final_retention_days must be positive")

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=retain)
    total = 0
    while True:
        n = asyncio.run(_archive_one_batch(settings.database_url, cutoff, batch))
        if n == 0:
            break
        total += n

    # 终态清理：归档表中 archived_at 超过保留期的行删除（TASK-089）。
    purge_cutoff = now - timedelta(days=final_retain)
    purged = 0
    while True:
        n = asyncio.run(
            _purge_expired_archive_batch(settings.database_url, purge_cutoff, batch)
        )
        if n == 0:
            break
        purged += n

    logger.info(
        "operation logs archived: total=%s cutoff=%s; archive purged=%s purge_cutoff=%s",
        total,
        cutoff,
        purged,
        purge_cutoff,
    )
    _record_success(archive_operation_logs)
    return {"archived": total, "purged": purged}


# ---------------------------------------------------------------------------
# 2. 清理过期附件（回收孤儿物理文件）
# ---------------------------------------------------------------------------


async def _fetch_existing_storage_paths(database_url: str) -> set[str]:
    """返回 DB 中所有仍被引用的 storage_path（孤儿判定基准）。"""
    engine = create_async_engine(database_url, pool_pre_ping=True)
    try:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            rows = (
                await session.execute(select(Base.metadata.tables["attachments"].c.storage_path))
            ).scalars().all()
            return set(rows)
    finally:
        await engine.dispose()


def _list_physical_keys(backend: StorageBackend) -> list[tuple[str, float]]:
    """列出 storage 根下全部物理文件的相对 key 与 mtime（秒）。

    只返回文件（目录忽略）；相对 key 用 ``/`` 分隔，与 ``attachments.storage_path``
    的存储约定一致，便于直接比对。
    """
    root = backend.root
    result: list[tuple[str, float]] = []
    for path in root.rglob("*"):
        if path.is_file():
            key = str(path.relative_to(root)).replace("\\", "/")
            result.append((key, path.stat().st_mtime))
    return result


@celery_app.task(
    bind=False,
    name=TASK_NAME_CLEANUP_ATTACHMENTS,
    autoretry_for=(SQLAlchemyError, OSError),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
    max_retries=5,
)
def cleanup_expired_attachments(min_age_seconds: int | None = None) -> dict:
    """回收 storage 卷中的孤儿物理文件（§17 / §23 / TASK-050）。

    孤儿定义：storage 卷中物理存在、但 DB 的 ``attachments`` 表无对应
    ``storage_path`` 记录的文件。来源是任务级联删除（TASK-033 删任务 →
    attachments 记录 CASCADE 清掉，但物理文件由本任务回收，见 TASK-042 注释）。

    :param min_age_seconds: 孤儿最小年龄（秒）；缺省用
        ``attachment_orphan_min_age_seconds``。仅当文件 mtime 早于
        ``now - min_age`` 才删除——给正常删除流程留竞争缓冲，避免误删
        「正在上传（先落盘后落库）」或「刚删任务尚未回收」的文件。
    :returns: ``{"scanned": int, "deleted": int, "skipped_referenced": int,
        "errors": int}``

    安全性（§9）：
    - 只用 ``LocalStorageBackend``（唯一做相对 key→绝对路径解析的地方），
      ``delete`` 已保证不越出存储根；
    - 删除前 ``validate_key`` 二次校验，拒绝任何穿越/非法 key（理论来自我们
      自己的扫描，但双保险）；
    - 删文件幂等（``missing_ok=True``），重投递再扫一遍时孤儿已不在 → no-op。
    """
    settings = get_settings()
    min_age = (
        min_age_seconds
        if min_age_seconds is not None
        else settings.attachment_orphan_min_age_seconds
    )
    if min_age < 0:
        raise ValueError("min_age_seconds must be non-negative")

    backend: StorageBackend = LocalStorageBackend(settings.upload_dir)
    existing = asyncio.run(_fetch_existing_storage_paths(settings.database_url))
    physical = _list_physical_keys(backend)

    now = time.time()
    deleted = 0
    skipped_referenced = 0
    errors = 0
    for key, mtime in physical:
        if key in existing:
            skipped_referenced += 1
            continue
        # 孤儿：防御性校验 key（双保险，拒绝穿越/非法）。
        try:
            validate_key(key)
        except UnsafeStorageKeyError:
            logger.warning("cleanup skipped unsafe key: %s", key)
            continue
        # 年龄窗口：太新的孤儿可能是进行中文件，跳过，留给下次运行。
        if now - mtime < min_age:
            continue
        try:
            backend.delete(key)
            deleted += 1
        except Exception:  # noqa: BLE001 — 单文件失败不应中断整批清理
            errors += 1
            logger.exception("cleanup failed for key: %s", key)

    logger.info(
        "attachment cleanup done: scanned=%s deleted=%s skipped=%s errors=%s",
        len(physical),
        deleted,
        skipped_referenced,
        errors,
    )
    _record_success(cleanup_expired_attachments)
    return {
        "scanned": len(physical),
        "deleted": deleted,
        "skipped_referenced": skipped_referenced,
        "errors": errors,
    }
