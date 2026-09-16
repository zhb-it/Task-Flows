"""租户上下文与数据访问作用域（TASK-095 完整版；骨架见 TASK-094）.

多租户隔离的三道防线，对应「忘记带 ``tenant_id`` 条件在结构上不可能」
（§61.3）：

1. **请求级租户上下文**（:data:`_current_tenant_id` ContextVar）：认证依赖
   （``app.core.deps.get_current_user``）加载用户后写入其 ``tenant_id``，
   请求结束在 ``finally`` 内还原。并发请求各持独立 context，不串号。
2. **应用层统一作用域**（本模块全局 ORM 事件）：
   - 查询：``do_orm_execute`` 事件对所有 ORM SELECT（排除 column/relationship
     内部加载）按 ``TenantScoped`` 实体自动追加 ``tenant_id == :当前租户``
     （``with_loader_criteria``）——**CRUD 层零改动**，不依赖各 router 自觉；
   - 写入：``before_flush`` 事件把 ContextVar 中的租户注入未赋值的新对象
     （TASK-094 落地），显式赋值优先（如归档拷贝）。
3. **PostgreSQL RLS 兜底**（迁移 b8d4f2a6c9e1）：12 张业务表 ENABLE + FORCE
   ROW LEVEL SECURITY，策略 ``tenant_isolation`` 以 ``app.current_tenant_id()``
   判定。本模块 ``after_begin`` 事件在每个事务开始时写入事务级 GUC：
   ContextVar 有租户 → ``SET LOCAL app.tenant_id``；无租户（登录前、Celery、
   系统任务）→ ``SET LOCAL app.tenant_bypass = 'on'``。应用层即使漏加条件，
   运行时数据库角色（非超管）也会被 RLS 拦住——纵深防御（项目规则 §6）。

**绕过作用域的唯一显式出口**：:func:`bypass_tenant_scope`——平台管理员跨租户
查询专用，集中在本模块便于审查；进入即记审计日志（含调用点）。任何绕过
应用层作用域的新需求必须经由它，不允许在查询里手写 ``tenant_id`` 条件。

设计注意：

- ``do_orm_execute`` 只处理 SELECT（docs 配方口径）；UPDATE/DELETE 走对象级
  变更（先读后改，读取已被作用域），批量 DML 如需跨租户须走显式出口；
- GUC 一律 ``SET LOCAL``（事务级）：连接池回收（rollback）自动还原，
  不跨事务泄漏；``app.*`` 前缀的自定义 GUC 无需预定义即可设置；
- ``after_begin`` / ``before_flush`` / ``do_orm_execute`` 全部挂在 Session
  类上——测试自建的 SessionFactory 与生产 ``get_db`` 同等生效；
- 无租户上下文时应用层不做默认租户查询（写入由 DB 列 DEFAULT
  ``current_default_tenant_id()`` 归属默认租户，TASK-094 语义）。
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Iterator, Optional

from sqlalchemy import event, inspect as sa_inspect, text
from sqlalchemy.orm import Session, with_loader_criteria

logger = logging.getLogger(__name__)

_current_tenant_id: ContextVar[Optional[int]] = ContextVar(
    "current_tenant_id", default=None
)

#: 显式出口开关（TASK-095）：仅 :func:`bypass_tenant_scope` 写入。
_scope_bypass: ContextVar[bool] = ContextVar("tenant_scope_bypass", default=False)

DEFAULT_TENANT_SLUG = "default"

#: RLS 事务级 GUC 名（与迁移 b8d4f2a6c9e1 的策略/函数一致）。
GUC_TENANT_ID = "app.tenant_id"
GUC_SCOPE_BYPASS = "app.tenant_bypass"


class TenantScoped:
    """业务模型标记 mixin：参与自动租户作用域与 RLS 的实体集合。

    纯标记类（无列定义）——``tenant_id`` 列本身由 TASK-094 的迁移与各模型
    声明；本 mixin 只供 ``with_loader_criteria`` 圈定作用范围。全部 12 张
    业务表的模型必须继承它，RBAC/tenants 等非归属表不得继承。
    """


def set_current_tenant_id(tenant_id: int) -> Token:
    """设置当前请求的租户（认证依赖调用；返回 Token 供 finally 还原）。"""
    return _current_tenant_id.set(tenant_id)


def reset_current_tenant_id(token: Token) -> None:
    """还原 ContextVar（请求结束时 finally 内调用）。"""
    _current_tenant_id.reset(token)


def get_current_tenant_id() -> Optional[int]:
    """读取当前租户（无请求上下文时为 None）。"""
    return _current_tenant_id.get()


@contextmanager
def bypass_tenant_scope() -> Iterator[None]:
    """唯一显式出口：平台管理员跨租户查询专用（TASK-095）。

    语义：作用域内禁用应用层自动租户过滤，并把事务级 GUC 置为 bypass
    （RLS 兜底同步放行）。进入即记 WARNING 审计日志（含调用点）——任何
    跨租户能力必须可追溯。离开即恢复。

    用法::

        with bypass_tenant_scope():
            rows = await crud.cross_tenant_query(db)
    """
    import inspect as _inspect

    frame = _inspect.stack()[1]
    origin = f"{frame.filename}:{frame.lineno} ({frame.function})"
    token = _scope_bypass.set(True)
    logger.warning(
        "tenant scope bypass entered (platform admin cross-tenant query) at %s",
        origin,
    )
    try:
        yield
    finally:
        _scope_bypass.reset(token)


def scope_bypassed() -> bool:
    """当前是否处于显式出口内。"""
    return _scope_bypass.get()


def _has_tenant_column(obj: object) -> bool:
    mapper = sa_inspect(obj).mapper
    return "tenant_id" in mapper.columns


@event.listens_for(Session, "before_flush")
def _inject_tenant_on_flush(
    session: Session, flush_context, instances
) -> None:
    """把 ContextVar 中的显式租户注入未赋值的新对象（TASK-094 落地）。

    ContextVar 为 None（系统/后台路径）时不注入——写入由 DB 层列 DEFAULT
    （current_default_tenant_id）归属默认租户。显式赋值优先（如归档拷贝）。
    """
    explicit = _current_tenant_id.get()
    if explicit is None:
        return
    for obj in list(session.new):
        if not _has_tenant_column(obj):
            continue
        if getattr(obj, "tenant_id", None) is not None:
            continue  # 显式赋值优先（如归档拷贝）。
        obj.tenant_id = explicit


@event.listens_for(Session, "do_orm_execute")
def _scope_orm_select(execute_state) -> None:
    """应用层统一查询作用域（TASK-095 主防线）。

    对所有 ORM SELECT（排除 column/relationship 内部加载，照 docs 配方）
    自动追加 ``tenant_id == 当前租户``。无租户上下文（登录前/后台任务）或
    处于显式出口内时不注入——前者本就没有租户语义，后者是受审计的例外。

    实现注记：``with_loader_criteria`` 的主体在本机 SQLAlchemy 版本对
    **纯 mixin（非映射类）** 会把 mixin 自身传入 lambda（无 ``tenant_id``
    属性而报错），因此这里遍历注册表、对每个带 ``tenant_id`` 的具体
    mapper 逐类挂 criteria——效果与 mixin 主体等价，且不依赖版本行为。
    """
    if not (
        execute_state.is_select
        and not execute_state.is_column_load
        and not execute_state.is_relationship_load
    ):
        return
    tenant_id = _current_tenant_id.get()
    if tenant_id is None or _scope_bypass.get():
        return
    from app.db.base import Base  # 局部导入：模型注册完成后再取 mapper 清单

    criteria_options = [
        with_loader_criteria(
            mapper.class_,
            lambda cls: cls.tenant_id == tenant_id,  # noqa: B023 — 每次执行取当前值
            include_aliases=True,
        )
        for mapper in Base.registry.mappers
        if mapper.inherits is None and hasattr(mapper.class_, "tenant_id")
    ]
    if criteria_options:
        execute_state.statement = execute_state.statement.options(*criteria_options)


@event.listens_for(Session, "after_begin")
def _apply_rls_guc_on_begin(session: Session, transaction, connection) -> None:
    """每个事务开始时写入 RLS 事务级 GUC（TASK-095 兜底防线）。

    有租户上下文 → ``SET LOCAL app.tenant_id``（RLS 按 tenant 过滤）；
    无上下文（登录前/Celery/系统任务）或显式出口 →
    ``SET LOCAL app.tenant_bypass = 'on'``。仅对 PostgreSQL 方言生效；
    非 PG（如单测内存方言）直接跳过。
    """
    if connection.dialect.name != "postgresql":
        return
    tenant_id = _current_tenant_id.get()
    if tenant_id is None or _scope_bypass.get():
        connection.exec_driver_sql(f"SET LOCAL {GUC_SCOPE_BYPASS} = 'on'")
        return
    # tenant_id 来自 DB int 主键，直接拼接安全；SET LOCAL 随事务结束自动还原。
    connection.exec_driver_sql(f"SET LOCAL {GUC_TENANT_ID} = {int(tenant_id)}")


async def enforce_tenant_guc(session: Session) -> None:
    """在**当前已开启**的事务内补写 GUC（认证依赖接线用）。

    ``after_begin`` 只在新事务开始时触发：认证依赖先以无上下文查询用户
    （该事务已带 bypass GUC），加载成功并写入 ContextVar 后调用本函数，
    把同一事务内的后续查询翻转为「tenant 过滤 + bypass 关」——保证端点
    处理器的第一条查询就受 RLS 约束。仅 PostgreSQL 方言生效。
    """
    if session.bind is not None and session.bind.dialect.name != "postgresql":
        return
    tenant_id = _current_tenant_id.get()
    if tenant_id is None:
        return
    await session.execute(
        text(
            "SELECT set_config(:guc_tenant, :tid, true), "
            "set_config(:guc_bypass, 'off', true)"
        ),
        {
            "guc_tenant": GUC_TENANT_ID,
            "tid": str(int(tenant_id)),
            "guc_bypass": GUC_SCOPE_BYPASS,
        },
    )
