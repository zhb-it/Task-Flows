"""Notification async tasks（§24 通知异步化 / TASK-049）.

流程（§24）::

    用户 A 分配任务给用户 B
        ↓
    TaskService 创建任务
        ↓
    提交 Celery Task（本模块）
        ↓
    HTTP 快速返回
        ↓
    Worker 创建通知（写 notifications 表）

§24 三条要求在本模块的落地方式
--------------------------------
1. **主业务失败不能产生错误通知**：派发方（TaskService，属 TASK-053 的
   业务接线）必须在**事务提交之后**才 ``delay()``——本任务只负责执行，
   前提由调用方保证；本任务对参数做防御性校验（user_id/type/title），
   非法参数抛 ``ValueError`` 且**不重试**（重试也永远不会成功）。
2. **失败可重试**：``autoretry_for=(SQLAlchemyError, OSError)``——数据库
   抖动、连接失败这类**瞬态**故障按指数退避自动重试（``max_retries=5``，
   退避上限 600s，带抖动防止重试风暴）；``ValueError`` 不在重试列表，
   参数错误重试无意义。
3. **重试不会产生大量重复通知**：调用方为每次通知派发生成唯一
   ``idempotency_key``（同一业务事件重派发/重试共享同一 key）。任务
   **先插库、后写 Redis 完成标记**（``taskflow:notify:done:<key>``，
   SETNX + TTL）：DB 是事实源——先标记后插库会在"标记后崩溃"时**丢
   通知**，而先插库后标记的崩溃窗口最多产生**一条**重复（§24 只要求
   "不产生大量重复"，at-least-once 语义下偶发单条重复可接受）。Redis
   故障时 fail-open（只损失去重，不丢通知）。

实现注意
--------
Celery worker 默认 prefork 池、任务在**同步上下文**执行，而本项目 DB 栈
是 asyncpg + asyncio。本模块采用**每次调用独立事件循环 + 短命 engine**
（``asyncio.run``）：不与 API 进程共享 engine 单例——asyncpg 连接池绑定
事件循环，跨 loop 复用必然报错；通知量级（每业务事件一两条）下短命
engine 的开销可忽略，且天然隔离测试与生产循环。

Redis 同理：``app.db.redis.get_redis_client`` 是 async 客户端（命令返回
协程），同步任务里不可用——使用连接层的同步入口 ``get_sync_redis_client``
（TASK-049 在 ``app/db/redis.py`` 补充，同一 URL 与超时纪律）。
"""

import asyncio
import logging
import uuid

from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.redis_keys import build_key
from app.db.redis import get_sync_redis_client
from app.models.notification import Notification
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

# 完成标记的保留时长：需覆盖最坏的重投递窗口（worker 崩溃 → 消息重投）。
# 取 7 天——远长于任何合理的重试/重投间隔，短于无限期占用 Redis。
IDEMPOTENCY_TTL_SECONDS = 7 * 24 * 3600

# idempotency key 的 Redis purpose（TASK-045 键约定：taskflow:<purpose>:<id>）。
PURPOSE_NOTIFY_DONE = "notify_done"

# Celery 任务名（派发方按此名字符串解耦引用）。
TASK_NAME_CREATE_NOTIFICATION = "app.create_notification"


def _notification_done_key(idempotency_key: str) -> str:
    return build_key(PURPOSE_NOTIFY_DONE, idempotency_key)


def _validate(user_id: int, ntype: str, title: str) -> None:
    """防御性校验。抛 ValueError（不重试——参数错误重试永远不会成功）。"""
    if not isinstance(user_id, int) or user_id <= 0:
        raise ValueError(f"user_id must be a positive int, got {user_id!r}")
    if not isinstance(ntype, str) or not ntype.strip() or len(ntype) > 50:
        raise ValueError(
            f"type must be a non-empty string of length <= 50, got {ntype!r}"
        )
    if not isinstance(title, str) or not title.strip() or len(title) > 255:
        raise ValueError(
            f"title must be a non-empty string of length <= 255, got {title!r}"
        )


