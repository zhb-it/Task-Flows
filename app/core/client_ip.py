"""客户端真实 IP 解析（TASK-060，§31 反代后的信任边界）。

## 为什么需要这个模块

DECISIONS 018 在 TASK-046（限流）就记下了一条遗留约束：IP 维度限流只用
``request.client.host``，**不**解析 ``X-Forwarded-For``——该头可被客户端任意
伪造，用它做身份标识等于让攻击者随手换身份绕过限制。

代价是：一旦接入 Nginx 反代（§31 的 `Client → Nginx → Gunicorn → Uvicorn`），
**所有**请求的对端都变成 Nginx，「按 IP 限流」随即退化为「所有匿名用户共享
一份配额」——保护形同虚设。DECISIONS 018 明确写了这件事「必须在 TASK-060
接入反代时一并解决」，本模块就是那个解决（完整决策见 DECISIONS 042）。

## 信任模型：三条同时成立才采信该头

1. **显式开关** ``TRUST_PROXY_HEADERS=true``（默认 ``False``）。默认关闭意味着
   「没有反代」的环境行为与 TASK-046 完全一致——不引入任何隐式信任；
2. **对端落在信任网段内**（``TRUSTED_PROXY_IPS``，逗号分隔的 IP/CIDR）。
   开关打开但网段列表为空/无法解析 → **不采信**。这是刻意的 fail-safe：
   配置错误退化成「安全但限流不准」，而不是退化成「信任任何人」；
3. **只认单一 IP 值**。本项目的 Nginx 用 ``$remote_addr`` **覆盖**写入该头
   （见 ``nginx/nginx.conf``，而非会追加的 ``$proxy_add_x_forwarded_for``），
   因此合法请求里它必然是**一个** IP。出现多值说明有中间环节在追加（或是
   客户端自己塞的），一律不采信并回落到对端地址。

## 与 ASGI server 的关系

``request.client.host`` 可能被 ASGI server 的 proxy-headers 中间件改写
（uvicorn 默认只信任 ``127.0.0.1``）。为避免「server 改一次、应用再判一次」
出现两套叠加逻辑，生产 compose 显式设 ``FORWARDED_ALLOW_IPS=""`` 关掉 server
侧改写，让**本模块成为唯一判定点**。
"""

from __future__ import annotations

import ipaddress
import logging
from functools import lru_cache

logger = logging.getLogger(__name__)

#: 对端地址不可知时的占位值（ASGI 直连等拿不到 client 的场景）。
UNKNOWN_CLIENT_IP = "unknown"

#: 客户端 IP 的请求头（由反代**覆盖**写入）。
FORWARDED_FOR_HEADER = "X-Forwarded-For"

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address
IPNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network


def _normalize_ip(value: str) -> IPAddress | None:
    """把字符串解析为 IP；非法返回 ``None``。

    IPv4-mapped IPv6（``::ffff:10.0.0.5``）归一为 IPv4——某些容器网络栈会把
    IPv4 对端表示成这种形式，若不归一，``in IPv4Network`` 恒为假，会出现
    「配置看起来对、信任却永远不生效」的静默故障。
    """
    try:
        ip = ipaddress.ip_address(value)
    except ValueError:
        return None
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        return ip.ipv4_mapped
    return ip


@lru_cache(maxsize=16)
def parse_trusted_proxies(raw: str) -> tuple[IPNetwork, ...]:
    """解析 ``TRUSTED_PROXY_IPS``（逗号分隔的 IP 或 CIDR）。

    - 单个 IP（``172.28.0.5``）按 ``/32``（IPv6 按 ``/128``）处理——运维写单个
      地址时不该被要求补掩码；
    - ``strict=False`` 允许 ``172.28.0.5/24`` 这类「主机位非零」的写法；
    - 空项跳过；非法项**跳过并告警**（不抛异常，避免一个笔误让整个服务起不来）。
    """
    networks: list[IPNetwork] = []
    for chunk in (raw or "").split(","):
        item = chunk.strip()
        if not item:
            continue
        try:
            networks.append(ipaddress.ip_network(item, strict=False))
        except ValueError:
            logger.warning("ignoring invalid entry in TRUSTED_PROXY_IPS: %r", item)
    return tuple(networks)


def _peer_is_trusted(peer_ip: str, trusted: tuple[IPNetwork, ...]) -> bool:
    """对端是否为可信代理。列表为空 → 恒不信任（fail-safe）。"""
    if not trusted:
        return False
    peer = _normalize_ip(peer_ip)
    if peer is None:
        return False
    return any(peer in network for network in trusted)


def _single_forwarded_ip(value: str | None) -> str | None:
    """从 ``X-Forwarded-For`` 取出**唯一**的合法 IP；多值/非法/空 → ``None``。"""
    if not value:
        return None
    parts = [part.strip() for part in value.split(",")]
    if len(parts) != 1:
        # 多值 = 有环节在追加（本项目的 Nginx 是覆盖写入），不可信。
        return None
    ip = _normalize_ip(parts[0])
    return str(ip) if ip is not None else None


def resolve_client_ip(
    peer_ip: str | None,
    forwarded_for: str | None,
    *,
    trust_proxy: bool,
    trusted_proxies: tuple[IPNetwork, ...] = (),
) -> str:
    """返回用于限流 / 日志的客户端 IP。

    采信 ``X-Forwarded-For`` 的条件（全部满足）：开关打开、对端在信任网段内、
    该头恰好是一个合法 IP。否则回落到 ``peer_ip``（TCP 对端地址，无法伪造）。

    回落的对端地址同样过一遍归一（``::ffff:203.0.113.7`` → ``203.0.113.7``）：
    ① 同一个地址不该因为网络栈的表示方式不同而被当成两个客户端；② 日志里也就
    不会混进 ``::ffff:`` 前缀这种噪声。对端本身解析不了时（例如 ``unknown``）
    原样返回，不把信息抹掉。
    """
    if not peer_ip:
        return UNKNOWN_CLIENT_IP

    peer = _normalize_ip(peer_ip)
    peer_str = str(peer) if peer is not None else peer_ip

    if not trust_proxy:
        return peer_str
    if not _peer_is_trusted(peer_ip, trusted_proxies):
        return peer_str
    return _single_forwarded_ip(forwarded_for) or peer_str
