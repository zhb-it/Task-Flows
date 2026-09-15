"""Celery application wiring（TASK-048，开发文档 §23）.

架构（§23）::

    FastAPI → Celery → Redis Broker → Celery Worker → 执行任务

职责边界
--------
本模块只做 **基础设施接线**：Celery 实例、Broker/Backend、序列化、可靠性
参数。业务任务以独立模块出现（``notification_tasks.py`` = TASK-049；
日志归档/附件清理 = TASK-050），并登记进 ``TASK_MODULES`` 供 Worker 启动
时自动导入。

关键决策（详见 docs/DECISIONS.md）
---------------------------------
- **Broker / Backend 均用 Redis**（§21 用途 3/4）：两者默认回落到
  ``redis_url``，留空表示"与限流共用同一实例"，避免本项目规模引入第二个
  Redis；需要隔离时用 ``CELERY_BROKER_URL`` / ``CELERY_RESULT_BACKEND``
  覆盖。
- **JSON-only 序列化**：Celery 默认接受 pickle——反序列化即执行任意代码，
  任务消息一旦被注入 Redis 的攻击面拿到就是 RCE。本项目只传可 JSON 化的
  标量参数，显式锁死 ``accept_content=["json"]``。
- **可靠性参数是规则 §8 的落点**：``task_acks_late=True``（任务执行完才
  ack，Worker 崩溃消息不丢）+ ``task_reject_on_worker_lost=True``（Worker
  被强杀时消息重新入队）+ ``worker_prefetch_multiplier=1``（每 Worker
  一次只预取 1 条，避免长任务堆在单个进程上饿死其他消息）。
  §8 明言"不要假设 Celery 任务只执行一次"——这三个参数组合意味着
  **at-least-once 投递**：任务可能被重复执行，幂等性由每个业务任务自己
  保证（TASK-049/050/051 落实）。
- **超时双保险**（§8 timeout）：``task_soft_time_limit`` 抛
  ``SoftTimeLimitExceeded`` 给任务自行清理的机会，``task_time_limit``
  硬杀进程兜底。
- **`global_keyprefix="taskflow:"`**：Celery 在 Redis 里的键（broker 队列、
  结果元数据）统一挂上 TASK-045 的键约定前缀，``taskflow:*`` 之外的键都
  不属于本项目，运维排查和按前缀清理都干净。
- **import 不连接**：本模块导入时只读配置构造对象，不发起任何网络连接
  （Celery 的连接是惰性的），API 进程导入它零成本，测试可在无 Redis
  环境下安全导入。
"""

from celery import Celery

from app.core.config import get_settings

# Worker 启动时导入的任务模块（Celery include）。
# 新增业务任务模块时在此登记（TASK-050 将追加日志归档/附件清理）。
TASK_MODULES = ["app.tasks.notification_tasks"]

# 挂在 Redis 上的所有 Celery 键前缀（TASK-045 键约定）。
CELERY_KEY_PREFIX = "taskflow:"


def create_celery_app() -> Celery:
    """Build the Celery application from current settings.

    Returns a fully configured (but not connected) ``Celery`` instance.
    """
    settings = get_settings()
    broker_url = settings.celery_broker_url or settings.redis_url
    result_backend = settings.celery_result_backend or settings.redis_url

    app = Celery(
        "taskflow",
        broker=broker_url,
        backend=result_backend,
        include=TASK_MODULES,
    )

    app.conf.update(
        # --- 序列化：JSON only，禁 pickle（安全，见模块 docstring）---
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],

        # --- 时间 ---
        timezone="UTC",
        enable_utc=True,

        # --- 可靠性（规则 §8：retry / timeout / failure / idempotency）---
        # 执行完成才 ack；Worker 崩溃则消息重投（at-least-once）。
        task_acks_late=True,
        # Worker 被 SIGKILL/OOM 杀死时，未 ack 的任务重新入队而不是丢掉。
        task_reject_on_worker_lost=True,
        # 每个子进程一次只预取 1 条消息，长任务不会囤积在单进程上。
        worker_prefetch_multiplier=1,
        # 任务开始执行时更新状态为 STARTED（默认任务只有 PENDING/SUCCESS），
        # 便于运维区分"排队中"与"执行中"。
        task_track_started=True,
        # 超时：软超时抛 SoftTimeLimitExceeded（任务可自行清理），硬超时杀进程。
        task_soft_time_limit=settings.celery_task_soft_time_limit,
        task_time_limit=settings.celery_task_time_limit,

        # --- 结果后端 ---
        # 结果仅作调试辅助，过期回收，避免 Redis 无界增长。
        result_expires=settings.celery_result_expires,

        # --- Redis 键前缀（TASK-045 键约定）---
        broker_transport_options={"global_keyprefix": CELERY_KEY_PREFIX},
        result_backend_transport_options={"global_keyprefix": CELERY_KEY_PREFIX},
    )
    return app


celery_app = create_celery_app()


@celery_app.task(name="app.ping")
def ping() -> str:
    """端到端冒烟任务：验证 Broker → Worker → Backend 全链路可用。

    除 compose 部署冒烟（TASK-048 验收）外无业务用途；幂等性的定义在此
    显得平凡——重复执行只是重复返回 "pong"，无副作用。
    """
    return "pong"
