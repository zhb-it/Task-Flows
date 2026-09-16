"""TASK-060：Nginx 反代配置与生产接线契约（§4 文件清单 / §31）。

这些用例**不启动 Docker**，只解析 ``nginx/nginx.conf`` 与
``docker-compose.prod.yml``，把「接入反代后必须成立的性质」固化成断言。
理由与 TASK-059 的 compose 契约测试同源：这类配置的错误是**静默**的——
配置改错了，服务照样起得来，只是安全属性悄悄消失。

本文件重点防三类事：

1. **真实 IP 被客户端伪造**（DECISIONS 018 遗留约束的正解被改错）：
   ``X-Forwarded-For`` 必须是 ``$remote_addr`` **覆盖**写入，
   一旦有人把它改成 ``$proxy_add_x_forwarded_for``（追加语义），客户端塞进来的
   值就会被保留，限流与审计日志同时失去可信度——而流量一切正常；
2. **附件鉴权被绕过**：nginx 里一旦出现 ``alias``/``root`` 指向附件卷，私有
   附件就变成了公开静态资源（TASK-043 的权限链形同虚设）；
3. **暴露面被悄悄放大**：app 重新发布宿主端口、或又冒出第二个发布端口的服务，
   都会让「只有 Nginx 能连应用」这条结构保证失效。

配置正文与注释要分开看：注释里会**引用反面写法**（例如说明为什么不能用
``$proxy_add_x_forwarded_for``），因此所有「不得出现」的断言都只看去掉注释后的
正文（``conf_code``）。同理，指令取值一律经过空白归一，避免断言被「多打两个空格」
这种无关改动打破。
"""

from __future__ import annotations

import ipaddress
import re
from pathlib import Path

import pytest
import yaml

from app.core.config import Settings

PROJECT_ROOT = Path(__file__).resolve().parent.parent
NGINX_CONF = PROJECT_ROOT / "nginx" / "nginx.conf"
PROD_COMPOSE = PROJECT_ROOT / "docker-compose.prod.yml"
DEV_COMPOSE = PROJECT_ROOT / "docker-compose.yml"
ENV_EXAMPLE = PROJECT_ROOT / ".env.example"

#: 应用监听端口（Dockerfile / Gunicorn 命令 / nginx upstream 三处必须一致）。
APP_PORT = 8000


# ---------------------------------------------------------------------------
# 夹具 / 工具
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def conf_text() -> str:
    return NGINX_CONF.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def conf_code(conf_text: str) -> str:
    """去掉注释行后的配置正文（见模块 docstring 的说明）。"""
    return "\n".join(
        line for line in conf_text.splitlines() if not line.lstrip().startswith("#")
    )


@pytest.fixture(scope="module")
def prod_text() -> str:
    return PROD_COMPOSE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def prod_config(prod_text: str) -> dict:
    return yaml.safe_load(prod_text)


@pytest.fixture(scope="module")
def prod_services(prod_config: dict) -> dict:
    return prod_config["services"]


@pytest.fixture(scope="module")
def dev_services() -> dict:
    return yaml.safe_load(DEV_COMPOSE.read_text(encoding="utf-8"))["services"]


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _directives(conf_code: str, name: str) -> list[str]:
    """取出 ``name value;`` 形式指令的所有值。

    ``[^;\\n]`` 里的 ``\\n`` 很关键：否则 ``server {`` 会连同后面的指令被
    整个吞进上一条匹配（``{ ... listen 80``），得到看似合理却错误的结果。
    """
    pattern = rf"^\s*{re.escape(name)}\s+([^;\n]+);"
    return [_normalize(m.group(1)) for m in re.finditer(pattern, conf_code, re.MULTILINE)]


def _block(conf_code: str, header: str) -> str:
    """取出 ``header {`` 之后到首个 ``}`` 之间的内容（用于无嵌套块的场景）。"""
    match = re.search(rf"^\s*{re.escape(header)}\s*\{{(.*?)\}}", conf_code, re.S | re.M)
    assert match, f"未找到 {header} 块"
    return match.group(1)


