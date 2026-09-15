"""结构化日志（TASK-056，项目文档 §33）.

§33 要求
--------
- 使用 Python ``logging``；
- **生产环境采用结构化日志格式**；
- 至少记录 ``timestamp / level / logger / message / request_id / user_id /
  path / method / status_code / duration``；
- 禁止日志输出 ``password / access_token / refresh_token`` 等敏感信息。

设计取舍
--------
1. **不引入第三方 JSON 日志库**（如 python-json-logger）：stdlib 的
   ``logging.Formatter`` + ``json.dumps`` 已完全够用，符合项目规则
   「不为了看起来复杂而增加无意义技术」。
2. **格式按环境切换**（TASK-056 用户确认）：``APP_ENV=production`` → JSON；
   其他环境 → 人读文本（本地排障友好）。可用 ``LOG_FORMAT=json|text`` 显式
   覆盖，``auto``（默认）即上述按环境推导。
3. **``request_id`` / ``user_id`` 走 ``ContextVar``**：§33 要求这两个字段
   出现在请求相关的日志上，而不只是访问日志。用 ``contextvars`` 承载，由
   中间件在请求开始时设置、结束还原；formatter 从 ContextVar 读取，未设置
   时输出 ``null``——**保持 schema 稳定**，日志聚合器不必处理「字段时有时无」。
   ``request_id`` 的生成与客户端透传由 ``RequestIdMiddleware``（TASK-057，§34）
   负责，本模块只负责把它渲染进日志。
4. **敏感信息自动脱敏**（TASK-056 用户确认）：§33 是硬禁止项，靠人工约定
   容易漏（一次 ``logger.info(f"login {token}")`` 就破）。因此在**日志出口**
   用 ``logging.Filter`` 统一脱敏——既覆盖 ``extra`` 里的结构化字段（含嵌套
   dict），也覆盖 message 里的 ``password=xxx`` 形式与裸 JWT 字面量。
5. **幂等**：``configure_logging()`` 可重复调用（应用启动、测试、多次 import），
   只移除**自己**上次安装的 handler（用标记属性识别），不触碰他人的 handler
   ——避免把 pytest 的捕获 handler 一起清掉。
"""

from __future__ import annotations

import json
import logging
import re
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any

from app.core.config import Settings, get_settings

# ---------------------------------------------------------------------------
# 1. 请求上下文（ContextVar）
# ---------------------------------------------------------------------------

#: 当前请求的 request_id（由 ``RequestIdMiddleware`` 设置，TASK-057；未设置时
#: formatter 输出 null——schema 恒定，聚合器不必处理「字段时有时无」）。
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

#: 当前请求的已认证用户 id（由请求日志中间件按 JWT ``sub`` 设置，不查库）。
user_id_var: ContextVar[int | None] = ContextVar("user_id", default=None)


# ---------------------------------------------------------------------------
# 2. reserved / 脱敏规则
# ---------------------------------------------------------------------------

#: ``LogRecord`` 的标准属性 + 本模块自行注入的字段——这些不由 ``record.__dict__``
#: 透传（否则会把 ``msg``/``args``/``exc_info`` 等原始对象一并塞进 JSON）。
_RESERVED_ATTRS = frozenset(
    {
        "name",
        "msg",
        "args",
        "levelname",
        "levelno",
        "pathname",
        "filename",
        "module",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "created",
        "msecs",
        "relativeCreated",
        "thread",
        "threadName",
        "processName",
        "process",
        "taskName",
        "message",
        "asctime",
        # 由 ContextVar 提供（见模块 docstring 第 3 点），不从 record 透传。
        "request_id",
        "user_id",
    }
)

MASK = "***"

#: 命中即整体脱敏的字段名（大小写不敏感，支持子串匹配：access_token / refresh_token
#: 都含 token）。
_SENSITIVE_KEY_RE = re.compile(
    r"(pass(word|wd)?|pwd|secret|token|authorization|api[_-]?key|credential)",
    re.IGNORECASE,
)

#: message 文本里的 ``password=xxx`` / ``token: xxx`` 形式。键名两侧允许**可选引号**，
#: 以便同时覆盖 Python repr（``{'password': 'x'}``）与 JSON 片段
#: （``"password": "x"``）——`logger.info({"password": ...})` 这种「把字典当消息」
#: 的写法最终正是以 repr 形式落进日志的（TASK-062 实测泄露，见 DECISIONS 044）。
_KV_RE = re.compile(
    r"(?P<key>['\"]?\b(?:pass(?:word|wd)?|pwd|secret|token|authorization|"
    r"access_token|refresh_token|api[_-]?key)\b['\"]?)"
    r"(?P<sep>\s*[=:]\s*)"
    r"(?P<value>\"[^\"]*\"|'[^']*'|\S+)",
    re.IGNORECASE,
)

