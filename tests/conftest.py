"""测试套件的全局夹具。

## 为什么默认关闭限流

TASK-046 引入的 `RateLimitMiddleware` 对**每个** `/api/v1` 请求生效。整个测试
套件里的客户端都来自同一个来源地址（`ASGITransport` 默认 `127.0.0.1`，
或各文件自建的 `testclient`），因此所有测试文件**共享同一个 IP 维度的限流键**。
默认额度是 60 次/60 秒，而单个文件（如 `test_refresh.py`）的请求数就可能超过它——
表现为「本该 401 的断言拿到了 429」（TASK-046 全量回归时真实出现过 2 个这样的失败）。

这不是被实现测出来的缺陷，而是**测试之间的隐式耦合**：一个测试的行为取决于
它之前跑过多少测试。修法有两条：

1. 给每个测试文件各自的 IP（`ASGITransport(client=...)`）——能解决 IP 维度，
   但无法解决「同一文件内请求数超额度」，且要改动 40 个既有文件；
2. **默认关闭限流，只有限流自己的测试显式打开**——一行全局配置解决全部耦合，
   且语义清晰：其他测试关心的是业务行为，不是限流。

采用方案 2。限流本身的测试（`tests/test_rate_limit.py`）在用例内用
`monkeypatch.setattr(settings, "rate_limit_enabled", True)` 显式打开，
因此覆盖率不受影响。
"""

import pytest

from app.core.config import get_settings

import app.services.task as task_service


@pytest.fixture(autouse=True)
def _disable_rate_limit_by_default(monkeypatch):
    """全测试套件默认关闭限流，避免跨文件共享 IP 配额造成的隐式耦合。

    限流测试通过在自己的用例内再次 `monkeypatch.setattr(..., True)` 覆盖，
    因此这个默认值不会削弱限流的测试覆盖（monkeypatch 在用例结束时自动还原）。
    """
    settings = get_settings()
    monkeypatch.setattr(settings, "rate_limit_enabled", False, raising=False)
    yield


@pytest.fixture(autouse=True)
def _silence_request_access_logs(monkeypatch):
    """默认关闭请求访问日志（TASK-056），避免 600+ 用例的请求日志刷屏。

    与 ``rate_limit_enabled`` 同一个套路：绝大多数测试关心的是业务行为，
    不是「每个请求都打了一条日志」。访问日志自身的测试
    （``tests/test_logging.py``）在用例内显式打开。
    """
    settings = get_settings()
    monkeypatch.setattr(settings, "log_requests", False, raising=False)
    yield


@pytest.fixture(autouse=True)
def _isolate_notification_dispatch(monkeypatch):
    """通知派发是 Celery best-effort side-effect，测试里不真连 broker。

    把 ``TaskService._dispatch_notification`` 替换成 no-op，避免测试依赖
    Redis/Celery 且保持确定性。TASK-053 的派发接线由 ``notification_dispatch``
    间谍夹具局部覆盖验证——该夹具请求时会在本 autouse 之后再次 setattr，
    故同一用例内以间谍的最终值为准（不影响 test_notification_task.py 直接
    调 ``.delay`` 验证 §24 真实执行的用例）。
    """
    monkeypatch.setattr(task_service, "_dispatch_notification", lambda *a, **k: None)


@pytest.fixture
def notification_dispatch(monkeypatch):
    """间谍：捕获 ``TaskService._dispatch_notification`` 的调用实参。

    返回 ``list[(args, kwargs)]``，仅当用例显式请求时启用（覆盖上面的
    autouse no-op）。可在用例中 ``.clear()`` 重置，隔离某一步的派发断言。
    """
    calls: list = []

    def _spy(*args, **kwargs):
        calls.append((args, kwargs))

    monkeypatch.setattr(task_service, "_dispatch_notification", _spy)
    return calls

