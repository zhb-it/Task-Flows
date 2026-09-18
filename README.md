# TaskFlow Pro

生产级团队任务协作平台后端。FastAPI + PostgreSQL + Redis + Celery，严格四层架构、
全链路异步、真实测试覆盖、可 Docker 部署、CI 全绿。

目标是「能被面试追问到底」的项目：每个设计选择都能说清**为什么这么做**、
**替代方案差在哪**、**怎么证明它真的成立**。可核查的证据集中在
[`docs/QUALITY.md`](docs/QUALITY.md)；逐条决策记录在
[`docs/DECISIONS.md`](docs/DECISIONS.md)。

| 维度 | 事实 |
| --- | --- |
| 运行时 | Python 3.13（CI 与镜像）· FastAPI 0.141 · SQLAlchemy 2.0 async · Pydantic v2 |
| 数据库 | PostgreSQL 16 · 20 个 Alembic 迁移 · 17 张业务表 · 35 条外键 · 9 个唯一约束 · 7 个 CHECK |
| HTTP 接口 | 56 个操作（49 个在 `/api/v1` 下，共 33 条 `/api/v1` 路径；另有 `GET /`、5 个健康探针与 `GET /metrics`） |
| 缓存与队列 | Redis 7：滑动窗口限流（ZSET + Lua）+ Celery Broker/Backend |
| 认证授权 | JWT 双 Token（jti 落库 + 轮换 + 登出撤销）· Argon2id · RBAC + 资源级归属链 |
| 测试 | 1230 passed，0 failed / 0 error / 0 skipped；覆盖率 99.74% 行、98.94% 分支 |
| 部署 | Dockerfile（`python:3.13-slim`，非 root）· 开发/生产两套 Compose · Nginx + Gunicorn/Uvicorn |
| CI | GitHub Actions 三 job：ruff / pytest（含迁移可逆性三步）/ docker build |
| 前端 | Vue 3 + TypeScript + Vite（`frontend/`，规格阶段 1~3 已交付：工程骨架、主框架布局、认证；Dashboard 概览已接入真实后端） |

> 当前处于 Phase 19（多租户地基），TASK-001 ~ TASK-096 全部交付（后端 TASK-001~064 + 前端 TASK-065~080 + RBAC 闭环 TASK-081~084 + 找人体验与占位清理 TASK-085~087；注册默认绑定 member 角色，权限页/角色管理/我的权限端点已上线，用户搜索与邀请选择器已上线，项目详情任务/看板 Tab 已接真实组件）。**TASK-088 起为已确认的企业化规划（Phase 18~23 / TASK-088~127）**：生产可靠性地基 → 多租户地基 → 身份与安全硬化 → 合规与数据治理 → 产品补齐 → 工程化与双底座交付；缺口证据、实测快照与排序理由见 [`docs/ENTERPRISE_READINESS.md`](docs/ENTERPRISE_READINESS.md)，任务定义见 [`docs/TASKS.md`](docs/TASKS.md)。
> 任务清单见 [`docs/TASKS.md`](docs/TASKS.md)，实时进度见 [`docs/PROGRESS.md`](docs/PROGRESS.md)，
> 两者的一致性由 CI 断言（见「本地检查清单」）。

---

## 项目介绍

团队内部的协作平台后端：**团队 → 项目 → 任务**三级结构，任务支持多人分配、
状态机流转、评论、私有附件、站内通知与操作审计。

它要解决的不是「把 CRUD 写出来」，而是这类系统真实的难点：

- **权限不是一层**：功能级权限（`task:update`）之外还有资源级归属链（你必须是
  该任务所属团队的成员）。跨团队或不存在的资源**统一返回 404 而非 403**，
  避免用状态码把「资源是否存在」泄露出去（防枚举）。
- **状态不能随便改**：任务状态只能走专用 transition 接口，普通 `PATCH` 请求体里
  **没有 `status` 字段**——从 API 形状上杜绝绕过状态机。
- **审计与通知不能和主流程同生共死**：审计日志在主事务内落库（与业务同生共死），
  通知派发走 Celery 异步（允许重试、必须幂等）。
- **性能问题要能解释**：N+1 不靠「记得加 eager load」，而是把关联读取写成显式
  批量 `IN` 查询，并用运行时 SQL 计数测试钉死。

已实现的能力（对应 33 条 `/api/v1` 路径 / 56 个操作）：

| 模块 | 能力 |
| --- | --- |
| Auth | 注册、登录、刷新（轮换）、登出（撤销） |
| User | 当前用户信息 |
| RBAC | 角色 / 权限种子数据 + 功能级权限依赖 + 资源级归属链校验 |
| Team | 团队 CRUD + 成员管理（角色：OWNER / ADMIN / MEMBER） |
| Project | 项目 CRUD（归属团队） |
| Task | 任务 CRUD、多条件过滤 + 分页 + 排序、多人分配、状态流转 |
| Comment | 任务评论（创建 / 列表 / 删除） |
| Attachment | 私有附件上传 / 下载 / 删除（大小与类型限制、路径穿越防护） |
| Notification | 站内通知（列表、已读、全部已读），创建与流转时异步产生 |
| Logs | 操作审计日志（按资源、按用户维度查询） |
| Tenant | 租户生命周期（创建 / 列表 / 详情 / 更新 / 状态机转换），平台管理员专属（`tenant:manage`） |
| Health | 存活与依赖探针 |

---

## 技术栈

| 层 | 技术 | 版本 | 用途 |
| --- | --- | --- | --- |
| 语言 | Python | 3.13（Dockerfile/CI 钉死 `3.13`） | 运行时 |
| Web 框架 | FastAPI | 0.141.1 | 路由、依赖注入、OpenAPI |
| ASGI | Uvicorn | 0.52.4 | 开发/容器内 ASGI 服务器 |
| 生产服务器 | Gunicorn | 26.2.0 | 进程管理 + `UvicornWorker` |
| 校验 | Pydantic / pydantic-settings | 2.13.5 / 2.15.0 | 请求响应模型、配置管理 |
| ORM | SQLAlchemy | 2.0.52（async） | 模型与查询 |
| 驱动 | asyncpg / greenlet | 0.31.0 / 3.5.5 | PostgreSQL 异步驱动 |
| 迁移 | Alembic | 1.20.0 | schema 版本化 |
| 数据库 | PostgreSQL | 16 | 唯一事实来源 |
| 缓存/队列 | Redis | 7（`redis` 8.1.0） | 限流、Celery Broker/Backend |
| 异步任务 | Celery | 5.6.3 | 通知派发、日志归档、附件清理 |
| 认证 | PyJWT / pwdlib[argon2] | 2.14.0 / 0.3.1 | 双 Token、Argon2id 口令散列 |
| 测试 | pytest / pytest-asyncio / httpx | 9.1.1 / 1.4.0 / 0.28.1 | 端到端与单元测试 |
| Lint | ruff | 0.16.7 | 规则集与版本钉死在仓库 |
| 覆盖率 | pytest-cov | 7.1.0（仅本地，不进 CI 门禁） | 覆盖率基线 |

依赖分两份：`requirements.txt`（生产镜像用）与 `requirements-dev.txt`（本地与 CI 用，
含 ruff / pytest-cov）。后者刻意不塞进前者——lint 工具约 10MB，装进生产镜像是纯死重量。

