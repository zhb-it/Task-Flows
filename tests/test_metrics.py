"""TASK-090 契约测试：``/metrics`` 指标端点与 5xx 统一信封。

覆盖 TASKS.md 的三条测试要求：

1. **指标端点契约**——内容类型（Prometheus 文本格式，不自造）、关键指标名
   存在、默认关闭时 404、路由标签不含原始 id（基数纪律）；
2. **500 信封用例**——结构断言（§26 的 ``{"detail": ...}``）、不泄露堆栈与
   异常信息、日志有 ``request_id`` 关联的 error 记录（§34）、
   ``X-Request-ID`` 头得以回传；
3. **标签基数用例**——两条不同 id 的请求不产生两个标签值（统一落
   ``unmatched`` 或同一模板）。

测试不需要真实 PostgreSQL/Redis：指标采集对依赖故障静默降级（这是
``TaskFlowCollector`` 的设计契约，本文件顺带验证它——依赖不可达时
``/metrics`` 仍返回 200）。
"""

import io
import logging
import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.logging_config import TextFormatter
from app.main import app, settings

#: Prometheus 文本格式的内容类型前缀（0.26 是 ``text/plain; version=0.0.4...``）。
METRICS_CONTENT_TYPE_PREFIX = "text/plain"


@pytest.fixture
def client() -> TestClient:
    """不向测试进程重抛服务端异常——500 信封本身就是被测行为。"""
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def metrics_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """打开指标端点（写的是 lru_cache 后的共享 Settings 实例，测后还原）。"""
    monkeypatch.setattr(settings, "metrics_enabled", True)


# ---------------------------------------------------------------------------
# 1. 指标端点契约
# ---------------------------------------------------------------------------


