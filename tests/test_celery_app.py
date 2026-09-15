"""TASK-048 — Celery App / Worker 基础设施测试.

分两层：
1. **配置契约**（不依赖 Redis）：Broker/Backend 派生规则、JSON-only 序列化、
   规则 §8 的可靠性参数（acks_late / reject_on_worker_lost / prefetch /
   timeout）、Redis 键前缀——这些配置一旦被人"顺手改掉"，at-least-once
   语义或键约定就静默失效，必须用测试钉住。
2. **任务执行**（eager 模式，不依赖 Redis）：``app.ping`` 可注册、可执行。

真实 Broker → Worker → Backend 链路由 compose 部署冒烟验证
（``docker compose up`` + ``celery inspect ping`` + 提交 ping 任务），
pytest 不负责拉起 Worker。

注意：``app.core.config.get_settings`` 是 lru_cache 的；本文件凡是涉及
覆盖配置的用例都必须先 ``cache_clear`` 再重建 Celery 实例，结束时再次
``cache_clear`` 还原（与 tests/test_rate_limit.py 的
``_reset_settings_cache`` 同理，此处按需局部处理）。
"""

import os
import subprocess
import sys

import pytest

from app.core.config import get_settings
from app.tasks.celery_app import CELERY_KEY_PREFIX, celery_app, create_celery_app

REDIS_URL = "redis://127.0.0.1:6389/0"


@pytest.fixture(autouse=True)
def _fresh_settings_cache():
    """每个用例前后都清掉 get_settings 的 lru_cache。

    前清：用例内 monkeypatch 的环境变量能被 get_settings() 看到；
    后清：不让用例期间的临时配置泄漏进其它测试文件的缓存。
    """
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _no_eager_leak():
    """eager 开关只在单个用例内生效，避免污染模块级 celery_app。"""
    yield
    celery_app.conf.task_always_eager = False


# ---------------------------------------------------------------------------
# 1. Broker / Backend 派生规则（DECISIONS 026）
# ---------------------------------------------------------------------------

def test_broker_and_backend_default_to_redis_url():
    app = create_celery_app()
    assert app.conf.broker_url == REDIS_URL
    assert app.conf.result_backend == REDIS_URL


def test_explicit_broker_and_backend_override(monkeypatch):
    monkeypatch.setenv("CELERY_BROKER_URL", "redis://broker.internal:6379/2")
    monkeypatch.setenv("CELERY_RESULT_BACKEND", "redis://backend.internal:6379/3")
    app = create_celery_app()
    assert app.conf.broker_url == "redis://broker.internal:6379/2"
    assert app.conf.result_backend == "redis://backend.internal:6379/3"


# ---------------------------------------------------------------------------
# 2. 序列化安全（JSON only，禁 pickle）
# ---------------------------------------------------------------------------

def test_json_only_serialization():
    app = create_celery_app()
    assert app.conf.task_serializer == "json"
    assert app.conf.result_serializer == "json"
    assert set(app.conf.accept_content) == {"json"}


# ---------------------------------------------------------------------------
# 3. 可靠性参数（规则 §8：retry / timeout / failure / idempotency）
# ---------------------------------------------------------------------------

def test_at_least_once_delivery_semantics():
    """acks_late + reject_on_worker_lost + prefetch=1 = at-least-once 投递。"""
    app = create_celery_app()
    assert app.conf.task_acks_late is True
    assert app.conf.task_reject_on_worker_lost is True
    assert app.conf.worker_prefetch_multiplier == 1


def test_track_started_is_enabled():
    assert celery_app.conf.task_track_started is True


def test_time_limits_wired_from_settings(monkeypatch):
    monkeypatch.setenv("CELERY_TASK_SOFT_TIME_LIMIT", "11")
    monkeypatch.setenv("CELERY_TASK_TIME_LIMIT", "22")
    app = create_celery_app()
    assert app.conf.task_soft_time_limit == 11
    assert app.conf.task_time_limit == 22
    # 硬超时必须大于软超时，否则任务永远得不到"自行清理"的机会。
    assert app.conf.task_time_limit > app.conf.task_soft_time_limit


def test_default_time_limits_are_sane():
    app = create_celery_app()
    assert 0 < app.conf.task_soft_time_limit < app.conf.task_time_limit
    assert app.conf.result_expires > 0


# ---------------------------------------------------------------------------
# 4. Redis 键约定（TASK-045：taskflow:<purpose>:<id>）
# ---------------------------------------------------------------------------

def test_redis_key_prefix_applies_to_broker_and_backend():
    app = create_celery_app()
    assert app.conf.broker_transport_options.get("global_keyprefix") == CELERY_KEY_PREFIX
    assert (
        app.conf.result_backend_transport_options.get("global_keyprefix")
        == CELERY_KEY_PREFIX
    )
    assert CELERY_KEY_PREFIX == "taskflow:"


# ---------------------------------------------------------------------------
# 5. 任务执行（eager 模式，不依赖 Redis）
# ---------------------------------------------------------------------------

def test_ping_task_executes_eagerly():
    celery_app.conf.task_always_eager = True
    result = celery_app.tasks["app.ping"].apply()
    assert result.get() == "pong"


def test_ping_task_is_registered():
    assert "app.ping" in celery_app.tasks


# ---------------------------------------------------------------------------
# 6. import 安全：导入模块不得发起任何网络连接
# ---------------------------------------------------------------------------

def test_module_import_does_not_connect_at_import():
    """在 REDIS_URL 指向不可达地址的子进程里导入模块——Celery 连接是惰性的，
    import 必须即时成功；若有人在模块顶层加 eager 连接/预连接，这里会挂。"""
    env = dict(os.environ)
    env["REDIS_URL"] = "redis://127.0.0.1:1/0"  # 端口 1：立即拒绝连接
    env.pop("CELERY_BROKER_URL", None)
    env.pop("CELERY_RESULT_BACKEND", None)
    proc = subprocess.run(
        [sys.executable, "-c", "import app.tasks.celery_app; print('IMPORT_OK')"],
        capture_output=True,
        text=True,
        env=env,
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert "IMPORT_OK" in proc.stdout