def _headers(conf_code: str, directive: str) -> dict[str, str]:
    """``<directive> NAME VALUE;`` → ``{NAME: VALUE}``。"""
    result: dict[str, str] = {}
    for raw in _directives(conf_code, directive):
        name, _, value = raw.partition(" ")
        result[name] = value
    return result


_NGINX_SIZE_UNITS = {"k": 1024, "m": 1024**2, "g": 1024**3}


def _nginx_size_to_bytes(value: str) -> int:
    """把 nginx 的尺寸写法（``12m`` / ``512k``）换算成字节。"""
    text = value.strip().lower()
    unit = _NGINX_SIZE_UNITS.get(text[-1:], 1)
    number = text[:-1] if text[-1:] in _NGINX_SIZE_UNITS else text
    return int(number) * unit


# ---------------------------------------------------------------------------
# 1. 文件与整体结构
# ---------------------------------------------------------------------------


def test_nginx_conf_exists(conf_text: str) -> None:
    """§4 文件清单要求仓库里存在 ``nginx/nginx.conf``。"""
    assert NGINX_CONF.is_file()
    assert conf_text.strip(), "nginx 配置不应为空文件"


def test_braces_are_balanced(conf_code: str) -> None:
    """括号不平衡是最常见的语法错误——这类错误只在容器启动时才暴露。"""
    assert conf_code.count("{") > 0
    assert conf_code.count("{") == conf_code.count("}")


def test_required_blocks_present(conf_code: str) -> None:
    """一份可独立替换 ``/etc/nginx/nginx.conf`` 的配置必须自带这些块。"""
    for block in ("events", "http", "server", "upstream app_backend", "upstream frontend_backend"):
        assert re.search(rf"^\s*{re.escape(block)}\s*\{{", conf_code, re.MULTILINE), (
            f"缺少 {block} 块"
        )


def test_upstream_targets_the_app_service(conf_code: str, prod_services: dict) -> None:
    """upstream 指向的必须是 compose 里真实存在的服务名，端口与应用监听端口一致。

    写错服务名的后果是每个请求都 502——静态检查能提前拦住这种低级失误。
    """
    servers = re.findall(r"^\s*server\s+([^;\n]+);", _block(conf_code, "upstream app_backend"), re.M)
    assert len(servers) == 1, f"upstream 应当只有一个后端: {servers}"
    host, _, port = servers[0].strip().partition(":")
    assert host in prod_services, f"upstream 指向了不存在的服务: {host}"
    assert int(port) == APP_PORT


def test_upstream_targets_the_frontend_service(conf_code: str, prod_services: dict) -> None:
    """TASK-079：前端 upstream 指向 compose 的 frontend 服务，端口 80。"""
    servers = re.findall(
        r"^\s*server\s+([^;\n]+);", _block(conf_code, "upstream frontend_backend"), re.M
    )
    assert len(servers) == 1, f"upstream 应当只有一个后端: {servers}"
    host, _, port = servers[0].strip().partition(":")
    assert host in prod_services, f"upstream 指向了不存在的服务: {host}"
    assert int(port) == 80


def test_routes_split_api_and_frontend(conf_code: str) -> None:
    """TASK-079（前端规格 §56）：``/api/`` → 应用，``/`` → 前端 SPA。

    入口是**唯一**分流点：API 侧的安全语义（覆盖写入的 X-Forwarded-For、
    请求体上限、超时、request_id）只存在于 ``location /api/`` 一处；静态侧
    不反代 API。若有人把 ``/api`` 反代挪进前端镜像或再抄一份，两处配置漂移
    就会把安全语义撕开——这里钉死「分流只发生在这两个 location」。
    """
    assert _directives(conf_code, "proxy_pass") == [
        "http://app_backend",
        "http://frontend_backend",
    ]
    api_block = _block(conf_code, "location /api/")
    assert "http://app_backend" in api_block
    assert "frontend_backend" not in api_block
    root_block = _block(conf_code, "location /")
    assert "http://frontend_backend" in root_block
    assert "app_backend" not in root_block


