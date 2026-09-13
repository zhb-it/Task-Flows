# TaskFlow Pro 当前进度

## Project Status
In Progress

## Current Phase
Phase 4：团队与项目

## Current Task
TASK-034 Task API（已完成）

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
- [x] TASK-026 Team/TeamMember
- [x] TASK-027 团队 CRUD
- [x] TASK-028 成员邀请/删除
- [x] TASK-029 Project Model/CRUD/Service/Router
- [x] TASK-030 团队与项目权限测试
- [x] TASK-031 Task Model/Migration
- [x] TASK-032 Task Schema/CRUD
- [x] TASK-033 Task Service
- [x] TASK-034 Task API
- [x] TASK-058 Dockerfile（因 TASK-009 要求在 Docker 中部署而提前完成并验证）

## In Progress
- [ ]

## Blocked
- None

## Next
TASK-035 Task 查询过滤/分页/排序（Phase 5 任务核心）

## 部署状态
Docker 全栈已启动并验证：taskflow-app(:8000) / taskflow-postgres(宿主 5433→5432) / taskflow-redis(宿主 6389→6379) 均 healthy；`GET /health` 返回 `{"status":"ok","database":"up","redis":"up"}`。
TASK-019 完成后已重建 app 镜像，并在真实容器上端到端验证 `POST /api/v1/auth/logout`：有效 Token 对登出 → 200 且库中 jti `revoked=true`、之后 refresh 401（§56 Phase 3 验收）；重复登出/伪造签名/类别不符的 Refresh Token → 200 幂等无副作用；跨用户撤销 → 403 且对方 Token 不受影响；禁用账号 → 403；无 Authorization 头 → 401。验证后 users 与 refresh_tokens 两表均 0 行残留。
TASK-020 为纯测试任务（未改应用代码，无需重建镜像）：§35 八项 Auth 测试要求逐条核对均有专项覆盖，新增 `tests/test_auth_flow.py` 5 项端到端验收链路测试（Phase 2 链路、Phase 3 链路、完整生命周期、三轮独立会话、OpenAPI 验收面），全量 143 passed。
TASK-021 为纯模型任务（迁移属 TASK-022，无库表操作）：定义 `roles` / `permissions` / `user_roles` / `role_permissions` 四表 ORM（TASK-021 确认的推断设计已登记 DB_SCHEMA.md），新增 `tests/test_rbac_model.py` 22 项离线模型测试，全量 165 passed。
TASK-022 完成 RBAC 迁移与 CRUD：`7e15047d3a10_create_rbac_tables.py`（autogenerate 建四表，宿主机侧显式 `DATABASE_URL=...5433` 执行 `upgrade head`，已用 `pg_constraint` / `pg_indexes` 实证）+ `0de65c197efc_seed_rbac_data.py`（种子数据迁移——TASK-022 决策：角色 admin/member、§6 全部 22 项权限、admin 绑定全部、member 授「读 + 基础写」10 项；全部 INSERT 带 `ON CONFLICT DO NOTHING` 幂等可重放）；CRUD 层 `app/crud/role.py` / `app/crud/permission.py`（flush-only，事务归 Service；`get_user_permissions` 沿模型链解析出去重后的 `resource:action` 名集合，为 TASK-023 权限依赖的直接输入）。新增 `tests/test_rbac_crud.py` 21 项测试（种子验证只读 + CRUD flush-only 集成），全量 186 passed；验证后开发库零残留、种子完好（2 角色 / 22 权限）。CRUD 尚未被端点消费，无需重建镜像。
TASK-023 完成权限依赖：`app/core/deps.py` 增补工厂 `require_permission(*permissions)`（TASK-023 决策：单权限 / AND 语义、缺权限 403 且文案列出缺失项；权限名格式在工厂创建时校验、启动期快速失败）——依赖链为 `get_current_user`（认证 401 / 禁用 403）→ `get_user_permissions`（模型链解析）→ 集合包含判定；`app/core/exceptions.py` 的 `app_error_handler` 从 `main.py` 抽取为可复用处理器（`main.py` 改为注册，行为不变）。新增 `tests/test_permission_dependency.py` 19 项测试（工厂校验离线 + 测试内探针应用走完整 HTTP 链路：member/admin 权限差异、AND 语义、认证链顺序、禁用账号 403 来源）。全量 205 passed；Docker 重建镜像后冒烟验证（/health、register、login、/users/me、无 Token 401）全 PASS、零残留。
TASK-024 完成 Service 资源级权限（TASK-024 决策：范围 = Service 守卫函数 + `ResourceNotFoundError`，§49 链式归属校验待 TASK-026+ 有实体表时实装；IDOR 场景「资源存在但不在归属链上」→ 404 防枚举，与「不存在」不可区分；`InvalidTransitionError` / `RateLimitExceededError` 随对应 Phase 再建）：新增 `app/services/authorization.py`（`validate_permission_name` 权限名校验收拢于此，`require_permission` 改为复用；`ensure_permission(db, user, *perms)` 与依赖同语义同文案，账号状态仍归认证链）+ `app/core/exceptions.py` 增补 `ResourceNotFoundError`(404)。新增 `tests/test_authorization_service.py` 24 项测试（守卫校验离线、真实数据库授权判定、IDOR 404 契约、探针路由验证 Service 异常的 HTTP 渲染链）。全量 229 passed；Docker 重建镜像后冒烟验证全 PASS、零残留。
TASK-025 为纯测试任务（未改应用代码，无需重建镜像）：§35 三项 RBAC 测试要求（有权限访问 / 无权限访问 / 不同角色权限差异）逐条核对均有专项覆盖（test_rbac_model / test_rbac_crud / test_permission_dependency / test_authorization_service 四模块），补上缺失的验收链路 `tests/test_rbac_flow.py` 10 项端到端测试——§56 Phase 4 验收（ADMIN/MEMBER 同端点集合表现不同、依赖层与守卫层各自独立判定）、角色生命周期（无角色 403 → 授予立即生效 → 撤销立即失效，权限解析实时查库无缓存）、多角色并集聚合去重、撤销单角色保留其余、权限绑定/解绑对既有持有者即时生效、自定义角色 + 种子权限走通依赖层、admin ⊇ member 种子健全性与测试数据零污染。全量 239 passed，验证后种子完好（2 角色 / 22 权限）、零残留。Phase 3 RBAC 全部收官。
TASK-026 完成 Team/TeamMember 模型与迁移（TASK-026 决策：团队角色 role_id 用 SmallInt + CHECK 枚举 1=OWNER/2=ADMIN/3=MEMBER，与全局 RBAC 角色两套体系互不污染；teams.owner_id 外键 ON DELETE RESTRICT——项目首个 RESTRICT 外键，删 owner 前必须先转让团队；teams.name 不加 UNIQUE；范围 = 模型 + 迁移，CRUD 留 TASK-027/028）：新增 `app/models/team.py` / `app/models/team_member.py`（含 TeamRole IntEnum）与迁移 `fc52c0603ba5_create_teams_and_team_members.py`（已 upgrade head，pg_constraint / pg_indexes 实证，并直连库实证 RESTRICT 行为：删有团队的用户抛 ForeignKeyViolationError）。新增 `tests/test_team_model.py` 21 项测试（14 项离线模型 + 7 项 DB 约束集成：复合 UNIQUE 拒重复加入、CHECK 拒非法角色、RESTRICT 拒删有团队用户、删团队级联清成员、同名团队可并存）。全量 260 passed，零残留。
TASK-027 完成团队 CRUD——产品应用首批资源型端点（POST/GET /teams、GET/PATCH/DELETE /teams/{team_id}；成员端点留 TASK-028）。TASK-027 决策（用户确认）：①创建团队自动写 `team_members` OWNER 行（归属链统一）；②PATCH/DELETE 资源级**仅 owner**（非 owner 一律 404，IDOR 契约）；③列表/详情可见范围 = 我参与的团队（owner 或成员）。新增 `app/schemas/team.py`（TeamCreate/TeamUpdate/TeamRead，PATCH 用 exclude_unset 部分更新、description 显式 null 清空）、`app/crud/team.py`（flush-only）、`app/services/team.py`（Service 层 commit，与 auth 服务同惯例；create 同事务写 teams + OWNER 成员行）、`app/api/v1/teams.py`（require_permission 依赖声明 team:create/read/update/delete）并注册进 api_router。新增 `tests/test_team_service.py` 12 项（CRUD/Service DB 集成）+ `tests/test_team_api.py` 13 项（真实产品应用 + 真实 Token 认证链的 HTTP 端到端：201 自动写 OWNER 行、member 403 先于归属 404、非 owner admin 404、无权限 owner 403、PATCH 部分语义、DELETE 级联、IDOR 404 不可区分、422 校验、分页、离线 openapi 路由注册断言）。全量 285 passed，验证后 teams/team_members 0 行、种子完好（2 角色 / 22 权限）。

