"""生产 compose 契约测试（TASK-059；开发文档 §4 / §29–§31 / §33）。

这些用例**不启动 Docker**：只解析 `docker-compose.prod.yml`，把「生产环境必须
成立的性质」固化成断言。理由是这类配置最容易在后续改动中被静默破坏——
最典型的两种情况：

1. **复制粘贴开发 compose**：开发版把 5433/6389 发布到宿主、把 DB 密码当可选项，
   一旦被复制进生产文件，数据库就会直接暴露在宿主上，而且没有任何测试会报警；
2. **compose 的合并语义陷阱**：`ports` 在多文件合并时是**拼接**而不是覆盖，
   所以「用覆盖文件去掉开发版的端口」这条路根本走不通（这也是本 TASK 选择
   独立完整文件的原因，见 DECISIONS 039）。

> TASK-060 更新：本文件原本断言「app 绑宿主回环 127.0.0.1」并显式排除 nginx
> （那时 nginx 尚未引入）。接入 Nginx 后暴露面收敛为**唯一入口**，app 的宿主
> 端口被整体去掉；nginx 的配置契约放在 `tests/test_nginx_config.py`，这里只保留
> 「服务集合 / 端口暴露面 / 环境变量 / 持久化 / 运行保障」这些 compose 层面的性质。

真正「拉起容器验证」的部分属冒烟测试（见 TESTING.md 的 TASK-059 / TASK-060
章节），这里只保证静态契约，因此无需 Docker 环境、可在 CI 中运行。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from app.core.config import Settings

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROD_COMPOSE = PROJECT_ROOT / "docker-compose.prod.yml"
DEV_COMPOSE = PROJECT_ROOT / "docker-compose.yml"
ENV_EXAMPLE = PROJECT_ROOT / ".env.example"

#: 生产栈应有的服务（TASK-060 起包含 nginx —— 它是 §31 要求的唯一对外入口）。
EXPECTED_SERVICES = {"app", "celery_worker", "nginx", "postgres", "redis"}

#: 需要健康检查的服务——缺了健康检查，depends_on 的 service_healthy 条件就形同虚设。
SERVICES_WITH_HEALTHCHECK = {"app", "celery_worker", "nginx", "postgres", "redis"}

#: 允许挂载宿主路径的**唯一**例外：nginx 的配置文件（只读）。
#:
#: 「生产不挂宿主源码目录」的本意是「镜像自带代码，不在运行时从宿主机注入代码」；
#: nginx 的配置属于**部署配置**（不是应用源码），只读挂载是业界标准做法。
#: 例外写在这里而不是放宽整条规则：新增任何宿主挂载都必须显式修改本常量。
ALLOWED_HOST_MOUNT_SUFFIXES = ("nginx/nginx.conf:/etc/nginx/nginx.conf:ro",)

#: 由 **ASGI server / 运行时**读取、而非应用 Settings 的环境变量。
#:
#: 下面的 `test_env_var_names_are_real_settings_fields` 用 Settings 字段清单拦截
#: 「拼错名字导致配置静默不生效」；这几个是明确不属于 Settings 的运行时变量，
#: 因此显式列出（不是放宽规则，而是把例外的理由写下来）。
RUNTIME_ONLY_ENV_VARS = {
    # uvicorn 的 proxy-headers 信任网段；TASK-060 显式置空，让应用成为客户端 IP
    # 的唯一判定点（见 DECISIONS 040）。
    "FORWARDED_ALLOW_IPS",
}


@pytest.fixture(scope="module")
def prod_text() -> str:
    """生产 compose 的原始文本（用于断言插值语法等 YAML 层面看不到的内容）。"""
    return PROD_COMPOSE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def prod_config(prod_text: str) -> dict:
    """解析后的生产 compose。锚点（`<<: *x`）由 SafeLoader 按 YAML 合并键展开。"""
    return yaml.safe_load(prod_text)


@pytest.fixture(scope="module")
def prod_services(prod_config: dict) -> dict:
    return prod_config["services"]


@pytest.fixture(scope="module")
def dev_services() -> dict:
    return yaml.safe_load(DEV_COMPOSE.read_text(encoding="utf-8"))["services"]


# ---------------------------------------------------------------------------
# 1. 文件与项目隔离
# ---------------------------------------------------------------------------


def test_prod_compose_exists(prod_text: str) -> None:
    """§4 文件清单要求仓库根目录存在 docker-compose.prod.yml。"""
    assert PROD_COMPOSE.is_file()
    assert prod_text.strip(), "生产 compose 不应为空文件"


def test_project_name_isolates_prod_from_dev(prod_config: dict) -> None:
    """独立的 compose 项目名 → 网络 / 卷 / 容器名都带前缀，不会串用开发栈。

    开发版没有顶层 name，项目名回落为目录名（task-flow）；生产若同名，两套栈
    会共用 `task-flow_postgres_data`——在开发机上启动生产 compose 就会连到
    开发库，是最危险的一类「看起来正常」的串用。
    """
    assert prod_config["name"] == "taskflow-prod"


def test_prod_services_do_not_set_container_name(prod_services: dict) -> None:
    """不设 container_name：固定名字既阻碍扩容，也会和开发栈的同名容器冲突。"""
    for name, service in prod_services.items():
        assert "container_name" not in service, f"{name} 不应硬编码 container_name"


def test_services_match_scope(prod_services: dict) -> None:
    """服务集合与 §29/§31 的范围一致；nginx 是唯一对外入口（TASK-060）。"""
    assert set(prod_services) == EXPECTED_SERVICES
    assert "nginx" in prod_services


def test_every_dev_service_is_covered_by_prod(prod_services: dict, dev_services: dict) -> None:
    """生产栈必须是开发栈的超集（否则某个服务在生产里根本不存在）。"""
    missing = set(dev_services) - set(prod_services)
    assert not missing, f"生产 compose 缺少服务: {sorted(missing)}"


def test_prod_does_not_reuse_dev_image_tag(prod_services: dict, dev_services: dict) -> None:
    """生产镜像用独立 tag：重建开发镜像不会顺手改掉生产镜像。

    只比较**本项目自建**的镜像（带 `build:` 的服务）；postgres / redis 用的是
    官方镜像，两套栈共用同一个 tag 是正常的。
    """
    def own_tags(services: dict) -> set[str]:
        return {s["image"] for s in services.values() if "build" in s and "image" in s}

    prod_tags, dev_tags = own_tags(prod_services), own_tags(dev_services)
    assert prod_tags, "生产 compose 应当自建镜像"
    assert prod_tags & dev_tags == set(), f"生产与开发共用了镜像 tag: {prod_tags & dev_tags}"
    assert all(not tag.endswith(":latest") for tag in prod_tags), "生产不应使用 latest 标签"


# ---------------------------------------------------------------------------
# 2. 端口暴露面（生产最容易出事的地方）
# ---------------------------------------------------------------------------


def test_postgres_does_not_publish_host_port(prod_services: dict) -> None:
    """数据库只在 compose 网络内可达；发布到宿主等于把库暴露给整台机器。"""
    assert "ports" not in prod_services["postgres"]


def test_redis_does_not_publish_host_port(prod_services: dict) -> None:
    """Redis 无认证（§21 未配置 requirepass），更不能发布到宿主。"""
    assert "ports" not in prod_services["redis"]


def test_app_and_database_ports_are_not_published(prod_services: dict, prod_text: str) -> None:
    """只有 nginx 发布宿主端口（TASK-060）。

    TASK-059 时 app 绑 `127.0.0.1:${APP_PORT:-8000}`；接入 Nginx 后这个回环端口
    被**整体去掉**——保留它会让「宿主上的进程可以绕过反代直连应用并伪造
    X-Forwarded-For」重新成为可能。这里断言的是「除 nginx 外无人发布端口」，
    比逐个服务断言更难被绕过。
    """
    publishers = {name for name, svc in prod_services.items() if svc.get("ports")}
    assert publishers == {"nginx"}, f"除 nginx 外仍有服务发布宿主端口: {publishers}"
    assert "${NGINX_HTTP_PORT:-80}" in prod_text


def test_containers_do_not_receive_env_file(prod_services: dict) -> None:
    """不把宿主的 .env 整体塞进容器。

    `.env` 是给**宿主机**用的（DATABASE_URL 指向 127.0.0.1:5433、REDIS_URL 指向
    127.0.0.1:6389）。用 `env_file` 注入会覆盖 compose 里正确拼好的容器内地址，
    容器随即连不上任何东西——这类故障排查成本极高，故用测试禁掉。
    """
    for name, service in prod_services.items():
        assert "env_file" not in service, f"{name} 不应使用 env_file 注入宿主 .env"


# ---------------------------------------------------------------------------
# 3. 生产环境变量
# ---------------------------------------------------------------------------


def test_app_runs_in_production_env(prod_services: dict, prod_text: str) -> None:
    """§33「生产环境采用结构化日志格式」依赖 APP_ENV 推导（logging_config）。

    `LOG_FORMAT=auto` 在 `APP_ENV=production` 下解析为 json（TASK-056 / DECISIONS
    037）。这里断言的是**默认值**仍是 auto —— 运维可显式覆盖，但默认走 JSON。
    """
    app_env = prod_services["app"]["environment"]
    assert app_env["APP_ENV"] == "production"
    assert "LOG_FORMAT: ${LOG_FORMAT:-auto}" in prod_text


def test_debug_is_disabled(prod_services: dict) -> None:
    """DEBUG 控制 SQLAlchemy echo：开着会让每条 SQL 都写进日志（§9 敏感日志）。"""
    app_env = prod_services["app"]["environment"]
    assert str(app_env["DEBUG"]).lower() == "false"


def test_access_log_and_rate_limit_enabled(prod_services: dict) -> None:
    """访问日志（§33）与限流（§22）在生产必须开启。"""
    app_env = prod_services["app"]["environment"]
    assert str(app_env["LOG_REQUESTS"]).lower() == "true"
    assert str(app_env["RATE_LIMIT_ENABLED"]).lower() == "true"


def test_required_secrets_fail_fast(prod_text: str) -> None:
    """必需密钥用 ${VAR:?} 必填语法：缺失/为空时 compose 直接拒绝启动。

    这是「启动即失败」策略的落地——生产最怕的不是崩溃，而是带着开发默认密钥
    静默上线（Token 签发权等同公开）。
    """
    assert "${JWT_SECRET_KEY:?" in prod_text
    assert "${POSTGRES_PASSWORD:?" in prod_text


def test_no_insecure_fallback_for_secrets(prod_text: str) -> None:
    """两个密钥都不得带 `:-默认值` 回落（`:-change-me` 是开发版的写法）。

    只看**非注释行**：注释里提到「开发默认密钥 change-me」是在解释为什么不能
    回落，本身无害；真正要拦住的是可执行的回落语法。
    """
    code_lines = [
        line for line in prod_text.splitlines() if not line.lstrip().startswith("#")
    ]
    code = "\n".join(code_lines)
    assert "change-me" not in code
    assert not re.search(r"\$\{JWT_SECRET_KEY:-", code)
    assert not re.search(r"\$\{POSTGRES_PASSWORD:-", code)


def test_env_var_names_are_real_settings_fields(prod_services: dict) -> None:
    """传给容器的每个环境变量都必须对应一个真实的 Settings 字段。

    拼错名字（如 `LOG_REQUEST`）不会报错，只会静默地按默认值运行——正是这类
    「配置不生效」最难发现，故用 Settings 的字段清单做交叉校验。
    少数由运行时（ASGI server）读取的变量在 `RUNTIME_ONLY_ENV_VARS` 里显式列出。
    """
    known = {field.upper() for field in Settings.model_fields} | RUNTIME_ONLY_ENV_VARS
    for service_name in ("app", "celery_worker"):
        for key in prod_services[service_name]["environment"]:
            assert key.upper() in known, f"{service_name} 传了未知环境变量: {key}"


def test_celery_worker_gets_same_environment_as_app(prod_services: dict) -> None:
    """worker 与 app 同镜像同配置：用锚点复用，避免「改了 app 忘了改 worker」。"""
    app_env = dict(prod_services["app"]["environment"])
    worker_env = dict(prod_services["celery_worker"]["environment"])
    assert worker_env == app_env


def test_env_example_documents_prod_required_keys() -> None:
    """`.env.example` 必须包含生产必填项，否则新克隆的仓库无法满足生产 compose。"""
    text = ENV_EXAMPLE.read_text(encoding="utf-8")
    for key in ("POSTGRES_PASSWORD", "JWT_SECRET_KEY", "POSTGRES_USER", "POSTGRES_DB"):
        assert re.search(rf"^{key}=", text, re.MULTILINE), f".env.example 缺少 {key}"


# ---------------------------------------------------------------------------
# 4. 数据持久化与存储
# ---------------------------------------------------------------------------


def test_named_volumes_declared_for_all_state(prod_services: dict, prod_config: dict) -> None:
    """有状态服务都必须挂命名卷，且顶层声明齐全（否则 compose 校验不过）。"""
    declared = set(prod_config.get("volumes") or {})
    assert {"postgres_data", "redis_data", "attachment_storage"} <= declared

    mounts = {name: [str(v) for v in svc.get("volumes", [])] for name, svc in prod_services.items()}
    assert any("postgres_data:" in m for m in mounts["postgres"])
    assert any("redis_data:" in m for m in mounts["redis"])
    for name in ("app", "celery_worker"):
        assert any("attachment_storage:/app/storage" == m for m in mounts[name])


def test_no_source_code_bind_mounts(prod_services: dict) -> None:
    """生产不挂源码目录：镜像自带代码，挂宿主目录会绕过镜像是不可复现的。

    唯一例外是 nginx 的**配置**文件（只读）——它是部署配置而不是应用源码，
    以常量形式显式列出，新增任何宿主挂载都必须先改这里（TASK-060）。
    """
    for name, service in prod_services.items():
        for mount in service.get("volumes", []):
            text = str(mount)
            if text.endswith(ALLOWED_HOST_MOUNT_SUFFIXES):
                continue
            assert not re.match(r"^[./\\]|^[A-Za-z]:", text), f"{name} 挂了宿主路径: {mount}"


def test_redis_enables_aof_persistence(prod_services: dict) -> None:
    """AOF：Celery 的 Broker 队列需要跨重启存活，否则重启即丢任务（§21/§23）。"""
    command = prod_services["redis"]["command"]
    joined = " ".join(command) if isinstance(command, list) else str(command)
    assert "--appendonly" in joined
    assert "yes" in joined


# ---------------------------------------------------------------------------
# 5. 运行保障：健康检查、重启策略、日志轮转
# ---------------------------------------------------------------------------


def test_every_stateful_service_has_healthcheck(prod_services: dict) -> None:
    for name in SERVICES_WITH_HEALTHCHECK:
        assert prod_services[name].get("healthcheck", {}).get("test"), f"{name} 缺少健康检查"


def test_app_and_worker_wait_for_healthy_dependencies(prod_services: dict) -> None:
    """depends_on 必须是 healthy 条件：只等「启动」会让 app 在库就绪前连库失败。"""
    for name in ("app", "celery_worker"):
        depends = prod_services[name]["depends_on"]
        for dependency in ("postgres", "redis"):
            assert depends[dependency]["condition"] == "service_healthy"


def test_all_services_restart_always(prod_services: dict) -> None:
    """生产用 always（开发版用 unless-stopped）。"""
    for name, service in prod_services.items():
        assert service.get("restart") == "always", f"{name} 的 restart 策略不是 always"


def test_container_logs_are_rotated(prod_services: dict) -> None:
    """容器日志不轮转会一直增长直到写满宿主磁盘。"""
    for name, service in prod_services.items():
        logging_cfg = service.get("logging", {})
        assert logging_cfg.get("driver") == "json-file", f"{name} 未配置日志驱动"
        options = logging_cfg.get("options", {})
        assert options.get("max-size")
        assert options.get("max-file")


def test_worker_graceful_shutdown_window(prod_services: dict) -> None:
    """worker 收到 SIGTERM 会 warm shutdown；默认 10s 会截断在途任务。"""
    worker = prod_services["celery_worker"]
    assert worker.get("stop_grace_period")
    command = " ".join(worker["command"])
    assert "worker" in command
    assert "--loglevel=info" in command
    assert "${CELERY_CONCURRENCY:-" in command
