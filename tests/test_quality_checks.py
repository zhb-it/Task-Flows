"""静态质量契约测试（TASK-062；开发文档 §57 / §26 / §45-49）。

本文件把「架构与质量必须成立的性质」固化成**不依赖数据库、不联网**的静态断言：
直接解析 `app/` 下的源码与 FastAPI 生成的 OpenAPI schema。理由与
`tests/test_ci_workflow.py` / `tests/test_prod_compose.py` 一致——分层、密钥、
响应字段这类性质一旦被破坏，本地跑业务用例多半仍然全绿，只有等到线上（或安全
审计）才暴露；把它们变成会红的测试，才能让「顺手重构」付出的代价立刻可见。

覆盖的性质：

1. 分层：Router 不碰 CRUD（§4 Router → Service → CRUD → Model）；
2. Service 不依赖 HTTP 传输类型（唯一豁免 `UploadFile`——文件上传必须有个
   传输对象，见下方注释）；
3. Model 不反向依赖上层，且**没有任何 `relationship()`**（本项目统一用显式
   IN 批量查询代替惰性加载，是 N+1 防护的实现前提，见 §46）；
4. 响应 schema 绝不出现密码字段（项目规则 §5 / §9）；
5. 领域错误统一由 `AppError` 家族 + 单一 handler 渲染 `{"detail": ...}`（§26）；
6. 所有带 `limit` 的查询端点都必须 `le=100` 且默认值不超上限（§26 分页护栏）；
7. 配置默认值里不得出现真实密钥 / 生产连接串（§9 敏感信息）。
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from app.core.config import Settings
from app.core.exceptions import AppError
from app.main import app as fastapi_app

PROJECT_ROOT = Path(__file__).resolve().parent.parent
APP_DIR = PROJECT_ROOT / "app"
ROUTERS_DIR = APP_DIR / "api" / "v1"
SERVICES_DIR = APP_DIR / "services"
MODELS_DIR = APP_DIR / "models"
SCHEMAS_DIR = APP_DIR / "schemas"


# ---------------------------------------------------------------------------
# AST 辅助
# ---------------------------------------------------------------------------


def _py_files(directory: Path) -> list[Path]:
    return sorted(p for p in directory.glob("*.py") if p.name != "__init__.py")


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _imported_modules(tree: ast.Module) -> list[tuple[str, int]]:
    """返回 ``[(module_name, lineno)]``，覆盖 `import x` 与 `from x import y`。

    只关心模块名（`from app.crud.team import get_team` → `app.crud.team`），
    足够判定分层方向。
    """
    out: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                out.append((alias.name, node.lineno))
        elif isinstance(node, ast.ImportFrom):
            if node.module:  # 相对 import（module=None）在本项目不存在
                out.append((node.module, node.lineno))
    return out


def _imported_names_from(tree: ast.Module, module_prefix: str) -> list[str]:
    """收集 `from <module_prefix...> import A, B` 里导入的**名字**。"""
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith(
            module_prefix
        ):
            names.extend(alias.name for alias in node.names)
    return names


def _class_field_names(tree: ast.Module) -> dict[str, list[str]]:
    """``{类名: [字段名, ...]}`` —— 取类体里的 **AnnAssign**（Pydantic 字段）。"""
    classes: dict[str, list[str]] = {}
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            fields = [
                stmt.target.id
                for stmt in node.body
                if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name)
            ]
            classes[node.name] = fields
    return classes


# ---------------------------------------------------------------------------
# 1 / 2 / 3：分层契约
# ---------------------------------------------------------------------------


def test_routers_never_import_the_crud_layer():
    """Router 只能编排 Service，不得直接摸 CRUD（§4）。

    否则「事务边界 / 权限校验 / 业务规则」会从 Service 漏到 HTTP 层，
    分层名存实亡。
    """
    offenders: list[str] = []
    for path in _py_files(ROUTERS_DIR):
        for module, lineno in _imported_modules(_parse(path)):
            if module == "app.crud" or module.startswith("app.crud."):
                offenders.append(f"{path.name}:{lineno} imports {module}")
    assert not offenders, (
        "Router 层不得直接依赖 CRUD（应经 Service 中转）：\n  " + "\n  ".join(offenders)
    )


def test_routers_do_not_build_sql_directly():
    """Router 层不得直接引入 SQL 构造原语（§4「Router 不承载复杂 SQL」）。

    这是比「Router 必须 import Service」更准确的判据：`GET /users/me` 就是反例——
    它的数据来自 `CurrentUser` 依赖（`app/core/deps.py` 经 Service 装载），本身
    不需要 Service import，却是完全正确的薄路由。真正要禁止的是**在 HTTP 层拼
    `select()/insert()/update()/delete()`**——那意味着查询逻辑绕过 CRUD/Service 直落
    路由，事务边界与权限校验都会失去统一落点。
    """
    sql_primitives = {"select", "insert", "update", "delete"}
    offenders: list[str] = []
    for path in _py_files(ROUTERS_DIR):
        names = set(_imported_names_from(_parse(path), "sqlalchemy"))
        bad = names & sql_primitives
        if bad:
            offenders.append(f"{path.name} imports {sorted(bad)}")
    assert not offenders, (
        "Router 层出现 SQL 构造原语（应下沉到 CRUD/Service）：\n  " + "\n  ".join(offenders)
    )


def test_services_do_not_depend_on_http_transport_types():
    """Service 层不应绑定 FastAPI 传输对象（§4）。

    唯一豁免：`UploadFile`。文件上传的业务逻辑（校验大小 / 类型 / 落盘 / 写元数据）
    天然需要一个「还没读进内存的字节流」抽象，FastAPI 的 `UploadFile` 就是它；
    为此造一个自定义协议类型只会增加适配层而无收益。其余任何 FastAPI 名字
    （`Request` / `Response` / `HTTPException` / `status` …）出现在 Service 都算越界。
    """
    allowed = {"UploadFile"}
    offenders: list[str] = []
    for path in _py_files(SERVICES_DIR):
        names = set(_imported_names_from(_parse(path), "fastapi"))
        extra = names - allowed
        if extra:
            offenders.append(f"{path.name} imports {sorted(extra)}")
    assert not offenders, (
        "Service 层出现 HTTP 传输类型（仅允许 UploadFile）：\n  " + "\n  ".join(offenders)
    )


def test_models_do_not_import_upper_layers():
    """Model 是最底层，不得反向依赖 Service / Router / CRUD。"""
    offenders: list[str] = []
    for path in _py_files(MODELS_DIR):
        for module, lineno in _imported_modules(_parse(path)):
            if module.startswith(("app.services", "app.api", "app.crud")):
                offenders.append(f"{path.name}:{lineno} imports {module}")
    assert not offenders, "Model 层反向依赖上层：\n  " + "\n  ".join(offenders)


def test_no_orm_relationship_anywhere_in_models():
    """全模型不使用 `relationship()`（§46 的实现前提）。

    惰性 `relationship()` 是 N+1 的经典来源：一次 `task.assignees` 访问就是
    一条隐式 SQL。本项目改用显式 IN 批量查询（`list_assignees_for_tasks`）把
    「查几次」写死在代码里。此断言把该约定钉死——一旦有人「顺手」加回关系映射，
    这里立刻变红，而不是等到某天列表接口慢下来。
    """
    offenders: list[str] = []
    for path in _py_files(MODELS_DIR):
        tree = _parse(path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id == "relationship":
                    offenders.append(f"{path.name}:{node.lineno}")
    assert not offenders, f"Model 层出现 relationship()（应改显式批量查询）：{offenders}"


# ---------------------------------------------------------------------------
# 4：响应 schema 绝不暴露密码
# ---------------------------------------------------------------------------


def test_response_schemas_never_expose_any_password_field():
    """`*Read` / `*Response` schema 不得出现 password / password_hash 字段（§5 / §9）。

    只校验**出参**方向：`UserCreate` / `LoginRequest` 这类入参携带明文 password
    是登录契约的正常部分（见 `app/schemas/user.py` 文档串），不在此断言范围。
    """
    offenders: list[str] = []
    for path in _py_files(SCHEMAS_DIR):
        for cls, fields in _class_field_names(_parse(path)).items():
            if not (cls.endswith("Read") or cls.endswith("Response")):
                continue
            for field in fields:
                if "password" in field.lower():
                    offenders.append(f"{path.name}: {cls}.{field}")
    assert not offenders, "出参 schema 暴露了密码字段：\n  " + "\n  ".join(offenders)


def test_user_read_explicitly_omits_the_password_hash():
    """把最关键的那一个模型单独钉死：`UserRead` 的字段集合不含 password_hash。"""
    from app.schemas.user import UserRead

    assert "password_hash" not in UserRead.model_fields
    assert not any("password" in name.lower() for name in UserRead.model_fields)


# ---------------------------------------------------------------------------
# 5：统一错误渲染
# ---------------------------------------------------------------------------


def test_domain_errors_carry_an_http_status_mapping():
    """每个 `AppError` 子类都显式声明 **4xx** 的具体状态码（§26）。

    不写死「必须恰好是 {401,403,404,409,429}」——上传链路的 `FileTooLargeError`
    (413) / `UnsupportedMediaTypeError` (415) / `InvalidUploadError` (400) 同样是
    合法的领域错误（首轮断言正是被 413 打红，才补全了这份清单）。真正的不变量是：
    **领域错误必须映射到一个具体的 4xx**，而不是回落到基类的 500。
    """
    subclasses = AppError.__subclasses__()
    assert subclasses, "AppError 应当有具体子类"

    for cls in subclasses:
        assert isinstance(cls.status_code, int), f"{cls.__name__} 未声明 status_code"
        assert 400 <= cls.status_code < 500, (
            f"{cls.__name__}.status_code={cls.status_code} 不是 4xx —— "
            "领域错误是「客户端可修正的错误」，落到 5xx 会让调用方无从下手"
        )
        assert cls.status_code != AppError.status_code, (
            f"{cls.__name__} 未覆盖基类的 {AppError.status_code}，等于没声明具体错误码"
        )

    codes = {cls.status_code for cls in subclasses}
    # 这些错误码是各业务线显式依赖的契约，必须持续存在（缺失意味着某个 AppError
    # 子类被删掉/改名，而调用方与文档仍在引用它）。
    required = {401, 403, 404, 409, 429, 400, 413, 415}
    assert required <= codes, f"缺少这些领域错误状态码：{sorted(required - codes)}"


def test_app_registers_a_single_apperror_handler():
    """产品应用为 `AppError` 注册了统一 handler，渲染 `{"detail": ...}` 信封（§26）。"""
    handlers = fastapi_app.exception_handlers
    assert AppError in handlers, "app 未注册 AppError 处理器"


async def test_apperror_handler_renders_the_detail_envelope():
    """handler 的响应体形状恒为 `{"detail": <str>}`，status_code 取自异常类（§26）。

    直接调用 handler 而不经 HTTP：这里要钉死的是**渲染契约**本身，与路由/认证无关。
    """
    import json

    from app.core.exceptions import ConflictError, app_error_handler

    response = await app_error_handler(None, ConflictError("boom"))  # type: ignore[arg-type]
    assert response.status_code == 409
    assert json.loads(response.body) == {"detail": "boom"}

    # 未显式传 detail 时回落到类级默认文案。
    response = await app_error_handler(None, ConflictError())  # type: ignore[arg-type]
    assert json.loads(response.body) == {"detail": ConflictError.detail}


# ---------------------------------------------------------------------------
# 6：分页护栏（§26）
# ---------------------------------------------------------------------------


def test_every_paginated_endpoint_caps_limit_and_floors_skip():
    """所有带 `limit` 的查询端点都必须 `le=100`，默认值不超上限；`skip` 必须 `ge=0`。

    上限缺失意味着客户端可以用 `?limit=1000000` 把一次请求变成全表扫描（§45 性能 /
    §49 资源耗尽）。这里从 FastAPI 生成的 OpenAPI schema 读取约束——它正是运行时
    真正生效的那份声明，比正则扒源码更可靠。
    """
    schema = fastapi_app.openapi()
    offenders: list[str] = []
    checked_limit = 0

    for path, methods in schema["paths"].items():
        for method, op in methods.items():
            for param in op.get("parameters", []):
                if param.get("in") != "query":
                    continue
                name = param.get("name")
                sch = param.get("schema", {}) or {}
                if name == "limit":
                    checked_limit += 1
                    if sch.get("maximum") != 100:
                        offenders.append(
                            f"{method.upper()} {path}: limit maximum={sch.get('maximum')}"
                        )
                    default = sch.get("default")
                    if isinstance(default, int) and default > 100:
                        offenders.append(
                            f"{method.upper()} {path}: limit default={default} > 100"
                        )
                elif name == "skip" and sch.get("minimum") != 0:
                    offenders.append(
                        f"{method.upper()} {path}: skip minimum={sch.get('minimum')}"
                    )

    assert checked_limit >= 6, (
        f"只发现 {checked_limit} 个 limit 参数，分页契约测试可能已经失效（端点被重命名？）"
    )
    assert not offenders, "分页护栏被破坏：\n  " + "\n  ".join(offenders)


# ---------------------------------------------------------------------------
# 7：配置默认值不含真实密钥 / 生产连接串（§9）
# ---------------------------------------------------------------------------


def test_declared_config_defaults_carry_no_real_secret():
    """`Settings` 的**类级默认值**不得是真实凭证。

    只看 `model_fields[*].default`（声明值），不实例化 `Settings()`——实例化会读
    本地 `.env`，那正是要检查其是否被提交的地方，且会让测试结果依赖开发机环境。
    """
    fields = Settings.model_fields

    # JWT 密钥默认必须是占位符：仓库里出现可用的默认密钥，等于所有部署共享同一把钥匙。
    jwt_default = fields["jwt_secret_key"].default
    assert jwt_default in {"change-me", "changeme", "CHANGE_ME", ""}, (
        f"jwt_secret_key 默认值不是占位符：{jwt_default!r}"
    )

    # 连接串默认应指向容器网络内的服务名或回环地址，而非公网主机。
    db_default = fields["database_url"].default
    assert any(h in db_default for h in ("@postgres:", "@127.0.0.1:", "@localhost:")), (
        f"database_url 默认值疑似指向真实主机：{db_default!r}"
    )

    # 通用兜底：任何字符串默认值若呈现「长随机串」形状，视为可疑密钥。
    suspicious = [
        name
        for name, field in fields.items()
        if isinstance(field.default, str)
        and len(field.default) >= 32
        and re.fullmatch(r"[A-Za-z0-9_\-]{32,}", field.default)
    ]
    assert not suspicious, f"这些配置项的默认值疑似硬编码密钥：{suspicious}"