def test_only_plain_http_and_no_tls_material(conf_code: str) -> None:
    """TASK-060 决策：只 listen 80，TLS 由上游负载均衡终止（证书不进仓库）。

    配套断言**不发** HSTS：在纯 HTTP 响应上发 ``Strict-Transport-Security``
    既不会被浏览器采纳（只对 HTTPS 生效），还会误导排查者以为已启用 TLS。
    """
    assert _directives(conf_code, "listen") == ["80"]
    assert _directives(conf_code, "ssl_certificate") == []
    assert not any(
        "Strict-Transport-Security" in raw
        for raw in _directives(conf_code, "add_header")
    )


# ---------------------------------------------------------------------------
# 2. 安全：真实 IP 的信任模型 + 附件鉴权 + 安全头
# ---------------------------------------------------------------------------


def test_forwarded_for_is_overwritten_not_appended(conf_code: str) -> None:
    """**本 TASK 最关键的一条**：用 ``$remote_addr`` 覆盖写入。

    ``$proxy_add_x_forwarded_for`` 是**追加**语义（把客户端传来的值拼在前面），
    一旦被改回去，客户端就能自带 ``X-Forwarded-For: 1.2.3.4`` 来冒充任意来源：
    限流可被拆成无限份（换个值就是新配额），审计日志也不可信。
    应用侧虽然还有「信任网段」这道闸，但覆盖写入才是让该头**值得**信任的前提。
    """
    headers = _headers(conf_code, "proxy_set_header")
    assert headers["X-Forwarded-For"] == "$remote_addr"
    assert "$proxy_add_x_forwarded_for" not in conf_code


def test_forwarded_proto_and_host_are_set(conf_code: str) -> None:
    """反代必须告知原始协议与主机，否则应用无法正确生成外部链接。"""
    headers = _headers(conf_code, "proxy_set_header")
    assert headers["X-Forwarded-Proto"] == "$scheme"
    assert headers["X-Forwarded-Host"] == "$host"


def test_host_header_uses_normalized_host(conf_code: str) -> None:
    """用 ``$host`` 而不是 ``$http_host``：后者会把客户端任意 Host 头透传给应用。"""
    assert _headers(conf_code, "proxy_set_header")["Host"] == "$host"
    assert "$http_host" not in conf_code


def test_client_request_id_is_passed_through(conf_code: str) -> None:
    """§34：客户端带的 request_id 要能穿过反代，两层日志才能用同一个 id 串联。

    用 ``$http_x_request_id`` 显式重设还有一个副作用：重复的同名头会被合并成
    「a, b」，应用侧白名单会拒绝它并重新生成——堵住了「用重复头伪装成别人的 id」。
    """
    assert _headers(conf_code, "proxy_set_header")["X-Request-ID"] == "$http_x_request_id"


def test_security_headers_present_and_apply_to_errors(conf_code: str) -> None:
    """§31「基础安全 Header」，且必须带 ``always``（否则 4xx/5xx 不带）。"""
    declared = _headers(conf_code, "add_header")
    for header in ("X-Content-Type-Options", "X-Frame-Options", "Referrer-Policy"):
        assert header in declared, f"缺少安全头 {header}"
        assert "always" in declared[header], f"{header} 未加 always"


def test_server_tokens_disabled(conf_code: str) -> None:
    """不暴露 nginx 版本号（§9：错误与响应头不泄露内部细节）。"""
    assert _directives(conf_code, "server_tokens") == ["off"]


def test_no_static_file_serving_directives(conf_code: str) -> None:
    """**附件不被 nginx 直出**（DECISIONS 040）。

    附件是私有资源：下载要过 ``attachment:download`` 功能权限 + 资源级归属链
    （TASK-043）。一旦出现 ``alias`` / ``root`` / ``autoindex`` 指向附件卷，
    鉴权就被完全绕过（任何人猜到路径即可下载任意附件 = IDOR）。
    因此这里断言：配置正文里没有任何静态文件服务指令，也不出现附件目录。
    """
    for forbidden in ("alias", "root", "autoindex", "X-Accel-Redirect"):
        assert not re.search(rf"^\s*{re.escape(forbidden)}\s", conf_code, re.MULTILINE), (
            f"出现静态文件服务指令 {forbidden}：会绕过附件鉴权"
        )
    assert "/app/storage" not in conf_code


