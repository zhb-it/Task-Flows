"""健康探针族测试（TASK-088，规格 §32）。

覆盖四个探针端点的正常路径与三种依赖降级路径。探测函数是
``app.main`` 的模块级函数，端点在调用时按名字解析模块全局——
因此 ``monkeypatch.setattr(app.main, "_check_database", fake)`` 即可
打桩，不必真停 PostgreSQL/Redis 容器。

零依赖运行：全部用例都打桩（不打桩的正向路径由集成环境里的
``test_app.py::test_health_endpoint`` 与全量套件覆盖），本文件不要求
真实 PostgreSQL/Redis 可达。
"""

from typing import Callable

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.main import app

Probe = Callable[[], bool]


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def _stub_probes(
    monkeypatch: pytest.MonkeyPatch, db_up: bool, redis_up: bool
) -> None:
    """把两个探测函数替换成同步返回桩值（保持 async 签名）。"""

    async def fake_check_database() -> bool:
        return db_up

    async def fake_check_redis() -> bool:
        return redis_up

    monkeypatch.setattr(main_module, "_check_database", fake_check_database)
    monkeypatch.setattr(main_module, "_check_redis", fake_check_redis)


# ---------------------------------------------------------------------------
# 正常路径：依赖全部可用
# ---------------------------------------------------------------------------


def test_health_live_is_always_200(client: TestClient) -> None:
    """`/health/live` 只回答「进程活着」，恒 200，与依赖状态无关。"""
    resp = client.get("/health/live")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_health_live_does_not_probe_dependencies(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """liveness 刻意不探测依赖：把探针替换成「必炸」函数也不影响它。"""

    async def explode() -> bool:
        raise AssertionError("liveness 不得探测依赖")

    monkeypatch.setattr(main_module, "_check_database", explode)
    monkeypatch.setattr(main_module, "_check_redis", explode)
    resp = client.get("/health/live")
    assert resp.status_code == 200


def test_health_ready_ok_when_dependencies_up(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_probes(monkeypatch, db_up=True, redis_up=True)
    resp = client.get("/health/ready")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "database": "up", "redis": "up"}


def test_health_db_ok_when_database_up(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_probes(monkeypatch, db_up=True, redis_up=False)
    resp = client.get("/health/db")
    assert resp.status_code == 200
    assert resp.json() == {"database": "up"}


def test_health_redis_ok_when_redis_up(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_probes(monkeypatch, db_up=False, redis_up=True)
    resp = client.get("/health/redis")
    assert resp.status_code == 200
    assert resp.json() == {"redis": "up"}


# ---------------------------------------------------------------------------
# 降级路径：DB 不可用 / Redis 不可用 / 两者都不可用
# ---------------------------------------------------------------------------


def test_health_ready_503_when_database_down(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_probes(monkeypatch, db_up=False, redis_up=True)
    resp = client.get("/health/ready")
    assert resp.status_code == 503
    assert resp.json() == {"status": "not_ready", "database": "down", "redis": "up"}


def test_health_ready_503_when_redis_down(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_probes(monkeypatch, db_up=True, redis_up=False)
    resp = client.get("/health/ready")
    assert resp.status_code == 503
    assert resp.json() == {"status": "not_ready", "database": "up", "redis": "down"}


def test_health_ready_503_when_both_down(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_probes(monkeypatch, db_up=False, redis_up=False)
    resp = client.get("/health/ready")
    assert resp.status_code == 503
    assert resp.json() == {"status": "not_ready", "database": "down", "redis": "down"}


def test_health_db_503_when_database_down(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_probes(monkeypatch, db_up=False, redis_up=True)
    resp = client.get("/health/db")
    assert resp.status_code == 503
    assert resp.json() == {"database": "down"}


def test_health_redis_503_when_redis_down(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_probes(monkeypatch, db_up=True, redis_up=False)
    resp = client.get("/health/redis")
    assert resp.status_code == 503
    assert resp.json() == {"redis": "down"}


# ---------------------------------------------------------------------------
# 兼容不变量：`/health` 行为不变
# ---------------------------------------------------------------------------


def test_health_stays_200_and_reports_dependency_status(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """依赖挂掉时 `/health` 仍 200（liveness 语义），body 标 down。

    既有测试（test_app.py、test_quality_gaps.py）与 compose healthcheck
    的旧版依赖此行为；TASK-088 明确要求它不变。
    """
    _stub_probes(monkeypatch, db_up=False, redis_up=True)
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "degraded"
    assert data["database"] == "down"
    assert data["redis"] == "up"


def test_health_response_structure_unchanged(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`/health` 的响应结构不得随探针族新增而漂移。"""
    _stub_probes(monkeypatch, db_up=True, redis_up=True)
    data = client.get("/health").json()
    assert set(data) == {
        "status",
        "app",
        "version",
        "env",
        "database",
        "redis",
    }


# ---------------------------------------------------------------------------
# 安全不变量：探针端点免认证
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", ["/health/live", "/health/ready", "/health/db", "/health/redis"])
def test_probe_endpoints_require_no_auth(client: TestClient, path: str) -> None:
    """编排器探针不带令牌，端点必须可匿名访问（非 401/403）。"""
    resp = client.get(path)
    assert resp.status_code not in {401, 403}