TASK-028 完成成员邀请/删除（TASK-028 决策，用户确认：①**双层判定**——功能级 team:invite/read + 资源级团队角色 OWNER/ADMIN，团队角色不足 403（调用者已在归属链、无泄露顾虑）；②邀请请求体 user_id + role 仅 admin/member（owner 不可邀请，"owner" → 422），重复邀请 409、目标用户不存在 404；③移除层级 OWNER > ADMIN > MEMBER——owner 可移除任何非 owner 成员、admin 仅可移除 member、owner 不可被移除（403，与 owner_id RESTRICT 语义一致）；④成员列表团队成员可见，局外人 404）：app/schemas/team.py 增补 TeamMemberInvite/TeamMemberRead；app/crud/team.py 增补 remove_team_member/list_team_members（join users 取 username）；app/services/team.py 增补 invite_member/remove_member/list_members；app/api/v1/teams.py 增补三个端点（POST /teams/{id}/members、GET /teams/{id}/members、DELETE /teams/{id}/members/{user_id}）。新增 tests/test_team_members_service.py 14 项 + tests/test_team_members_api.py 10 项（真实产品应用 HTTP 端到端：双层判定的三种 403 形态、可见性翻转、层级移除、409/404 契约、422 校验）。全量 309 passed，零残留；Docker 重建镜像后真实容器冒烟 6 项 PASS（邀请 201 → 重复 409 → 成员列表可见 → 移除后 404 → owner 不可移除 → 零残留）。

