"""TASK-060：客户端真实 IP 解析与反向代理信任边界（§31）。

## 这个文件在防什么

DECISIONS 018 在 TASK-046（限流）就记下了遗留约束：IP 维度只用 TCP 对端地址，
**不**解析 ``X-Forwarded-For``（可被客户端任意伪造）。代价是接入 Nginx 之后
所有请求的对端都变成 Nginx，「按 IP 限流」退化为**所有匿名用户共享一份配额**。

TASK-060 的解法是「反代覆盖写入 + 应用侧按信任网段判定」，而这个文件负责把
判定逻辑的**每一条边界**钉死。最容易出的两个错都是静默的：

1. 为了「让 IP 看起来对」而无条件信任该头 —— 攻击者随手加个
   ``X-Forwarded-For: 大把不同地址`` 就能把限流拆成无限份；
2. 开关打开但网段没配/配错 —— 信任永远不生效，限流继续退化，而日志里
   一切正常（没有报错、没有告警），只能靠线上被打才发现。

因此用例集中在：**不开开关时行为与 TASK-046 完全一致**、**配置错误时向安全
方向退化**、**只认反代写入的单一值**。

分层：``parse_trusted_proxies`` 纯函数 → ``resolve_client_ip`` 纯函数 →
Settings 默认值（安全默认）→ 中间件接入（含访问日志字段）。
"""

from __future__ import annotations

import io
import ipaddress
import json
import logging

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from starlette.requests import Request

from app.core.client_ip import (
    UNKNOWN_CLIENT_IP,
    parse_trusted_proxies,
    resolve_client_ip,
)
from app.core.config import Settings
from app.core.logging_config import JsonFormatter
from app.core.middleware import RequestLoggingMiddleware, _client_ip

#: 与生产 compose 里 TRUSTED_PROXY_IPS 一致的样例网段。
PROXY_NET = "172.28.0.0/24"
TRUSTED = parse_trusted_proxies(PROXY_NET)

#: 一个「外部客户端」地址，用来验证采信路径。
CLIENT_IP = "203.0.113.7"


# ---------------------------------------------------------------------------
# 夹具 / 工具
# ---------------------------------------------------------------------------


def _make_request(
    headers: dict[str, str] | None = None, client: tuple[str, int] | None = ("127.0.0.1", 12345)
) -> Request:
    """构造一个 Starlette Request（``client`` 即 TCP 对端地址）。"""
    raw_headers = [
        (key.lower().encode("latin-1"), value.encode("latin-1"))
        for key, value in (headers or {}).items()
    ]
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/",
            "raw_path": b"/",
            "query_string": b"",
            "root_path": "",
            "headers": raw_headers,
            "client": client,
            "server": ("probe", 80),
        }
    )


@pytest.fixture
def apply_settings(monkeypatch):
    """把 ``app.core.middleware`` 看到的 Settings 换成本用例构造的那份。"""
    import app.core.middleware as mw

    def _apply(settings: Settings) -> None:
        monkeypatch.setattr(mw, "get_settings", lambda: settings, raising=True)

    return _apply


# ---------------------------------------------------------------------------
# 1. parse_trusted_proxies（配置解析）
# ---------------------------------------------------------------------------


def test_single_ip_becomes_host_network() -> None:
    """运维写单个地址时不该被要求补掩码。"""
    assert parse_trusted_proxies("172.28.0.5") == (
        ipaddress.ip_network("172.28.0.5/32"),
    )


def test_cidr_is_preserved() -> None:
    assert parse_trusted_proxies(PROXY_NET) == (ipaddress.ip_network(PROXY_NET),)


def test_host_bits_are_tolerated() -> None:
    """``172.28.0.5/24`` 这类「主机位非零」写法按网段处理，而不是报错。"""
    assert parse_trusted_proxies("172.28.0.5/24") == (
        ipaddress.ip_network("172.28.0.0/24"),
    )


def test_multiple_entries_and_blank_items() -> None:
    assert parse_trusted_proxies(f" {PROXY_NET} , , 10.0.0.1 ") == (
        ipaddress.ip_network(PROXY_NET),
        ipaddress.ip_network("10.0.0.1/32"),
    )


def test_invalid_entries_are_skipped_not_fatal() -> None:
    """一个笔误不该让服务起不来；跳过非法项、保留合法项。"""
    assert parse_trusted_proxies(f"{PROXY_NET},not-an-ip,999.1.1.1/8") == (
        ipaddress.ip_network(PROXY_NET),
    )


def test_empty_value_yields_no_networks() -> None:
    """空配置 = 没有可信代理（下面会断言这是 fail-safe 的）。"""
    assert parse_trusted_proxies("") == ()
    assert parse_trusted_proxies("   ,  ") == ()


def test_ipv6_networks_are_supported() -> None:
    assert parse_trusted_proxies("fd00::/8") == (ipaddress.ip_network("fd00::/8"),)


