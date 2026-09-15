"""TASK-056：结构化日志（§33）单元 + 中间件测试.

§33 要求：Python logging；生产环境结构化（JSON）格式；至少记录
``timestamp / level / logger / message / request_id / user_id / path / method /
status_code / duration``；禁止输出 password / access_token / refresh_token。

本文件分四层：
1. **JSON formatter 契约**——字段齐备、ContextVar 注入、extra 透传、异常/非
   可序列化对象不丢日志、单行输出；
2. **文本 formatter**——开发环境人读格式，仍带上下文；
3. **敏感信息脱敏**——§33 硬禁止项：extra 字段（含嵌套 dict）、message 里的
   ``key=value``、裸 JWT 字面量；只脱敏值、保留键名；
4. **configure_logging 与 RequestLoggingMiddleware**——格式按环境推导、
   非法级别回落、幂等、访问日志四个字段（method/path/status_code/duration）
   与 user_id（JWT ``sub``，不查库）、ContextVar 供下游日志复用、异常记 500、
   关闭开关生效、token 不落日志。

注意：``configure_logging`` 会动**真实 root logger**（与 ``app.main`` 的启动
路径一致），因此本文件的 ``_restore_logging`` 夹具在使用前后快照/还原 root 与
uvicorn logger 状态，避免污染其它测试。
"""

import io
import json
import logging
import time
import uuid
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings
from app.core.logging_config import (
    MASK,
    JsonFormatter,
    SensitiveDataFilter,
    TextFormatter,
    configure_logging,
    request_id_var,
    resolve_format,
    resolve_level,
    user_id_var,
)
from app.core.middleware import RequestLoggingMiddleware
from app.core.security import create_access_token

RUN_TOKEN = uuid.uuid4().hex[:8]


# ---------------------------------------------------------------------------
# 夹具
# ---------------------------------------------------------------------------


@pytest.fixture
def _restore_logging():
    """快照并还原 root / uvicorn logger 状态（configure_logging 会动全局状态）。"""
    root = logging.getLogger()
    saved_root_handlers = list(root.handlers)
    saved_root_level = root.level
    uvicorn_names = ("uvicorn", "uvicorn.error", "uvicorn.access")
    saved_uvicorn = {
        name: (
            list(logging.getLogger(name).handlers),
            logging.getLogger(name).level,
            logging.getLogger(name).propagate,
        )
        for name in uvicorn_names
    }
    yield
    root.handlers = saved_root_handlers
    root.setLevel(saved_root_level)
    for name, (handlers, level, propagate) in saved_uvicorn.items():
        lg = logging.getLogger(name)
        lg.handlers = handlers
        lg.setLevel(level)
        lg.propagate = propagate


@pytest.fixture
def _clear_contextvars():
    """还原 ContextVar，避免请求上下文泄漏到其它用例。"""
    request_id_token = request_id_var.set(None)
    user_id_token = user_id_var.set(None)
    yield
    request_id_var.reset(request_id_token)
    user_id_var.reset(user_id_token)