---

## 系统架构

```text
Client
  ↓
Nginx                    ← 生产唯一入口：反代、请求体上限、安全头、覆盖式 X-Forwarded-For
  ↓
Gunicorn + UvicornWorker ← 进程管理 + ASGI（开发环境直接 Uvicorn）
  ↓
FastAPI                  ← 中间件：Request ID（最外层）→ 访问日志 → 限流
  ↓
Router  app/api/v1       ← 只做 HTTP 层：解析、依赖注入、调用 Service
  ↓
Service app/services     ← 业务规则、权限、事务边界、状态机、Redis/Celery 协调
  ↓
CRUD    app/crud         ← 只做数据库读写，不含业务判断
  ↓
Model   app/models       ← 表结构、约束、索引（DB 保证完整性）
  ↓
PostgreSQL
```

Redis 与 FastAPI / Celery 平级协作：限流判定、Celery Broker 与结果后端。
Celery Worker 与 API 是**同一镜像、不同命令**的两个进程。

**分层规则是机器可验证的**，不靠约定：`tests/test_quality_checks.py` 用 AST 解析
源码，断言 Router 不导入 CRUD 层、Router 不构造 SQL、Service 不依赖 HTTP 传输类型、
Model 不反向依赖上层、模型里零 `relationship()`。改坏了会当场变红。

### 模块职责

| 目录 | 职责 |
| --- | --- |
| `app/api/v1` | HTTP 层：路由、依赖注入、状态码；复杂度受契约测试约束 |
| `app/services` | 业务逻辑、权限校验、事务协调、状态机、Redis/Celery 调用 |
| `app/crud` | 数据访问，无业务判断 |
| `app/models` | ORM 模型（表、外键、约束、索引） |
| `app/schemas` | 请求/响应模型（响应模型永不暴露口令字段，有契约测试） |
| `app/core` | 配置、安全（JWT/口令）、异常、日志、中间件、真实客户端 IP 判定 |
| `app/db` | 引擎、Session、Redis 客户端 |
| `app/tasks` | Celery 应用与业务任务 |
| `migrations` | Alembic 迁移（20 个，可逆性在 CI 里验证） |
| `tests` | 72 个测试文件，见 [`docs/TESTING.md`](docs/TESTING.md) |
| `scripts` | 文档一致性检查（`check_docs.py`） |

---

## 目录结构

```text
task-flow/
├── app/
│   ├── main.py                  # 应用装配：中间件顺序、路由、异常处理、/health
│   ├── api/v1/                  # Router 层（11 个模块：auth/users/permissions/teams/projects/tasks/
│   │                            #   comments/attachments/notifications/logs/tenants）
│   ├── core/                    # config / security / exceptions / deps /
│   │                            #   logging_config / middleware / client_ip / redis_keys
│   ├── crud/                    # 13 个数据访问模块
│   ├── db/                      # base / session / redis
│   ├── models/                  # 17 个模型模块
│   ├── schemas/                 # 12 个请求响应模型模块
│   ├── services/                # 17 个业务服务（含 state_machine / authorization /
│   │                            #   rate_limit / storage / rbac）
│   └── tasks/                   # celery_app / notification_tasks / maintenance_tasks
├── migrations/
│   ├── env.py
│   └── versions/                # 20 个迁移（含 RBAC 种子数据、member 角色回填、租户化、RBAC 租户化与 RLS）
├── nginx/nginx.conf             # 生产反代配置（只读挂载进容器）
├── scripts/check_docs.py        # 文档一致性检查（退出码 0/1）
├── tests/                       # 72 个测试文件 + conftest.py
├── .github/workflows/ci.yml     # 三 job：ruff / pytest / docker build
├── Dockerfile                   # python:3.13-slim，非 root 运行
├── docker-compose.yml           # 开发栈（app + worker + postgres + redis）
├── docker-compose.prod.yml      # 生产栈（+ nginx，无对外 DB/Redis 端口）
├── alembic.ini / pyproject.toml # 迁移与工具配置（ruff、pytest、coverage 均在此）
├── requirements.txt             # 生产依赖
└── requirements-dev.txt         # 开发与 CI 依赖（-r requirements.txt）
```

---

## ER 图

17 张业务表、35 条外键。关系图（实体名对应 `app/models/*.py` 的 `__tablename__`；TASK-094 起 users/teams/tasks 等 15 张表经 `tenant_id` FK 归属租户，TASK-096 起 RBAC 三表同样带 `tenant_id`，图中按实体维度略去）：

```mermaid
erDiagram
    USERS ||--o{ REFRESH_TOKENS : "登录会话"
    USERS ||--o{ USER_ROLES : "租户内角色"
    ROLES ||--o{ USER_ROLES : ""
    ROLES ||--o{ ROLE_PERMISSIONS : "角色权限"
    PERMISSIONS ||--o{ ROLE_PERMISSIONS : ""
    USERS ||--o{ TEAMS : "owner_id RESTRICT"
    TEAMS ||--o{ TEAM_MEMBERS : "成员"
    USERS ||--o{ TEAM_MEMBERS : ""
    TEAMS ||--o{ PROJECTS : "团队下的项目"
    USERS ||--o{ PROJECTS : "owner_id RESTRICT"
    PROJECTS ||--o{ TASKS : "项目下的任务"
    USERS ||--o{ TASKS : "creator_id"
    TASKS ||--o{ TASK_ASSIGNEES : "多人分配"
    USERS ||--o{ TASK_ASSIGNEES : ""
    TASKS ||--o{ COMMENTS : "评论"
    USERS ||--o{ COMMENTS : ""
    TASKS ||--o{ ATTACHMENTS : "附件"
    USERS ||--o{ ATTACHMENTS : "uploader_id"
    USERS ||--o{ NOTIFICATIONS : "站内通知"
    TENANTS : "TASK-093 新增，暂无外键（TASK-094 落 tenant_id）"
```

删除策略不是一刀切，按「这条数据是不是主体的从属物」分别选：

| 外键 | ON DELETE | 理由 |
| --- | --- | --- |
| `teams.owner_id`、`projects.owner_id` | `RESTRICT` | 主体链上的归属人：删用户前必须先转移归属，否则团队/项目会失去负责人 |
| `user_roles.role_id`、`role_permissions.*`、`refresh_tokens.user_id` | `CASCADE` | 纯从属记录，随主体消失 |
| `tasks.project_id`、`task_assignees.task_id`、`comments.task_id`、`attachments.task_id` | `CASCADE` | 任务被删，其下挂载物一并清理 |
| `notifications.user_id`、`team_members.*` | `CASCADE` | 用户退场后无悬挂意义 |

两处**有意为之**的设计：

- `operation_logs.user_id` **没有外键**。审计日志的语义是「比被审计对象活得更久」——
  如果跟着用户级联删除，删账号就等于销毁审计痕迹（TASK-039 决策）。
- `task_assignees` 用 `(task_id, user_id)` 复合主键，不额外造 `id`：分配关系本身就是
  业务主键，加代理键只会多一个可以被误用的唯一标识。