def test_parsing_is_cached() -> None:
    """请求路径上每个请求都会解析一次，必须命中缓存（身份判定不能引入 IO/开销）。"""
    first = parse_trusted_proxies("10.11.12.0/24")
    second = parse_trusted_proxies("10.11.12.0/24")
    assert first is second


# ---------------------------------------------------------------------------
# 2. resolve_client_ip（判定逻辑）
# ---------------------------------------------------------------------------


def test_disabled_trust_ignores_forwarded_header() -> None:
    """开关关闭 → 与 TASK-046 行为完全一致（客户端塞什么都没用）。"""
    assert (
        resolve_client_ip(
            "172.28.0.9", CLIENT_IP, trust_proxy=False, trusted_proxies=TRUSTED
        )
        == "172.28.0.9"
    )


def test_trusted_peer_uses_forwarded_ip() -> None:
    """DECISIONS 018 遗留约束的解法：反代之后的真实客户端 IP 能拿到。"""
    assert (
        resolve_client_ip(
            "172.28.0.9", CLIENT_IP, trust_proxy=True, trusted_proxies=TRUSTED
        )
        == CLIENT_IP
    )


def test_untrusted_peer_is_ignored() -> None:
    """不在信任网段内的对端（例如某个直连的容器）写入的头一律不采信。"""
    assert (
        resolve_client_ip(
            "10.0.0.9", CLIENT_IP, trust_proxy=True, trusted_proxies=TRUSTED
        )
        == "10.0.0.9"
    )


def test_enabled_but_empty_network_list_fails_safe() -> None:
    """**关键**：开关打开但网段没配 → 不采信（而不是信任任何人）。

    这是最危险的配置错误：``TRUST_PROXY_HEADERS=true`` 却没有
    ``TRUSTED_PROXY_IPS``。若这里退化成「信任」，任何人都能靠伪造该头把限流
    拆成无限份。故断言它退化为「安全但限流不准」的那一侧。
    """
    assert (
        resolve_client_ip(CLIENT_IP, "1.2.3.4", trust_proxy=True, trusted_proxies=())
        == CLIENT_IP
    )


def test_multiple_forwarded_entries_are_rejected() -> None:
    """只认单一 IP 值：多值说明有环节在**追加**（本项目的 Nginx 是覆盖写入）。"""
    assert (
        resolve_client_ip(
            "172.28.0.9",
            f"{CLIENT_IP}, 172.28.0.9",
            trust_proxy=True,
            trusted_proxies=TRUSTED,
        )
        == "172.28.0.9"
    )


def test_malformed_forwarded_value_falls_back_to_peer() -> None:
    for bad in ("not-an-ip", "999.1.1.1", f"{CLIENT_IP},", "<script>", "1.1.1.1 2.2.2.2"):
        assert (
            resolve_client_ip(
                "172.28.0.9", bad, trust_proxy=True, trusted_proxies=TRUSTED
            )
            == "172.28.0.9"
        ), bad


def test_missing_forwarded_header_falls_back_to_peer() -> None:
    for empty in (None, ""):
        assert (
            resolve_client_ip(
                "172.28.0.9", empty, trust_proxy=True, trusted_proxies=TRUSTED
            )
            == "172.28.0.9"
        )


def test_whitespace_around_value_is_tolerated() -> None:
    assert (
        resolve_client_ip(
            "172.28.0.9", f"  {CLIENT_IP}  ", trust_proxy=True, trusted_proxies=TRUSTED
        )
        == CLIENT_IP
    )


def test_ipv6_client_ip_is_supported() -> None:
    assert (
        resolve_client_ip(
            "fd00::2", "2001:db8::1", trust_proxy=True, trusted_proxies=parse_trusted_proxies("fd00::/8")
        )
        == "2001:db8::1"
    )


def test_ipv4_mapped_ipv6_peer_matches_ipv4_network() -> None:
    """容器网络栈可能把 IPv4 对端表示成 ``::ffff:a.b.c.d``。

    若不归一，``in IPv4Network`` 恒为假，「配置看起来对、信任却永远不生效」，
    而且没有任何报错——正是最需要防的静默失效。
    """
    assert (
        resolve_client_ip(
            "::ffff:172.28.0.9", CLIENT_IP, trust_proxy=True, trusted_proxies=TRUSTED
        )
        == CLIENT_IP
    )
    # 归一同样作用于回落值：日志里不该出现 ::ffff: 前缀这种噪声。
    assert (
        resolve_client_ip(
            "::ffff:203.0.113.7", None, trust_proxy=True, trusted_proxies=TRUSTED
        )
        == "203.0.113.7"
    )


def test_unknown_peer_is_never_overridden() -> None:
    """拿不到对端地址时（ASGI 直连）给占位值，且**绝不**用客户端可控的头填。"""
    assert (
        resolve_client_ip(None, CLIENT_IP, trust_proxy=True, trusted_proxies=TRUSTED)
        == UNKNOWN_CLIENT_IP
    )
    assert resolve_client_ip(None, CLIENT_IP, trust_proxy=True) == UNKNOWN_CLIENT_IP