#: 裸 JWT 字面量（三段 base64url，以 ``eyJ`` 开头）——§33 禁止输出 token。
_JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]{4,}\b")


def redact_text(text: str) -> str:
    """把文本里的敏感值替换为 ``***``（键名保留，便于排障）。"""
    redacted = _KV_RE.sub(lambda m: f"{m.group('key')}{m.group('sep')}{MASK}", text)
    return _JWT_RE.sub(MASK, redacted)


def _redact_value(key: str, value: Any) -> Any:
    """按字段名判定是否脱敏；字符串值再做文本级脱敏；dict 递归一层。"""
    if _SENSITIVE_KEY_RE.search(key):
        return MASK
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {k: _redact_value(str(k), v) for k, v in value.items()}
    return value


def _redact_args(args: Any) -> Any:
    """脱敏 ``record.args``（tuple / dict / 单个对象三种形态都要覆盖）。

    logging 在只有一个参数时会把 ``args`` 存成**裸对象**而非 tuple，因此必须
    单独处理字符串形态，否则 ``logger.info("%s", token)`` 这种最常见的写法
    会漏掉。dict 形态对应 ``%(name)s`` 模板：键名敏感则整值脱敏，否则做文本
    脱敏。
    """
    if isinstance(args, dict):
        return {
            key: (
                _redact_value(str(key), value)
                if isinstance(key, str)
                else value
            )
            for key, value in args.items()
        }
    if isinstance(args, tuple):
        return tuple(redact_text(a) if isinstance(a, str) else a for a in args)
    if isinstance(args, str):
        return redact_text(args)
    return args


class SensitiveDataFilter(logging.Filter):
    """日志出口的敏感信息脱敏（§33）。

    覆盖三处泄漏面：①``extra`` 的结构化字段（含嵌套 dict）；②message 文本里的
    ``key=value``；③裸 JWT 字面量。**只脱敏值、保留键名**——排障时仍能看到
    「这里有个 token 字段」，但看不到它的内容。

    ⚠ 实现要点：**有 ``args`` 时绝不修改 ``record.msg``**。此时 msg 是
    ``"%s"`` 形式的**模板**，把它一起做文本脱敏会吃掉占位符
    （``"token=%s"`` → ``"token=***"``），``record.getMessage()`` 随之抛
    ``TypeError: not all arguments converted``——logging 会吞掉该异常并把整条
    日志丢掉（只在 stderr 留下一行 "--- Logging error ---"）。因此：

    - 有 ``args`` → 只脱敏 args（模板保持原样，格式化仍能成功）；
    - 无 ``args`` → msg 就是最终文本，直接脱敏。
    """

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003 (stdlib 命名)
        # ① message / args
        if record.args:
            record.args = _redact_args(record.args)
        else:
            # 无 args 时 `LogRecord.getMessage()` 会对 msg 做 `str()`——即**任何**
            # 类型的 msg 最终都会变成一段文本。早先这里只对 `isinstance(msg, str)`
            # 生效，于是 `logger.info({"password": "..."})` 会把字典 repr 原样写进
            # 日志（TASK-062 实测泄露，§48「敏感日志泄露」）。统一按文本脱敏，
            # 等价于「对最终会输出什么就脱敏什么」。
            record.msg = redact_text(str(record.msg))

        # ② 结构化字段（含 extra 传入的自定义字段）
        for key, value in list(record.__dict__.items()):
            if key in _RESERVED_ATTRS or key.startswith("_"):
                continue
            record.__dict__[key] = _redact_value(key, value)
        return True


# ---------------------------------------------------------------------------
# 3. Formatter
# ---------------------------------------------------------------------------


def _base_payload(record: logging.LogRecord) -> dict[str, Any]:
    return {
        "timestamp": datetime.fromtimestamp(
            record.created, tz=timezone.utc
        ).isoformat(),
        "level": record.levelname,
        "logger": record.name,
        "message": record.getMessage(),
        # §33 要求：这两个字段恒定存在（无值即 null），schema 保持稳定。
        "request_id": request_id_var.get(),
        "user_id": user_id_var.get(),
    }


class JsonFormatter(logging.Formatter):
    """结构化（JSON）日志格式（生产环境，§33）。

    输出单行 JSON：§33 的固定字段（timestamp/level/logger/message/request_id/
    user_id）+ 调用方通过 ``extra`` 传入的字段（访问日志的 path/method/
    status_code/duration）+ 异常堆栈（``exception``）。
    """

    def format(self, record: logging.LogRecord) -> str:  # noqa: A003
        payload = _base_payload(record)
        for key, value in record.__dict__.items():
            if key in _RESERVED_ATTRS or key.startswith("_"):
                continue
            payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack_info"] = self.formatStack(record.stack_info)
        # default=str：把 UUID/datetime 等非 JSON 原生类型降级为字符串，
        # 保证「任何日志调用都不会因为格式化失败而丢日志」。
        return json.dumps(payload, ensure_ascii=False, default=str)


