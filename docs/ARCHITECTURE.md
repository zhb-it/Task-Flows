# TaskFlow Pro 架构

## 分层
```text
Client
  ↓
Nginx
  ↓
Gunicorn + Uvicorn
  ↓
FastAPI
  ↓
Router
  ↓
Service
  ↓
CRUD
  ↓
SQLAlchemy
  ↓
PostgreSQL
```

Redis 与 FastAPI/Celery 协作，用于限流、JWT 黑名单以及 Celery Broker/Backend。

## 模块职责
- core：配置、安全、依赖、异常
- db：数据库 Session 与 Base
- models：ORM 模型
- schemas：请求/响应模型
- crud：数据库 CRUD
- services：业务逻辑、权限、状态机、事务协调
- api/v1：HTTP API
- tasks：Celery
- middleware：限流
- tests：测试

## 核心依赖规则
Router 不直接承载复杂 SQL 或业务规则。
Service 可以组合多个 CRUD，并协调 Redis/Celery。
数据库约束负责数据完整性，Service 负责业务规则。

## 事务边界
例如创建任务、分配成员、写操作日志等多个数据库动作必须由 Service 统一协调；任一步失败则整体回滚。

## 性能原则
分页（统一 `skip`/`limit`，`limit` 上限 100）、合理索引、批量查询、防止 N+1；必要时使用 EXPLAIN ANALYZE。

> **实现口径（TASK-062 订正）**：本行原写「selectinload/joinedload」，但本项目**全程零 `relationship()`**，因而也无从使用这两个 eager-load 选项——那不是被遗漏，而是刻意的设计选择：关联读取一律走**显式批量 IN 查询**（如 `app/crud/task_assignee.py::list_assignees_for_tasks`，一次 `WHERE task_id IN (...)` 组装列表内嵌字段）。
>
> 两种做法的抗 N+1 效果等价（都是「1 条主查询 + 1 条关联查询」，与行数无关），但显式批量查询把「查了几次」写死在代码里、可被 `tests/test_query_efficiency.py` 用运行时 SQL 计数直接验证；`selectinload` 的效果则依赖 `relationship()` 配置正确且调用方不忘 `.options(...)`，一旦漏掉就静默退化成 N+1。本项目选前者。**订正记录见 DECISIONS 044。**