# ---------------------------------------------------------------------------
# 3. Settings 默认值：不配就安全
# ---------------------------------------------------------------------------


def test_trust_is_off_by_default() -> None:
    """默认关闭 → 未配置反代的环境（含全部现有测试）行为不变。

    同时断言「生产必须显式开启」这件事是显式的：``APP_ENV=production`` 本身
    不会打开信任，否则等于用环境名暗中改变信任边界。
    """
    assert Settings(_env_file=None).trust_proxy_headers is False
    assert Settings(_env_file=None).trusted_proxy_ips == ""
    assert Settings(_env_file=None, app_env="production").trust_proxy_headers is False


# ---------------------------------------------------------------------------
# 4. 中间件接入（限流身份 + 访问日志字段）
# ---------------------------------------------------------------------------


def test_middleware_ignores_forwarded_header_when_trust_disabled(apply_settings) -> None:
    apply_settings(Settings(_env_file=None, trust_proxy_headers=False))
    request = _make_request({"X-Forwarded-For": CLIENT_IP}, client=("172.28.0.9", 1))
    assert _client_ip(request) == "172.28.0.9"


def test_middleware_uses_forwarded_header_when_trusted(apply_settings) -> None:
    apply_settings(
        Settings(_env_file=None, trust_proxy_headers=True, trusted_proxy_ips=PROXY_NET)
    )
    request = _make_request({"X-Forwarded-For": CLIENT_IP}, client=("172.28.0.9", 1))
    assert _client_ip(request) == CLIENT_IP


def test_middleware_handles_request_without_client(apply_settings) -> None:
    apply_settings(Settings(_env_file=None, trust_proxy_headers=True, trusted_proxy_ips=PROXY_NET))
    assert _client_ip(_make_request(client=None)) == UNKNOWN_CLIENT_IP


def _build_probe_app() -> FastAPI:
    probe = FastAPI()
    probe.add_middleware(RequestLoggingMiddleware)

    @probe.get("/ok")
    async def ok():
        return {"ok": True}

    return probe


async def _get(app: FastAPI, path: str, headers: dict[str, str] | None = None):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://probe") as client:
        return await client.get(path, headers=headers)


@pytest.fixture
def access_log_stream(monkeypatch):
    """捕获 ``app.core.middleware`` 的日志（并显式设定级别，见 TASK-056 教训）。"""
    logger = logging.getLogger("app.core.middleware")
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    old_level, old_propagate = logger.level, logger.propagate
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    try:
        yield stream
    finally:
        logger.removeHandler(handler)
        logger.setLevel(old_level)
        logger.propagate = old_propagate


def _last_payload(stream: io.StringIO) -> dict:
    lines = [line for line in stream.getvalue().splitlines() if line.strip()]
    return json.loads(lines[-1])


async def test_access_log_has_client_ip_field(access_log_stream, apply_settings) -> None:
    """访问日志带 ``client_ip``：反代之后只记对端地址的话，日志全是 Nginx 的地址。"""
    apply_settings(Settings(_env_file=None, trust_proxy_headers=False, log_requests=True))
    resp = await _get(_build_probe_app(), "/ok")
    assert resp.status_code == 200
    payload = _last_payload(access_log_stream)
    # httpx 的 ASGITransport 把对端固定为 127.0.0.1。
    assert payload["client_ip"] == "127.0.0.1"


async def test_access_log_records_real_client_ip_behind_proxy(
    access_log_stream, apply_settings
) -> None:
    """信任生效时日志记的是**真实客户端**而不是 Nginx —— 排查时才有区分度。"""
    apply_settings(
        Settings(
            _env_file=None,
            trust_proxy_headers=True,
            trusted_proxy_ips="127.0.0.0/8",
            log_requests=True,
        )
    )
    resp = await _get(
        _build_probe_app(), "/ok", headers={"X-Forwarded-For": CLIENT_IP}
    )
    assert resp.status_code == 200
    assert _last_payload(access_log_stream)["client_ip"] == CLIENT_IP


async def test_access_log_keeps_rejecting_spoofed_header_when_trust_off(
    access_log_stream, apply_settings
) -> None:
    """信任关闭时，伪造的头既不能影响限流身份，也不能污染审计日志。"""
    apply_settings(
        Settings(
            _env_file=None,
            trust_proxy_headers=True,
            trusted_proxy_ips="10.99.0.0/16",  # 不含 ASGITransport 的 127.0.0.1
            log_requests=True,
        )
    )
    resp = await _get(
        _build_probe_app(), "/ok", headers={"X-Forwarded-For": CLIENT_IP}
    )
    assert resp.status_code == 200
    assert _last_payload(access_log_stream)["client_ip"] == "127.0.0.1"