TASK-029 完成 Project Model/CRUD/Service/Router（TASK-029 决策，用户确认：①projects 字段自定——team_id FK→teams CASCADE + owner_id FK→users RESTRICT（创建者，可转让），name 不加 UNIQUE；②创建授权 = 全局 project:create + 团队成员即可；③改删授权 = 全局 project:update/delete + 团队角色 OWNER/ADMIN（角色不足 403「Only team owner or admin can manage projects」，不在归属链 404）；④列表 = 我所在团队下的项目）。可见性按规格 §5「用户只能访问其所属团队链路下的资源」，归属链 = 项目所属团队的 team_members 成员。交付：app/models/project.py + 迁移 99f70df5d269（information_schema 实证 CASCADE/RESTRICT/双索引）；schemas/crud/service/api 四件套；owner_id 恒为创建者不开放客户端指定。tests/test_project_model.py 12 项（离线 + DB 约束集成：CASCADE 删团队清项目、RESTRICT 拒删有项目用户、同名可并存）+ tests/test_project_api.py 11 项（HTTP 端到端：三层 403/404 形态、可见性、exclude_unset、删团队级联清项目）。全量 332 passed，零残留；Docker 容器冒烟 6 项 PASS。

TASK-030 完成团队与项目权限测试（Phase 4 收尾）：新增 tests/test_team_project_permissions.py 11 项——把 TASK-027/028/029 分散的授权语义整合为「全局 RBAC 角色 × 团队角色 × 操作」系统性矩阵验收（六用户阵容：owner/tmember/tadmin/gmember/outsider/nobody），落实开发文档 §56 Phase 4 验收点「ADMIN / MEMBER 权限表现不同」；覆盖双层判定两方向（团队角色高不补全局权限、全局权限高不过资源级归属）、IDOR 404 契约一致性（含列表不泄露）、可见性翻转、无角色用户 403 优先。TESTING.md 增补「团队与项目权限矩阵」章节。全量 343 passed，零残留（纯测试任务，无应用代码变更，无需镜像重建）。