class TextFormatter(logging.Formatter):
    """人读文本格式（开发环境，§33 只强制生产环境结构化）。"""

    def format(self, record: logging.LogRecord) -> str:  # noqa: A003
        line = (
            f"{self.formatTime(record, '%Y-%m-%d %H:%M:%S')} "
            f"{record.levelname:<8} {record.name} :: {record.getMessage()}"
        )
        ctx: list[str] = []
        request_id = request_id_var.get()
        if request_id:
            ctx.append(f"request_id={request_id}")
        user_id = user_id_var.get()
        if user_id is not None:
            ctx.append(f"user_id={user_id}")
        # 结构化访问日志字段：只渲染这张白名单里的键（而不是把所有 extra 都打出来），
        # 避免任意 `extra=` 把一行日志撑爆或混进非预期内容。
        # 新增字段时必须同时加进这里——**否则它只在生产 JSON 里存在**：开发环境
        # 看不到，而开发环境恰恰是人看日志的地方（TASK-060 加 client_ip 时实测踩到）。
        for key in ("method", "path", "status_code", "duration", "client_ip"):
            if key in record.__dict__:
                ctx.append(f"{key}={record.__dict__[key]}")
        if ctx:
            line += " | " + " ".join(ctx)
        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)
        return line


# ---------------------------------------------------------------------------
# 4. 配置入口
# ---------------------------------------------------------------------------

#: 标记属性：用于识别「本模块安装的 handler」，使 configure_logging 幂等。
_HANDLER_MARKER = "_taskflow_structured_handler"

_LEVELS = {
    "CRITICAL": logging.CRITICAL,
    "ERROR": logging.ERROR,
    "WARNING": logging.WARNING,
    "INFO": logging.INFO,
    "DEBUG": logging.DEBUG,
}


def resolve_level(level_name: str) -> int:
    """把配置里的级别名解析为 ``logging`` 常量；非法值回落到 INFO。

    不抛错是刻意的：日志级别写错不应该让应用起不来（§11 错误处理的最小爆炸面），
    回落到 INFO 并继续服务。
    """
    return _LEVELS.get((level_name or "").strip().upper(), logging.INFO)


def resolve_format(settings: Settings) -> str:
    """解析最终格式：显式 ``json``/``text`` 优先，否则按 ``APP_ENV`` 推导（§33）。"""
    configured = (settings.log_format or "auto").strip().lower()
    if configured in {"json", "text"}:
        return configured
    return "json" if (settings.app_env or "").strip().lower() == "production" else "text"


def configure_logging(
    settings: Settings | None = None, *, stream: Any = None
) -> logging.Handler:
    """安装应用日志 handler（幂等）。

    :param settings: 缺省用 ``get_settings()``。
    :param stream: 输出流；缺省 ``sys.stderr``（uvicorn/容器惯例）。测试可传
        ``io.StringIO`` 以断言输出内容。
    :returns: 本次安装的 ``logging.Handler``（供测试直接检查 formatter）。

    行为：
    - 按 §33 选择 JSON / 文本 formatter，并挂上 ``SensitiveDataFilter``；
    - 只移除**自己**上次安装的 handler（重复调用不会叠加日志）；
    - 把 uvicorn 自带的 ``uvicorn`` / ``uvicorn.error`` / ``uvicorn.access``
      logger 收编到 root（清空其自带 handler、打开 propagate）——否则 uvicorn
      的访问日志会用自己的格式旁路掉结构化格式，同一请求出现两种日志格式。
    """
    settings = settings or get_settings()
    level = resolve_level(settings.log_level)
    fmt = resolve_format(settings)
    formatter: logging.Formatter = JsonFormatter() if fmt == "json" else TextFormatter()

    handler = logging.StreamHandler(stream)
    handler.setFormatter(formatter)
    handler.addFilter(SensitiveDataFilter())
    handler.setLevel(level)
    setattr(handler, _HANDLER_MARKER, True)

    root = logging.getLogger()
    for existing in list(root.handlers):
        if getattr(existing, _HANDLER_MARKER, False):
            root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(level)

    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers = []
        uvicorn_logger.propagate = True
        uvicorn_logger.setLevel(level)

    # uvicorn 自带的访问日志与本项目的 ``RequestLoggingMiddleware`` 重复：同一
    # 请求会产生**两条**访问日志，而 uvicorn 那条既没有 ``duration`` 也没有
    # ``user_id``（§33 明确要求）。本项目的中间件记录更完整的字段，因此把
    # ``uvicorn.access`` 压到 WARNING——例行的访问行不再输出，真正的异常日志
    # 仍然保留。这一条由 TASK-056 的真实容器冒烟发现（每个请求两条访问日志）。
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    return handler