def _make_record(
    message: str = "hello",
    *,
    level: int = logging.INFO,
    args=None,
    exc_info=None,
    **extra,
) -> logging.LogRecord:
    record = logging.LogRecord(
        name="app.test",
        level=level,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=args,
        exc_info=exc_info,
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def _parse_lines(raw: str) -> list[dict]:
    return [json.loads(line) for line in raw.splitlines() if line.strip()]


# ---------------------------------------------------------------------------
# 1. JSON formatter（§33 结构化格式）
# ---------------------------------------------------------------------------


def test_json_formatter_has_all_required_fields(_clear_contextvars):
    """§33 固定字段必须齐备；request_id / user_id 无值时是 null（schema 稳定）。"""
    payload = json.loads(JsonFormatter().format(_make_record("hello")))
    assert set(payload) >= {
        "timestamp",
        "level",
        "logger",
        "message",
        "request_id",
        "user_id",
    }
    assert payload["level"] == "INFO"
    assert payload["logger"] == "app.test"
    assert payload["message"] == "hello"
    assert payload["request_id"] is None
    assert payload["user_id"] is None


def test_json_formatter_timestamp_is_iso_utc(_clear_contextvars):
    payload = json.loads(JsonFormatter().format(_make_record()))
    parsed = datetime.fromisoformat(payload["timestamp"])
    assert parsed.tzinfo is not None
    assert abs((datetime.now(timezone.utc) - parsed).total_seconds()) < 10


def test_json_formatter_reads_contextvars(_clear_contextvars):
    request_id_var.set("rid-abc")
    user_id_var.set(42)
    payload = json.loads(JsonFormatter().format(_make_record()))
    assert payload["request_id"] == "rid-abc"
    assert payload["user_id"] == 42


def test_json_formatter_passes_through_extra_fields(_clear_contextvars):
    """访问日志的 method/path/status_code/duration 就是这样进 JSON 的。"""
    payload = json.loads(
        JsonFormatter().format(
            _make_record(
                "request completed",
                method="GET",
                path="/api/v1/tasks",
                status_code=200,
                duration=12.345,
            )
        )
    )
    assert payload["method"] == "GET"
    assert payload["path"] == "/api/v1/tasks"
    assert payload["status_code"] == 200
    assert payload["duration"] == 12.345


def test_json_formatter_single_line_and_no_standard_attrs(_clear_contextvars):
    raw = JsonFormatter().format(_make_record("one line"))
    assert "\n" not in raw
    payload = json.loads(raw)
    # 标准 LogRecord 内部属性不得泄漏进 JSON
    for leaked in ("msg", "args", "exc_info", "levelno", "pathname", "lineno"):
        assert leaked not in payload


def test_json_formatter_includes_exception(_clear_contextvars):
    try:
        raise ValueError("boom")
    except ValueError:
        import sys

        record = _make_record("failed", exc_info=sys.exc_info())
    payload = json.loads(JsonFormatter().format(record))
    assert "ValueError: boom" in payload["exception"]


def test_json_formatter_includes_stack_info(_clear_contextvars):
    """``stack_info`` 存在时进 JSON 负载（``logger.info(..., stack_info=True)``）。

    与 ``exception`` 是两条独立路径：``exc_info`` 只在异常处理里出现，
    ``stack_info`` 用于「没抛异常但我要看清调用链」的排障场景。只看
    ``exc_info`` 的实现会把它静默丢掉，而那正是这类日志唯一的信息来源。
    """
    record = _make_record("no exception here", stack_info="Stack (most recent call last):")
    payload = json.loads(JsonFormatter().format(record))
    assert "stack_info" in payload
    assert "most recent call last" in payload["stack_info"]


def test_json_formatter_omits_exception_and_stack_info_when_absent(_clear_contextvars):
    """两者都不存在时**不得**出现空键（负载 schema 才稳定，下游不必区分 null/缺失）。"""
    payload = json.loads(JsonFormatter().format(_make_record("plain")))
    assert "exception" not in payload
    assert "stack_info" not in payload


def test_json_formatter_non_serializable_value_does_not_lose_log(_clear_contextvars):
    """default=str：任何类型的 extra 都不会让日志格式化失败（不丢日志优先）。"""
    payload = json.loads(JsonFormatter().format(_make_record("x", obj=object())))
    assert "obj" in payload
    assert isinstance(payload["obj"], str)


# ---------------------------------------------------------------------------
# 2. 文本 formatter（开发环境）
# ---------------------------------------------------------------------------


def test_text_formatter_human_readable(_clear_contextvars):
    line = TextFormatter().format(_make_record("hello world"))
    assert "INFO" in line
    assert "app.test" in line
    assert "hello world" in line


def test_text_formatter_appends_context_and_request_fields(_clear_contextvars):
    request_id_var.set("rid-1")
    user_id_var.set(7)
    line = TextFormatter().format(
        _make_record("request completed", method="POST", path="/x", status_code=201)
    )
    assert "request_id=rid-1" in line
    assert "user_id=7" in line
    assert "method=POST" in line
    assert "path=/x" in line
    assert "status_code=201" in line


def test_text_formatter_renders_client_ip(_clear_contextvars):
    """文本格式必须渲染 ``client_ip``（TASK-060）。

    文本格式对额外字段是**白名单**渲染，因此新增一个访问日志字段时如果只加进
    ``extra={...}`` 而没加进白名单，它就会**只在生产 JSON 里存在**——开发环境
    看不到，而开发环境恰恰是人看日志的地方。这个缺口是 TASK-060 的容器冒烟
    发现的（pytest 只断言 JSON 负载，测不出来）。
    """
    line = TextFormatter().format(
        _make_record(
            "request completed",
            method="GET",
            path="/health",
            status_code=200,
            duration=1.5,
            client_ip="203.0.113.7",
        )
    )
    assert "client_ip=203.0.113.7" in line


# ---------------------------------------------------------------------------
# 3. 敏感信息脱敏（§33 禁止输出 password / token）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "key",
    ["password", "passwd", "pwd", "access_token", "refresh_token", "token", "secret"],
)
def test_filter_redacts_sensitive_extra_keys(key):
    record = _make_record("x", **{key: "super-secret-value"})
    SensitiveDataFilter().filter(record)
    assert getattr(record, key) == MASK
    # 键名保留（排障时仍能看到这里有个敏感字段）
    assert key in record.__dict__