库级约束（不只是应用层校验）：9 个唯一约束（TASK-094 起 `users.username`、`users.email`
的唯一性由 `(tenant_id, username)` / `(tenant_id, email)` 复合约束承担；`refresh_tokens.jti`、`roles.name`、`permissions.name`、`uq_team_members_team_user`、
`uq_user_roles_user_id_role_id`、`uq_role_permissions_role_id_permission_id`、
`uq_tenants_slug`）、7 个 CHECK（`ck_tasks_status_values`、`ck_tasks_priority_values`、
`ck_team_members_role_id`，以及 TASK-093 的 `ck_tenants_status`、`ck_tenants_slug_format`、
`ck_tenants_member_limit`、`ck_tenants_storage_limit`）。
**数据库负责数据完整性，Service 负责业务规则**——两者不互相替代。

---

## 核心业务流程

### 登录（双 Token 签发）

```text
POST /api/v1/auth/login
  → Router 解析 LoginRequest
  → AuthService.authenticate_user
      → 查 User（用户名或邮箱）
      → verify_password（Argon2id 校验；用户不存在与口令错误**同文案**，防用户名枚举）
  → AuthService.issue_token_pair
      → 签发 Access Token（30 分钟，无状态）
      → 签发 Refresh Token（7 天，带 jti）+ **把 jti 落库**（同一事务）
  → 返回 {access_token, refresh_token, token_type}
```

关键点：**签发与登记必须同生共死**（同一事务）。否则会出现「客户端拿到 Refresh
Token，但服务端查不到 jti」的中间态——用户下一次刷新就莫名 401。

### 创建任务

```text
POST /api/v1/tasks
  → JWT 认证（无状态解析 Access Token）→ CurrentUser
  → 功能级权限 task:create
  → TaskService.create_task
      → 校验项目存在且调用者在归属链上（否则统一 404 Project not found）
      → INSERT tasks（status 恒为 TODO，请求体不接受 status）
      → INSERT operation_logs（action=task:create，同一事务）
      → COMMIT
  → 事务提交后：投递 Celery 通知任务（失败不影响已提交的创建结果）
  → 返回 TaskRead（内嵌 assignees）
```

审计日志在事务内（与业务同生共死），通知在事务外异步派发（允许重试）。这个边界是刻意的：
把通知放进事务会让「通知服务抖动」变成「任务创建失败」。

### 状态流转

```text
POST /api/v1/tasks/{task_id}/transition   body: {"to_status": "IN_PROGRESS"}
  → JWT → 功能级权限 task:transition → 资源级归属链
  → TaskService.transition_task
      → 查 Task（不在归属链 → 404 Task not found 同文案）
      → state_machine.validate_transition(current, target)
          非法 → ConflictError(409) "Invalid status transition"，状态不变
      → UPDATE status + INSERT operation_logs（同一事务）→ COMMIT
  → 异步通知
```

### 附件上传（安全边界）

```text
POST /api/v1/tasks/{task_id}/attachments  (multipart)
  → 权限 + 归属链
  → 大小限制（MAX_UPLOAD_SIZE，默认 10 MiB，边读边计数，不信任 Content-Length）
  → sanitize_filename（去除路径成分、空名兜底、过长截断）
  → StorageBackend.build_key（服务端生成存储键，不使用客户端文件名做路径）
  → CRUD 落库 storage_path
下载时反向校验：validate_key（语义层，拒绝 `..`/绝对路径/URL 编码绕过）
             + LocalStorageBackend._resolve（结构层，解析后必须仍在根目录内）
```

两层守卫是纵深防御：语义层可能漏（编码变体），结构层兜底（真实路径必须落在根内）。
`tests/test_storage_guards.py` 共 42 项，含各类绕过尝试。

### 通知异步化

```text
FastAPI（业务事务已提交）
  → notification_tasks.dispatch_notification.delay(...)
      → Redis Broker → Celery Worker
          → 幂等键（idempotency_key）检查：已存在则直接返回，不重复落库
          → INSERT notifications
  重试：autoretry_for + retry_backoff + max_retries + jitter
  超时：soft_time_limit（可自行清理）/ time_limit（硬杀兜底）
```

---

## API 文档

- 交互式文档：启动后访问 **`/docs`**（Swagger UI）或 **`/redoc`**；机器可读的
  OpenAPI 在 **`/openapi.json`**。三者由 FastAPI 从路由与 Pydantic 模型自动生成，
  因此**不会与实现漂移**。
- 契约文档（人读的版本，含每端点的授权、错误码、字段约束）：
  [`docs/API_CONTRACT.md`](docs/API_CONTRACT.md)。

### 端点总览（43 个 `/api/v1` 操作）

| 分组 | 路径 | 说明 |
| --- | --- | --- |
| Auth | `POST /auth/register`、`POST /auth/login`、`POST /auth/refresh`、`POST /auth/logout` | 注册（自动绑 member 角色）/ 登录 / 刷新（轮换）/ 登出（撤销） |
| User | `GET /users/me` | 当前用户 |
| User（RBAC） | `GET /users`（支持 `q` 按用户名/邮箱搜索）、`GET /users/me/permissions`、`GET|PUT /users/{user_id}/roles` | 用户列表（搜索找人）/ 我的有效权限 / 角色管理（PUT 仅 admin） |
| Permissions | `GET /permissions` | 角色-权限矩阵（仅 admin） |
| Team | `GET|POST /teams`、`GET|PATCH|DELETE /teams/{team_id}` | 团队 CRUD |
| Team Members | `GET|POST /teams/{team_id}/members`、`DELETE /teams/{team_id}/members/{user_id}` | 成员管理 |
| Project | `GET|POST /projects`、`GET|PATCH|DELETE /projects/{project_id}` | 项目 CRUD |
| Task | `GET|POST /tasks`、`GET|PATCH|DELETE /tasks/{task_id}` | 任务 CRUD |
| Task 分配 | `POST /tasks/{task_id}/assignees`、`DELETE /tasks/{task_id}/assignees/{user_id}` | 多人分配 |
| Task 流转 | `POST /tasks/{task_id}/transition` | 状态机唯一入口 |
| Comment | `GET|POST /tasks/{task_id}/comments`、`DELETE /comments/{comment_id}` | 评论 |
| Attachment | `GET|POST /tasks/{task_id}/attachments`、`GET|DELETE /attachments/{attachment_id}` | 附件 |
| Notification | `GET /notifications`、`PATCH /notifications/{id}/read`、`PATCH /notifications/read-all` | 站内通知 |
| Logs | `GET /logs`、`GET /logs/{resource_type}/{resource_id}` | 操作审计 |
| Health | `GET /health`（兼容端点）、`GET /health/live`、`GET /health/ready`、`GET /health/db`、`GET /health/redis`（另有 `GET /` 返回应用名/版本/环境） | 探针 |

### 统一响应与错误

```jsonc
// 成功
{"data": { /* 资源对象或列表 */ }, "message": "success"}

// 错误（唯一信封）
{"detail": "Task not found"}
```

