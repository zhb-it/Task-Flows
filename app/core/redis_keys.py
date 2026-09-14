"""Redis key naming convention（TASK-045）.

开发文档 §21/§22/§44 要求 Redis 承担 JWT 黑名单、API 限流、Celery。多个用途
共用同一个 Redis 实例（甚至共享 DB）时，**Key 必须集中定义**，否则会出现：

- 两处独立拼字符串，前缀不一致 → 同一逻辑数据出现两份，TTL 与清理互相打架；
- 某人改了前缀而没改另一处 → 线上「限流突然失效」这类难排查的故障；
- 无法一眼看出哪些 Key 是我们写的，运维清理时误删他人数据。

因此本模块是**唯一**的 Key 构造点（与 ``app/services/storage.py`` 的
``build_key`` 是同一思路：把「命名」这件事收敛到一个函数里）。

## 命名格式

    taskflow:<purpose>:<identifier>

- ``taskflow`` 是**全局命名空间前缀**：同一个 Redis 实例可能被多个应用共享，
  前缀把我们的键和其它应用的键隔开，也让 ``SCAN taskflow:*`` 成为安全的运维
  操作。前缀可通过 ``KEY_PREFIX`` 常量调整（若将来多环境共用实例，可加环境
  后缀）。
- ``<purpose>`` 是用途段（``ratelimit`` / ``jwt`` / ``celery`` ...），与 §21 的
  用途清单一一对应。
- ``<identifier>`` 是**由调用方提供的业务标识**（IP、user id、jti 等）。

## 为什么 identifier 要单独一段而不是拼在 purpose 里

- ``ratelimit:<scope>:<value>`` 让我们可以对某个 scope 整体扫描（例如清理某类
  限流计数），而不必枚举所有可能的值；
- JWT 黑名单按 ``jti`` 定位（§19），一个 jti 一个键，天然唯一。

## TTL 放在这里的理由

TTL 与 Key 是一体两面的契约：``jwt:blacklist:*`` 的 TTL 必须**不小于** Access
Token 的剩余寿命（否则 Token 在过期前就被从黑名单里放出来）；限流窗口的 TTL
必须覆盖整个窗口。把这些常量集中定义，才能让「Key 与 TTL 一起评审」。
"""

#: 全局命名空间前缀。变更会影响所有已存在的 Key（等同数据迁移），务必谨慎。
KEY_PREFIX = "taskflow"

#: 用途段常量——避免调用方各写各的字符串字面量。
PURPOSE_RATE_LIMIT = "ratelimit"
PURPOSE_JWT = "jwt"
PURPOSE_CELERY = "celery"


def build_key(purpose: str, *parts: object) -> str:
    """构造 ``taskflow:<purpose>:<part1>:<part2>...`` 形式的 Key。

    ``parts`` 会按 ``str()`` 转换后用 ``:`` 连接。空 ``parts`` 是允许的（返回
    ``taskflow:<purpose>``），但调用方应当总是给出足以区分业务的标识。

    分隔符统一为 ``:``（Redis 社区惯例，且 RedisInsight 等工具按 ``:`` 分层
    展示）。

    安全性说明：``parts`` 由**服务端**构造（IP、user id、jti），不直接来自
    用户可控的原始输入；若某天确需放入用户输入，调用方必须先规范化——本函数
    不做转义，因为「转义规则」应当由持有业务语义的那一层决定。
    """
    if not purpose:
        raise ValueError("purpose must be a non-empty string")
    if ":" in purpose:
        raise ValueError("purpose must not contain ':'")
    segments = [KEY_PREFIX, purpose, *(str(p) for p in parts)]
    return ":".join(segments)


# ---------------------------------------------------------------------------
# §21.1 / §22：API 限流（滑动窗口，TASK-046 消费）
# ---------------------------------------------------------------------------

#: 限流维度。IP 维度用于未认证流量，user 维度用于已认证流量（§22「IP / User」）。
RATE_LIMIT_SCOPE_IP = "ip"
RATE_LIMIT_SCOPE_USER = "user"


def rate_limit_key(scope: str, identifier: object) -> str:
    """限流 ZSET 的 Key，例如 ``taskflow:ratelimit:ip:203.0.113.7``。

    同一个 (scope, identifier) 对应一个 ZSET；ZSET 的 score 是请求时间戳，
    member 是请求唯一标识，滑动窗口算法在 TASK-046 中实现。
    """
    return build_key(PURPOSE_RATE_LIMIT, scope, identifier)


# ---------------------------------------------------------------------------
# §21.1：JWT 黑名单
# ---------------------------------------------------------------------------


def jwt_blacklist_key(jti: str) -> str:
    """Access Token 黑名单 Key，例如 ``taskflow:jwt:blacklist:<jti>``。

    §19 的登出目前靠**数据库**撤销 Refresh Token 的 jti。Access Token 是无状态
    的，要让它提前失效就需要一处「已撤销 jti」的记录——这正是 §21 列出的
    JWT 黑名单用途。本 TASK 只定义 Key 约定；**接入校验链路是后续任务**，避免
    在没有需求驱动时改动认证热路径（项目规则 §7）。
    """
    if not jti:
        raise ValueError("jti must be a non-empty string")
    return build_key(PURPOSE_JWT, "blacklist", jti)
