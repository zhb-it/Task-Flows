"""TASK-057：Request ID（§34）单元 + 中间件 + 真实应用测试.

§34 要求：每个 HTTP 请求都要有 ``request_id``；**可由客户端传入，也可以服务端
生成**；并且**日志中必须带**这个字段（目的是凭一个 id 捞出该次请求的全部日志）。

TASK-056 已把 ``request_id_var`` ContextVar 与 formatter 字段通道建好（无值输出
``null``，schema 稳定）；TASK-057 补上「生成 / 客户端透传 / 响应回传」这一环。
三处实现契约经用户确认（DECISIONS 038）：

1. 头名统一 ``X-Request-ID``（单一头，不作多头兼容）；
2. 客户端传入值**经白名单校验后才接受**，否则丢弃并重新生成；
3. ``request_id`` **不进入**错误响应体（§26 信封保持 ``{"detail": ...}`` 不变）。

本文件四层：

1. **``resolve_request_id`` 纯函数**——生成形态、合法值透传、非法值拒绝
   （日志注入 / 超长 / 字符集外）；
2. **中间件契约**——响应头回传、服务端生成、非法值丢弃、ContextVar 在请求内
   可见且请求结束后还原；
3. **与其它中间件协作**——最外层嵌套下访问日志带上 request_id；§26 错误信封
   的响应也带头；未处理异常的**已知边界**（响应无头但日志有 id）；
4. **真实应用**——``app.main`` 确实注册了该中间件（``/`` 与 401 均带头），
   且错误响应体未被改动。
"""

import io
import json
import logging
import re
import uuid

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from starlette.requests import Request

from app.core.config import Settings
from app.core.exceptions import AppError, ResourceNotFoundError, app_error_handler
from app.core.logging_config import JsonFormatter, request_id_var
from app.core.middleware import (
    REQUEST_ID_HEADER,
    RequestIdMiddleware,
    RequestLoggingMiddleware,
    resolve_request_id,
)
from app.main import app as real_app

RUN_TOKEN = uuid.uuid4().hex[:8]

#: 服务端生成的 id 形态：uuid4 的 hex（32 位小写十六进制）。
_GENERATED_RE = re.compile(r"[0-9a-f]{32}")


# ---------------------------------------------------------------------------
# 夹具 / 工具
# ---------------------------------------------------------------------------


@pytest.fixture
def _clear_request_id():
    """还原 request_id ContextVar，避免请求上下文泄漏到其它用例。"""
    token = request_id_var.set(None)
    yield
    request_id_var.reset(token)


def _make_request(headers: dict[str, str] | None = None) -> Request:
    """直接构造一个 Starlette Request（用于纯函数级测试，可放任意脏值）。

    头名按 HTTP 规范用 latin-1 编码；**头的值按 UTF-8 编码成原始字节**——
    因为 ASGI 层给的是字节、Starlette 的 ``Headers`` 再用 **latin-1 解码**，
    所以客户端真发出非 ASCII（如 ``中文id``）时，中间件看到的是一串 latin-1
    乱码（``ä¸æ–‡id``）。这正是它必须拒绝的形态，而不是被编码器提前拦下。
    """
    raw_headers = [
        (key.lower().encode("latin-1"), value.encode("utf-8"))
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
            "client": ("127.0.0.1", 12345),
            "server": ("probe", 80),
        }
    )


def _build_probe_app(*, access_log: bool = False) -> FastAPI:
    """探针应用：RequestId 永远注册，访问日志可选，顺序与 ``app/main.py`` 一致。"""
    probe = FastAPI()
    if access_log:
        probe.add_middleware(RequestLoggingMiddleware)
    # 后注册者更靠外：与 main.py 相同的「RequestId 在最外层」嵌套关系。
    probe.add_middleware(RequestIdMiddleware)
    probe.add_exception_handler(AppError, app_error_handler)

    @probe.get("/ok")
    async def ok():
        return {"ok": True}

    @probe.get("/ctx")
    async def ctx():
        # 请求内「下游」看到的 request_id（由中间件写进 ContextVar）
        return {"ctx_request_id": request_id_var.get()}

    @probe.get("/missing")
    async def missing():
        raise ResourceNotFoundError("Task not found")

    @probe.get("/boom")
    async def boom():
        raise RuntimeError("kaboom")

    return probe


async def _get(app, path, headers=None, *, raise_app_exceptions=True):
    transport = ASGITransport(app=app, raise_app_exceptions=raise_app_exceptions)
    async with AsyncClient(transport=transport, base_url="http://probe") as client:
        return await client.get(path, headers=headers)


@pytest.fixture
def access_log_stream(monkeypatch):
    """捕获 ``app.core.middleware`` 的日志，并打开访问日志开关（TASK-056 范式）。"""
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
    # ⚠ 必须显式设级别：pytest 默认把 root logger 设为 WARNING，否则 INFO 级
    # 访问日志被过滤掉，断言会「假通过」（TASK-056 已踩过这个坑）。
    logger.setLevel(logging.INFO)
    logger.propagate = False
    try:
        yield stream
    finally:
        logger.removeHandler(handler)
        logger.setLevel(old_level)
        logger.propagate = old_propagate


