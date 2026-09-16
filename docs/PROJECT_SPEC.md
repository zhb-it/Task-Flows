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
Python 3.13、FastAPI、Pydantic v2、SQLAlchemy 2.0、Alembic、PostgreSQL 16、Redis 7、Celery、JWT、pytest、pytest-asyncio、httpx、Docker、Nginx、Gunicorn、Uvicorn、GitHub Actions。

> 版本口径统一为 **Python 3.13**（`Dockerfile` 的 `python:3.13-slim`、CI 的 `PYTHON_VERSION=3.13`、`pyproject.toml` 的 `target-version = "py313"` 三处一致）。原句写作「3.11/3.12」，是初始化阶段的宽松区间，与后来落地的三处 3.13 钉死不兼容；**订正记录见 DECISIONS 044**。
>
> 已知环境偏差：本地开发 venv 为 Python 3.14.6（高于 CI/生产的 3.13）。功能等价、测试全绿，但**版本相关缺陷（弃用警告、新语法）在本地不会暴露**；因此 CI 的 3.13 job 是版本口径的最终裁判（见 docs/QUALITY.md「环境偏差」）。


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

## 7. 企业化扩展（TASK-088 起）
经项目所有者确认，项目按「企业可直接使用」标准继续演进。**四个边界**：目标形态为
**多租户 SaaS**；交付底座为 **Docker Compose 与 Kubernetes 都要**；身份档位为
**本地账号加固 + MFA（TOTP）+ 企业目录（OIDC/LDAP）**；**不做「最小可交付版」**。

新增需求的**规格事实来源是开发文档 §61**（租户层、MFA/SSO、邮件、备份、指标、
CSP/TLS、数据主体权利、`total` 分页、对象存储、K8s 清单等）；本节不重复其内容，
只登记「以下三节的既有口径在哪些地方被修订」：

- **§2 明确需求**：追加租户与配额、健康检查四端点与指标、邮件、会话管理、SSO 与 MFA、
  备份恢复、数据主体权利。
- **§5 重要业务规则**：`username` / `email` 唯一**改为租户内唯一**；新增「所有资源
  访问必须有租户作用域，跨租户一律返回与不存在不可区分的响应」；RBAC 改为租户内角色。
- **§6 非功能要求**：在其上追加「可观测、可运维、可合规」——指标与告警、备份与恢复演练、
  保留期由代码执行。

任务的实施顺序与验收标准见 `docs/TASKS.md`（Phase 18~23 / TASK-088~127）；
缺口证据与排序理由见 `docs/ENTERPRISE_READINESS.md`。