| 状态码 | 含义 | 例子 |
| --- | --- | --- |
| 400 | 请求内容不合法（格式合法但语义不成立） | `Invalid upload` |
| 401 | 未认证 / Token 不可用 | 签名错误、过期、jti 不存在、已被撤销 |
| 403 | 已认证但**无功能级权限** | `Permission denied: task:delete` |
| 404 | 资源不存在**或不在你的归属链上**（统一文案，防枚举） | `Task not found` |
| 409 | 状态冲突 | 非法状态流转、重复分配、用户名已注册 |
| 413 / 415 | 上传超限 / 类型不支持 | |
| 422 | 请求体/查询参数校验失败（Pydantic） | 枚举值非法 |
| 429 | 触发限流（带 `Retry-After` 与 `X-RateLimit-*`） | |

`AppError` 及其子类由 `app/main.py` 注册的**唯一**异常处理器渲染成上述信封
（契约测试断言「只有一个 handler」「每个子类都映射到 4xx」，防止有人绕过信封）。

### 列表查询约定

- 分页：`?skip=0&limit=100`（`skip ≥ 0`，`limit` 上限 100，所有分页端点一致——
  契约测试逐端点断言）。
- 过滤：任务支持 `project_id`（必填）、`status`、`priority`、`assignee_id`。
- 搜索：`keyword` 走标题大小写不敏感子串匹配（`%`/`_`/`\` 转义后按字面处理），
  由 `pg_trgm` 的 GIN 索引加速（见「性能优化」）。
- 排序：`?sort=id|created_at|due_at|priority&order=asc|desc`（白名单，防注入式排序）。
  `priority` 按**业务权重** `URGENT > HIGH > MEDIUM > LOW` 排序，而非字母序。

---

## 环境配置

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements-dev.txt   # Windows（POSIX: .venv/bin/pip）
cp .env.example .env                                # Windows: copy .env.example .env
```

`.env` 只用于本机、**不入库**（`.gitignore`）；仓库里的模板是 `.env.example`。

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `APP_ENV` / `DEBUG` | `development` / `false` | 生产必须 `false`（生产 compose 显式注入） |
| `DATABASE_URL` | `postgresql+asyncpg://…@postgres:5432/taskflow` | **容器内**服务名；宿主机直连用 `127.0.0.1:5433` |
| `REDIS_URL` | `redis://redis:6379/0` | 宿主机直连用 `127.0.0.1:6389` |
| `JWT_SECRET_KEY` | `change-me` | **生产必填且不得用默认值**（compose 用 `$VAR:?` 语法，缺失即拒绝启动） |
| `ACCESS_TOKEN_EXPIRE_MINUTES` / `REFRESH_TOKEN_EXPIRE_DAYS` | `30` / `7` | 双 Token 寿命 |
| `RATE_LIMIT_ENABLED` / `RATE_LIMIT_REQUESTS` / `RATE_LIMIT_WINDOW_SECONDS` | `true` / `60` / `60` | 滑动窗口限流 |
| `UPLOAD_DIR` / `MAX_UPLOAD_SIZE` | `storage` / `10485760` | 附件根目录与上限（10 MiB） |
| `CELERY_*` | 见 `.env.example` | Broker/Backend 留空则回落 `REDIS_URL`；软/硬超时 300/600 秒 |
| `LOG_LEVEL` / `LOG_FORMAT` / `LOG_REQUESTS` | `INFO` / `auto` / `true` | `auto`：生产 JSON、其余 text |
| `TRUST_PROXY_HEADERS` / `TRUSTED_PROXY_IPS` | 未设 | 是否采信 `X-Forwarded-For`（**两条同时成立才采信**） |
| `WEB_CONCURRENCY` / `NGINX_HTTP_PORT` | `2` / `80` | 仅生产 compose 使用 |

两个容易踩的坑（都写在 `.env.example` 注释里）：

1. **端口映射是 5433 / 6389，不是默认端口**。本机 5432 被另一个 PostgreSQL 占用，
   开发栈才映射到 5433；Redis 同理用 6389。
2. **宿主机连容器要用 `127.0.0.1`，不要用 `localhost`**。Windows 上 `localhost`
   优先解析到 IPv6 `::1`，而 Docker 只发布 IPv4，连接会挂到超时。

生成生产密钥：

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

配置本身也有安全契约测试：`tests/test_quality_checks.py` 断言**声明层默认值里不含
真实密钥**（防止有人把真密钥写进 `config.py` 默认值）。

---

## Docker 启动

### 开发栈（`docker-compose.yml`）

```bash
# 1) 构建并启动 app + celery_worker + postgres + redis
docker compose -f docker-compose.yml --env-file .env up -d --build

# 2) 首次必须手动执行迁移（容器不会自动迁移）
docker compose -f docker-compose.yml exec app alembic upgrade head

# 3) 冒烟
curl -s http://127.0.0.1:8000/health
# {"status":"ok","app":"TaskFlow Pro","version":"0.1.0","env":"development",
#  "database":"up","redis":"up"}
```

开发栈对外发布：API `8000`、PostgreSQL `5433`、Redis `6389`；数据落在三个命名卷
（`postgres_data` / `redis_data` / `attachment_storage`）。

`/health` 的语义要说清楚：**只要进程活着就返回 200**，依赖状态放在 body 里。
这样编排系统能区分「入口进程挂了」和「后端依赖抖了」，而不会因为数据库短暂不可用
就把正在重启的容器判定为死。

### 生产栈（`docker-compose.prod.yml`）

```bash
# 1) 首次部署：执行迁移
docker compose -f docker-compose.prod.yml --env-file .env run --rm app alembic upgrade head

# 2) 启动（app 用 Gunicorn + UvicornWorker；celery_worker 独立进程；nginx 唯一入口）
docker compose -f docker-compose.prod.yml --env-file .env up -d --build

# 3) 换对外端口（默认 80）
NGINX_HTTP_PORT=8080 docker compose -f docker-compose.prod.yml --env-file .env up -d
```

生产栈与开发栈的差异是刻意设计的：

- **只有 Nginx 对宿主发布端口**，PostgreSQL / Redis / app 都不发布——数据库不该
  出现在宿主机网络上；
- `JWT_SECRET_KEY` / `POSTGRES_PASSWORD` 用 `$VAR:?` **必填语法**，缺失或沿用开发
  默认值直接拒绝启动（fail-fast，而不是带着弱密钥跑起来）；
- 应用以 `appuser` 非 root 用户运行，附件目录 `/app/storage` 在构建时创建并授权。

细节（含 TLS、真实客户端 IP、健康检查）见 [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md)。

---

## 数据库迁移

Alembic 是 schema 的唯一入口（模型是事实来源，迁移是它的版本化产物）。

```bash
# 应用最新迁移（宿主机跑必须显式指定端口，因为 .env 里是容器内服务名）
DATABASE_URL="postgresql+asyncpg://postgres:postgres@127.0.0.1:5433/taskflow" \
  alembic upgrade head

alembic current        # 当前版本
alembic heads          # 迁移头
alembic history        # 历史

# 改模型后自动生成迁移（生成后必须人读一遍，autogenerate 不会替你判断删除是否安全）
alembic revision --autogenerate -m "add xxx"

# 回滚一步
alembic downgrade -1
```