def _parse_lines(raw: str) -> list[dict]:
    return [json.loads(line) for line in raw.splitlines() if line.strip()]


# ---------------------------------------------------------------------------
# 1. resolve_request_id 纯函数
# ---------------------------------------------------------------------------


def test_generates_uuid_hex_when_header_absent(_clear_request_id):
    generated = resolve_request_id(_make_request())
    assert _GENERATED_RE.fullmatch(generated)


def test_generation_is_unique_per_call(_clear_request_id):
    first = resolve_request_id(_make_request())
    second = resolve_request_id(_make_request())
    assert first != second


def test_generation_is_itself_accepted_by_the_validator(_clear_request_id):
    """自生成值必须落在白名单内——否则「回传的 id 客户端下次传回来会被丢弃」。"""
    generated = resolve_request_id(_make_request())
    echoed = resolve_request_id(_make_request({REQUEST_ID_HEADER: generated}))
    assert echoed == generated


def test_accepts_client_supplied_safe_value():
    supplied = f"client-rid-{RUN_TOKEN}.v1_x"
    assert resolve_request_id(_make_request({REQUEST_ID_HEADER: supplied})) == supplied


def test_accepts_w3c_traceparent_style_value():
    traceparent = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
    got = resolve_request_id(_make_request({REQUEST_ID_HEADER: traceparent}))
    assert got == traceparent


def test_accepts_value_with_surrounding_whitespace():
    """前后空白是传输噪声（不是攻击），strip 后合法即接受。"""
    assert resolve_request_id(_make_request({REQUEST_ID_HEADER: "  rid-1  "})) == "rid-1"


def test_accepts_exactly_max_length():
    value = "a" * 64
    assert resolve_request_id(_make_request({REQUEST_ID_HEADER: value})) == value


@pytest.mark.parametrize(
    "dirty",
    [
        "a" * 65,  # 超长
        "bad value",  # 空格
        "a*b",  # 字符集外
        "rid;drop",  # 分隔符
        "../../etc/passwd",  # 路径穿越样式
        "<script>alert(1)</script>",  # HTML
        "中文id",  # 非 ASCII
        "rid\nsecond-line",  # **日志注入**：换行使一行日志变成两行
        "rid\r\ninjected",  # CRLF
        "rid\x00null",  # 控制字符
    ],
)
def test_rejects_unsafe_client_value_and_regenerates(dirty):
    """非法值（含日志注入）一律丢弃并重新生成，绝不复用脏值。"""
    generated = resolve_request_id(_make_request({REQUEST_ID_HEADER: dirty}))
    assert generated != dirty
    assert _GENERATED_RE.fullmatch(generated)


def test_empty_header_generates(_clear_request_id):
    assert _GENERATED_RE.fullmatch(resolve_request_id(_make_request({REQUEST_ID_HEADER: ""})))
    assert _GENERATED_RE.fullmatch(resolve_request_id(_make_request({REQUEST_ID_HEADER: "   "})))


# ---------------------------------------------------------------------------
# 2. RequestIdMiddleware 契约
# ---------------------------------------------------------------------------


async def test_response_header_is_server_generated_when_client_sends_none(
    _clear_request_id,
):
    resp = await _get(_build_probe_app(), "/ok")
    assert resp.status_code == 200
    header = resp.headers.get(REQUEST_ID_HEADER)
    assert header is not None
    assert _GENERATED_RE.fullmatch(header)


async def test_response_header_echoes_valid_client_value(_clear_request_id):
    supplied = f"gw-{RUN_TOKEN}"
    resp = await _get(_build_probe_app(), "/ok", headers={REQUEST_ID_HEADER: supplied})
    assert resp.headers[REQUEST_ID_HEADER] == supplied


async def test_response_header_does_not_echo_unsafe_client_value(_clear_request_id):
    dirty = "bad value!"
    resp = await _get(_build_probe_app(), "/ok", headers={REQUEST_ID_HEADER: dirty})
    assert resp.headers[REQUEST_ID_HEADER] != dirty
    assert _GENERATED_RE.fullmatch(resp.headers[REQUEST_ID_HEADER])


async def test_two_requests_get_different_ids(_clear_request_id):
    first = await _get(_build_probe_app(), "/ok")
    second = await _get(_build_probe_app(), "/ok")
    assert first.headers[REQUEST_ID_HEADER] != second.headers[REQUEST_ID_HEADER]


async def test_request_id_visible_to_downstream_code(_clear_request_id):
    """请求内任何代码都能通过 ContextVar 拿到 id（端点也可据此写业务日志）。"""
    resp = await _get(_build_probe_app(), "/ctx", headers={REQUEST_ID_HEADER: "rid-ctx-1"})
    assert resp.json()["ctx_request_id"] == "rid-ctx-1"


