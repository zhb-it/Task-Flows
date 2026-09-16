"""Prometheus 指标（§1「日志与指标」/ TASK-090）.

规格 §1 的交付清单写着「日志与指标」，但直到 TASK-088 前指标是 0 实现——
出了故障只能翻日志，没有可供监控告警的数值视图。本模块是指标对象的
**唯一定义点**（与 ``redis_keys`` 收敛 Key、``logging_config`` 收敛日志是
同一思路）。

## 指标集

- ``taskflow_http_requests_total{method,route,status}``——请求计数；
- ``taskflow_http_request_duration_seconds{method,route}``——请求延迟直方图；
- ``taskflow_http_requests_in_progress{method}``——进行中请求数；
- ``taskflow_redis_operation_seconds``——Redis 命令延迟直方图
  （``app/db/redis.py`` 的埋点客户端写入）；
- ``taskflow_db_pool_connections{state}``——DB 连接池占用（抓取时采样）；
- ``taskflow_celery_queue_depth``——Celery 默认队列深度（抓取时读 Redis）；
- ``taskflow_celery_tasks_total{state}``——任务成功/失败/重试累计（worker
  经 Celery 信号写入 Redis，抓取时读出——worker 是独立进程，进程内 Counter
  看不见它）；
- ``taskflow_maintenance_last_success_timestamp{task}``——维护任务最后成功
  时间戳（TASK-089 的交付物在此暴露，监控据此告警「维护任务没在跑」）；
- prometheus_client 默认注册表自带的进程指标（CPU/内存/GC）一并暴露。

## 两条标签纪律

1. **route 必须是路由模板**（如 ``/api/v1/tasks/{task_id}``），绝不能是原始
   路径——路径里的 UUID/数字 id 会把标签基数打爆（每条资源一个序列，监控
   存储直接爆炸）。未命中路由（404）统一落 ``unmatched`` 标签。
2. **跨进程数据只经 Redis 中转**，不引入新的存储：queue 深度、任务计数、
   维护时间戳都读自 ``redis_keys`` 定义的 Key，Redis 不可用时按 0/缺失处理
   ——``/metrics`` 绝不能因为依赖故障而 500（监控探活端点自己挂了最讽刺）。
"""