def test_connection_header_cleared_for_upstream_keepalive(conf_code: str) -> None:
    """upstream keepalive 生效的前提：请求头 ``Connection`` 必须置空。"""
    assert _headers(conf_code, "proxy_set_header")["Connection"] == '""'
    assert _directives(conf_code, "keepalive") == ["32", "32"]


def test_forwarded_for_only_in_api_location(conf_code: str) -> None:
    """TASK-079：覆盖写入的 ``X-Forwarded-For`` 必须且只出现在 ``/api/`` 块里。

    静态前端不需要真实客户端 IP 做安全决策；把它抄进 ``/`` 块等于给一份
    安全语义开了第二份拷贝，将来其中一份被改动就会静默漂移。
    """
    api_block = _block(conf_code, "location /api/")
    assert re.search(r"proxy_set_header\s+X-Forwarded-For\s+\$remote_addr;", api_block)
    root_block = _block(conf_code, "location /")
    assert "X-Forwarded-For" not in root_block


# ---------------------------------------------------------------------------
# 3. §31 的其余职责：请求体大小、超时、日志
# ---------------------------------------------------------------------------


def test_body_size_limit_is_an_outer_guard_above_app_limit(conf_code: str) -> None:
    """nginx 的 body 上限必须是**粗粒度外圈**，且严格大于应用上限。

    若 nginx 比应用更严格，超限上传会得到 nginx 的 HTML 错误页，而不是 API 的
    统一 JSON 信封（§26）——客户端无法统一处理。留出余量还让
    ``MAX_UPLOAD_SIZE`` 调大时不必同步改这里（避免两处配置漂移）。
    """
    values = _directives(conf_code, "client_max_body_size")
    assert len(values) == 1, "应当只声明一次 client_max_body_size"
    nginx_limit = _nginx_size_to_bytes(values[0])
    app_limit = Settings(_env_file=None).max_upload_size
    assert nginx_limit > app_limit, (
        f"nginx 上限（{nginx_limit}）必须大于应用上限（{app_limit}）"
    )


def test_basic_timeouts_are_configured(conf_code: str) -> None:
    """§31「基础超时配置」：慢速客户端与后端超时都要有上界。"""
    for directive in (
        "client_body_timeout",
        "client_header_timeout",
        "send_timeout",
        "proxy_connect_timeout",
        "proxy_send_timeout",
        "proxy_read_timeout",
    ):
        assert _directives(conf_code, directive), f"缺少超时配置 {directive}"


def test_logs_are_written_to_container_stdout(conf_code: str) -> None:
    """日志进 stdout/stderr，交给 Docker 的 json-file 驱动轮转。

    同时断言日志格式带 ``$http_x_request_id``——两层的日志才能用同一个 id 串起来。
    注意 ``access_log`` 会出现两次（全局一行 + 健康探针 location 里的 ``off``），
    因此断言「包含」而不是「等于」；``off`` 那处是刻意关掉探针日志。
    """
    assert "/dev/stdout main" in _directives(conf_code, "access_log")
    assert _directives(conf_code, "error_log") == ["/dev/stderr warn"]
    assert "$http_x_request_id" in conf_code


# ---------------------------------------------------------------------------
# 4. 生产 compose 接线
# ---------------------------------------------------------------------------


def test_prod_has_nginx_service(prod_services: dict) -> None:
    assert "nginx" in prod_services, "§31 要求生产栈包含 Nginx"