20 个迁移按依赖顺序：users → refresh_tokens → RBAC 四表 → RBAC 种子数据 →
teams/team_members → projects → tasks → task_assignees → comments → attachments →
operation_logs → operation_logs_archive → notifications → 任务搜索索引 →
无角色用户补绑 member 角色（数据回填，downgrade 为显式 no-op）→
tenants + tenant:manage 权限种子（TASK-093）→
15 张表加 tenant_id 列 + FK + 索引（TASK-094；TASK-096 起含 RBAC 三表）→
默认租户回填 + users 唯一约束租户化 + 置 NOT NULL + 写入桥接默认值（TASK-094）→
RLS 策略 + app 函数 + 运行时角色 taskflow_app（TASK-095）→
RBAC 三表加 tenant_id 列 + FK + 索引 + 角色租户化 + 租户内种子播种（TASK-096）。

**可逆性是被 CI 验证的**：CI 在空库上跑 `upgrade head → downgrade base → upgrade head`，
三步共用一个 shell 且 `set -euo pipefail`——任一步失败立即中断，从而排除「downgrade
悄悄失败、后面的 upgrade 变成 no-op、最后 pytest 在旧库上通过」这种假绿。

一处有意的边界：任务搜索索引迁移里 `downgrade` **不 `DROP EXTENSION pg_trgm`**。
扩展是数据库级对象，表级回滚不该拆除它；且若其它表将来也用 trigram，拆除会误伤。

---

## 测试

```bash
# 全量（与 CI 的 pytest job 同一条命令）
pytest

# 本地覆盖率（CI 不跑这条：覆盖率不进 CI 门禁，见下）
pytest --cov --cov-report=term-missing

# lint（规则集与 ruff 版本都钉在仓库里，因此结果只取决于提交内容）
ruff check .
```

**当前基线（快照 2026-09-17，TASK-129 重测）**：1230 passed，0 failed / 0 error / 0 skipped；
覆盖率 3065 语句 / 8 未覆盖 / 472 分支 → 99.74% 行、98.94% 分支。
可核查的分层明细、双口径披露与刻意排除项见
[`docs/QUALITY.md`](docs/QUALITY.md)（那里的数字是权威版本）。

测试结构（策略与理由见 [`docs/TESTING.md`](docs/TESTING.md)）：

| 类型 | 做法 |
| --- | --- |
| HTTP 端到端 | httpx `ASGITransport` 直打真实 app + 真实 PostgreSQL/Redis（不 mock 数据库） |
| 夹具自洽 | 每个测试文件自建 `RUN_TOKEN` 前缀数据，autouse teardown 精确删除本次运行的数据，**开发库零残留** |
| 离线契约 | 用 AST 解析源码 + 读 OpenAPI schema：分层规则、响应模型不含口令字段、分页上限、异常映射、配置默认值无密钥 |
| 运行时护栏 | 挂 SQLAlchemy `before_cursor_execute` 事件数 SELECT 条数，断言「列表查询的 SQL 条数不随行数增长」（N+1 的真探针） |
| 文档护栏 | `tests/test_docs_consistency.py` + `tests/test_readme.py`：文档之间不许互相矛盾 |
| 反向用例 | 护栏类测试必须用**合成输入**证明自己会失败——「永远返回空列表的检查器」也能让正向断言通过 |

两条工程判断：

- **覆盖率不进 CI 门禁**。覆盖率是一个诊断指标，不是质量目标；把它设成阈值会诱导
  「为了抬数字而写无意义断言」。它只在本地测量并写入 `docs/QUALITY.md`（TASK-062 决策）。
- **测试连真实依赖**。限流、jti 撤销、`pg_trgm` 执行计划这些东西，mock 掉等于什么都
  没验证——本项目的限流测试真的读写 Redis，搜索索引测试真的 `EXPLAIN` 真实查询计划。

---

## CI

[`.github/workflows/ci.yml`](.github/workflows/ci.yml)，推送到 `master` 与 Pull Request
触发，三 job 并行：

| job | 内容 |
| --- | --- |
| `lint` | Python 3.13 + `pip install -r requirements-dev.txt` + `ruff check .` |
| `test` | Python 3.13 + `postgres:16` / `redis:7` service → **迁移可逆性三步** → `pytest` |
| `docker-build` | `docker build --tag taskflow-app:ci .`（只验证可构建，不推送镜像） |

几个不显然的设计：

- **service 端口对齐测试里的硬编码**：测试文件把 `127.0.0.1:5433`（DB）与
  `127.0.0.1:6389`（Redis）写成常量，于是 CI 的 service 映射到同样的端口。
  让 CI 去适配测试而不是反过来改几十个测试文件——后者会削弱「CI 跑的就是本地跑的
  那套断言」这个性质。
- **显式注入 `DATABASE_URL` / `REDIS_URL` / `JWT_SECRET_KEY`**：默认值是容器内服务名，
  而 CI 里既没有 `.env` 也没有 Docker 网络，不设就会去连不存在的主机名（报错信息和
  真实原因隔得很远）。
- **权限最小化**：`permissions: contents: read`，且不推送镜像——把 `packages:write`
  扩到一个纯验证步骤上没有收益。
- **同分支新 run 取消旧 run**（`concurrency`），推送一串提交时不必排队。

本地复现 CI：`ruff check . && alembic upgrade head && pytest`。

---

## 性能优化

| 优化 | 做法 | 证据 |
| --- | --- | --- |
| 消除 N+1 | 关联读取一律显式批量 `IN` 查询（如 `list_assignees_for_tasks` 一次 `WHERE task_id IN (...)` 后分组），**全项目零 `relationship()`** | `tests/test_query_efficiency.py` 数真实 SELECT：3 行与 12 行的列表请求 SQL 条数**相同**；分配人恒为 1 条带 `IN (` 的查询 |
| 搜索索引 | `pg_trgm` 扩展 + `ix_tasks_title_trgm`（`GIN (title gin_trgm_ops)`）＋ `tasks.search_vector` 生成列 + GIN 索引 | `EXPLAIN` 实证：`ILIKE '%login%'` 与 `ILIKE '%登录缺陷%'` 都从**顺序扫描**变为 `Bitmap Index Scan on ix_tasks_title_trgm` |
| 部分索引 | `ix_tasks_due_at_open` 只索引未完成/未取消任务（`WHERE status IN ('TODO','IN_PROGRESS','REVIEW')`） | 索引体积与已完结任务量脱钩 |
| 分页 | 所有列表端点统一 `skip`/`limit`，`limit ≤ 100` 硬上限 | 契约测试逐端点断言上限与 `skip ≥ 0` |
| 限流零额外往返 | 限流关闭时**完全不做 Redis 调用**（不是「调用了但忽略结果」） | `tests/test_quality_gaps.py` 用「一调用就炸」的哨兵函数钉死 |
| 限流单次往返 | 清理 + 计数 + 判定 + 写入 + 续期在**一个 Lua 脚本**内完成 | 见下节 |
| 连接复用 | Redis 共享客户端（`/health` 探测也复用，不再每次新建连接池）；Nginx `upstream keepalive` | |
| 异步 IO | 全链路 async（asyncpg），耗时任务（通知、归档、清理）移出请求路径 | |