from prometheus_client import (
    REGISTRY,
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

#: HTTP 请求计数。status 是响应状态码（含 500——异常路径也计数）。
REQUEST_COUNT = Counter(
    "taskflow_http_requests_total",
    "Total HTTP requests processed",
    ["method", "route", "status"],
)

#: HTTP 请求延迟直方图（秒）。
REQUEST_LATENCY = Histogram(
    "taskflow_http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "route"],
)

#: 进行中请求数（并发视图，排障时看是否堆积）。
IN_PROGRESS = Gauge(
    "taskflow_http_requests_in_progress",
    "HTTP requests currently being processed",
    ["method"],
)

#: Redis 命令延迟直方图（埋点在 app/db/redis.py 的共享客户端上）。
REDIS_LATENCY = Histogram(
    "taskflow_redis_operation_seconds",
    "Redis command latency in seconds",
)

#: 未命中任何路由的请求（404）统一使用的 route 标签值。
#: 用固定常量而不是原始路径——原因见模块 docstring 的标签纪律第 1 条。
ROUTE_UNMATCHED = "unmatched"


def route_label(request_scope: dict) -> str:
    """从请求 scope 取**路由模板**作为标签值（标签纪律第 1 条）。

    Starlette 在路由分发成功后把命中的 ``APIRoute`` 写进 ``scope["route"]``，
    中间件在 ``call_next`` 返回后可以读到它的 ``.path``（即含 ``{param}``
    的模板）。未命中（404）或在路由前就失败时返回 ``unmatched``。
    """
    route = request_scope.get("route")
    if route is None:
        return ROUTE_UNMATCHED
    path = getattr(route, "path", None)
    return path if isinstance(path, str) and path else ROUTE_UNMATCHED


def render_metrics() -> tuple[bytes, str]:
    """渲染 Prometheus 文本格式与对应 Content-Type（不自造格式）。

    使用默认注册表：本项目指标 + 自定义采集器 + 进程指标（CPU/内存/GC）
    一并输出。采集器内部的 Redis/DB 访问失败已被吞掉（见
    ``TaskFlowCollector.collect``），这里不会因依赖故障抛错。
    """
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST


class TaskFlowCollector:
    """抓取时采样的采集器：DB 连接池 + 跨进程的 Celery/维护任务状态.

    为什么不用普通 Gauge/Counter 在别处更新：

    - DB 连接池、Redis 里的队列深度是**瞬时值**，只有抓取那一刻采样才有意义；
    - worker 进程的计数在 worker 内存里，API 进程的 Counter 更新不到——
      中转 Key（``redis_keys.celery_task_stats_key`` 等）在抓取时读出即可，
      语义仍是「自启动以来的累计值」（Counter 语义不因实现而变）。
    """

    def collect(self):  # noqa: D102 — prometheus_client 采集器协议
        from prometheus_client.core import (
            CounterMetricFamily,
            GaugeMetricFamily,
        )

        from app.core.redis_keys import (
            celery_queue_key,
            celery_task_stats_key,
            maintenance_last_success_key,
        )

        # --- DB 连接池（同进程，直接采样 engine.pool）---
        pool_gauge = GaugeMetricFamily(
            "taskflow_db_pool_connections",
            "SQLAlchemy connection pool usage by state",
            labels=["state"],
        )
        engine = _get_engine()
        if engine is not None:
            pool = engine.pool
            pool_gauge.add_metric(["in_use"], pool.checkedout())
            pool_gauge.add_metric(["available"], pool.checkedin())
            pool_gauge.add_metric(["overflow"], pool.overflow())
        yield pool_gauge

        # --- Celery 队列深度 / 任务计数 / 维护时间戳（跨进程，读 Redis）---
        queue = GaugeMetricFamily(
            "taskflow_celery_queue_depth",
            "Celery default queue depth",
        )
        tasks = CounterMetricFamily(
            "taskflow_celery_tasks_total",
            "Celery task outcomes by state (success/failure/retry)",
            labels=["state"],
        )
        last_success = GaugeMetricFamily(
            "taskflow_maintenance_last_success_timestamp",
            "Unix timestamp of the last successful maintenance task run",
            labels=["task"],
        )

        redis_state = _read_celery_state(
            celery_queue_key(),
            celery_task_stats_key(),
            maintenance_last_success_key(),
        )
        queue.add_metric([], redis_state["queue_depth"])
        for state in ("success", "failure", "retry"):
            tasks.add_metric([state], redis_state["tasks"].get(state, 0))
        for task_name, timestamp in redis_state["last_success"].items():
            last_success.add_metric([task_name], timestamp)
        yield queue
        yield tasks
        yield last_success


def _get_engine():
    """惰性取 DB engine；导入失败（测试裁剪环境）返回 None 而非炸掉采集。"""
    try:
        from app.db.session import engine
    except Exception:  # noqa: BLE001 — 指标采集不应让应用起不来
        return None
    return engine


def _read_celery_state(
    queue_key: str, stats_key: str, last_success_key: str
) -> dict:
    """读 Redis 汇聚跨进程状态；**任何失败都静默降级为空值**。

    ``/metrics`` 是监控的数据源，它自己绝不能 500：Redis 挂了时队列深度报 0、
    计数缺失——监控会看到「数据消失」而不是「抓取失败」，配合
    ``taskflow_db_pool_connections`` 等同进程指标仍然健康这一点，可以定位到
    是 Redis 而不是应用。同步客户端带 1s socket 超时（app/db/redis.py），
    抓取延迟有上界。
    """
    from app.db.redis import get_sync_redis_client

    state: dict = {"queue_depth": 0, "tasks": {}, "last_success": {}}
    try:
        client = get_sync_redis_client()
        pipe = client.pipeline(transaction=False)
        pipe.llen(queue_key)
        pipe.hgetall(stats_key)
        pipe.hgetall(last_success_key)
        depth, tasks, last_success = pipe.execute()
        state["queue_depth"] = int(depth or 0)
        state["tasks"] = {k: int(v) for k, v in (tasks or {}).items()}
        state["last_success"] = {
            k: float(v) for k, v in (last_success or {}).items()
        }
    except Exception:  # noqa: BLE001 — 见函数 docstring：采集永不因依赖故障失败
        pass
    return state


def register_collector() -> None:
    """把自定义采集器注册进默认注册表（幂等）。

    模块被 import 时调用一次；重复调用由 ``REGISTRY._collector_to_names``
    去重（同一实例重复注册会抛错，所以用模块级单例兜底）。
    """
    try:
        REGISTRY.register(_collector)
    except ValueError:
        # 已注册（configure/测试重复 import）——幂等即可。
        pass


_collector = TaskFlowCollector()
register_collector()