def test_filter_keeps_non_sensitive_values():
    record = _make_record("x", username="alice", count=3)
    SensitiveDataFilter().filter(record)
    assert record.username == "alice"
    assert record.count == 3


def test_filter_redacts_nested_dict_extra():
    record = _make_record("login attempt", payload={"password": "p", "user": "bob"})
    SensitiveDataFilter().filter(record)
    assert record.payload["password"] == MASK
    assert record.payload["user"] == "bob"


def test_filter_redacts_key_value_pairs_in_message():
    record = _make_record("login failed password=hunter2 user=bob")
    SensitiveDataFilter().filter(record)
    text = record.getMessage()
    assert "hunter2" not in text
    assert "password=***" in text
    assert "bob" in text  # 非敏感部分不受影响


def test_filter_redacts_bare_jwt_literal():
    token = create_access_token(1)
    record = _make_record(f"authorization header: {token}")
    SensitiveDataFilter().filter(record)
    assert token not in record.getMessage()
    assert MASK in record.getMessage()


def test_filter_redacts_token_in_args():
    token = create_access_token(2)
    record = _make_record("token=%s", args=(token,))
    SensitiveDataFilter().filter(record)
    assert token not in record.getMessage()


def test_filter_redacts_a_single_string_arg(_clear_contextvars):
    """单个字符串参数必须脱敏——这是全项目最常见的日志写法。

    ``logger.info("token=%s", token)`` 在 logging 内部把 ``args`` 存成**裸字符串**
    而不是 ``(token,)``。只处理 tuple 的实现会在这里整段漏掉，而它恰好是
    ``logger.info("%s", token)`` 这类调用唯一的形态（§33 禁止输出 token）。
    """
    token = create_access_token(4)
    record = _make_record("token=%s", args=token)
    SensitiveDataFilter().filter(record)
    assert token not in record.getMessage()
    assert MASK in record.getMessage()


def test_filter_leaves_bare_non_string_args_unchanged(_clear_contextvars):
    """非 str 的裸参数**原样返回**（同一对象），脱敏不得改变参数的值或类型。

    为什么这条重要：``_redact_args`` 对三种形态分别处理（dict / tuple / 裸对象），
    兜底分支若被写成「统一 ``str()`` 化」，非文本参数就会被悄悄改写成字符串——
    ``"payload=%r" % args`` 之类的模板随后得到的东西与调用方传入的不再相同，
    日志的可信度就没了。断言 ``is``（同一对象）而不是 ``==``，把「不改动」钉死。
    """
    raw = b"not-a-string-arg"
    record = _make_record("payload=%r", args=raw)
    SensitiveDataFilter().filter(record)
    assert record.args is raw


def test_filter_returns_true_so_record_is_not_dropped():
    assert SensitiveDataFilter().filter(_make_record("x")) is True


# ---------------------------------------------------------------------------
# 4. configure_logging / RequestLoggingMiddleware
# ---------------------------------------------------------------------------