**为什么 `keyword` 搜索不用 `search_vector`**（一个刻意不做的优化）：`to_tsvector('simple')`
**不做中文分词**——实测 `'修复登录缺陷'` 会被当成**一个** token，于是
`to_tsquery('simple','登录')` 命中 0 条，而 `ILIKE '%登录%'` 命中 1 条。本项目内容是中文，
切到全文检索会让子串搜索**静默失效**（不报错，只是搜不到）。因此 `keyword` 保持 `ILIKE`
语义，由与语言无关的 trigram 索引加速；`search_vector` 列与 GIN 索引按文档落库备用。
这个边界写成了双向断言，将来有人顺手改坏会立刻变红。

---

## Redis 限流原理

滑动窗口限流：`ZSET` 的 `score` 是请求毫秒时间戳，`member` 是本次请求的唯一标识，
统计窗口内请求数 = 数 `score > now - window` 的成员。key 形如
`taskflow:ratelimit:{ip|user}:{标识}`。

**为什么不是固定窗口**（`INCR` + `EXPIRE`）：限 60 次/分钟时，客户端可以在第 59 秒
发 60 次、第 61 秒再发 60 次——两秒内 120 次全部放行。滑动窗口用「每个请求的时间戳」
判断「过去 N 秒有多少请求」，没有这个边界突刺。

**为什么必须用 Lua**：判定需要五步（删窗口外 → 计数 → 判超限 → 写入 → 续期）。拆成
多条命令时两个并发请求会交错：都读到「窗口内 59 次」→ 都认为没超限 → 都写入，限流被
击穿。Lua 在 Redis 中单线程原子执行，判断与写入之间不存在竞态窗口。

**时间取 Redis 服务器时间**（脚本内 `redis.call('TIME')`），不取客户端时间：多实例
部署时各客户端时钟可能不一致，用客户端时间会让同一用户在不同实例落到不同窗口位置，
限流形同虚设。

**被拒时不写入本次请求**，并根据 ZSET 中最早成员离开窗口的时刻算出 `Retry-After`：
客户端拿到的等待时间是有依据的，不是固定值。响应头返回 `X-RateLimit-Limit` /
`X-RateLimit-Remaining`（仅在限额已知时）。

**维度选择与反代配合**：已认证请求按 `user` 维度，匿名按 `IP` 维度。反代之后若直接
信任 `X-Forwarded-For`，攻击者伪造该头就能给自己换一份新配额——所以链路是两层：
Nginx 用 `$remote_addr` **覆盖式**写入（而不是 `$proxy_add_x_forwarded_for` 那种拼接），
应用侧再要求 `TRUST_PROXY_HEADERS=true` **且** 请求的 TCP 对端落在
`TRUSTED_PROXY_IPS` 网段内。缺任何一条都**回落到对端地址**（fail-safe）——代价是
「按 IP 限流」退化成匿名用户共享一份配额，但不会变成「随便伪造就换新配额」。

实现：`app/services/rate_limit.py`（纯判定，可离线单测）+ `app/core/redis_keys.py`
（key 与 TTL 集中定义）+ `app/core/middleware.py`（中间件在所有路由之前生效，
新增端点自动受保护，不会因为忘记声明依赖而留下裸奔入口）。

---

## Celery 原理

```text
FastAPI ──delay()──▶ Redis Broker ──▶ Celery Worker ──▶ 执行任务
                        ▲                    │
                        └──── 结果后端 ◀──────┘（结果仅作调试，过期自动回收）
```

三个业务任务：通知派发（`notification_tasks`）、日志归档、附件清理
（`maintenance_tasks`）。Worker 与 API 是**同一镜像、不同命令**的两个进程。

关键配置及其理由：

| 配置 | 作用 | 为什么这么选 |
| --- | --- | --- |
| `accept_content=["json"]` + JSON 序列化 | 禁 pickle | Celery 默认接受 pickle，**反序列化即执行任意代码**；任务消息一旦被拿到就是 RCE |
| `task_acks_late=True` | 执行完成才 ack | Worker 崩溃时消息不丢 |
| `task_reject_on_worker_lost=True` | Worker 被强杀时消息重新入队 | 否则 SIGKILL/OOM 会让任务凭空消失 |
| `worker_prefetch_multiplier=1` | 每 Worker 一次只预取 1 条 | 长任务不会囤积在单进程上饿死其他消息 |
| `task_soft_time_limit` / `task_time_limit` | 软超时抛异常可自行清理，硬超时杀进程 | 超时双保险 |
| `global_keyprefix="taskflow:"` | Celery 在 Redis 里的键统一加前缀 | `taskflow:*` 之外都不是本项目的键，运维排查与清理都干净 |

前四条合起来意味着投递语义是 **at-least-once**：任务**可能被重复执行**。所以幂等性
不能靠「任务只执行一次」的假设，必须落在每个任务自己身上——通知派发用幂等键
（`idempotency_key`）判定「已存在则直接返回」，归档与清理做成可重复执行而不产生副作用。

重试策略：`autoretry_for` + `retry_backoff`（指数退避）+ `max_retries` + jitter
（抖动，避免一批任务同时重试造成二次雪崩）。

`import` 不连接：`app/tasks/celery_app.py` 导入时只读配置构造对象，不发网络连接
（Celery 连接是惰性的），因此 API 进程导入它零成本，测试可在无 Redis 环境下安全导入。

---

## JWT 原理

双 Token 的核心动机：**Access Token 必须无状态**（否则每个请求都要查库/查 Redis），
但无状态令牌的天然弱点是无法撤销。于是把它拆成两个：

| | Access Token | Refresh Token |
| --- | --- | --- |
| 寿命 | 30 分钟 | 7 天 |
| 携带信息 | `sub`（用户 id）、`exp`、`type`、`jti` | 同左 |
| 服务端状态 | **无**（纯签名校验） | **jti 落库**（`refresh_tokens` 表） |
| 用途 | 每次请求携带 | 只用于换取新 Token 对 |

于是：泄露的 Access Token 最多只能用 30 分钟（窗口有限），而**长期凭据是可撤销的**——
撤销能力放在数据库里（`refresh_tokens.revoked`），不放在热路径上。

- **刷新 = 轮换**：`POST /auth/refresh` 校验签名、过期、`type` 之后，还要
  **查库确认 jti 存在且未被撤销**，然后把旧 jti 立即置 `revoked=true`，同时签发并登记
  新的一对。若旧 Refresh Token 再次出现（说明可能已被窃取），因为它已被撤销，
  请求会被拒绝。
- **登出 = 撤销**：`POST /auth/logout` 把调用者自己的 Refresh Token jti 置撤销，
  且**幂等**——Token 本来就不可用（签名错/过期/未登记/已撤销）时也返回成功，
  不泄露「这个 Token 是否存在过」。
- **Access Token 的黑名单**：key 约定已定义（`taskflow:jwt:blacklist:<jti>`，TTL 必须
  不小于 Access Token 剩余寿命），但**校验链路未接入**——在没有需求驱动的阶段改动认证
  热路径不划算（项目规则 §7：不为使用 Redis 而使用 Redis）。这条边界在
  `app/core/redis_keys.py` 里写明，不假装已实现。
- **口令**：Argon2id（`pwdlib` 的推荐参数），只存散列；登录时「用户不存在」与「口令
  错误」返回**同一文案**，避免用户名枚举。
- **签名密钥**：生产环境用 `$VAR:?` 强制提供，缺失即拒绝启动；弱密钥（< 32 字节）会
  触发 PyJWT 的 `InsecureKeyLengthWarning`（RFC 7518 §3.2），本项目已用 64 字符随机密钥。