def test_metrics_disabled_by_default_returns_404(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    """默认关闭：404 + 与其它 404 一致的信封（不是 403，不暴露端点存在）。"""
    monkeypatch.setattr(settings, "metrics_enabled", False)
    resp = client.get("/metrics")
    assert resp.status_code == 404
    assert resp.json() == {"detail": "Not Found"}


def test_metrics_enabled_contract(metrics_enabled, client: TestClient) -> None:
    """打开后：200、Prometheus 文本内容类型、关键指标名全部在场。"""
    # 产生至少一次请求计数/延迟观测。
    assert client.get("/health").status_code == 200

    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith(METRICS_CONTENT_TYPE_PREFIX)
    body = resp.text
    for metric_name in (
        "taskflow_http_requests_total",
        "taskflow_http_request_duration_seconds",
        "taskflow_http_requests_in_progress",
        "taskflow_db_pool_connections",
        "taskflow_redis_operation_seconds",
        "taskflow_celery_queue_depth",
        "taskflow_celery_tasks_total",
        "taskflow_maintenance_last_success_timestamp",
    ):
        assert metric_name in body, f"缺少关键指标 {metric_name}"


def test_metrics_available_even_when_dependencies_down(
    metrics_enabled, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """依赖故障静默降级：Redis/DB 不可达时 /metrics 仍 200（采集永不 500）。

    用指向不存在地址的 URL 构造最坏的依赖状态；采集器按 0/缺失处理。
    （这是 app/core/metrics.py 模块 docstring 承诺的行为契约。）

    同时清掉模块级客户端单例，确保真的用坏地址新建连接；monkeypatch 还原
    后单例引用也随之还原，不影响后续用例。
    """
    import app.db.redis as db_redis

    monkeypatch.setattr(settings, "redis_url", "redis://127.0.0.1:1/0", raising=False)
    monkeypatch.setattr(db_redis, "_sync_client", None)
    monkeypatch.setattr(db_redis, "_client", None)
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert "taskflow_celery_queue_depth" in resp.text


def test_route_labels_use_templates_not_raw_ids(
    metrics_enabled, client: TestClient
) -> None:
    """标签基数纪律：路由标签是模板/unmatched，原始 UUID 绝不进标签。"""
    resource_id = uuid.uuid4().hex
    assert client.get("/health").status_code == 200
    # 未命中路由：两条不同 id 的请求 → 同一个 unmatched 标签（验收标准）。
    assert client.get(f"/health/{resource_id}").status_code == 404
    other_id = uuid.uuid4().hex
    assert client.get(f"/health/{other_id}").status_code == 404

    body = client.get("/metrics").text
    # 原始 id 与请求路径不得出现在任何标签值里（注意 /health/ready 等同类
    # 模板是合法标签，不能按前缀排除——只排除「恰好等于请求路径」的标签值）。
    assert f'"/health/{resource_id}"' not in body
    assert f'"/health/{other_id}"' not in body
    # 固定模板在；两条不同 id 的请求共享同一个 unmatched 标签（验收标准）。
    assert 'route="/health"' in body
    assert 'route="unmatched"' in body


# ---------------------------------------------------------------------------
# 2. 500 统一信封（§26 / B9）
# ---------------------------------------------------------------------------


@pytest.fixture
def exploding_health(monkeypatch: pytest.MonkeyPatch):
    """让 /health 的 DB 探测抛未处理异常（模拟任意路由内的未捕获错误）。"""
    from app import main as app_main

    def boom() -> bool:
        raise RuntimeError("boom-secret-internal")

    monkeypatch.setattr(app_main, "_check_database", boom)


def test_unhandled_exception_returns_envelope_without_stack(
    exploding_health, client: TestClient
) -> None:
    """未捕获异常 → §26 信封；对外不含堆栈、不含异常消息。"""
    resp = client.get("/health", headers={"X-Request-ID": "rid-envelope-1"})
    assert resp.status_code == 500
    assert resp.json() == {"detail": "Internal server error"}
    # 异常细节只进日志，不进响应体。
    assert "boom-secret-internal" not in resp.text
    assert "Traceback" not in resp.text
    # request_id 得以回传（异常被本中间件转换而非冒泡到最外层）。
    assert resp.headers["X-Request-ID"] == "rid-envelope-1"


def test_unhandled_exception_logs_error_with_request_id(
    exploding_health, client: TestClient
) -> None:
    """error 级日志带 exc_info 全量堆栈，且与 request_id 关联（§34）。"""
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(TextFormatter())
    root = logging.getLogger()
    root.addHandler(handler)
    try:
        resp = client.get("/health", headers={"X-Request-ID": "rid-log-42"})
    finally:
        root.removeHandler(handler)

    assert resp.status_code == 500
    out = stream.getvalue()
    assert "unhandled exception" in out
    assert "request_id=rid-log-42" in out  # 日志与请求的关联
    assert "Traceback" in out  # 全量堆栈在日志里（对外才不泄露）
    assert "boom-secret-internal" in out


def test_unhandled_exception_is_counted_in_metrics(
    exploding_health, metrics_enabled, client: TestClient
) -> None:
    """异常路径计入 taskflow_http_requests_total（status="500"）——5xx 率告警的数据源。"""
    assert client.get("/health").status_code == 500
    body = client.get("/metrics").text
    line = next(
        ln
        for ln in body.splitlines()
        if ln.startswith("taskflow_http_requests_total")
        and 'route="/health"' in ln
        and 'status="500"' in ln
    )
    assert float(line.rsplit(" ", 1)[1]) >= 1


# ---------------------------------------------------------------------------
# 3. 跨进程指标的中转通道（Redis Hash 写入侧）
# ---------------------------------------------------------------------------


class _FakeTask:
    """模拟 Celery Task 实例（``_record_success`` 只用 name 与 request）。"""

    def __init__(self, name: str, is_eager: bool) -> None:
        self.name = name
        self.request = type("R", (), {"is_eager": is_eager})()


def test_record_success_writes_redis_hash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """任务成功 → HSET 时间戳进共享 Hash（worker 写、/metrics 读）。"""
    from app.tasks import maintenance_tasks

    calls: list[tuple] = []

    class FakeClient:
        def hset(self, key, field, value):  # noqa: ANN001
            calls.append((key, field, float(value)))

    fake_task = _FakeTask("app.archive_operation_logs", is_eager=False)
    monkeypatch.setattr(
        "app.db.redis.get_sync_redis_client", lambda: FakeClient()
    )

    maintenance_tasks._record_success(fake_task)

    assert len(calls) == 1
    key, field, _ = calls[0]
    assert key == "taskflow:celery:maintenance:last_success"
    assert field == "app.archive_operation_logs"


def test_record_success_skips_eager_and_never_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """eager（测试/同步调用）不记账；Redis 故障只吞掉不外抛。"""
    from app.tasks import maintenance_tasks

    def forbidden():  # pragma: no cover — 被调用即测试失败
        raise AssertionError("eager 模式不应触碰 Redis")

    monkeypatch.setattr("app.db.redis.get_sync_redis_client", forbidden)

    # eager：直接跳过。
    maintenance_tasks._record_success(_FakeTask("app.x", is_eager=True))

    # 非 eager + Redis 故障：吞掉（forbidden 抛 AssertionError 也被吞——
    # 这正是「观测失败绝不影响任务结果」的契约）。
    maintenance_tasks._record_success(_FakeTask("app.x", is_eager=False))


def test_task_stat_signal_increments_and_skips_eager(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Celery 信号计数：非 eager HINCRBY，eager 跳过（口径与 _record_success 一致）。"""
    from app.tasks import celery_app as celery_module

    calls: list[tuple] = []

    class FakeClient:
        def hincrby(self, key, field, amount=1):  # noqa: ANN001
            calls.append((key, field, amount))

    monkeypatch.setattr(
        "app.db.redis.get_sync_redis_client", lambda: FakeClient()
    )

    celery_module._bump_task_stat("success", _FakeTask("app.x", is_eager=False))
    assert calls == [("taskflow:celery:task_stats", "success", 1)]

    calls.clear()
    celery_module._bump_task_stat("failure", _FakeTask("app.x", is_eager=True))
    assert calls == []


# ---------------------------------------------------------------------------
# 4. 采集器自身的健壮性（保持 core/tasks 层 100% 覆盖）
# ---------------------------------------------------------------------------


def test_register_collector_is_idempotent() -> None:
    """重复 import/注册不得炸掉（configure 与测试多次导入的现实场景）。"""
    from app.core import metrics as metrics_module

    metrics_module.register_collector()  # 已注册 → ValueError 被吞


def test_collector_survives_missing_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    """engine 不可用（裁剪环境）→ 池指标空、其余指标照常产出。"""
    from app.core import metrics as metrics_module

    monkeypatch.setattr(metrics_module, "_get_engine", lambda: None)
    families = {f.name for f in metrics_module._collector.collect()}
    assert "taskflow_db_pool_connections" in families
    assert "taskflow_celery_queue_depth" in families


def test_collector_reads_redis_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """采集器把 Redis 里的队列深度/任务计数/维护时间戳转成指标族。"""
    from app.core import metrics as metrics_module

    class FakePipe:
        def llen(self, _key):
            return self

        def hgetall(self, _key):
            return self

        def execute(self):
            return [7, {"success": "12", "failure": "3"},
                    {"app.archive_operation_logs": "1726488000.0"}]

    class FakeClient:
        def pipeline(self, transaction=False):
            return FakePipe()

    import app.db.redis as db_redis

    monkeypatch.setattr(db_redis, "get_sync_redis_client", lambda: FakeClient())
    by_name = {f.name: f for f in metrics_module._collector.collect()}
    assert by_name["taskflow_celery_queue_depth"].samples[0].value == 7
    # CounterMetricFamily 的 family name 去掉 _total 后缀（样本名才带 _total）。
    task_values = {
        smp.labels["state"]: smp.value
        for smp in by_name["taskflow_celery_tasks"].samples
    }
    assert task_values == {"success": 12, "failure": 3, "retry": 0}
    last = by_name["taskflow_maintenance_last_success_timestamp"].samples
    assert last[0].labels["task"] == "app.archive_operation_logs"


def test_bump_task_stat_never_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """Redis 故障时信号计数静默吞掉（观测不能影响任务结果）。"""

    def forbidden():  # pragma: no cover — 被调用即抛
        raise AssertionError("redis down")

    import app.db.redis as db_redis

    monkeypatch.setattr(db_redis, "get_sync_redis_client", forbidden)
    from app.tasks import celery_app as celery_module

    celery_module._bump_task_stat("success", _FakeTask("app.x", is_eager=False))