def test_resolve_format_auto_follows_app_env():
    assert resolve_format(Settings(app_env="production", log_format="auto")) == "json"
    assert resolve_format(Settings(app_env="development", log_format="auto")) == "text"


def test_resolve_format_explicit_override_wins():
    assert resolve_format(Settings(app_env="production", log_format="text")) == "text"
    assert resolve_format(Settings(app_env="development", log_format="json")) == "json"


def test_resolve_level_known_and_fallback():
    assert resolve_level("debug") == logging.DEBUG
    assert resolve_level("WARNING") == logging.WARNING
    # 非法值回落 INFO，不抛错（配置写错不该让应用起不来）
    assert resolve_level("nonsense") == logging.INFO
    assert resolve_level("") == logging.INFO


def test_configure_logging_emits_json_in_production(_restore_logging, _clear_contextvars):
    stream = io.StringIO()
    configure_logging(Settings(app_env="production", log_format="auto"), stream=stream)
    logging.getLogger("app.probe").info("structured please")
    payload = _parse_lines(stream.getvalue())[-1]
    assert payload["message"] == "structured please"
    assert payload["logger"] == "app.probe"
    assert set(payload) >= {"timestamp", "level", "logger", "message", "request_id"}


def test_configure_logging_emits_text_in_development(_restore_logging, _clear_contextvars):
    stream = io.StringIO()
    configure_logging(Settings(app_env="development", log_format="auto"), stream=stream)
    logging.getLogger("app.probe").info("human please")
    out = stream.getvalue()
    assert "human please" in out
    with pytest.raises(json.JSONDecodeError):
        json.loads(out.splitlines()[-1])


def test_configure_logging_is_idempotent(_restore_logging):
    """重复调用只保留一个自装 handler（应用启动 + 多次 import 不得叠加日志）。"""
    configure_logging(Settings(app_env="development"))
    configure_logging(Settings(app_env="development"))
    configure_logging(Settings(app_env="development"))
    marked = [
        h for h in logging.getLogger().handlers if getattr(h, "_taskflow_structured_handler", False)
    ]
    assert len(marked) == 1


def test_configure_logging_does_not_touch_foreign_handlers(_restore_logging):
    """不得清掉别人的 handler（否则会破坏 pytest 的日志捕获等外部集成）。"""
    root = logging.getLogger()
    foreign = logging.NullHandler()
    root.addHandler(foreign)
    try:
        configure_logging(Settings(app_env="development"))
        assert foreign in root.handlers
    finally:
        root.removeHandler(foreign)


def test_configure_logging_adopts_uvicorn_loggers(_restore_logging):
    """uvicorn 自带 logger 被收编到 root，避免同一请求出现两种日志格式。"""
    configure_logging(Settings(app_env="production"))
    for name in ("uvicorn", "uvicorn.error"):
        lg = logging.getLogger(name)
        assert lg.handlers == []
        assert lg.propagate is True
    # uvicorn.access 压到 WARNING：本项目的 RequestLoggingMiddleware 已记录更完整
    # 的访问日志（含 duration / user_id），保留 uvicorn 那条会让每个请求出现两条。
    access = logging.getLogger("uvicorn.access")
    assert access.handlers == []
    assert access.propagate is True
    assert access.level == logging.WARNING


def test_configure_logging_sets_root_level(_restore_logging):
    configure_logging(Settings(app_env="development", log_level="WARNING"))
    assert logging.getLogger().level == logging.WARNING


def test_configure_logging_applies_sensitive_filter(_restore_logging, _clear_contextvars):
    """端到端：敏感值经 handler 出口就已脱敏（不是靠调用方自觉）。"""
    stream = io.StringIO()
    configure_logging(Settings(app_env="production"), stream=stream)
    logging.getLogger("app.probe").info("login", extra={"password": "top-secret"})
    payload = _parse_lines(stream.getvalue())[-1]
    assert payload["password"] == MASK
    assert "top-secret" not in stream.getvalue()