---

## 状态机设计

状态集合：`TODO / IN_PROGRESS / REVIEW / DONE / CANCELLED`。

```text
TODO ──────────▶ IN_PROGRESS ──────────▶ REVIEW ──────────▶ DONE  (终态)
  │                   │                     │
  └───────────────────┴─────────────────────┴──────────▶ CANCELLED  (终态)
```

| 规则 | 决策 |
| --- | --- |
| 前进链严格线性 | `TODO → IN_PROGRESS → REVIEW → DONE`，**不允许相邻回退**（`IN_PROGRESS → TODO`、`REVIEW → IN_PROGRESS` 非法） |
| 跨级跳转 | 非法（`TODO → DONE` 被拒） |
| 取消 | 任意**非终态** → `CANCELLED` |
| 终态 | `DONE` / `CANCELLED` **完全封死**，无任何出边（含 `DONE → CANCELLED`） |
| 同状态重复流转 | 视为非法（流转必须真实改变状态） |
| 非法流转的响应 | `409 Conflict` + `Invalid status transition`，且**状态不变** |

两条设计选择值得强调：

1. **状态只能通过 `POST /tasks/{id}/transition` 变更**。`POST /tasks` 的请求体里没有
   `status` 字段，`PATCH /tasks/{id}` 同样没有——新任务一律 `TODO` 起步。这不是靠
   「记得别传 status」的自觉，而是从 **API 形状**上让绕过状态机变得不可能。
2. **规则层与 HTTP 层分离**。`app/services/state_machine.py` 只有纯函数
   （`TRANSITIONS` / `can_transition` / `validate_transition` / `allowed_targets`），
   不依赖数据库与 Session，可离线单测；它抛领域异常 `ConflictError`，由全局处理器
   统一渲染成 409。`allowed_targets()` 还能直接服务于前端渲染「当前状态该显示哪些
   按钮」或看板拖拽白名单。

每次成功流转都在**同一事务**内写一条操作审计日志，因此「状态怎么变成现在这样的」
可以从事后追溯（`GET /logs/{resource_type}/{resource_id}`）。

---

## 项目难点

下表是开发过程中真正卡住过、或者想错了会留下隐患的点（详细决策见
[`docs/DECISIONS.md`](docs/DECISIONS.md)）。

| # | 难点 | 本质 | 处置 |
| --- | --- | --- | --- |
| 1 | 并发注册返回 500 而不是 409 | `IntegrityError` 兜底只包住了 `commit()`，而唯一冲突实际由内部 `flush()` 抛出，兜底分支**不可达** | 把 `create_user` + `commit()` 一起纳入 try；写测试撞出来并修复 |
| 2 | 明文口令写进 JSON 日志 | 脱敏过滤器只处理字符串消息，`logger.info({"password": …})` 走 `getMessage()` 的 `str(msg)` 路径，把字典 repr 原样写入 | 过滤器覆盖非字符串消息；键名匹配兼容 Python repr 与 JSON 两种写法 |
| 3 | N+1 的「防不住」 | 用 `relationship()` + eager load 时，漏写 `.options(...)` 会**静默**退化成 N+1，无任何报错 | 全项目零 `relationship()`，关联读取写显式批量 `IN` 查询；再用运行时 SQL 计数测试钉死 |
| 4 | 反代之后按 IP 限流失效 | `X-Forwarded-For` 是客户端可控输入，直接采信等于把限流配额交给攻击者 | 两层校验：Nginx 覆盖式写入 + 应用侧「开关 + 对端网段」双条件，任一不满足即 fail-safe 回落 |
| 5 | 限流被并发击穿 | 判定与写入之间若有多条 Redis 命令，并发请求会交错读到同一个旧计数 | 单 Lua 脚本内完成全部步骤，原子执行；时间取 Redis 服务器时间 |
| 6 | 私有附件与 Nginx 静态直出冲突 | `alias`/`root` 直出会**完全绕过鉴权**，知道路径即可下载任意附件（教科书式 IDOR） | 反代只做转发，附件仍走 API 鉴权后返回；理由与替代方案（`X-Accel-Redirect`）记入 DECISIONS 040 |
| 7 | 中文全文检索「看起来能用其实搜不到」 | `to_tsvector('simple')` 不做中文分词，整句成为一个 token | `keyword` 保持 `ILIKE` 子串语义 + `pg_trgm` 索引加速；边界写成双向断言 |
| 8 | 审计日志被级联删除 | `operation_logs.user_id` 若加外键，删用户会销毁审计痕迹 | 该列**有意不加外键**；同时测试 teardown 必须自己清理它（否则残留） |
| 9 | 进度文档反复「报成功但没落盘」 | 编辑动作报告成功、内容却没写入；不报错、不影响测试，唯一表现是文档说谎（已 4 次） | 把核验变成 CI 断言：`scripts/check_docs.py` + 反向用例测试 |
| 10 | CI 与本地端口不一致 | 40+ 个测试文件把 `5433`/`6389` 写成常量 | 让 CI 的 service 去适配测试端口，而不是改测试（否则「CI 跑的就是本地那套断言」这个性质被削弱） |

---

## 解决方案

逐条对应上表，给出落点与验证方式（「怎么证明它真的成立」）。

**1. 并发注册的 409 兜底**
`app/services/auth.py::register_user`：把内部 `create_user`（内含 `flush()`）与
`commit()` **一起**放进 `try/except IntegrityError`，冲突时 `rollback()` 后抛
`ConflictError`（409）。验证：并发场景由真实数据库唯一约束触发，测试断言返回 409 而非 500。

**2. 日志脱敏覆盖非字符串消息**
`app/core/logging_config.py`：`SensitiveDataFilter` 对所有非字符串 `msg` 也执行
`redact_text(str(msg))`；键名正则允许键两侧可选引号，因此 `'password': 'x'`（repr）
与 `"password": "x"`（JSON）都能命中。验证：
`tests/test_logging.py::test_non_string_message_is_still_redacted` 对 dict / list 两种
消息形态断言日志里**不存在明文**。

**3. N+1 的可验证消除**
`app/crud/task_assignee.py::list_assignees_for_tasks` 用一次
`WHERE task_id IN (...)` 取回后按 task 分组组装。验证：
`tests/test_query_efficiency.py` 挂 `before_cursor_execute` 事件数 SELECT——
3 行与 12 行的列表请求 SQL 条数相同（不随行数增长），分配人查询恒为 1 条且含 `IN (`。

**4. 真实客户端 IP 的信任边界**
`nginx/nginx.conf` 用 `$remote_addr` **覆盖**写入 `X-Forwarded-For`（不用
`$proxy_add_x_forwarded_for` 的拼接语义）；`app/core/client_ip.py` 仅在
`TRUST_PROXY_HEADERS=true` **且**对端落在 `TRUSTED_PROXY_IPS` 内时采信，否则回落
对端地址。验证：`tests/test_client_ip.py`、`tests/test_rate_limit.py` 覆盖开关组合、
网段判定、不可解析对端（fail-safe）与畸形头。

