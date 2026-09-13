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
分页、合理索引、批量查询、selectinload/joinedload、防止 N+1；必要时使用 EXPLAIN ANALYZE。
