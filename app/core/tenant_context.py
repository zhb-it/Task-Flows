"""租户上下文骨架（TASK-094 立骨架，TASK-095 扩展为完整版）.

TASK-094 把全部业务表的 ``tenant_id`` 置为 NOT NULL，而租户上下文的完整
实现（认证依赖注入、CRUD 作用域、RLS）属 TASK-095。本模块先立骨架并
解决两者之间的**写入桥接**：租户上下文尚无来源的今天，新写入行归属
哪个租户？

答案沿用回填迁移（a9b7c5d3e1f0）的语义——**默认租户回退**，分两层：

1. **DB 层**（迁移 a9b7c5d3e1f0）：业务表 ``tenant_id`` 的列 DEFAULT 调用
   ``current_default_tenant_id()``（STABLE SQL 函数，查 ``tenants.slug =
   'default'``）。INSERT 不带 tenant_id 时由数据库自动归属默认租户——
   与存量回填语义一致，应用层零桥接；租户上下文（095）落地后，应用层
   显式赋值优先于列默认，本层自动退化为兜底。
2. **应用层**（本模块）：:data:`_current_tenant_id` ContextVar 是 TASK-095
   的请求级租户来源（认证依赖写入、``finally`` 还原）；flush 事件把
   ContextVar 中的显式租户注入到未赋值的新对象。本 TASK 阶段无人写入
   ContextVar，事件为 no-op——095 接线后即刻生效，注入点无需再改。

为什么注入点在 flush 层而不是各 CRUD 手写：TASK-095 的目标就是「忘记带
tenant_id 在结构上不可能」——收口在 flush 层比要求每个 CRUD 自觉更接近
这个目标；095 再叠加查询作用域与 RLS 形成纵深防御。

设计注意：

- flush 注入只处理 ``tenant_id IS None`` 的新对象，**显式赋值优先**
  （如归档任务从原日志行拷贝 tenant_id，不受注入影响）；
- 默认租户的解析只发生在 DB 层（列 DEFAULT），应用层不做默认租户查询，
  避免「同步事件里做异步查询」的结构性别扭。
"""

from __future__ import annotations

from contextvars import ContextVar, Token
from typing import Optional

from sqlalchemy import event, inspect as sa_inspect
from sqlalchemy.orm import Session

_current_tenant_id: ContextVar[Optional[int]] = ContextVar(
    "current_tenant_id", default=None
)

DEFAULT_TENANT_SLUG = "default"


def set_current_tenant_id(tenant_id: int) -> Token:
    """设置当前请求的租户（TASK-095 认证依赖调用；本 TASK 预留）。"""
    return _current_tenant_id.set(tenant_id)


def reset_current_tenant_id(token: Token) -> None:
    """还原 ContextVar（请求结束时 finally 内调用，TASK-095 接线）。"""
    _current_tenant_id.reset(token)


def get_current_tenant_id() -> Optional[int]:
    """读取当前租户（无请求上下文时为 None）。"""
    return _current_tenant_id.get()


def _has_tenant_column(obj: object) -> bool:
    mapper = sa_inspect(obj).mapper
    return "tenant_id" in mapper.columns


@event.listens_for(Session, "before_flush")
def _inject_tenant_on_flush(
    session: Session, flush_context, instances
) -> None:
    """把 ContextVar 中的显式租户注入未赋值的新对象（TASK-095 接线点）。

    本 TASK 阶段 ContextVar 恒为 None，事件为 no-op——无上下文的写入由
    DB 层列 DEFAULT（current_default_tenant_id）归属默认租户。095 由
    认证依赖写入 ContextVar 后，本事件自动生效，无需改动。
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
