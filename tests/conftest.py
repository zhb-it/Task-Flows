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

import os

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.core.tenant_context import (
    reset_current_tenant_id,
    set_current_tenant_id,
)
from app.models.tenant import Tenant

import app.services.task as task_service

#: 与直连测试文件一致的默认测试库（宿主 5433）；可通过 DATABASE_URL 覆盖。
_TEST_DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql+asyncpg://postgres:postgres@127.0.0.1:5433/taskflow"
)
_DEFAULT_TENANT_SLUG = "default"


@pytest_asyncio.fixture(scope="module")
async def _rbac_test_engine():
    """模块级引擎：仅供默认租户上下文夹具查询默认租户 id，连接复用。"""
    engine = create_async_engine(_TEST_DATABASE_URL, poolclass=NullPool)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def _default_tenant_context(request, _rbac_test_engine):
    """所有测试默认运行在**默认租户**上下文（TASK-096 租户化 RBAC 后必需）。

    RBAC 三表（roles / role_permissions / user_roles）现在带 tenant_id 且受
    ``before_flush`` 注入约束——不显式置租户上下文时新建角色/授权会因 tenant_id
    为 NULL 触发表约束。本夹具把 ContextVar 置为默认租户 id，使直连 CRUD 的
    测试（如 ``test_rbac_crud`` 的 ``create_role``）与原先「全局 RBAC」语义等价。

    幂等/安全：查不到默认租户（如未迁移的库）时退化为不设置上下文；离线单测
    不受影响。每个测试结束还原 ContextVar。

    例外：``tests/test_tenant_isolation.py`` 显式断言「无租户上下文」行为
    （TASK-095 的越权隔离实证），其用例自行管理 ContextVar，故本夹具对该
    模块跳过，避免污染其 no-context 断言与跨租户种子。
    """
    if request.module is not None and request.module.__name__.endswith(
        ("test_tenant_isolation", "test_rbac_tenant")
    ):
        yield
        return
    try:
        async with async_sessionmaker(
            _rbac_test_engine, expire_on_commit=False
        )() as s:
            tenant_id = (
                await s.execute(
                    select(Tenant.id).where(Tenant.slug == _DEFAULT_TENANT_SLUG)
                )
            ).scalar_one_or_none()
    except Exception:  # noqa: BLE001 — 连不上库时退化为不置上下文，绝不拖垮测试
        tenant_id = None

    if tenant_id is None:
        yield
        return

    token = set_current_tenant_id(tenant_id)
    try:
        yield
    finally:
        reset_current_tenant_id(token)


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

