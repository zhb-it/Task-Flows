"""生产配置自检（TASK-091，§51 补充）。

四类危险错配各一条拒绝用例、合法配置放行、开发环境不检查，外加两条
「自检真的被执行」的验证：

* 收集全部问题一次报出（拒绝运维「改一项撞一项」的循环）；
* 真实子进程 ``import app.main`` 在 ``APP_ENV=production`` + ``DEBUG=true``
  下以非零退出（验证 main.py 的接入点，不只是函数本身的行为）。

用例直接构造 ``Settings(**kwargs)``，显式覆盖所有被检字段——Settings 会读
本地 `.env`，显式传参保证用例不依赖开发机上的具体 `.env` 内容。
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.core.config import (
    MIN_JWT_SECRET_LENGTH,
    Settings,
    collect_production_config_problems,
    validate_production_config,
)

REPO_ROOT = Path(__file__).resolve().parents[1]

STRONG_SECRET = "x" * MIN_JWT_SECRET_LENGTH
SAFE_DATABASE_URL = "postgresql+asyncpg://taskflow:s3cret-db@db:5432/taskflow"


def _settings(**overrides) -> Settings:
    """一份完全合法的生产配置基线，单条错配用例在其上只改一个字段。"""
    fields = {
        "app_env": "production",
        "debug": False,
        "jwt_secret_key": STRONG_SECRET,
        "database_url": SAFE_DATABASE_URL,
        "trust_proxy_headers": False,
        "trusted_proxy_ips": "",
        # 与 .env / 环境隔离无关紧要，但 extra="ignore" 下多传无害的字段
        # 一律不传，保持用例聚焦被检项。
    }
    fields.update(overrides)
    return Settings(**fields)


def test_debug_true_rejected() -> None:
    problems = collect_production_config_problems(_settings(debug=True))
    assert len(problems) == 1
    assert "DEBUG" in problems[0]


def test_default_jwt_secret_rejected() -> None:
    problems = collect_production_config_problems(
        _settings(jwt_secret_key="change-me")
    )
    assert len(problems) == 1
    assert "JWT_SECRET_KEY" in problems[0]
    assert "默认值" in problems[0]


def test_short_jwt_secret_rejected() -> None:
    problems = collect_production_config_problems(
        _settings(jwt_secret_key="too-short")
    )
    assert len(problems) == 1
    assert "JWT_SECRET_KEY" in problems[0]
    assert str(MIN_JWT_SECRET_LENGTH) in problems[0]
    assert "9" in problems[0]  # 当前长度被点名


def test_default_database_password_rejected() -> None:
    problems = collect_production_config_problems(
        _settings(database_url="postgresql+asyncpg://postgres:postgres@db:5432/taskflow")
    )
    assert len(problems) == 1
    assert "DATABASE_URL" in problems[0]


def test_trust_proxy_without_ips_rejected() -> None:
    problems = collect_production_config_problems(
        _settings(trust_proxy_headers=True, trusted_proxy_ips="")
    )
    assert len(problems) == 1
    assert "TRUSTED_PROXY_IPS" in problems[0]


def test_valid_production_config_passes() -> None:
    # 合法配置（含显式信任网段）不产生任何问题，validate 也不抛。
    ok = _settings(trust_proxy_headers=True, trusted_proxy_ips="172.28.0.0/24")
    assert collect_production_config_problems(ok) == []
    validate_production_config(ok)  # 不抛即通过


def test_development_environment_not_checked() -> None:
    # 开发环境保留「零配置可用」：四类错配叠加也全部放行。
    broken = _settings(
        app_env="development",
        debug=True,
        jwt_secret_key="change-me",
        database_url="postgresql+asyncpg://postgres:postgres@db:5432/taskflow",
        trust_proxy_headers=True,
    )
    assert collect_production_config_problems(broken) == []
    validate_production_config(broken)  # 不抛即通过


def test_all_problems_reported_at_once() -> None:
    # 收集式而非 fail-fast：四类错配一次全部点名，运维一轮改完。
    broken = _settings(
        debug=True,
        jwt_secret_key="change-me",
        database_url="postgresql+asyncpg://postgres:postgres@db:5432/taskflow",
        trust_proxy_headers=True,
    )
    problems = collect_production_config_problems(broken)
    assert len(problems) == 4
    joined = "\n".join(problems)
    for item in ("DEBUG", "JWT_SECRET_KEY", "DATABASE_URL", "TRUSTED_PROXY_IPS"):
        assert item in joined


def test_validate_raises_with_named_items() -> None:
    broken = _settings(debug=True)
    with pytest.raises(RuntimeError) as excinfo:
        validate_production_config(broken)
    message = str(excinfo.value)
    assert "拒绝启动" in message
    assert "DEBUG" in message


def test_import_main_refuses_to_start_in_production() -> None:
    """端到端：uvicorn 的第一步是 import app.main，错配在这一步就退出。

    真实子进程 + 环境变量（环境变量优先级高于 .env，不受开发机 .env 干扰）。
    """
    env = {
        **os.environ,
        "APP_ENV": "production",
        "DEBUG": "true",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    proc = subprocess.run(
        [sys.executable, "-c", "import app.main"],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode != 0, "错配配置必须拒绝启动"
    output = proc.stdout + proc.stderr
    assert "生产配置自检失败" in output
    assert "DEBUG" in output


def test_import_main_starts_in_production_with_valid_config() -> None:
    """端到端反例：合法生产配置下 import app.main 正常完成（退出码 0）。"""
    env = {
        **os.environ,
        "APP_ENV": "production",
        "DEBUG": "false",
        "JWT_SECRET_KEY": STRONG_SECRET,
        "DATABASE_URL": SAFE_DATABASE_URL,
        "TRUST_PROXY_HEADERS": "false",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    proc = subprocess.run(
        [sys.executable, "-c", "import app.main"],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, f"合法生产配置应能启动：\n{proc.stdout}\n{proc.stderr}"