def test_non_string_message_is_still_redacted(_restore_logging, _clear_contextvars):
    """把**非字符串**消息（dict / list）交给 logger 时也必须脱敏（§48 敏感日志泄露）。

    回归测试：`logger.info({"password": "..."})` 曾经**完全绕过**脱敏——过滤器只对
    `isinstance(msg, str)` 调用 `redact_text`，而 `LogRecord.getMessage()` 对「无 args」
    的记录会做 `str(self.msg)`，于是字典 repr（含明文口令）原样写进 JSON 日志。
    由 TASK-062 的覆盖率排查发现并修复（见 DECISIONS 044）。

    两条断言分别覆盖两种形态：**字典 repr** 与**列表内嵌的 `key: value`**——后者的
    键名两侧带引号，正是老正则「键名必须紧邻分隔符」这一定义匹配不到的那种写法。
    """
    stream = io.StringIO()
    configure_logging(Settings(app_env="production"), stream=stream)
    logger = logging.getLogger("app.probe")

    logger.info({"password": "top-secret", "user": "bob"})
    logger.warning(["refresh_token: other-secret"])

    out = stream.getvalue()
    assert "top-secret" not in out, out
    assert "other-secret" not in out, out

    payloads = _parse_lines(out)
    assert MASK in payloads[0]["message"] and "bob" in payloads[0]["message"]
    assert MASK in payloads[1]["message"]


# --- 访问日志中间件 ---------------------------------------------------------


def _build_probe_app() -> FastAPI:
    probe = FastAPI()
    probe.add_middleware(RequestLoggingMiddleware)

    @probe.get("/ok")
    async def ok():
        return {"ok": True}

    @probe.get("/")
    async def root_path():
        return {"root": True}

    @probe.get("/ctx")
    async def ctx():
        # 请求内「下游日志」看到的 user_id（由中间件写进 ContextVar）
        return {"ctx_user_id": user_id_var.get()}

    @probe.get("/boom")
    async def boom():
        raise RuntimeError("kaboom")

    return probe


@pytest.fixture
def access_log_stream(monkeypatch):
    """捕获 ``app.core.middleware`` 的日志，并打开访问日志开关。"""
    settings = Settings(app_env="development", log_requests=True)
    import app.core.middleware as mw

    monkeypatch.setattr(mw, "get_settings", lambda: settings, raising=True)

    logger = logging.getLogger("app.core.middleware")
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    handler.setLevel(logging.INFO)
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


async def _get(app, path, headers=None, *, raise_app_exceptions=True):
    transport = ASGITransport(app=app, raise_app_exceptions=raise_app_exceptions)
    async with AsyncClient(transport=transport, base_url="http://probe") as client:
        return await client.get(path, headers=headers)


async def test_access_log_records_method_path_status_duration(
    access_log_stream, _clear_contextvars
):
    resp = await _get(_build_probe_app(), "/ok")
    assert resp.status_code == 200

    payload = _parse_lines(access_log_stream.getvalue())[-1]
    assert payload["message"] == "request completed"
    assert payload["method"] == "GET"
    assert payload["path"] == "/ok"
    assert payload["status_code"] == 200
    assert isinstance(payload["duration"], (int, float))
    assert payload["duration"] >= 0
    # client_ip（TASK-060）：反代之后只记 TCP 对端地址的话，日志里全是 Nginx 的
    # 地址，排查时无法区分请求来源。这里断言字段存在且为对端地址（该探针没有
    # 反代，也没有开启代理信任）。
    assert payload["client_ip"] == "127.0.0.1"
    # 未认证：user_id 为 null。该探针应用只注册了 RequestLoggingMiddleware，
    # 没有 RequestIdMiddleware（TASK-057），因此 request_id 也是 null——
    # 恰好验证了「formatter 在 ContextVar 未设置时输出 null」的 schema 稳定性。
    assert payload["user_id"] is None
    assert payload["request_id"] is None


async def test_access_log_records_non_api_paths(access_log_stream, _clear_contextvars):
    """用户确认：全部路径都记录（含 ``/``、``/health``、``/docs``）。"""
    await _get(_build_probe_app(), "/")
    paths = [p["path"] for p in _parse_lines(access_log_stream.getvalue())]
    assert "/" in paths