def test_nginx_image_is_pinned(prod_services: dict) -> None:
    """不追随 ``latest``：反代层的版本漂移会让「本地能跑、线上不行」难以复现。"""
    image = prod_services["nginx"]["image"]
    assert image != "nginx:latest"
    assert re.match(r"^nginx:\d+\.\d+", image), f"镜像 tag 未固定版本: {image}"


def test_nginx_is_the_only_service_publishing_host_ports(prod_services: dict) -> None:
    """暴露面收敛到唯一入口。

    这是「X-Forwarded-For 值得信任」的**结构前提**：只要没有第二个对外端口，
    外部流量就必须经过 Nginx，客户端无法绕过覆盖写入的那一步。
    """
    publishers = {name for name, svc in prod_services.items() if svc.get("ports")}
    assert publishers == {"nginx"}, f"除 nginx 外仍有服务发布宿主端口: {publishers}"


def test_nginx_publishes_configurable_http_port(prod_services: dict) -> None:
    ports = prod_services["nginx"]["ports"]
    assert len(ports) == 1
    assert str(ports[0]).endswith(":80")
    assert "${NGINX_HTTP_PORT:-80}" in str(ports[0]), "对外端口应当可覆盖（本机验证用）"


def test_app_publishes_no_host_port(prod_services: dict) -> None:
    """TASK-059 时 app 绑 127.0.0.1:8000；接入 Nginx 后连回环端口也去掉。

    保留任何宿主端口都会让「宿主上的进程可以直连应用并伪造 X-Forwarded-For」
    重新成为可能——回环端口尤其危险，因为它对同机的所有进程开放。
    """
    assert "ports" not in prod_services["app"]


def test_nginx_config_is_mounted_read_only(prod_services: dict) -> None:
    mounts = [str(m) for m in prod_services["nginx"].get("volumes", [])]
    assert any(
        m.endswith("nginx/nginx.conf:/etc/nginx/nginx.conf:ro") for m in mounts
    ), f"nginx 配置必须以只读方式挂载: {mounts}"


def test_nginx_waits_for_healthy_app(prod_services: dict) -> None:
    """等 app healthy 再起入口：否则入口启动的头几秒所有 /api 请求都是 502。"""
    depends = prod_services["nginx"]["depends_on"]
    assert depends["app"]["condition"] == "service_healthy"


def test_nginx_waits_for_healthy_frontend(prod_services: dict) -> None:
    """TASK-079：同理，入口也要等前端镜像健康再开站（否则头几秒 / 是 502）。"""
    depends = prod_services["nginx"]["depends_on"]
    assert depends["frontend"]["condition"] == "service_healthy"


def test_nginx_healthcheck_uses_local_endpoint(prod_services: dict, conf_code: str) -> None:
    """健康检查探 nginx 自有的 /nginx-health，不依赖上游。

    否则应用重启期间 nginx 也会被标记为不健康，「入口挂了」与「后端重启中」
    混为一谈，排障时反而看不清是哪一层的问题。
    """
    test = prod_services["nginx"]["healthcheck"]["test"]
    joined = " ".join(test) if isinstance(test, list) else str(test)
    assert "/nginx-health" in joined
    assert "location = /nginx-health" in conf_code, "配置里必须真有这个 location"


def test_app_runs_gunicorn_with_uvicorn_workers(prod_services: dict) -> None:
    """§31：生产是 Gunicorn + Uvicorn Worker，不是裸 uvicorn 单进程。"""
    command = " ".join(prod_services["app"]["command"])
    assert command.startswith("gunicorn")
    assert "--worker-class=uvicorn.workers.UvicornWorker" in command
    assert f"--bind=0.0.0.0:{APP_PORT}" in command
    assert "--workers=${WEB_CONCURRENCY:-" in command, "worker 数应当可配置"


def test_gunicorn_access_log_is_not_duplicated(prod_services: dict) -> None:
    """不开 Gunicorn 自带访问日志。

    访问日志已由应用的 ``RequestLoggingMiddleware`` 按 §33 记录（含
    request_id / user_id / duration）。再开一份会重复输出——这正是 TASK-056 在
    uvicorn 上实测踩过的坑（同一请求两条访问日志）。
    """
    command = " ".join(prod_services["app"]["command"])
    assert "--access-logfile" not in command