TASK-031 完成 Task Model/Migration（Phase 5 开始；TASK-031 决策，用户确认：①基础十列——id/project_id/title/description/status/priority/creator_id/due_at/created_at/updated_at，无 assignee 列（多人分配在 task_assignees，TASK-036），无单独 owner_id；②creator_id FK→users **CASCADE**——creator 是创建者非 owner 式所有者，删用户级联清其创建的任务不卡删除；③status/priority 存 **VARCHAR + CHECK 字面字符串**（'TODO' 等，API/DB/日志同字面值，Python 侧 TaskStatus/TaskPriority StrEnum）。DB_SCHEMA 硬约束全落实：双 CHECK（ck_tasks_status_values/ck_tasks_priority_values）、复合索引 (project_id,status)、(creator_id)、due_at 部分索引（WHERE status IN 未完成三态，谓词精确落库）。新增 app/models/task.py + 迁移 6f1cfcc35abe（autogenerate，information_schema/pg_constraint/pg_indexes 实证）+ tests/test_task_model.py 15 项（离线 9 + DB 集成 6：默认值 roundtrip、CHECK 拒非法值、删项目/删 creator 级联清任务、同名并存）。全量 358 passed，零残留；Docker 重建后容器冒烟 PASS（模型变更不影响启动与既有端点）。

TASK-032 完成 Task Schema/CRUD（TASK-032 决策，用户确认：①POST 创建请求体**不含 status**——新任务一律 TODO 起步，状态流转只能走 transition API（TASK-038），杜绝绕过状态机直接建出 DONE 任务；②CRUD 层仅基础操作——get_task / list_tasks_by_project（id 升序）/ create / update / delete，过滤/分页/排序留 TASK-035 专项不超前实现）。交付：app/schemas/task.py（TaskCreate/TaskUpdate/TaskRead；TaskUpdate 同样不含 status/project_id/creator_id；priority 用 TaskPriority StrEnum 校验，默认 MEDIUM；title 1-200；TaskRead 暴露全 10 列）+ app/crud/task.py（flush-only，事务边界在 Service）。tests/test_task_crud.py 13 项（Schema 离线 7 + DB 集成 6：TODO 起步、roundtrip/due_at、项目隔离与升序、exclude_unset 部分更新且 status 不受影响、删除）。全量 371 passed，零残留；Docker 重建后容器冒烟 PASS（tasks 路由未提前暴露）。清理了早前失败运行留下的 taskcrud 前缀孤儿行（teardown 修复前产生）。

TASK-033 完成 Task Service（TASK-033 决策，用户确认：①创建授权 = 全局 task:create + 项目所属团队成员即可——项目不存在或非成员统一 404 Project not found（IDOR 防枚举，类比 POST /projects 对不可见团队报 Team not found）；②更新 = 归属链上成员即可（task:update，seed member 有此权限暗示协作式更新），删除 = 全局 task:delete + 团队角色 OWNER/ADMIN（seed member 无 task:delete——删除是管理行为；角色不足 403 Only team owner or admin can delete tasks）。归属链 = 任务 → 项目 → 团队 → team_members（规格 §5）。交付：app/services/task.py（create/get_for_user/list/update/delete + _get_task_on_chain 资源级判定原语；commit 事务边界在本层；status 不可经 update 触达，流转留 TASK-038 transition）。tests/test_task_service.py 9 项（DB 集成：成员创建 creator=caller+TODO 起步、非成员/不存在 404 同文案、成员/局外读可见性、项目隔离列表、member 更新 OK 且 status 不变、member 删除 403、owner 删除 OK）。全量 380 passed，零残留；容器冒烟 PASS。

TASK-034 完成 Task API（Phase 5：五端点挂载 /api/v1——POST /tasks 201 TODO 起步、GET /tasks?project_id={id} 必填 query 参数（缺失 422）、GET/PATCH/DELETE /tasks/{task_id}；授权语义沿用 TASK-033 决策，无新决策）。tests/test_task_api.py 10 项 HTTP 端到端（真实产品应用+真实 Token）：创建 201/无全局权限 403/非成员与不存在 404 同文案/请求体带 status 被忽略（额外字段默认忽略，核心契约恒 TODO）、成员读可见+局外人 404（详情与列表）、PATCH exclude_unset（显式 null 清空 description、未传 title 保持、status 不可触达）、删除双 403 形态辨析——member 全局角色无 task:delete 被功能级 403 挡住，资源级 403（Only team owner or admin can delete tasks）由「全局 admin+团队 MEMBER」触发、owner 删除 200+复查 404。全量 390 passed，零残留；Docker 重建后真实容器冒烟 6 项 PASS。

## 规则
只有真实完成并验证后才能勾选 Completed。