async def _insert_notification(
    database_url: str, user_id: int, ntype: str, title: str, content: str | None
) -> int:
    """在独立事件循环里用短命 engine 写入一条通知，返回通知 id。"""
    engine = create_async_engine(database_url, pool_pre_ping=True)
    try:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            notification = Notification(
                user_id=user_id, type=ntype, title=title, content=content
            )
            session.add(notification)
            await session.commit()
            await session.refresh(notification)
            return notification.id
    finally:
        await engine.dispose()


def _mark_done(idempotency_key: str) -> bool:
    """写 Redis 完成标记（SETNX + TTL）。Redis 故障时 fail-open 返回 False。"""
    try:
        client = get_sync_redis_client()
        return bool(
            client.set(
                _notification_done_key(idempotency_key),
                "1",
                nx=True,
                ex=IDEMPOTENCY_TTL_SECONDS,
            )
        )
    except RedisError:
        logger.warning(
            "notify idempotency mark failed (fail-open): key=%s",
            _notification_done_key(idempotency_key),
            exc_info=True,
        )
        return False


def _already_done(idempotency_key: str) -> bool:
    try:
        return bool(
            get_sync_redis_client().exists(_notification_done_key(idempotency_key))
        )
    except RedisError:
        logger.warning(
            "notify idempotency check failed (fail-open): key=%s",
            _notification_done_key(idempotency_key),
            exc_info=True,
        )
        return False


def new_idempotency_key() -> str:
    """派发方为一次通知事件生成幂等键（uuid4，跨重试稳定）。"""
    return uuid.uuid4().hex


@celery_app.task(
    bind=False,
    name=TASK_NAME_CREATE_NOTIFICATION,
    autoretry_for=(SQLAlchemyError, OSError),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
    max_retries=5,
)
def create_notification(
    user_id: int,
    ntype: str,
    title: str,
    content: str | None = None,
    idempotency_key: str | None = None,
) -> dict:
    """创建一条站内通知（§18 / §24）。

    :param user_id: 接收人 id。
    :param ntype: 通知类型（§18 场景：任务分配/任务状态变更/任务被评论/
        团队邀请）。
    :param title: 通知标题（摘要，必填 ≤255）。
    :param content: 通知正文（可空）。
    :param idempotency_key: 幂等键，**调用方生成**（uuid4），同一业务事件
        的重试/重投递共享同一 key；缺省时本任务自行生成（此时重试不去重，
        仅适合手动调用场景）。
    :returns: ``{"status": "created"|"skipped", "notification_id": int|None}``

    重试语义（规则 §8）：``SQLAlchemyError`` / ``OSError`` 视为瞬态故障，
    指数退避自动重试（上限 600s，带抖动）；参数错误抛 ``ValueError``，
    不在 autoretry 列表——重试永远不会成功，快速失败并报警。
    """
    _validate(user_id, ntype, title)
    if idempotency_key is None:
        idempotency_key = new_idempotency_key()
    if not isinstance(idempotency_key, str) or not idempotency_key:
        raise ValueError("idempotency_key must be a non-empty string")

    # §24 要求 3：重试/重投递不再产生第二条通知（先插库后标记，见模块 docstring）。
    if _already_done(idempotency_key):
        logger.info(
            "notification skipped (idempotency): key=%s user_id=%s type=%s",
            idempotency_key,
            user_id,
            ntype,
        )
        return {"status": "skipped", "notification_id": None}

    notification_id = asyncio.run(
        _insert_notification(
            get_settings().database_url, user_id, ntype.strip(), title.strip(), content
        )
    )
    _mark_done(idempotency_key)
    logger.info(
        "notification created: id=%s user_id=%s type=%s key=%s",
        notification_id,
        user_id,
        ntype,
        idempotency_key,
    )
    return {"status": "created", "notification_id": notification_id}
