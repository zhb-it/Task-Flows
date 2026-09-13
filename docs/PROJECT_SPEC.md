# TaskFlow Pro 项目规格

## 1. 项目定位
生产级团队任务协作平台后端，用于团队任务、成员、项目、权限、通知和审计管理。

## 2. 明确需求
- 用户注册、登录、身份认证
- JWT Access Token + Refresh Token + JTI + Token 撤销
- RBAC：User / Role / Permission / UserRole / RolePermission
- Team / TeamMember / Project
- Task 创建、查询、修改、删除、多人分配
- Task 状态机
- Comment / Attachment
- Operation Log
- Notification
- Redis 限流、JWT 黑名单、Celery Broker/Backend
- Celery 异步通知、日志归档、附件清理
- PostgreSQL 16、Alembic、索引优化、全文搜索
- pytest API/核心业务测试
- Docker / Compose / Nginx / Gunicorn / Uvicorn
- GitHub Actions CI
- Health Check、日志、Request ID

## 3. 技术栈
Python 3.11/3.12、FastAPI、Pydantic v2、SQLAlchemy 2.0、Alembic、PostgreSQL 16、Redis 7、Celery、JWT、pytest、pytest-asyncio、httpx、Docker、Nginx、Gunicorn、Uvicorn、GitHub Actions。

## 4. 架构
Router -> Service -> CRUD -> Model。
Router 不承担复杂业务；Service 负责业务规则、权限、状态机、事务协调；CRUD 负责数据库操作；Model 负责 ORM 映射。

## 5. 重要业务规则
- username、email 唯一
- password 不能明文保存，API 不返回 password_hash
- 用户只能访问其所属团队链路下的资源
- TaskAssignee 使用 UNIQUE(task_id, user_id)
- Task 状态：TODO -> IN_PROGRESS -> REVIEW -> DONE；任意状态可 -> CANCELLED
- DONE/CANCELLED 不允许继续流转
- status 不允许通过普通 Task PATCH 任意修改，必须使用 transition API
- 多数据库操作必须在 Service 事务中协调
- 数据库结构变化必须通过 Alembic

## 6. 非功能要求
真实可运行、可测试、可部署、可解释；禁止虚构接口、字段、运行结果和无实际用途的技术。
