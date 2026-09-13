# TaskFlow Pro 当前进度

## Project Status
In Progress

## Current Phase
Phase 4：团队与项目

## Current Task
TASK-025 RBAC 测试（已完成）

## Completed
- [x] TASK-001 初始化 Git 与 Python 项目骨架
- [x] TASK-002 配置基础依赖与环境变量
- [x] TASK-003 创建 FastAPI 应用与基础配置
- [x] TASK-004 配置 PostgreSQL Docker 服务
- [x] TASK-005 配置 Redis Docker 服务
- [x] TASK-006 配置 SQLAlchemy Async Session/Base
- [x] TASK-007 初始化 Alembic
- [x] TASK-008 实现 /health
- [x] TASK-009 启动 Compose 并验证 API/PostgreSQL/Redis
- [x] TASK-010 第一次 Git Commit
- [x] TASK-011 User Model
- [x] TASK-012 User Migration
- [x] TASK-013 User Schema/CRUD
- [x] TASK-014 密码哈希与安全模块
- [x] TASK-015 注册
- [x] TASK-016 登录与 Access Token
- [x] TASK-017 `/users/me`
- [x] TASK-018 Refresh Token/JTI
- [x] TASK-019 Logout/Token revoke
- [x] TASK-020 Auth 测试
- [x] TASK-021 Role/Permission Model
- [x] TASK-022 RBAC Migration/CRUD
- [x] TASK-023 权限依赖
- [x] TASK-024 Service 资源级权限
- [x] TASK-025 RBAC 测试
- [x] TASK-058 Dockerfile（因 TASK-009 要求在 Docker 中部署而提前完成并验证）

## In Progress
- [ ]

## Blocked
- None

## Next
TASK-026 Team/TeamMember（Phase 4 团队与项目）

## 部署状态
Docker 全栈已启动并验证：taskflow-app(:8000) / taskflow-postgres(宿主 5433→5432) / taskflow-redis(宿主 6389→6379) 均 healthy；`GET /health` 返回 `{"status":"ok","database":"up","redis":"up"}`。
TASK-019 完成后已重建 app 镜像，并在真实容器上端到端验证 `POST /api/v1/auth/logout`：有效 Token 对登出 → 200 且库中 jti `revoked=true`、之后 refresh 401（§56 Phase 3 验收）；重复登出/伪造签名/类别不符的 Refresh Token → 200 幂等无副作用；跨用户撤销 → 403 且对方 Token 不受影响；禁用账号 → 403；无 Authorization 头 → 401。验证后 users 与 refresh_tokens 两表均 0 行残留。
TASK-020 为纯测试任务（未改应用代码，无需重建镜像）：§35 八项 Auth 测试要求逐条核对均有专项覆盖，新增 `tests/test_auth_flow.py` 5 项端到端验收链路测试（Phase 2 链路、Phase 3 链路、完整生命周期、三轮独立会话、OpenAPI 验收面），全量 143 passed。
TASK-021 为纯模型任务（迁移属 TASK-022，无库表操作）：定义 `roles` / `permissions` / `user_roles` / `role_permissions` 四表 ORM（TASK-021 确认的推断设计已登记 DB_SCHEMA.md），新增 `tests/test_rbac_model.py` 22 项离线模型测试，全量 165 passed。
TASK-022 完成 RBAC 迁移与 CRUD：`7e15047d3a10_create_rbac_tables.py`（autogenerate 建四表，宿主机侧显式 `DATABASE_URL=...5433` 执行 `upgrade head`，已用 `pg_constraint` / `pg_indexes` 实证）+ `0de65c197efc_seed_rbac_data.py`（种子数据迁移——TASK-022 决策：角色 admin/member、§6 全部 22 项权限、admin 绑定全部、member 授「读 + 基础写」10 项；全部 INSERT 带 `ON CONFLICT DO NOTHING` 幂等可重放）；CRUD 层 `app/crud/role.py` / `app/crud/permission.py`（flush-only，事务归 Service；`get_user_permissions` 沿模型链解析出去重后的 `resource:action` 名集合，为 TASK-023 权限依赖的直接输入）。新增 `tests/test_rbac_crud.py` 21 项测试（种子验证只读 + CRUD flush-only 集成），全量 186 passed；验证后开发库零残留、种子完好（2 角色 / 22 权限）。CRUD 尚未被端点消费，无需重建镜像。
TASK-023 完成权限依赖：`app/core/deps.py` 增补工厂 `require_permission(*permissions)`（TASK-023 决策：单权限 / AND 语义、缺权限 403 且文案列出缺失项；权限名格式在工厂创建时校验、启动期快速失败）——依赖链为 `get_current_user`（认证 401 / 禁用 403）→ `get_user_permissions`（模型链解析）→ 集合包含判定；`app/core/exceptions.py` 的 `app_error_handler` 从 `main.py` 抽取为可复用处理器（`main.py` 改为注册，行为不变）。新增 `tests/test_permission_dependency.py` 19 项测试（工厂校验离线 + 测试内探针应用走完整 HTTP 链路：member/admin 权限差异、AND 语义、认证链顺序、禁用账号 403 来源）。全量 205 passed；Docker 重建镜像后冒烟验证（/health、register、login、/users/me、无 Token 401）全 PASS、零残留。
TASK-024 完成 Service 资源级权限（TASK-024 决策：范围 = Service 守卫函数 + `ResourceNotFoundError`，§49 链式归属校验待 TASK-026+ 有实体表时实装；IDOR 场景「资源存在但不在归属链上」→ 404 防枚举，与「不存在」不可区分；`InvalidTransitionError` / `RateLimitExceededError` 随对应 Phase 再建）：新增 `app/services/authorization.py`（`validate_permission_name` 权限名校验收拢于此，`require_permission` 改为复用；`ensure_permission(db, user, *perms)` 与依赖同语义同文案，账号状态仍归认证链）+ `app/core/exceptions.py` 增补 `ResourceNotFoundError`(404)。新增 `tests/test_authorization_service.py` 24 项测试（守卫校验离线、真实数据库授权判定、IDOR 404 契约、探针路由验证 Service 异常的 HTTP 渲染链）。全量 229 passed；Docker 重建镜像后冒烟验证全 PASS、零残留。
TASK-025 为纯测试任务（未改应用代码，无需重建镜像）：§35 三项 RBAC 测试要求（有权限访问 / 无权限访问 / 不同角色权限差异）逐条核对均有专项覆盖（test_rbac_model / test_rbac_crud / test_permission_dependency / test_authorization_service 四模块），补上缺失的验收链路 `tests/test_rbac_flow.py` 10 项端到端测试——§56 Phase 4 验收（ADMIN/MEMBER 同端点集合表现不同、依赖层与守卫层各自独立判定）、角色生命周期（无角色 403 → 授予立即生效 → 撤销立即失效，权限解析实时查库无缓存）、多角色并集聚合去重、撤销单角色保留其余、权限绑定/解绑对既有持有者即时生效、自定义角色 + 种子权限走通依赖层、admin ⊇ member 种子健全性与测试数据零污染。全量 239 passed，验证后种子完好（2 角色 / 22 权限）、零残留。Phase 3 RBAC 全部收官。

## 规则
只有真实完成并验证后才能勾选 Completed。