def test_gunicorn_graceful_timeout_matches_stop_grace_period(prod_services: dict) -> None:
    """``--graceful-timeout`` 与 compose 的 ``stop_grace_period`` 对齐。

    否则 SIGTERM 之后 compose 可能在 Gunicorn 收尾完之前就强杀，在途请求被截断
    （worker 侧的 30s 同理）。
    """
    command = " ".join(prod_services["app"]["command"])
    assert "--graceful-timeout=30" in command
    assert prod_services["app"]["stop_grace_period"] == "30s"


def test_trust_boundary_matches_declared_network(prod_config: dict, prod_text: str) -> None:
    """**交叉校验**：TRUSTED_PROXY_IPS 必须等于 compose 声明的子网。

    应用只在「对端落在该网段」时采信 X-Forwarded-For。若两处不一致（改了子网
    忘了改信任网段，或反过来），信任判定会静默失效——限流继续退化成共享配额，
    而日志里一切正常。把这条对应关系钉死在测试里，是唯一能让它不漂移的办法。
    """
    env = prod_config["services"]["app"]["environment"]
    assert env["TRUST_PROXY_HEADERS"] in (True, "true")
    assert "TRUSTED_PROXY_IPS" in env, "开启信任却不写网段（应用会 fail-safe 地不采信）"

    declared = prod_config["networks"]["default"]["ipam"]["config"][0]["subnet"]
    assert ipaddress.ip_network(env["TRUSTED_PROXY_IPS"]) == ipaddress.ip_network(declared), (
        f"TRUSTED_PROXY_IPS({env['TRUSTED_PROXY_IPS']}) 与 compose 子网({declared}) 不一致"
    )
    # 该子网段必须是「只属于本项目」的私有段，不能撞上 Docker 常用默认段。
    assert ipaddress.ip_network(declared).is_private
    assert str(declared) not in ("172.17.0.0/16", "172.18.0.0/16", "172.19.0.0/16")


def test_asgi_server_proxy_rewrite_is_disabled(prod_services: dict) -> None:
    """关掉 uvicorn 的 proxy-headers 重写，让应用成为客户端 IP 的**唯一**判定点。

    否则客户端 IP 会由「ASGI server 一层 + 应用一层」共同决定：server 默认信任
    127.0.0.1，一旦有人把应用放到本机反代之后，判定就会发生变化——两套逻辑
    叠加出的行为是排障噩梦。
    """
    assert prod_services["app"]["environment"]["FORWARDED_ALLOW_IPS"] == ""


def test_dev_stack_does_not_trust_proxy_headers(dev_services: dict) -> None:
    """开发栈没有反代，必须保持「不信任任何转发头」的安全默认。"""
    for name, service in dev_services.items():
        env = service.get("environment") or {}
        assert "TRUST_PROXY_HEADERS" not in env, f"{name} 不应在生产之外开启该信任开关"


def test_env_example_documents_proxy_settings() -> None:
    """`.env.example` 要能回答「生产部署需要配哪些与反代相关的值」。"""
    text = ENV_EXAMPLE.read_text(encoding="utf-8")
    for key in (
        "NGINX_HTTP_PORT",
        "WEB_CONCURRENCY",
        "TRUST_PROXY_HEADERS",
        "TRUSTED_PROXY_IPS",
    ):
        assert key in text, f".env.example 未提及 {key}"


# ---------------------------------------------------------------------------
# 5. 前端接入（TASK-079；前端规格 §56 / §59 阶段 15）
# ---------------------------------------------------------------------------

FRONTEND_DIR = PROJECT_ROOT / "frontend"
FRONTEND_DOCKERFILE = FRONTEND_DIR / "Dockerfile"
FRONTEND_NGINX_CONF = FRONTEND_DIR / "nginx.conf"
FRONTEND_DOCKERIGNORE = FRONTEND_DIR / ".dockerignore"


