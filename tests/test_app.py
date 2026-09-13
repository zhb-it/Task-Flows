"""Smoke tests for the FastAPI application shell (TASK-003).

These tests must run without PostgreSQL or Redis, because `app.main` does
not open any external connection at import time.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import app


def test_app_is_fastapi_instance() -> None:
    assert isinstance(app, FastAPI)


def test_root_endpoint() -> None:
    client = TestClient(app)
    resp = client.get("/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "TaskFlow Pro"
    assert "version" in data
    assert "env" in data


def test_health_endpoint() -> None:
    """`/health` must respond 200 and report dependency status structure.

    It does not require live PostgreSQL/Redis: when they are unreachable the
    body reports ``database``/``redis`` as ``"down"`` but the endpoint still
    returns 200 (the process is alive).
    """
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in {"ok", "degraded"}
    assert data["database"] in {"up", "down"}
    assert data["redis"] in {"up", "down"}
    assert "app" in data
    assert "version" in data