**5. 限流的原子性与服务器时间**
`app/services/rate_limit.py` 的 Lua 脚本五步原子执行；`redis.call('TIME')` 取服务器
时间；被拒时不写入并按最早成员离开窗口的时刻计算 `Retry-After`。验证：
`tests/test_rate_limit.py`（纯逻辑与边界）、`tests/test_rate_limit_integration.py`
（真实 Redis 上的并发与窗口滑动）。

**6. 附件不作为静态资源直出**
`nginx/nginx.conf` 只做反代，附件链路始终是 `Client → Nginx → API → 文件流`，
下载端点在鉴权后才读文件。若将来要做大文件吞吐优化，正确方向是 `X-Accel-Redirect`
指向 `internal` location（鉴权仍在应用层），而不是放开目录直出。验证：
`tests/test_nginx_config.py` 断言配置中**不存在**把存储目录直出的 location。

**7. 中文搜索的语义边界**
迁移 `6765bdcfa73e_*` 建 `pg_trgm` 扩展与 `ix_tasks_title_trgm`，另加
`search_vector` 生成列与 GIN 索引；`keyword` 查询语义不变（仍是标题 `ILIKE`）。
验证：`tests/test_task_search_indexes.py` 用**真实 `EXPLAIN`** 断言两个查询分别命中
`ix_tasks_title_trgm` 与 `ix_tasks_search_vector`，并双向断言中文子串（`%登录%`）能命中、
`to_tsquery('simple','登录')` 命中 0 条（把「为什么不用全文检索」固化成测试）。

**8. 审计日志的独立生命周期**
`operation_logs` 表不加 `user_id` 外键（迁移里显式说明）；同时因为「不被级联删除」，
测试 teardown 必须显式清理它——这一点在本项目里真实踩过：全量测试曾在开发库留下
507 行孤儿审计日志，最终定位到 3 个文件的 teardown 漏洞并补齐。验证：
全量测试后逐表核对：除 RBAC 种子字典表外，其余各表均为 0 行。

**9. 文档不许互相矛盾**
`scripts/check_docs.py` 校验 `PROGRESS.md` ↔ `TASKS.md` 的六条不变量（含「`Completed`
末行 == `Current Task`」——历史事故的直接探针），另校验 README/DEPLOYMENT 的端点
声明 ↔ `app.openapi()`/nginx（TASK-092，A1 类漂移的护栏）与 README 健康探针族声明
完整性；`tests/test_readme.py` 校验 README 与规格/进度的一致性；两层各有**反向用例**
证明自己会失败（否则「永远报通过的检查器」也能让正向断言通过）。验证：`python scripts/check_docs.py` 退出码 0，且 CI 的 pytest
自动执行同一套断言。

**10. CI 与本地行为一致**
`ci.yml` 的 service 端口映射为 `5433:5432` / `6389:6379`，与测试中的硬编码常量一致；
显式注入 `DATABASE_URL` / `REDIS_URL` / `JWT_SECRET_KEY`；迁移可逆性三步用
`set -euo pipefail` 串在一个 shell 里。验证：`.github/workflows/ci.yml` 本身有契约测试
（`tests/test_ci_workflow.py`，35 项）断言这些性质，改坏 CI 配置会让测试变红。

---

## 面试技术难点

[`docs/INTERVIEW.md`](docs/INTERVIEW.md) 按开发文档 §56 的九个领域、35 个问题逐条作答，
每条答案都指向本项目的真实代码、决策编号或测试名（不是通用八股）：

| 领域 | 问题数 | 例子 |
| --- | --- | --- |
| FastAPI | 4 | 为什么适合这个项目 / `Depends` 做什么 / async 如何工作 / Pydantic 的角色 |
| SQLAlchemy | 4 | 2.0 有什么变化 / Session 生命周期 / ORM 与 SQL 的关系 / 如何解决 N+1 |
| PostgreSQL | 5 | 为什么选 PG / GIN 是什么 / JSONB 优势 / `pg_trgm` 用途 / 索引何时有害 |
| Redis | 4 | 为什么适合限流 / ZSET 为什么适合滑动窗口 / Lua 为什么必要 / 原子性如何保证 |
| JWT | 3 | 双 Token 为什么分开 / 为什么需要 JTI / Logout 如何让 JWT 失效 |
| RBAC | 3 | 怎么设计 / 认证与授权的区别 / 如何防越权 |
| Celery | 4 | 为什么需要 / 与 `BackgroundTasks` 的区别 / 失败怎么办 / 如何保证幂等 |
| 数据库 | 3 | 为什么需要事务 / 什么情况产生脏数据 / 如何处理并发更新 |
| 工程化 | 5 | Docker / Nginx 的角色 / Gunicorn 与 Uvicorn 的关系 / CI 做什么 / 如何设计 CI |

---

## 文档

| 文档 | 内容 |
| --- | --- |
| [`docs/PROJECT_SPEC.md`](docs/PROJECT_SPEC.md) | 项目定位、需求、业务规则、非功能要求 |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | 分层、模块职责、依赖规则、事务边界、性能原则 |
| [`docs/API_CONTRACT.md`](docs/API_CONTRACT.md) | 逐端点契约（授权、字段、错误码、决策编号） |
| [`docs/DB_SCHEMA.md`](docs/DB_SCHEMA.md) | 表结构、约束、索引、PostgreSQL 能力清单 |
| [`docs/TASKS.md`](docs/TASKS.md) | 全部任务与所属 Phase（事实来源） |
| [`docs/PROGRESS.md`](docs/PROGRESS.md) | 实时进度（与 `TASKS.md` 的一致性由 CI 保证） |
| [`docs/DECISIONS.md`](docs/DECISIONS.md) | 逐条决策记录：选了什么、为什么、放弃了什么 |
| [`docs/QUALITY.md`](docs/QUALITY.md) | 质量基线与验收对照：覆盖率、§57 清单、发现的缺陷、已知偏差 |
| [`docs/TESTING.md`](docs/TESTING.md) | 测试策略、夹具约定、覆盖率基线 |
| [`docs/SECURITY.md`](docs/SECURITY.md) | 安全清单与认证授权边界 |
| [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) | 开发/生产部署、反代、TLS、健康检查、CI 复现 |
| [`docs/INTERVIEW.md`](docs/INTERVIEW.md) | 面试技术难点（§56 的 35 问答） |
| [`docs/CONVENTIONS.md`](docs/CONVENTIONS.md) | 代码约定 |
| [`docs/CHANGELOG.md`](docs/CHANGELOG.md) | 变更记录 |
| [`docs/FRONTEND_PROJECT_SPEC.md`](docs/FRONTEND_PROJECT_SPEC.md) | 前端规格（阶段 1~3 + Dashboard 已实现，见 [`frontend/README.md`](frontend/README.md)） |
| [`docs/FRONTEND_API_MAPPING.md`](docs/FRONTEND_API_MAPPING.md) | 前端 ↔ 后端接口映射与契约差异（规格 §57 要求的「确认真实 API」记录） |
| [`团队任务协作系统_项目开发文档.md`](团队任务协作系统_项目开发文档.md) | 原始开发文档（规格事实来源） |

---

## 本地检查清单

提交前跑这三条，与 CI 等价：

```bash
python scripts/check_docs.py    # 文档之间不许互相矛盾（退出码 0/1）
ruff check .                    # lint
pytest                          # 全量测试
```
