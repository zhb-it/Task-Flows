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


@pytest.fixture(autouse=True)
def _disable_rate_limit_by_default(monkeypatch):
    """全测试套件默认关闭限流，避免跨文件共享 IP 配额造成的隐式耦合。

    限流测试通过在自己的用例内再次 `monkeypatch.setattr(..., True)` 覆盖，
    因此这个默认值不会削弱限流的测试覆盖（monkeypatch 在用例结束时自动还原）。
    """
    settings = get_settings()
    monkeypatch.setattr(settings, "rate_limit_enabled", False, raising=False)
    yield