async def test_contextvar_is_reset_after_request(_clear_request_id):
    """请求结束必须还原，否则 id 会串到同一 worker 的下一个请求。"""
    await _get(_build_probe_app(), "/ok")
    assert request_id_var.get() is None


async def test_error_envelope_response_carries_header(_clear_request_id):
    """§26 错误信封（4xx）同样带 X-Request-ID——客户端报障时才有 id 可给。"""
    resp = await _get(_build_probe_app(), "/missing")
    assert resp.status_code == 404
    assert resp.json() == {"detail": "Task not found"}
    assert resp.headers.get(REQUEST_ID_HEADER)


async def test_error_envelope_body_is_unchanged(_clear_request_id):
    """用户确认：request_id **不进**响应体，§26 信封形状保持不变。"""
    resp = await _get(_build_probe_app(), "/missing")
    assert set(resp.json()) == {"detail"}


# ---------------------------------------------------------------------------
# 3. 与其它中间件协作（嵌套顺序）
# ---------------------------------------------------------------------------


async def test_access_log_carries_client_supplied_request_id(
    access_log_stream, _clear_request_id
):
    """§34 的核心要求：日志里必须有 request_id——且与响应头一致。"""
    resp = await _get(
        _build_probe_app(access_log=True),
        "/ok",
        headers={REQUEST_ID_HEADER: "rid-log-1"},
    )
    assert resp.headers[REQUEST_ID_HEADER] == "rid-log-1"
    payload = _parse_lines(access_log_stream.getvalue())[-1]
    assert payload["message"] == "request completed"
    assert payload["request_id"] == "rid-log-1"
    assert payload["path"] == "/ok"


async def test_access_log_carries_server_generated_request_id(
    access_log_stream, _clear_request_id
):
    resp = await _get(_build_probe_app(access_log=True), "/ok")
    payload = _parse_lines(access_log_stream.getvalue())[-1]
    assert payload["request_id"] == resp.headers[REQUEST_ID_HEADER]
    assert _GENERATED_RE.fullmatch(payload["request_id"])


async def test_access_log_request_id_differs_across_requests(
    access_log_stream, _clear_request_id
):
    await _get(_build_probe_app(access_log=True), "/ok")
    await _get(_build_probe_app(access_log=True), "/ok")
    lines = _parse_lines(access_log_stream.getvalue())
    assert len({line["request_id"] for line in lines}) == len(lines) == 2


async def test_unhandled_exception_boundary_log_has_id_but_response_has_no_header(
    access_log_stream, _clear_request_id
):
    """已知边界（TASK-057 决策记录）：未处理异常由 Starlette 的 ServerErrorMiddleware
    渲染 500，而它在本中间件**之外**，因此该响应**没有** X-Request-ID 头。
    这不影响 §34 的硬要求——请求的日志里仍然带着 request_id（下面断言）。"""
    resp = await _get(
        _build_probe_app(access_log=True), "/boom", raise_app_exceptions=False
    )
    assert resp.status_code == 500
    assert resp.headers.get(REQUEST_ID_HEADER) is None

    payload = _parse_lines(access_log_stream.getvalue())[-1]
    assert payload["status_code"] == 500
    assert payload["path"] == "/boom"
    assert payload["request_id"] is not None


# ---------------------------------------------------------------------------
# 4. 真实应用（app.main）
# ---------------------------------------------------------------------------


def test_real_app_registers_request_id_outermost():
    """RequestIdMiddleware 必须是最外层（最后注册）——否则访问日志拿不到 id。"""
    assert real_app.user_middleware[0].cls is RequestIdMiddleware
    registered = [m.cls for m in real_app.user_middleware]
    assert registered.index(RequestIdMiddleware) < registered.index(
        RequestLoggingMiddleware
    )


async def test_real_app_sets_header_on_root_path(_clear_request_id):
    transport = ASGITransport(app=real_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/")
    assert resp.status_code == 200
    assert _GENERATED_RE.fullmatch(resp.headers[REQUEST_ID_HEADER])


async def test_real_app_echoes_client_request_id(_clear_request_id):
    sent = f"gateway-{RUN_TOKEN}"
    transport = ASGITransport(app=real_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/", headers={REQUEST_ID_HEADER: sent})
    assert resp.headers[REQUEST_ID_HEADER] == sent


async def test_real_app_401_carries_header_and_unchanged_body(_clear_request_id):
    """真实端点的认证失败：带头（可追溯）+ 信封未变（§26 / 用户决策）。"""
    transport = ASGITransport(app=real_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/api/v1/users/me")
    assert resp.status_code == 401
    assert resp.headers[REQUEST_ID_HEADER]
    assert resp.json() == {"detail": "Not authenticated"}
    assert resp.headers["WWW-Authenticate"] == "Bearer"