def test_prod_has_frontend_service(prod_services: dict) -> None:
    """前端规格 §56：生产栈要有承载 Vue 静态文件的服务。"""
    assert "frontend" in prod_services


def test_frontend_builds_from_its_own_directory_with_pinned_tag(prod_services: dict) -> None:
    """构建上下文是 frontend/、镜像用独立 tag（与开发栈 / app 镜像互不串用）。"""
    service = prod_services["frontend"]
    assert service["build"]["context"] == "./frontend"
    assert service["build"]["dockerfile"] == "Dockerfile"
    assert service["image"] == "taskflow-frontend:prod"
    assert not service["image"].endswith(":latest")


def test_frontend_publishes_no_host_port(prod_services: dict) -> None:
    """前端与 app 同理只在内网被入口转发；「唯一对外是 nginx」不许破。"""
    assert "ports" not in prod_services["frontend"]


def test_frontend_image_files_exist() -> None:
    """§59 阶段 15 的三个交付文件必须存在且非空。"""
    for path in (FRONTEND_DOCKERFILE, FRONTEND_NGINX_CONF, FRONTEND_DOCKERIGNORE):
        assert path.is_file() and path.read_text(encoding="utf-8").strip(), f"{path} 缺失或为空"


def test_frontend_dockerfile_is_multi_stage_with_pinned_bases() -> None:
    """多阶段构建 + 基础镜像钉版本（node 与本地开发一致、nginx 与入口同线）。"""
    text = FRONTEND_DOCKERFILE.read_text(encoding="utf-8")
    code = "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("#")
    )
    froms = re.findall(r"^FROM\s+(\S+)", code, re.M)
    assert froms == ["node:22-alpine", "nginx:1.27-alpine"], f"FROM 阶段异常: {froms}"
    # 依赖按 lockfile 安装（构建可复现），产物与配置进运行时阶段。
    assert "npm ci" in code
    assert "COPY --from=build /app/dist" in code
    assert "COPY nginx.conf /etc/nginx/nginx.conf" in code


def test_frontend_nginx_conf_is_static_only_with_spa_fallback() -> None:
    """前端镜像的 nginx 只做静态托管：有 SPA 回退，但**不反代**。

    API 反代（含全部安全头语义）收敛在入口 ``nginx/nginx.conf`` 的
    ``/api/`` location；若有人在本层再抄一份 ``proxy_pass``，同一条安全
    语义就有了第二份会漂移的拷贝。
    """
    text = FRONTEND_NGINX_CONF.read_text(encoding="utf-8")
    code = "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("#")
    )
    # history 模式路由（router/index.ts 用 createWebHistory）必须有回退。
    assert "try_files" in code and "/index.html" in code
    assert not re.search(r"^\s*proxy_pass\s", code, re.M), "前端层不应出现 API 反代"
    assert _directives(code, "server_tokens") == ["off"]
    # 带 hash 的构建产物可永久缓存；入口壳不缓存（发版即刻生效）。
    # 单条 Cache-Control（expires 指令会另追加一条造成重复头，禁用）。
    assets_block = _block(code, "location /assets/")
    assert "immutable" in assets_block and "max-age=31536000" in assets_block
    assert not re.search(r"^\s*expires\s", assets_block, re.M)
    root_block = _block(code, "location /")
    assert "no-cache" in root_block
    # add_header 继承规则：带缓存头的 location 必须重复声明安全头（nosniff 等）。
    for header in ("X-Content-Type-Options", "X-Frame-Options", "Referrer-Policy"):
        assert header in assets_block and header in root_block, f"{header} 在缓存 location 中丢失"


def test_frontend_dockerignore_excludes_node_modules_and_dist() -> None:
    """构建上下文里不许有 node_modules（平台相关二进制）/ dist（应现场构建）。"""
    text = FRONTEND_DOCKERIGNORE.read_text(encoding="utf-8")
    entries = {line.strip() for line in text.splitlines() if line.strip() and not line.startswith("#")}
    assert "node_modules" in entries
    assert "dist" in entries