async def test_access_log_includes_user_id_from_token(
    access_log_stream, _clear_contextvars
):
    user_id = 4242
    resp = await _get(
        _build_probe_app(),
        "/ok",
        headers={"Authorization": f"Bearer {create_access_token(user_id)}"},
    )
    assert resp.status_code == 200
    payload = _parse_lines(access_log_stream.getvalue())[-1]
    assert payload["user_id"] == user_id


async def test_access_log_ignores_invalid_token(access_log_stream, _clear_contextvars):
    resp = await _get(
        _build_probe_app(), "/ok", headers={"Authorization": "Bearer not-a-jwt"}
    )
    assert resp.status_code == 200
    payload = _parse_lines(access_log_stream.getvalue())[-1]
    assert payload["user_id"] is None  # 解不出来 → null，不是 500


async def test_access_log_never_leaks_authorization_header(
    access_log_stream, _clear_contextvars
):
    token = create_access_token(99)
    await _get(
        _build_probe_app(), "/ok", headers={"Authorization": f"Bearer {token}"}
    )
    assert token not in access_log_stream.getvalue()


async def test_middleware_propagates_user_id_contextvar_to_downstream(
    access_log_stream, _clear_contextvars
):
    """§33 要求 request_id/user_id 出现在请求内的日志上——靠 ContextVar 承接。"""
    user_id = 777
    resp = await _get(
        _build_probe_app(),
        "/ctx",
        headers={"Authorization": f"Bearer {create_access_token(user_id)}"},
    )
    assert resp.json()["ctx_user_id"] == user_id
    # 请求结束后必须还原，避免泄漏到下一个请求
    assert user_id_var.get() is None


async def test_access_log_records_500_on_unhandled_exception(
    access_log_stream, _clear_contextvars
):
    resp = await _get(_build_probe_app(), "/boom", raise_app_exceptions=False)
    assert resp.status_code == 500

    payload = _parse_lines(access_log_stream.getvalue())[-1]
    assert payload["status_code"] == 500
    assert payload["path"] == "/boom"


async def test_access_log_disabled_by_setting(monkeypatch, _clear_contextvars):
    """LOG_REQUESTS=false 时不产生访问日志（测试套件默认走这条路径）。"""
    settings = Settings(app_env="development", log_requests=False)
    import app.core.middleware as mw

    monkeypatch.setattr(mw, "get_settings", lambda: settings, raising=True)

    logger = logging.getLogger("app.core.middleware")
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setLevel(logging.INFO)
    old_level = logger.level
    logger.addHandler(handler)
    # 显式设级别，确保「无输出」是开关生效、而非级别过滤造成的假通过。
    logger.setLevel(logging.INFO)
    try:
        resp = await _get(_build_probe_app(), "/ok")
        assert resp.status_code == 200
        assert stream.getvalue() == ""
    finally:
        logger.removeHandler(handler)
        logger.setLevel(old_level)


async def test_access_log_duration_reflects_slow_handler(monkeypatch, _clear_contextvars):
    """duration 是真实耗时的上界观测（不是常量 0）。"""
    import asyncio

    probe = FastAPI()
    probe.add_middleware(RequestLoggingMiddleware)

    @probe.get("/slow")
    async def slow():
        await asyncio.sleep(0.05)
        return {"ok": True}

    settings = Settings(app_env="development", log_requests=True)
    import app.core.middleware as mw

    monkeypatch.setattr(mw, "get_settings", lambda: settings, raising=True)

    logger = logging.getLogger("app.core.middleware")
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    old_propagate = logger.propagate
    old_level = logger.level
    logger.propagate = False
    # ⚠ 必须显式设级别：pytest 默认把 root logger 设为 WARNING，若不设级别，
    # INFO 级访问日志会被 `isEnabledFor` 过滤掉，得到空输出。
    logger.setLevel(logging.INFO)
    try:
        started = time.perf_counter()
        await _get(probe, "/slow")
        elapsed_ms = (time.perf_counter() - started) * 1000
        payload = _parse_lines(stream.getvalue())[-1]
        assert 40 <= payload["duration"] <= elapsed_ms + 50
    finally:
        logger.removeHandler(handler)
        logger.propagate = old_propagate
        logger.setLevel(old_level)
