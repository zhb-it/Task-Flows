# TaskFlow Pro 当前进度

## Project Status
Completed——`docs/TASKS.md` 中 TASK-001 ~ TASK-064 全部勾选，无未完成任务。

## Current Phase
Phase 10：工程化

## Current Task
TASK-063 README 与面试技术难点（Phase 10：README 按规格 §Phase 17 的 19 个部分重写 + `docs/INTERVIEW.md` 覆盖 §56 的 9 领域 35 问 + 两者纳入文档护栏）

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
- [x] TASK-035 Task 查询过滤/分页/排序
- [x] TASK-036 TaskAssignee 多人分配
- [x] TASK-037 状态机规则
- [x] TASK-038 Transition API
- [x] TASK-039 OperationLog
- [x] TASK-040 状态机与审计测试
- [x] TASK-041 Comment
- [x] TASK-042 Attachment
- [x] TASK-043 上传/下载权限与安全校验
- [x] TASK-044 评论/附件测试
- [x] TASK-045 Redis 连接与 Key 约定
- [x] TASK-046 ZSET + Lua 滑动窗口限流
- [x] TASK-047 限流测试
- [x] TASK-048 Celery App/Worker
- [x] TASK-049 通知异步任务（含提前完成的 notifications 建模，见 DECISIONS 029）
- [x] TASK-050 日志归档/附件清理任务（见 DECISIONS 031/032）
- [x] TASK-051 幂等、重试与任务测试（纯测试任务，Phase 8 收尾，见 DECISIONS 033）
- [x] TASK-052 Notification Model（建模提前于 TASK-049，本 TASK 补 Model 检查测试 `tests/test_notification_model.py` 16 项，见 DECISIONS 034）
- [x] TASK-053 通知 Service/API（查询/标记已读端点 + 业务派发点接线，见 DECISIONS 035）
- [x] TASK-054 通知 read-all / 标记全部已读（响应体返回标记条数 `{"marked": N}`，见 DECISIONS 036）
- [x] TASK-055 通知端到端测试（真实派发全链路，`tests/test_notification_e2e.py` 7 项，Phase 9 收官）
- [x] TASK-056 结构化日志（JSON/文本按环境推导 + 出口脱敏 + 访问日志中间件，`tests/test_logging.py` 41 项，见 DECISIONS 037）
- [x] TASK-057 Request ID（`X-Request-ID` 单一头 + 客户端值白名单校验 + 独立最外层中间件，`tests/test_request_id.py` 34 项，见 DECISIONS 038）
- [x] TASK-058 Dockerfile（因 TASK-009 要求在 Docker 中部署而提前完成并验证）
- [x] TASK-059 Production Compose（独立完整文件 `docker-compose.prod.yml`：端口内外分离 + 密钥 fail-fast + 卷/项目名隔离，`tests/test_prod_compose.py` 26 项，见 DECISIONS 039）
- [x] TASK-060 Nginx/Gunicorn/Uvicorn（`nginx/nginx.conf` + 唯一入口反代 + Gunicorn/UvicornWorker；覆盖式 `X-Forwarded-For` 与信任网段判定解决 DECISIONS 018 遗留约束；`tests/test_client_ip.py` 26 项 + `tests/test_nginx_config.py` 32 项，见 DECISIONS 040/041/042）
- [x] TASK-061 GitHub Actions CI（`.github/workflows/ci.yml` 三 job：ruff lint / pytest（service 端口贴测试硬编码的 5433+6389 + 迁移可逆性验证）/ docker build；`requirements-dev.txt` 与 `[tool.ruff]` 钉死版本与规则集；`tests/test_ci_workflow.py` 35 项，见 DECISIONS 043）
- [x] TASK-062 完整测试与质量检查（956 passed；覆盖率 2373 语句 / 1 未覆盖 / 358 分支 / 0 分支半覆盖 → 99.96% 行、100% 分支，仅本地基线与文档、不进 CI 门禁；新增 4 个测试模块 80 项——存储安全守卫 / 有价值分支 / 质量契约 / N+1 运行时护栏；顺带修复 2 处生产缺陷（并发注册 409 兜底不可达、非字符串日志消息绕过脱敏）与 3 处测试自身残留，订正 3 处文档矛盾，`docs/QUALITY.md` 新建，见 DECISIONS 044）
- [x] TASK-064 数据库搜索索引 `pg_trgm` / `tsvector`（落实 §57 与 §14：`CREATE EXTENSION pg_trgm` + `GIN (title gin_trgm_ops)` + `search_vector` 生成列 + `GIN (search_vector)`；`EXPLAIN` 实证 `ILIKE '%x%'` 由顺序扫描转为 `Bitmap Index Scan`，`keyword` 查询语义不变；附带把「PROGRESS 三处核验」变成 CI 自动拦截的 `scripts/check_docs.py` + `tests/test_docs_consistency.py`，见 DECISIONS 045）
- [x] TASK-063 README 与面试技术难点（README 按规格 §Phase 17 的 19 个必需部分重写，全部数字取自真实仓库且受断言约束；新建 `docs/INTERVIEW.md` 逐条作答 §56 的 9 领域 35 问、题干逐字照抄；`tests/test_readme.py` 把 README 的结构性声明与 ORM metadata / OpenAPI schema / 文件系统对齐，含反向用例，见 DECISIONS 046）

## In Progress
- [ ]

## Blocked
- None

## Next
无——TASK-001 ~ TASK-064 全部交付，`docs/TASKS.md` 中已无未勾选任务（见 DECISIONS 046 与 §60 开发终点）。

## 部署状态
Docker 全栈已启动并验证：taskflow-app(:8000) / taskflow-postgres(宿主 5433→5432) / taskflow-redis(宿主 6389→6379) 均 healthy；`GET /health` 返回 `{"status":"ok","database":"up","redis":"up"}`。
TASK-059 生产栈（`docker-compose.prod.yml`）已在真实 Docker 上验证并**完整拆除**：四服务 healthy、app 仅 `127.0.0.1:18080->8000`（LAN 地址原始 socket 连接超时，反证仅回环可达）、postgres/redis 零宿主端口、卷为 `taskflow-prod_*` 前缀（与开发栈隔离）、迁移后 `/health` 返回 `env=production`、注册/登录/`users/me` 全通、容器日志为 §33 JSON 十字段、Redis AOF=`yes`；`down -v` 后生产容器与卷零残留，开发栈全程保持 healthy。生产栈与服务端 nginx/Gunicorn 的对外暴露留待 TASK-060。**（TASK-060 更新：上面「app 绑回环端口」已被取代——反代接入后 app 不再发布任何宿主端口，对外只有 nginx；同一套冒烟验证与零残留结论见 TASK-060 条目。）**
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

TASK-035 完成 Task 查询过滤/分页/排序（TASK-035 决策，用户确认：①分页沿用 skip/limit——与 teams/projects 同惯例，响应仍为纯列表 {data: [...]}，skip≥0、limit 1-100 默认 100；②过滤范围 = status 枚举精确 + priority 枚举精确 + keyword 标题模糊——%/_/\ 通配符转义后按字面 ILIKE 匹配、纯空白视为未传，负责人筛选依赖 TASK-036 TaskAssignee 暂不做；③排序 = sort 白名单 id/created_at/due_at/priority（TaskSortField StrEnum，非法 422 防注入）+ order asc/desc，**priority 按业务权重（URGENT > HIGH > MEDIUM > LOW）而非字母序**（Service 层 SQL case 映射）；④project_id 保持必填，跨项目「我的任务」视图留待 TASK-036 后再议）。交付：app/schemas/task.py 增补 TaskSortField/TaskSortOrder；app/crud/task.py 的 list_tasks_by_project 演进为过滤/分页/排序查询（排序子句由 Service 传入，CRUD 保持纯数据操作）；app/services/task.py 的 list_tasks 扩展参数并做 keyword 转义/白名单映射（可见性 404 契约不变）；app/api/v1/tasks.py 的 GET /tasks 挂载全部 query 参数。新增 tests/test_task_query_api.py 8 项 HTTP 端到端（status 过滤含 fixture 直插 IN_PROGRESS/DONE 行——POST 只能建 TODO；priority 过滤；keyword 大小写不敏感 + % 字面匹配 + 空白忽略；分页窗口/超界空列表/边界 422；sort=id 与 priority 业务序双向、due_at desc；非法 sort/order/limit/skip/status 422；过滤+分页组合与局外人 404 可见性不变）。全量 398 passed，开发库零残留；Docker 重建镜像后真实容器冒烟 10 项 PASS（过滤/排序/分页/422 全链路，冒烟数据 API+DB 双通道清理干净）。

TASK-036 完成 TaskAssignee 多人分配（Phase 5 收官；TASK-036 决策，用户确认：①分配/移除授权 = 功能级 **task:update**（分配是更新行为，不新增 seed 权限项）+ 资源级**任务所属团队成员即可**——协作式，member 可分配他人与自领；②目标用户不存在或非任务所属团队成员 → 404 `User not found` 同文案（防枚举）；目标已是负责人 → 409 `User already assigned to this task`；目标非该任务负责人 → 404 `Assignee not found`；任务不在归属链 → 404 `Task not found`；③TaskRead 内嵌 `assignees: [{user_id, username, assigned_at}]`——创建/详情/列表/更新响应统一内嵌，Service 批量 IN 查询组装避免 N+1，未分配恒空列表；④GET /tasks 增可选 `assignee_id` 负责人筛选）。交付：app/models/task_assignee.py（复合主键 (task_id, user_id) 落实规格 §5 UNIQUE；assigned_by_id 最小审计推断设计；user_id 单列索引）+ 迁移 b90b4cff0f64（information_schema/pg_indexes 实证复合 PK、三 FK 全 CASCADE、索引）；app/crud/task_assignee.py（flush-only：add/remove/is_assignee/list_assignees/list_assignees_for_tasks 批量/filter_tasks_by_assignee「我的任务」原语）；app/crud/task.py 的 list_tasks_by_project 增 assignee_id exists 过滤；app/services/task.py 增 assign_task/unassign_task/assignees_map；app/api/v1/tasks.py 增 POST /tasks/{id}/assignees 与 DELETE /tasks/{id}/assignees/{user_id}，全部任务响应经 _serialize_task(s) 内嵌 assignees。新增 tests/test_task_assignee_api.py 8 项 HTTP 端到端（内嵌渲染、member 分配他人+自领、重复 409、目标不存在/非成员 404 同文案、无全局权限 403 与 IDOR 404 辨析、移除 200→404、assignee_id 过滤全生命周期、多负责人与删任务级联清分配行 DB 实证）；tests/test_task_crud.py 的 TaskRead 字段集断言同步 assignees。全量 406 passed（team_api 一例 DB 连接超时为瞬时抖动，重跑即绿）；零残留。

TASK-037 完成状态机规则（Phase 6 首任务；纯规则层，无端点/无迁移；TASK-037 决策，用户确认：①**仅严格前进**——规格只画线性链，相邻回退（IN_PROGRESS→TODO、REVIEW→IN_PROGRESS）与跨级跳转一律非法；②**终态完全封死**——DONE/CANCELLED 无任何出边（含 →CANCELLED），「任意状态→CANCELLED」理解为任意**非终态**，与规格「终态不可流转」无矛盾；③非法流转（含同状态重复流转如 TODO→TODO）→ **409 Conflict** `Invalid status transition`（复用 ConflictError，TASK-038 API 消费时呈现）；④独立模块落位）。交付：app/services/state_machine.py——TRANSITIONS 流转表（from → frozenset(to)，覆盖全部 5 状态）、TERMINAL_STATUSES、can_transition 纯查询、validate_transition（非法抛 ConflictError）、allowed_targets（前端看板拖拽白名单）；不依赖 DB/Session 可离线单测。新增 tests/test_state_machine.py 29 项离线测试（合法前进 3 + 非终态→CANCELLED 3、终态封死 8 + 跨级 6、同状态 5、409 文案与状态码、allowed_targets 全表、StrEnum/str 互操作）。纯规则模块尚未被任何端点 import，无需重建镜像（TASK-038 消费时重建）。

TASK-038 完成 Transition API（Phase 6；TASK-038 决策，用户确认：①请求体 `{"to_status": "<状态>"}`——字段名与 PATCH set 语义及 GET ?status= 过滤区分，非法值/缺失/null → 422；②功能级 `task:transition`（§6 权限清单专门项，种子仅 admin 持有）+ 资源级**任务所属团队成员即可**（协作式，与更新/分配同语义，区别于删除的 OWNER/ADMIN））。交付：app/schemas/task.py 增 TaskTransitionCreate、app/services/task.py 增 transition_task（_get_task_on_chain 404 契约 → validate_transition Service 层拦截 409 → 改 status → commit）、app/api/v1/tasks.py 挂载 POST /tasks/{task_id}/transition（200 返回更新后 TaskRead 含 assignees 内嵌；Decision 005 不破坏——PATCH 依旧不可触达 status）。新增 tests/test_task_transition_api.py 7 项 HTTP 端到端（合法前进链全链 + GET 复查持久化、三个非终态→CANCELLED、11 对非法流转矩阵 409 且 GET 证实状态不变、422 校验三种形态、member/无角色 403 同文案、局外人/不存在 404 防枚举、全局 admin+团队 MEMBER 协作式流转 200）。全量 442 passed（435 + 7），零残留；Docker 重建镜像后真实容器冒烟 11 项 PASS（register→授权→login→建链→TODO→IN_PROGRESS 200→回退/跨级 409→API+SQL 双通道清理→users/tasks/projects/teams 零残留）。

TASK-039 完成 OperationLog 审计日志（Phase 6；TASK-039 决策，用户确认：①`operation_logs.user_id` **不加外键**——审计日志独立于用户生命周期，删用户后日志完整保留且不卡删除，user_id 仍 NOT NULL（每条日志由已认证用户产生）；②埋点范围 = **仅 transition**（协作式且 §15 payload 示例恰好对应流转，Phase 6 审计主题自洽，不跨未完成的创建/删除评论功能）；③日志查询授权 = **资源级隔离**——`GET /logs` 仅返回当前用户自己的日志，`GET /logs/{type}/{id}` 须验证用户对资源的归属权限）。交付：app/models/operation_log.py（id/user_id/resource_type/resource_id/action/payload JSONB/created_at；§15 三索引全落实——(resource_type,resource_id)、(user_id,created_at DESC)、GIN(payload)）+ 迁移 c5f8e1a2b3d4（已 `DATABASE_URL=...5433` upgrade head，information_schema/pg_indexes 实证 jsonb 列与三个索引）；app/crud/operation_log.py（flush-only：create/list_by_user/list_by_resource，按 created_at DESC 分页）；app/schemas/operation_log.py（OperationLogRead，payload 原样透传）；app/services/operation_log.py（write_operation_log 仅 flush 由调用方提交 + list_user_logs + list_resource_logs 资源级归属校验，非 task 类型/非成员 → 404 防枚举）；app/api/v1/logs.py（GET /logs、GET /logs/{resource_type}/{resource_id}，require_permission("log:read")，分页 skip/limit）注册进 api_router；app/services/task.py 的 transition_task 在同一事务内写 `action=task:transition` / `payload={old_status,new_status}` 审计行。新增 tests/test_operation_log_api.py 6 项 HTTP 端到端（transition 写日志且 GET /logs 与 GET /logs/task/{id} 均返回、资源级隔离只看自己、非成员 404、非 task 类型 404、分页 DESC、无 log:read 角色 403）。全量 448 passed（442 + 6），零残留；Docker 重建镜像后真实容器冒烟 5 项 PASS（/health → transition 200 → GET /logs payload 正确 → GET /logs/task/{id} 同条 → 清理零残留）。

TASK-040 完成状态机与审计测试（Phase 6 收官；纯测试任务，未改应用代码，无迁移，无需重建镜像——同 TASK-020/025/030 先例）。先对开发文档 §35「Task 重点测试」（状态正常流转/非法状态流转/DONE 不允许回退）、§56 Phase 8「状态机」验收条款（状态枚举/transition API/Service 状态机/非法状态拦截/操作日志）、§55.3 链路（状态变更 → 写 OperationLog → 提交）逐条核对，确认 TASK-037/038/039 分散模块已覆盖细粒度规则与端点，补上此前缺失的**整合验收链路与事务原子性**：新增 tests/test_state_machine_audit_flow.py 6 项——①§56 Phase 8 完整链路演示（TODO→IN_PROGRESS→REVIEW→DONE 跑通 + DONE→TODO 被拒绝，规格原文两条）；②§35 状态正常流转（每跳 200 且持久化）；③§35 非法流转 + DONE 不回退（跨级/同状态/终态出边全 409 且状态不动）；④审计 ⇄ 状态一致性（三次成功流转 → 三条日志，old_status/new_status 与状态链严格衔接）；⑤被拒流转不产生日志；⑥**§55.3 事务原子性**（monkeypatch 让 write_operation_log 抛异常 → 任务状态一并回滚仍 TODO 且库中零日志，证明「状态变更 + 写日志 + 提交」同事务、不存在状态变了但没日志的不一致）。TESTING.md 增补「状态机与审计（TASK-040）」章节。全量 454 passed（448 + 6），零残留。Phase 6 状态机与审计全部收官。

TASK-041 完成 Comment 评论（Phase 7 起点；TASK-041 决策，用户确认：①`comments.user_id` **FK→users ON DELETE CASCADE**——评论是用户产出内容，删用户级联清其评论（与 tasks.creator_id 同惯例），审计追溯由 OperationLog 承担；②删除授权 = 功能级 `comment:delete` + 资源级**评论作者本人或任务所属团队 OWNER/ADMIN**（两者都不是 → 403），与删除任务的 OWNER/ADMIN 语义一致且尊重作者删自己评论的需求；③**不做编辑端点**——§16 有 updated_at 但 §25.6 端点清单仅 POST/GET/DELETE，字段由 DB 维护，编辑能力留后续 TASK）。交付：app/models/comment.py（id/task_id FK CASCADE/user_id FK CASCADE/content TEXT/created_at/updated_at；索引 (task_id, created_at) 复合 + user_id 单列）+ 迁移 d7a3b9c1e5f2（已 upgrade head，information_schema/pg_constraint/pg_indexes 实证双 FK confdeltype='c' 与索引）；app/crud/comment.py（flush-only：create/get/list_by_task（join users 取 username 防 N+1）/delete）；app/schemas/comment.py（CommentCreate content 1-2000、CommentRead 内嵌 username）；app/services/comment.py（create_comment/list_comments 归属链校验 404 防枚举；delete_comment 双层授权——作者或团队 OWNER/ADMIN 否则 403、不在链 404 同文案、**删除同事务写 action=comment:delete 审计日志**§16 规则 4）；app/api/v1/comments.py（POST/GET /tasks/{task_id}/comments + DELETE /comments/{comment_id}）注册进 api_router。**读取功能级权限复用 task:read**（§6 清单无 comment:read，评论是任务一部分，有据可依的推断）。新增 tests/test_comment_api.py 11 项 HTTP 端到端（创建 201 内嵌 username、时间升序列表、functional 403、局外人/不存在任务 404、作者删自己 200 且审计行字段精确、团队 ADMIN 删他人 200、团队成员删他人 403 文案、member 作者删自己因无 comment:delete 被功能级 403 先挡、局外人删 404 双形态、422 三种、删任务级联清评论）。全量 465 passed（454 + 11），零残留；Docker 重建镜像后真实容器冒烟 6 项 PASS（/health → POST 201 → GET 列表 → DELETE 200 且写审计日志 → 删除后列表空 → 清理零残留）。

TASK-042 完成 Attachment 附件（Phase 7；TASK-042 决策，用户确认：①**042 实现全量含安全**——上传/下载/删除与 §9 安全校验一次交付，不为 043 预留半成品；②**存储层用「接口 + 本地实现」**——定义 `StorageBackend` 协议 + `LocalStorageBackend`，为 §17 预留对象存储迁移；③**`attachments.storage_path` 只存相对 key**（如 `tasks/12/ab12cd34.bin`），不存绝对路径，DB 不绑定部署机器的文件系统布局）。交付：app/models/attachment.py（id/task_id FK CASCADE/uploader_id FK CASCADE/filename VARCHAR(255)/storage_path VARCHAR(512) UNIQUE/content_type/size/created_at；索引 (task_id, created_at) + storage_path UNIQUE + uploader_id）+ 迁移 e9b4c2d6f8a1（已 `DATABASE_URL=...5433` upgrade head）；**.gitignore 补 `storage/`**；app/services/storage.py（StorageBackend Protocol + LocalStorageBackend：`save`（边写边累计、超限中止并清理半成品）/`open`/`delete`（幂等 + 清理空目录）/`exists`，外加 `validate_key`（字符集白名单 + 拒绝绝对路径/穿越段/盘符）与 `build_key`（`tasks/{task_id}/{token_hex(16)}{ext}` 随机名，用户输入不参与路径构造）**双层穿越防护**：语义校验 + `_resolve` 解析后断言仍在根目录内；`get_storage_backend()` 单例为唯一注入点）；app/crud/attachment.py（flush-only：create/get/list_by_task（join users 取 uploader）/delete）；app/schemas/attachment.py（AttachmentRead 内嵌 uploader；入站刻意不用 Pydantic——multipart 的大小校验必须在流式写入过程中完成，先读进内存再校验会被超大文件撑爆）；app/services/attachment.py（**§17 全部要求落位**：①`ALLOWED_TYPES` 扩展名→规范 MIME 白名单，**以扩展名判定而非采信客户端 Content-Type**；②`sanitize_filename` 去目录成分（POSIX+Windows 双分隔符）/去控制字符/去首尾点空白/折叠 Windows 保留设备名/截断保留扩展名；③`resolve_content_type` 415；④大小硬限 413；⑤归属链 404 防枚举；⑥删除双层授权——上传者本人或团队 OWNER/ADMIN 否则 403；⑦删除写 `action=attachment:delete` 审计日志；**一致性设计**：先落盘再落库（避免有记录无文件的幽灵附件）、落库失败回滚物理文件（避免孤儿垃圾）、删除时先删文件再删记录且删文件失败不删记录（可重试，不制造不可回收泄漏）+ 记录在但物理文件缺失 → 404 而非 500；`_UploadReader` 同步/异步桥接，说明为何不能用 `run_until_complete`（循环已在运行））；app/api/v1/attachments.py（POST/GET `/tasks/{task_id}/attachments` + GET/DELETE `/attachments/{attachment_id}`；下载用 StreamingResponse 分块 + `Content-Disposition: attachment; filename*=UTF-8''{quote(...)}`（结构上杜绝响应头注入）+ `X-Content-Type-Options: nosniff`）注册进 api_router。**权限映射**：列表读复用 `task:read`（§6 无 attachment:read），删除复用 `attachment:upload`（§6 无 attachment:delete）。新增 tests/test_attachment_api.py 27 项 HTTP 端到端（上传+列表、时间升序、同名文件 storage_path 唯一且互不覆盖、413 超限且零残留、边界恰好等于上限通过、415 五种危险扩展名、扩展名大小写不敏感、伪造 Content-Type 被拒、`../../etc/passwd` 清洗为 `passwd.txt` 且 key 不含用户输入、Windows 分隔符清洗、控制字符剥离、保留设备名折叠、空文件 400、功能级 403 三端点、资源级 404 四端点一致、不存在 id 404 同文案、member 正常上传下载、下载字节一致+三个响应头、非 ASCII 文件名 RFC 5987 编码、物理文件缺失 404、上传者删自己 200 + 审计字段精确、团队 ADMIN 删他人 200、普通成员删他人 403、member 删自己 200、无角色 403、删任务级联、删用户级联）。全量 **492 passed**（465 + 27），零残留。

TASK-043 完成 上传/下载权限与安全校验（Phase 7，**安全对抗性专项**，而非重复 042 的功能测试）。方法：先写**真实攻击面探测脚本**（不走 pytest，直接构造恶意请求 + 直连 DB 篡改存储字段），据探测结果而非推测定位缺陷，然后逐一修复并把每个缺陷固化为回归测试。**探测发现并修复的 3 个真实实现缺陷**：①**非法 `storage_path` 触发 500 + 堆栈**（最严重）——`attachments.storage_path` 正常由 `build_key` 生成必然合法，但若被绕过 API 改写（DB 被入侵 / 迁移脚本写错 / 历史脏数据）为穿越 key 或绝对路径，存储层抛 `UnsafeStorageKeyError`，而 042 只捕获 `StorageObjectNotFoundError` → 未捕获异常变 500，把存储根的 key 校验规则泄露给调用者。修复（**两个路径刻意不同处理**，见 Decision 009）：**下载**把该异常一并映射为 404 `Attachment not found`（语义等价于「拿不到文件」）；**删除**捕获后跳过物理删除、继续删记录（若同样抛错会形成**永远删不掉的脏记录**——记录里的 key 永远非法，用户永远删不掉；删除的目标是让记录消失，那个文件本就不在存储根内）。②**`%XX` 百分号编码绕过扩展名白名单**——`a.txt%00.png` 按最后一段 `.png` 通过白名单，但 `%00` 在下游任何一处 URL 解码后变成 NUL 并截断字符串，使「校验时的扩展名」与「实际使用的扩展名」不一致（经典 §48 文件上传漏洞）。修复（Decision 010）：`sanitize_filename` 在去控制字符**之前**主动剥离所有 `%XX` 序列（`_PERCENT_ESCAPE_RE`；顺序必须如此，否则 `%00` 解码出的 NUL 会绕过控制字符过滤），把不确定性从整条链路收敛到一个函数。③**无主名文件名行为不一致**——`.txt` 经清洗变成 `txt` 后被 415 拒绝，**原因（扩展名不在白名单）与表象不符**。修复（Decision 011）：`resolve_content_type` 用 `rpartition` 三元组显式判定「无主名」并统一 415。**探测额外发现的自伤缺陷**：`write_operation_log` 被调用 **2 次**（单次删除写 2 条审计日志）——根因是之前一次 Edit 只替换了上半段，旧的 `write_operation_log` + `db.commit()` 块残留在同一函数内；已删除重复块，单次删除恰好 1 条日志。新增 tests/test_attachment_security.py **19 项**对抗性安全测试（全部从攻击者视角）：篡改穿越 key 下载→404 而非 500、篡改 key 删除→记录消失而非死锁、任何文件名/篡改组合都不在存储根外写出文件、`%00` 不改变有效扩展名、百分号穿越被中和、百分号编码扩展名矩阵、退化文件名一致拒绝、截断保留扩展名、**只取最后一段扩展名 + 磁盘 key 白名单契约**（防后续以「加强校验」为名改成检查全部扩展名而误拒 `release.tar.gz`）、恶意 Content-Type 永不参与存储决策、响应头注入被阻断、下载 Content-Length 与入库 size 一致、畸形 multipart、并发同名上传不冲突、拥有全权限的局外人 token 仍 404、未认证 401 而非 404（Authentication ≠ Authorization）、审计日志不泄露 storage_path、存储错误信息不外泄、大小限制用真实字节而非声明的 Content-Length。**验证**：`tests/` 全量 **511 passed**（492 + 19，零失败零错误）；Docker 重建镜像后真实容器冒烟 **37 项 PASS**（含真实 HTTP + 真实 PostgreSQL：未认证四端点 401 / 无权限四端点 403 / 完整上传下载删除链路 / 415 四种危险扩展名 / 穿越与 `%00` 中和 / 下载字节一致 + 三个响应头 + RFC 5987 / 删除后 404 同文案 / 审计日志不泄露 / `storage_path` 不进 API 响应），存储卷内只出现白名单扩展名且文件名为随机 hex（证明磁盘 key 完全由服务端生成）；开发库与容器存储卷**零残留**。文档：DECISIONS 新增 009/010/011，TESTING 新增 TASK-043 章节，.gitignore 补 `.pytest_tmp/`。

**环境注意事项（非产品缺陷，勿误判）**：本机 WorkBuddy 沙箱通过注入 `sitecustomize.py` 劫持 `Path.unlink` / `shutil.rmtree` 做「trash 式安全删除」，并有一个**按 turn 累计、阈值 50** 的批量删除守卫。跑全量 pytest 时会因临时目录清理累计超过阈值而抛 `SystemExit: 1`（表现为 `ERROR at setup`），**看起来像大批测试失败，实际是环境拦截**。规避方式：跑测试时设 `CODEBUDDY_SAFE_DELETE_ENABLED=0`（或把 `--basetemp` 指向独立目录并在同一进程内清理），并**不要**在 shell 的第一段命令里用 `shutil.rmtree`（该段未继承环境变量）。

TASK-044 完成 评论/附件测试（Phase 7 收官；**纯测试任务，未改应用代码/迁移**，同 TASK-040 先例）。性质定位：**整合验收**，而非重复 TASK-041（11 项）/042（27 项）/043（19 项）的细粒度断言——那些已充分覆盖单模块行为，缺的是**三个模块放在一起才暴露的跨模块问题**。交付 `tests/test_comment_attachment_flow.py` **16 项**：①**共存**——同一任务上评论与附件交错写入、两条时间线互不污染、跨任务零串联（§16「评论必须属于任务」）、磁盘文件数与该任务目录归属正确；②**审计命名空间不串号**——两类删除写同一张 `operation_logs`，`action`/`resource_type`/`payload` 各归其位（comment id 与 attachment id 可能重号，靠 `(resource_type, resource_id)` 索引分开），并固化契约「创建评论与上传附件**都不写**审计日志」（§16 规则 4 只要求删除写，防后续「顺手加审计」改变 §15 语义边界）；③**§48 越权表现逐字节一致**——局外人对 8 个端点全部 404，「不存在」与「存在但无权」同文案，响应体不含资源标识/内容/`storage`/`traceback`（前端要能用统一逻辑区分 403 与 404，任何一类资源给不同文案都是设计缺陷）；④**认证 ≠ 授权**——无 Token 时 7 个端点全部 **401**；**功能级 403 先于资源级 404**——无全局权限者对真实存在的与不存在的 id **都**得到 403，因此无法用状态码差异枚举 id；⑤**删除权限层级在同一阵容下各自成立**（最易被重构抹平的一条）——评论=作者或团队 OWNER/ADMIN、附件=上传者或团队 OWNER/ADMIN，用同一组用户（owner / 团队 ADMIN / 团队 MEMBER，全局均 admin）同时验证：普通成员删他人两资源都 403 **且文案各自准确**、普通成员删自己两资源都 200、团队 ADMIN 与 OWNER 删他人两资源都 200；互补边界——**member 全局角色**（无 `comment:delete`）删自己的评论仍被功能级 403 先挡；⑥**级联**——删任务时评论与附件**同时**级联清；删用户时其内容随 FK CASCADE 消失但**审计日志保留**（`operation_logs.user_id` 无外键，TASK-039 决策）；⑦**§55.2 事务原子性**——monkeypatch 让 `write_operation_log` 抛错，两类删除均整体回滚（记录仍在、零日志）；附件路径额外固化「先删文件再删记录」的已知取舍（审计失败回滚后物理文件已不在，文件不可回收优于「记录删了文件还在」）；⑧**分页契约一致**——两类列表 skip/limit 语义相同，`limit=0`/`limit=101`/`skip=-1` 均 422；⑨**生命周期独立**——删评论不影响附件，删附件后磁盘与 DB 同步清零无孤儿文件。**测试有效性验证（变异测试）**：临时移除评论删除的资源级授权判定后，`test_delete_authorization_differs_per_resource_same_roster` 立即失败（得到 200 而非 403），证明断言真实承重、非空过；随后还原源码并用 `git hash-object` 核对与 HEAD 的 blob 逐字符一致。**验证**：全量 **527 passed**（511 + 16，零失败零错误）；开发库零残留。因无应用代码变更，**无需重建镜像/容器冒烟**（同 TASK-040/020/025/030 先例）。文档：TESTING.md 新增「评论与附件整合验收（TASK-044）」章节。

TASK-045 完成 Redis 连接与 Key 约定（**Phase 8 首个任务**）。范围界定：开发文档 §21 列出 Redis 五项用途（JWT 黑名单 / API 限流 / Celery Broker / Celery Backend / 后续缓存），§22 要求限流用 ZSET+Lua 滑动窗口。本 TASK **只交付连接层与 Key 约定**这两项地基——**不实现限流**（§22 的 ZSET+Lua 属 TASK-046）、**不接入 JWT 黑名单校验链路**（§19 登出目前靠数据库撤销 Refresh Token 的 jti，Access Token 是无状态的；在 TASK-052+ 通知/黑名单需求到来前不动认证热路径，遵守 §44「不为用缓存而用缓存」与项目规则 §7）。交付物：①**新增 `app/db/redis.py`** —— Redis 连接层**唯一入口**（所有需要 Redis 的代码经此拿客户端，而非各自 `Redis.from_url`）。三项设计取舍：**import 时惰性不连接**（`redis.asyncio` 首次命令才握手，因此无 Redis 环境也能 import 应用——与 `db/session.py` 惯例一致）；**进程内连接池单例**（每次请求新建 client 哪怕同 URL 都会新建连接池，是典型资源泄漏）；**本层不做业务判断**（限流/黑名单语义属调用方）。四个函数：`get_redis_client()`（惰性单例，`Redis.from_url(settings.redis_url, encoding="utf-8", decode_responses=True)`）、`get_redis()`（FastAPI 依赖，yield 共享客户端**不关闭**——与 `get_db` 的每请求一份必须关闭形成刻意对比）、`close_redis()`（幂等释放连接池，lifespan shutdown 调用）、`reset_redis()`（测试用，只清引用不关池）。②**新增 `app/core/redis_keys.py`** —— Key 命名**唯一构造点**，把命名收敛到一处避免「两处独立拼串前缀不一致 / 改了一处漏另一处 → 线上限流突然失效 / 无法安全 SCAN 清理」。约定 `taskflow:<purpose>:<identifier>`：`KEY_PREFIX="taskflow"` 全局命名空间（让 `SCAN taskflow:*` 成为安全运维操作）、purpose 段（`ratelimit`/`jwt`/`celery`）与 §21 用途一一对应、identifier 由调用方给业务标识（IP/user id/jti）。`build_key(purpose, *parts)` 拒绝空 purpose 与含 `:` 的 purpose（会破坏用途段结构）、非字符串 part 自动 `str()`（user id 是 int）；`rate_limit_key(scope, identifier)` → `taskflow:ratelimit:<scope>:<id>`（`RATE_LIMIT_SCOPE_IP`/`_USER`，同一标识在不同 scope 下必须是不同键否则两类流量互相挤兑配额）；`jwt_blacklist_key(jti)` → `taskflow:jwt:blacklist:<jti>`（拒绝空 jti）。③**改造 `app/main.py`** —— 删除原先 `/health` 里临时 `Redis.from_url`（一次探测建一个连接池，是资源浪费，也让「应用到底怎么连 Redis」出现第二份真相），新增 `lifespan` asynccontextmanager（shutdown 时 `close_redis()`），`_check_redis` 改为复用共享客户端且**不关闭它**（它属进程不属本次探测）。④**新增 `tests/test_redis.py` 24 项**，分三类：**Key 约定纯函数 13 项**（形状、`KEY_PREFIX` 字面量显式钉住——前缀是数据兼容性契约，改它等同迁移线上所有键，故断言字面量而非引用常量以免形成「常量改了断言跟着改」的循环、非字符串转换、三类非法输入拒绝、scope 隔离、全键同前缀）；**连接层契约 5 项**（import 不连接——用**全新子进程**且把 `REDIS_URL` 指向**不可达**的 6399 再 import `app.main`，通过即证明懒连接成立（单进程内断言 `_client is None` 不可靠）；池单例；`decode_responses=True` 经 `connection_pool.connection_kwargs` 断言；依赖 yield 共享实例且请求结束不关闭；`reset_redis` 只清引用不关池）；**真实连通性 6 项**（连宿主 Redis 7——宿主 **6389**／容器 6379，与 PostgreSQL 5433/5432 映射惯例一致；`PING`/`decode_responses` 实拿 `str`/Key 构造器产出键被真实 Redis 接受且 `scan_iter` 前缀能命中/TTL 语义/**ZSET 五命令自检**（`ZADD`/`ZCARD`/`ZREMRANGEBYSCORE`/`ZRANGE`/`ZCOUNT`——本 TASK 不实现限流但要确保 §22 所需数据结构在连接层就绪，否则 TASK-046 会卡在环境问题）/`pipeline(transaction=True)`）。连接层的问题（URL 解析、`decode_responses` 实际行为、池生命周期）在假客户端上照不出来，而这恰是本 TASK 的交付物，故必须连真实实例；测试用本次运行唯一 token 作中间段、`try/finally` 逐键删除、**不 FLUSHDB**（会误删他人数据）。**验证**：`tests/test_redis.py` **24 passed**；全量 **551 passed**（527 + 24，零失败零错误，含 6 项真实 Redis 连通性）。应用代码变更仅涉及连接层与 `/health` 复用，**未新增 API 路由**（openapi 仍 24 路径），无需容器冒烟（同 TASK-040/044 纯内部改造先例）。文档：TASKS.md 勾选 TASK-045，TESTING.md 新增「Redis 连接与 Key 约定（TASK-045）」章节，PROGRESS.md 修正滞后的 Completed 清单（补 042/043/044）并推进 Current Phase 至 Phase 8。

TASK-046 完成 ZSET + Lua 滑动窗口限流（**Phase 8 第 2 个任务**）。**范围界定与用户确认**：§22 只规定机制（`IP / User → Redis ZSET → 滑动窗口 → 判请求数 → 超限 429`，Lua 保证五步原子），**未定义任何数值**。按规则 §3「不允许猜测业务规则」已向用户确认两项：①阈值采用写入 `Settings` 的可覆盖默认值（`rate_limit_requests=60` / `rate_limit_window_seconds=60` / `rate_limit_enabled=True`），可经 `.env` 覆盖；②限流做**全局中间件**，按维度取键（已认证按 user id、未认证按 IP）。交付物：①**`app/core/config.py`** 新增三项限流配置（`window_seconds` 同时作为 ZSET 的 TTL，窗口内无新请求时键自动回收）。②**`app/core/exceptions.py`** 新增 `RateLimitExceededError`(429)，支持 `retry_after` 生成 `Retry-After` 头（并对 0/负值取 `max(1, ...)`——否则客户端会立刻重试再次被拒）。③**`app/services/rate_limit.py`** —— Lua 脚本 + `check_rate_limit()` + `enforce_rate_limit()`。脚本内五步严格按 §22：`ZREMRANGEBYSCORE` 删窗口外 → `ZCARD` 统计 → 判超限（超限则**不写入**本次）→ `ZADD` 记录 → `PEXPIRE`。三个关键设计：**时间取自 `redis.call('TIME')`** 而非客户端时钟（多实例部署时客户端时钟漂移会让同一用户落到不同窗口位置，限流形同虚设）；**超限时不写入**（否则持续攻击会让 ZSET 无界增长且窗口永远滚不过去，等于把攻击者永久锁死）；**member 必须唯一**（同一 member 会被 `ZADD` 折叠为更新 score，计数偏低导致击穿）。④**`app/core/middleware.py`** —— `RateLimitMiddleware`（`BaseHTTPMiddleware`）。为什么用中间件而非路由依赖：依赖需逐端点声明、漏一个就是无保护入口，而中间件对所有 `/api/v1` 自动生效；也只拦 `/api/v1`，`/health`、`/docs`、`/` 等运维端点豁免（否则编排器探针会消耗额度）。**身份判定不查库**：中间件在路由层之前运行，`get_db` 尚未建立，在此查库等于给每个请求（含未认证）加一次数据库往返，而限流的初衷恰是保护数据库、自相矛盾；因此只解 JWT 的 `sub`（纯计算无 IO），解不出则退化为 IP 维度——这恰好就是 §22「IP / User」两层维度的自然含义。**Redis 故障 fail-open**（放行 + warning）：限流是保护性措施，不应成为新的单点故障，Redis 一挂就让整个 API 不可用代价远大于短时限流失效；Redis 状态由 `/health` 暴露，属可观测的已知状态。**IP 只取 `request.client.host`，不解析 `X-Forwarded-For`**（可被客户端任意伪造，用它做限流标识等于让攻击者随手换身份绕过）；真实 IP 的信任边界属反代配置，留待 TASK-060。⑤**`app/main.py`** 注册中间件。⑥**`tests/test_rate_limit.py` 22 项**（Lua 语义 9 + 中间件契约 9 + 配置与延迟上界 4）。**全部连真实 Redis**（DECISIONS 016）：限流被击穿的三个常见根因——判断/写入竞态、member 折叠、TTL 缺失——在假客户端上一个都测不出来，而那正是本 TASK 的交付物。核心用例如并发原子性（20 个并发请求放行数**恰好**等于额度）、被拒不写入、滑动恢复（1 秒窗口睡 1.1 秒）、`Retry-After` 由最早成员推算、IP 与 user 两层配额隔离、429 信封符合 §26、fail-open。**测试隔离教训（首轮踩坑）**：中间件按 `request.client.host` 取标识，而 `ASGITransport` 默认全是用例 `127.0.0.1`——前一个用例消耗的额度会泄漏到后一个，导致 `X-RateLimit-Remaining` 得到 7 而非预期的 9 这类假失败；改为每个用例经 `ASGITransport(client=("10.99.x.y", 0))` 分配**独占 IP** 并清理该键。认证类用例还需把 `get_db` 覆盖到**宿主 5433 的真实开发库**（`.env` 的 `localhost:5432` 是另一台 PostgreSQL，不覆盖则在连接阶段抛错、掩盖真正的中间件行为）。**测试有效性验证（变异测试）**：把 Lua 的 `if current >= max_requests then` 改为 `if false and ...` 后 **10 个用例立即失败**（含并发原子性用例），证明断言真实承重；随后还原源码并核验。**验证**：`tests/test_rate_limit.py` **22 passed**；全量 **573 passed**（551 + 22，零失败零错误，204s）。应用代码新增中间件但**未新增 API 路由**（openapi 仍 24 路径），无需容器冒烟。文档：TASKS.md 勾选；TESTING.md 新增 TASK-046 章节；DECISIONS.md 新增 015（阈值默认值）/016（必须连真实 Redis）/017（不查库 + fail-open）/018（Retry-After + 不信任 XFF）/019（延迟上界 + 127.0.0.1）/020（失败路径显式测试）/021（测试套件默认关闭限流）；PROGRESS 推进至 TASK-047。

**收尾补充（同属 TASK-046，纠正上段滞后数字）**：上段写作时的 19 项 / 570 passed 为中间态。补齐「延迟上界」相关测试后，`tests/test_rate_limit.py` 共 **22 项**（新增：`test_redis_client_has_socket_timeouts`、`test_middleware_declares_call_timeout_bound`、`test_unreachable_redis_fails_open_within_bound`），全量 **573 passed**。此三项来自本 TASK 最严重的真实缺陷（见下）。**另发现并修复**：全量回归出现 2 failed（571 passed）——`test_refresh.py` 两个用例断言 401 却得 429，根因是**所有测试文件共用同一来源地址**因而共享同一 IP 限流键，`test_refresh.py` 单文件请求数逾 60/min 触发限流。修复：新增 `tests/conftest.py` 的 autouse fixture **默认关闭限流**，`test_rate_limit.py` 在用例内显式开启；刻意不采用「每个文件独占 IP」——那只是把耦合藏得更深。见 DECISIONS 021。**延迟上界缺陷（最严重）**：`.env` 的 `REDIS_URL` 指向的不是本项目 Redis（compose 映射为宿主 6389，6379 上是另一个要求 AUTH 的实例），客户端不带密码 → `-NOAUTH` → 按默认重试直到宽松默认超时（实测单次 PING 失败 **5.02s**）；限流对每个请求都访问 Redis，成本被乘到全站（单个用例从 <1s 涨到 27s、全量从 5 分钟劣化到 15+ 分钟并看似卡死）。修复三处：`app/db/redis.py` 显式 `socket_timeout`/`socket_connect_timeout=1.0s`、中间件加 `asyncio.timeout(2.0)` 双保险、`.env` 端口与主机名改对——修复后单次限流调用 **0.6ms**。**第二个环境陷阱**：Windows 上 `localhost` 优先解析到 IPv6 `::1`（`getaddrinfo` 实测 `::1` 排在 `127.0.0.1` 前），而容器只发布 IPv4，即便端口改对写 `localhost:6389` 仍会挂超时；`.env` 中 `DATABASE_URL`/`REDIS_URL` **一律改用 `127.0.0.1`**。见 DECISIONS 019。

**遗留约束（记入 TASK-060）**：IP 维度使用 `request.client.host`，在 Nginx 反代后所有请求的来源地址都会变成 Nginx 的地址，届时 IP 维度会退化为「所有匿名用户共享一个配额」。接入反代时必须一并解决（按部署拓扑决定是否信任反代写入的头），见 DECISIONS 018。

TASK-047 完成限流测试（**Phase 8 第 3 个任务，纯测试任务，未改应用代码**——同 TASK-040/044 先例，无需重建镜像/容器冒烟）。**范围界定**：TASK-046 已有 22 项细粒度测试，本 TASK **不重复**，只测「必须借助真实用户 + 真实业务端点 + 真实审计表 + 真实 Redis 键空间才能观察到」的跨模块性质。**方法论（同 TASK-043/044「先探测再断言」）**：先跑一次性探测脚本观测 10 个交叉面——跨端点配额、多用户隔离、换 IP、写副作用、审计、登录暴力破解、键命名空间与 TTL、匿名洪水、404 路径、响应体泄露——**据观测结果**决定断言；脚本用完即删、不入库。探测结果：**十个面全部行为正确，未发现缺陷**（换 IP 绕不过 user 维度；429 零副作用；被限流请求零审计日志；登录暴力破解被挡；限流键全部在 `taskflow:ratelimit:*` 且都有 TTL）。因此本 TASK 的产出是**契约固化**而非修复。交付 `tests/test_rate_limit_integration.py` **15 项**，分四组：**①限流 × 认证**（登录暴力破解 → `401×3+429×2`；限流前后都不泄露账号是否存在——存在/不存在的用户文案逐字一致；匿名洪水被挡在认证之前 → 429 先于 401；同一用户换 4 个独占 IP 仍在第 4 次被限——换 IP 绕不过 user 维度）；**②限流 × 业务副作用**（`POST /tasks` 连打 5 次 → `201×3+429×2` 且库中任务数恰好 3，证明 429 真的挡住执行而非「先做再报错」；被限流的流转请求零审计日志，只有真正成功的那次留下 1 条 `task:transition`；额度跨端点共享；两个用户额度独立；20 并发分属两用户时各自恰好放行 3 次——原子性 × 隔离性叠加）；**③限流 × 运维**（用「跑前/跑后 `SCAN taskflow:*` 取差集」断言新增键全部以 `taskflow:ratelimit:` 开头且有 TTL，取差集是为了不受遗留键干扰且**不 FLUSHDB**；不存在的路径同样吃配额，防随机路径枚举）；**④限流 × 错误契约**（429 体不含 user id / 来源 IP / `taskflow` 前缀 / 堆栈；429 与 401/403/404 **同信封** `{"detail"}`；放行请求业务结果 201 与配额头同时正确；`rate_limit_enabled=False` 后已被限死的身份立刻恢复——误伤时不改代码不重启的逃生舱）。**测试有效性验证（变异测试，4 个变异全部被杀死）**：去掉 429 分支 → 13 failed；身份维度退化为只用 IP → 3 failed（恰好三项 user 隔离用例，说明断言精准）；Lua 去掉 `PEXPIRE` → 1 failed；`member` 改用固定字符串 → 10 failed。还原后源码 blob hash 与 HEAD 逐字符一致。**验证**：`tests/test_rate_limit_integration.py` **15 passed**；全量 **588 passed**（573 + 15）。文档：TASKS.md 勾选 TASK-047；TESTING.md 新增「限流整合验收（TASK-047）」章节；DECISIONS.md 新增 022（配额身份级共享，跨端点）/023（限流不落审计）/024（429 先于认证且不泄露内部标识）/025（TASK-047 定位为整合验收 + 先探测再断言 + 变异结果）；PROGRESS 推进至 TASK-048。

## TASK-048 完成 Celery App/Worker

**范围界定**：纯基础设施——Celery App 接线（Redis Broker/Backend，§21/§23）+ compose `celery_worker` 服务（§29「开发环境至少包含」）。业务任务不在本 TASK：通知 = TASK-049，日志归档/附件清理 = TASK-050，幂等/重试测试 = TASK-051。未新增 API 路由，无迁移变更。

**实现**
- `app/tasks/celery_app.py`（新建）：`create_celery_app()` 按配置构造 Celery 实例；`app.ping` 冒烟任务（验证 Broker→Worker→Backend 全链路，无业务副作用）。import 零网络连接（Celery 连接惰性），API 进程引用零成本。
- `app/core/config.py`：`celery_broker_url` / `celery_result_backend`（留空回落 `REDIS_URL`）、`celery_task_soft_time_limit=300` / `celery_task_time_limit=600`（规则 §8 timeout）、`celery_result_expires=3600`。
- 可靠性参数（规则 §8 的 App 层落点）：`task_acks_late=True` + `task_reject_on_worker_lost=True` + `worker_prefetch_multiplier=1` → **at-least-once 投递**（Worker 崩溃消息不丢、会重投；幂等责任在业务任务侧，TASK-049/050/051 落实）；`accept_content=["json"]` 禁 pickle（pickle 反序列化 = 任意代码执行，任务消息被注入即 RCE）；`task_track_started=True`。
- `broker/backend` 均 `global_keyprefix="taskflow:"`：Celery 键纳入 TASK-045 键约定。
- `docker-compose.yml`：新增 `celery_worker`（同镜像覆盖 command，`celery inspect ping` 健康检查，依赖 postgres/redis healthy，挂附件卷备 TASK-050）。
- `tests/test_celery_app.py`：11 项（派生规则 2 / JSON-only 1 / 可靠性 4 / 键前缀 1 / eager 执行 2 / import 安全 1），全部不依赖真实 Redis；`get_settings` lru_cache 用 autouse fixture 前后 `cache_clear`。

**compose 部署冒烟（真实链路，四服务全绿）**：`up -d --build` 后 app healthy、worker `1 node online`；app 容器内 `ping.delay().get()` → **`pong, SUCCESS`**（完整经过 Redis Broker → Worker → Redis Backend）；`redis-cli --scan` 实测所有 Celery 键（含 `_kombu.binding.*`、`celery-task-meta-*`）都在 `taskflow:` 前缀之下。

**验证**：`tests/test_celery_app.py` **11 passed**（1.10s）；全量 **599 passed**（588 + 11）。文档：TASKS.md 勾选；TESTING.md 新增「Celery App / Worker（TASK-048）」章节；DECISIONS.md 新增 026（Broker/Backend 回落 REDIS_URL）/027（at-least-once + JSON-only，§8 落点）/028（Celery 键挂 taskflow: 前缀）；PROGRESS 推进至 TASK-049。

## TASK-049 完成 通知异步任务

**范围界定**：Worker 端通知落库——`app/tasks/notification_tasks.py` 的 `create_notification` 任务写 `notifications` 表（§24）。业务派发点（任务分配/状态变更时从 TaskService 提交）属 Phase 13 的 TASK-053，不在本 TASK。**范围决策（用户确认）**：notifications 表建模（Model + 迁移）提前于 TASK-052 并入本 TASK——§24 的可重试/不重复语义依赖真实持久化，空壳任务无法实现与测试（沿用 TASK-058 提前完成先例，DECISIONS 029）。

**实现**
- `app/models/notification.py` + 迁移 `b7d2e9a4c6f8`（§18 原文七字段；user_id FK CASCADE；`(user_id, created_at)` 复合索引；type 不加 CHECK、content 可空，理由记 DECISIONS 029）。
- `app/tasks/notification_tasks.py`：`app.create_notification`。§24 三条要求落地：①主业务失败不产生错误通知 = 派发方须在事务提交后 `delay()`（TASK-053 接线）+ 任务参数防御（`ValueError` 不重试零副作用）；②失败可重试 = `autoretry_for=(SQLAlchemyError, OSError)` 指数退避 max 5 + 抖动（§8 retry）；③重试不大量重复 = 调用方生成幂等键，任务「先插库、后 `SETNX taskflow:notify_done:<key>`（TTL 7 天）」——DB 是事实源，反向顺序会丢通知；Redis 故障 fail-open（DECISIONS 030）。
- `app/db/redis.py`：补充同步入口 `get_sync_redis_client()`——Celery prefork 同步上下文用不了 async 客户端（命令返回协程；首轮测试 8 failed 全因 `bool(coroutine)` 恒真、全部被误判"已完成"跳过，暴露了这一点）；同一 URL 与 socket 超时纪律。
- 任务内 DB 写入用**每次调用独立事件循环 + 短命 engine**：asyncpg 连接池绑定事件循环，跨 loop 复用必报错，不能共享 API 进程的 engine 单例（DECISIONS 030）。
- `app/tasks/celery_app.py`：新增 `TASK_MODULES` include 机制，Worker 启动自动注册任务模块。
- `tests/test_notification_task.py`：15 项（注册接线 2 / 执行链路 3 / 不大量重复 4 / 参数防御 2 / 可重试声明 2 / FK 级联 1 / 同步客户端超时 1）。全部同步用例——任务体 `asyncio.run` 不能嵌套在 async 用例的事件循环里；验证用 asyncpg 直连，与任务写入路径相互独立。

**compose 部署冒烟（真实链路）**：重建镜像后 `celery inspect registered` 列出 `app.create_notification`；app 容器内真实派发（含幂等键）→ Worker 落库 `{'status': 'created', 'notification_id': 32}`，字段全对、`is_read=false`、完成标记 TTL≈7 天；随后精确删除该通知与标记，表归零。

**验证**：`tests/test_notification_task.py` + `test_celery_app.py` **26 passed**；全量 **614 passed**（599 + 15）。文档：TASKS.md 勾选 TASK-049 并注明 TASK-052 建模部分已提前完成；TESTING.md 新增「通知异步任务（TASK-049）」章节；DECISIONS.md 新增 029（表提前建模，用户确认）/030（幂等先插库后标记 + 短命 engine + 同步 Redis 客户端）；PROGRESS 推进至 TASK-050。**异常记录**：TASK-048 提交中 Current Task 行的更新曾静默丢失（其它修改都在），本轮随 TASK-049 一并修正并在提交前逐行核验。

## TASK-050 完成 日志归档/附件清理任务

**范围**：§23 两类后台维护任务——`archive_operation_logs`（超期日志迁入 `operation_logs_archive`，DECISIONS 031）/ `cleanup_expired_attachments`（回收 storage 卷孤儿物理文件，DECISIONS 032）。两项「归档/过期」动作的业务规则 §23 未定义，经用户确认后落地。新增 `app/models/operation_log_archive.py` + 迁移 `524ab172e659`、两个 Celery 任务、3 项 Settings（保留期 90 天 / 孤儿年龄窗口 3600s / 批大小 1000）、`tests/test_maintenance_tasks.py` 13 项。全量 **627 passed**（614 + 13）。提交 `b850e30`（已推送）。详见 DECISIONS 031/032 与 TESTING「维护异步任务（TASK-050）」章节。

## TASK-051 完成 幂等、重试与任务测试（Phase 8 收尾，纯测试任务）

**范围**：TASK-048/049/050 已覆盖**声明层**（autoretry_for 元组、幂等键跳过、参数防御 ValueError）与**直接调用层**；本任务补**行为层**——这些声明在真实故障下是否真的生效（同 TASK-040/044/047「整合验收」定位，纯测试、不改应用代码）。新增 `tests/test_task_resilience.py` **8 项**，分六组：

- **重试行为（真实）**：瞬态 `SQLAlchemyError` 后 Celery 真的重跑任务体并最终成功，恰好 1 行（幂等去重与重试协同）；永久故障超 `max_retries` 后真的抛错、`_insert_notification` 被调用 `1+max` 次、零通知行（§8 failure / §24 要求 1「主业务失败不产生错误通知」）。
- **失败短路**：非法参数在触达 DB **之前**被 `_validate` 拦截，插入函数 0 次调用、0 重试、0 行（`ValueError` 不在 autoretry_for，重试永不成功）。
- **维护任务经 Celery 任务机执行**：`archive` / `cleanup` 经 `delay()` → 任务机 → 执行端到端（此前只测了直接调用）。
- **清理重投递幂等**：孤儿删后再跑一遍 → 0 删除、0 错误（删文件幂等 + 孤儿判定只读 DB）。
- **整体 at-least-once 安全（跨模块整合）**：通知 / 归档 / 清理**各跑两遍**，累计副作用 = 单跑一遍，跨模块互不串扰（类比 TASK-044 整合验收）。
- **超时不被绕过**：三个业务任务都不覆盖 App 级 `soft/hard_time_limit`，§8 的 300/600s 超时对其生效（钉住不被 `task(...)` 装饰器静默旁路）。

**验证**：`tests/test_task_resilience.py` **8 passed**（3.45s）；全量 **635 passed**（627 + 8，4m06s，零失败零错误）。验证用前缀（`rsl_<RUN_TOKEN>_` / 幂等键前缀）teardown 精确清理，开发库零残留。**不重复既有测试**：未重写 autoretry 声明 / 幂等键跳过 / Redis fail-open 等已在 TASK-049/050 覆盖的细粒度断言，只补行为层与跨模块整合。文档：TASKS.md 勾选 TASK-051；TESTING.md 新增「Celery 任务韧性（TASK-051）」章节；DECISIONS.md 新增 033；PROGRESS 推进至 TASK-052（Phase 9）。

## TASK-052 完成 Notification Model（检查项，补 Model 测试）

**范围**：DECISIONS 029 把建模（Notification Model + 迁移 `b7d2e9a4c6f8`）提前并入 TASK-049，并明确「TASK-052 届时为检查项」。本 TASK 不产生新应用代码——建模已在 TASK-049 落库（表 + 索引 + FK CASCADE 已 `upgrade head` 实证）；TASK-049 提前建模时只写了「通知任务测试」，缺「通知 Model 本身」专项测试，本 TASK 补 `tests/test_notification_model.py` **16 项**固化 §18 七字段完整性（对齐 TASK-021/026/031 的 Model TASK 惯例）。

**实现（仅测试）**
- `tests/test_notification_model.py`（新建）：离线 10 项（表注册 / tablename / 列集严格 = §18 七字段 / id BigInteger PK / user_id FK→users CASCADE+单列索引 / type·title 非空 String(50/255) / content 可空 Text / is_read 非空默认 false / created_at tz-aware 默认 now / `(user_id, created_at)` 复合索引 / repr）+ DB 集成 6 项（七字段 roundtrip / content 可空 / is_read·created_at 有 DB 默认 / 删用户 CASCADE 清通知 / 按接收人降序查主访问路径），真实 5433；写入用户带 `ntf_<RUN_TOKEN>_` 前缀、autouse teardown 删前缀用户（通知随 FK 级联清），开发库零残留。

**验证**：`tests/test_notification_model.py` **16 passed**（2.00s）；全量 **651 passed**（635 + 16，5m33s，零失败零错误）。文档：TASKS.md 勾选 TASK-052；TESTING.md 新增「Notification Model（TASK-052）」章节；DECISIONS.md 新增 034；PROGRESS 推进至 TASK-053（Phase 9）。

## TASK-053 完成 通知 Service/API + 派发点接线

**范围**：Phase 9 通知第 2 个任务。交付两件事：①通知查询 / 标记已读端点（`GET /api/v1/notifications`、`PATCH /api/v1/notifications/{id}/read`，§18 / §25.8）；②业务派发点接线——`assign_task`（任务分配）与 `transition_task`（任务状态变更）事务**提交后**调用 `create_notification.delay()`（TASK-049 已实现的 Celery 任务）。`read-all` 标记全部已读端点属 TASK-054，不在本 TASK 范围（规则 §13 只执行当前 TASK）。

**实现**
- `app/schemas/notification.py`（新建）：`NotificationRead` 出站契约，对齐 §18 七字段（`ConfigDict(from_attributes=True)`）。
- `app/crud/notification.py`（新建）：主访问路径 `(user_id, created_at DESC)`，复用模型复合索引；`list_by_user` / `get_for_user`（归属校验、非接收人返回 None）/ `mark_read`（flush-only、已读幂等）；CRUD 层只 `flush`，事务边界在 Service（规则 §4）。
- `app/services/notification.py`（新建）：`list_user_notifications` / `mark_notification_read`（非接收人 / 不存在 → `ResourceNotFoundError("Notification not found")`，Service 提交）；**仅认证不加功能级权限**，理由记 DECISIONS 035。
- `app/api/v1/notifications.py`（新建）：Router 只做 HTTP ⇄ Service 翻译；端点 `list_my_notifications` / `mark_notification_read`（别名导入 Service 函数 `svc_mark_notification_read`，避免与端点同名导致自递归）。
- `app/api/v1/__init__.py`：聚合导入 `notifications` 并 `include_router(notifications.router)`。
- `app/services/task.py`：补 `from app.tasks.notification_tasks import create_notification, new_idempotency_key`；新增私有包装 `_dispatch_notification`（try/except best-effort，broker 故障 `warning` 吞掉、不回滚主业务，§24 对称面——主业务已成功，通知丢失也不该回滚）；`assign_task` 提交后 `if payload.user_id != user.id` 派发 `task_assigned`；`transition_task` 提交后取负责人列表、排除 `user.id` 逐人派发 `task_status_changed`。
- `tests/conftest.py`：新增 autouse 夹具 `_isolate_notification_dispatch`（把 `_dispatch_notification` 换 no-op，测试不真连 broker）+ `notification_dispatch` 间谍夹具（局部覆盖验证接线；请求时覆盖上面 no-op，不影响 `test_notification_task.py` 直接调 `.delay` 验证 §24 真实执行）。
- `tests/test_notification_api.py`（新建）：11 项（见 TESTING 章节）。

**验证**：`tests/test_notification_api.py` **11 passed**；全量 **662 passed**（651 + 11，零失败零错误）；开发库零残留。文档：TASKS.md 勾选 TASK-053；TESTING.md 新增「通知 Service/API（TASK-053）」章节；DECISIONS.md 新增 035；PROGRESS 推进至 TASK-054（Phase 9）。

## TASK-054 完成 通知 read-all / 标记全部已读

**范围**：Phase 9 通知第 3 个任务。交付 `PATCH /api/v1/notifications/read-all`（§25.8 第三端点）——把当前登录用户**全部未读**通知标记为已读。资源级隔离沿用 TASK-053/DECISIONS 035（仅认证 `CurrentUser`、只动自己的收件箱），无新权限项、无迁移。**响应体决策（用户确认，DECISIONS 036）**：返回 `{"data": {"marked": N}}`，N = 本次真正从已读翻转为已读的条数（已读的不计入）——前端一次调用即可同步未读角标，重复调用幂等返回 0。

**实现**
- `app/crud/notification.py`：新增 `mark_all_read`（flush-only）——单条 `UPDATE ... WHERE user_id = :uid AND is_read = false`，只命中未读行（`rowcount` 即真翻转数），SQL 层 WHERE 带归属条件限定自己的收件箱。
- `app/services/notification.py`：新增 `mark_all_notifications_read`（Service 提交）；空收件箱 → 200 `marked=0`（「没有未读」是合法的 0，不是 404）。
- `app/schemas/notification.py`：新增 `NotificationMarkAllRead`（`marked: int`）出站契约。
- `app/api/v1/notifications.py`：挂载 `PATCH /read-all`，**刻意声明在参数化路由 `/{notification_id}/read` 之前**消除路径解析歧义（两段路径本无实际匹配冲突，防御性排序）。
- `tests/test_notification_api.py` 增补 3 项（A2 组）+ 既有 401 用例扩到 read-all：只标记未读且幂等（3 未读 + 1 已读 → `marked==3`、GET 全已读、重复调 `marked==0`）、资源级隔离（a 标记只计自己条数，b 的通知保持未读）、空收件箱 `marked==0`。

**验证**：`tests/test_notification_api.py` **14 passed**（11 + 3）；全量 **665 passed**（662 + 3，3m01s，零失败零错误）；开发库零残留（`ntfapi_` 前缀用户 0、notifications 表 0 行）。因无既有端点行为变更（纯新增端点），未重建镜像（消费时随下一镜像重建冒烟）。文档：TASKS.md 勾选 TASK-054；TESTING.md 新增「通知 read-all 标记全部已读（TASK-054）」章节；API_CONTRACT.md Notification 章节补齐三端点契约；DECISIONS.md 新增 036；PROGRESS 推进至 TASK-055（Phase 9 收尾）。

## TASK-055 完成 通知端到端测试（Phase 9 收官，纯测试任务）

**范围与定位**：Phase 9 通知第 4 个任务，**纯测试任务、未改应用代码/迁移**（同 TASK-040/044/047/051 先例，无需重建镜像）。TASK-053 用 `conftest` 的 autouse `_isolate_notification_dispatch` 把 `_dispatch_notification` 换 no-op + `notification_dispatch` 间谍夹具**只验证接线**——通知行从不被真实写出。本 TASK 做 **端到端整合验收**：恢复真实派发，验证「API 动作 → 真实通知入库 → 收件箱可见 → 可标记已读 / 全部已读」整条链路。新增 `tests/test_notification_e2e.py` **7 项**。

**关键实现约束（本 TASK 唯一技术难点）**：通知任务体（`app.tasks.notification_tasks.create_notification`）内用 `asyncio.run` 写库；若在本测试的 async event loop 调用栈里直接 `.delay()`（Celery eager），会触发 `RuntimeError: asyncio.run() cannot be called from a running event loop`（API 端点本身是协程）。生产里 Worker 是**独立进程 / 独立 loop**，本文件用**守护线程**等价模拟——任务在独立线程内跑自己的 loop，不干扰测试 loop，且仍执行真实的入库 + Redis 幂等标记逻辑（与 TASK-049 直接调任务体验证 §24 同思路）；线程 `join()` 保证通知落库后再断言（确定性）。任务注册 / 接线已由 TASK-049/051/053 覆盖，本文件只关心「通知真的进收件箱」。前置核实：`.env` 的 `DATABASE_URL` 指向 `127.0.0.1:5433`，与测试库（`TEST_DATABASE_URL`）同库，eager 派发写入的行对 `GET /notifications` 可见（否则端到端断言根本不可能成立）。

**交付 7 项**（分三组）：
- **动作 → 入库 → 可见（3 项）**：任务分配 → 被分派者收件箱出现 1 条 `task_assigned`（`user_id` 对、未读、title 含任务摘要）；**自领不产生通知**（与 TASK-053 决策一致，收件箱为空）；任务状态变更 → 全部负责人收到 `task_status_changed`、**排除触发者本人**（触发者收件箱为空）。
- **真实写入可读 / 全部已读（2 项）**：真实通知经 `PATCH /notifications/{id}/read` 标记已读（GET 复查 `is_read=true`）；3 条真实通知下 `PATCH /read-all` → `marked==3` 且收件箱全已读（TASK-054 端点在真实数据上闭环）。
- **内容 + 资源级隔离（2 项）**：通知 `title`/`content` 由派发方按 §18 场景填充（精确断言 `你被分配到任务「<title>」` / `{username} 将你分配到任务 #{id}`，钉住派发文案契约）；局外人收件箱为空、持有者可见自己的——通知不泄露给非接收人。

**验证**：`tests/test_notification_e2e.py` **7 passed**（5.06s）；全量 **672 passed**（665 + 7，3m13s，零失败零错误）；开发库零残留（`ntfe2e` 前缀 users/tasks/teams/projects 及关联 notifications 全 0）。文档：TASKS.md 勾选 TASK-055（Phase 9 收官）；TESTING.md 新增「通知端到端测试（TASK-055）」章节；PROGRESS 推进至 TASK-056（Phase 10 工程化）。

## TASK-056 完成 结构化日志（Phase 10 首个任务）

**范围**：§33 要求「Python logging + 生产环境结构化日志 + 至少记录 timestamp/level/logger/message/request_id/user_id/path/method/status_code/duration + 禁止输出 password/token」。三项文档未定义的实现点经**用户确认**（DECISIONS 037）：①格式按环境推导（production→JSON、其余→文本，`LOG_FORMAT` 可覆盖）；②加**出口自动脱敏过滤器**；③访问日志**记录全部路径**（含 `/health`/`/docs`/`/`）。§34 的 `request_id` 生成/透传属 TASK-057——本 TASK 只建好字段通道（无值输出 `null`，schema 稳定）。

**实现**
- `app/core/logging_config.py`（新建）：`request_id_var` / `user_id_var` 两个 ContextVar（让请求内**任何**日志都带上这两个字段，由中间件设置、结束还原）；`JsonFormatter`（§33 固定字段 + `extra` 透传 + `exception` 堆栈 + `default=str` 保证不丢日志）/ `TextFormatter`（开发环境人读，仍追加上下文）；`SensitiveDataFilter`（**只脱敏值、保留键名**；覆盖 extra 结构化字段含嵌套 dict、message 里 `key=value`、裸 JWT 字面量）；`resolve_level`（非法级别回落 INFO 不抛错）/ `resolve_format`（auto 按 APP_ENV 推导）；幂等的 `configure_logging()`（只移除自己上次装的 handler、不触碰他人 handler；把 uvicorn 三个 logger 收编到 root；`uvicorn.access` 压到 WARNING）。
- `app/core/middleware.py`：新增 `RequestLoggingMiddleware`（访问日志一条含 method/path/status_code/duration；user_id 解 JWT `sub` **不查库**——中间件在路由层之前没有 Session，权威判定仍归端点；写进 ContextVar 供请求内下游日志复用；**异常也记 500**）。
- `app/core/config.py`：`log_level` / `log_format` / `log_requests` 三项（§33 未给数值，取可覆盖默认）。
- `app/main.py`：`configure_logging(settings)` 先于应用创建；访问日志中间件注册在限流**之后**（更外层 → duration 含限流开销，是客户端实际等待时间）。
- `tests/conftest.py`：autouse 关闭访问日志（`log_requests=False`，与 `rate_limit_enabled` 同套路），避免 600+ 用例刷屏。
- `.env.example`：补 `LOG_LEVEL` / `LOG_FORMAT` / `LOG_REQUESTS`。
- `tests/test_logging.py`（新建）：**41 项**（JSON formatter 7 / 文本 2 / 脱敏 13 / 配置与中间件 19，全离线）。

**本 TASK 实测发现并修复的 3 个真实缺陷**（前两个由新测试捕获、第三个由真实容器冒烟捕获；均非推测）：
1. **脱敏过滤器吃掉 `%s` 占位符 → 整条日志静默丢失**：初版对 `record.msg` 一律脱敏，`logger.info("token=%s", token)` 的模板被改成 `"token=***"`，`getMessage()` 抛 `TypeError`，logging 吞掉异常使日志**消失**。修复：有 `args` 时**只脱敏 args**、保留模板。
2. **访问日志 `user_id` 恒为 `null`**：初版在 `finally` 里先还原 ContextVar 再写日志，导致每个成功请求都丢掉 §33 要求携带的 user_id。修复：改用 `try/except/else/finally`，日志写在 `else`、还原交给 `finally`。
3. **每个请求两条访问日志**：收编 uvicorn logger 后 `uvicorn.access` 那行也走了我们的 formatter，与中间件重复（且不含 duration/user_id）。修复：`uvicorn.access` 压到 WARNING。**此缺陷 pytest 测不出**（探针应用没有 uvicorn 层），只能靠真实容器冒烟发现——再次印证「部署冒烟不可省」。
- 附带效应（已知可接受）：`db/session.py` 的 `echo=settings.debug` 此前因 root 无 handler 而不可见，现在**开发环境 SQL 语句日志会真正输出**（debug 的既有意图得以生效）；生产 `DEBUG=false` 不输出。

**验证**：`tests/test_logging.py` **41 passed**（0.36s，全离线）；全量 **713 passed**（672 + 41，3m17s，零失败零错误）。**真实容器冒烟（重建镜像后，四服务 healthy）**：`/health` 与 `/` 均 200；`docker logs` 显示每个请求**恰好一条**结构化访问日志（`INFO app.core.middleware :: request completed | method=GET path=/health status_code=200 duration=3.498`），`uvicorn.access` 重复行已消失；容器内以 `APP_ENV=production` 独立进程验证 JSON 输出——字段与 §33 完全一致（`timestamp/level/logger/message/request_id/user_id`），且脱敏生效（`"password": "***"`、`"token=***"`）。测试环境要点：pytest 默认把 root logger 设为 WARNING，断言 INFO 日志的用例必须显式 `setLevel(INFO)`（本 TASK 修正两处会「假通过」的用例）。文档：TASKS.md 勾选 TASK-056；TESTING.md 新增「结构化日志（TASK-056）」章节；DECISIONS.md 新增 037（含三个缺陷）；`.env.example` 同步；PROGRESS 推进至 TASK-057。

## TASK-057 完成 Request ID（Phase 10 第二个任务）

**范围**：§34 要求「每个 HTTP 请求生成 `request_id`；可由客户端传入或服务端生成；日志中必须带它」。TASK-056 已把 `request_id_var` 与 formatter 字段通道建好（无值输出 `null`），本 TASK 补上**生成 / 客户端透传 / 响应回传**。三处文档未定义契约经**用户确认**（DECISIONS 038）：①头名统一 `X-Request-ID`（单一头）；②客户端值经白名单校验后才接受，否则丢弃并重新生成；③`request_id` **不进入**错误响应体（§26 信封保持 `{"detail": ...}`）。另有一项工程决策：**独立中间件且注册在最外层**——生成与 `LOG_REQUESTS` 开关解耦（否则 §34 的硬要求会被一个日志开关悄悄破坏），且只有在最外层，本次请求的**所有**日志（含限流 warning 与访问日志本身）才都带 id。

**实现**
- `app/core/middleware.py`：新增 `REQUEST_ID_HEADER`（`"X-Request-ID"`）、`resolve_request_id()`（客户端值 strip 后白名单 `^[A-Za-z0-9._-]{1,64}$` 校验，非法则 `uuid4().hex`）、`RequestIdMiddleware`（设置 ContextVar → 调用下游 → `finally` 还原 → 用**局部变量**写响应头；模块文档补齐三个中间件的嵌套顺序说明）。
- `app/main.py`：**最后**注册 `RequestIdMiddleware` → 位于最外层；运行时嵌套为 `RequestId → RequestLogging → RateLimit → 路由`。
- `app/core/logging_config.py`：docstring 更新（`request_id_var` 现由 `RequestIdMiddleware` 填充）。
- `tests/test_logging.py`：访问日志用例的注释更新为「该探针应用未注册 `RequestIdMiddleware`，故 `request_id` 为 null」——恰好固化「ContextVar 未设置时输出 null」的 schema 稳定性。
- `tests/test_request_id.py`（新建）：**34 项**（纯函数 13 / 中间件契约 8 / 协作 4 / 真实应用 4，全离线）。

**安全要点（白名单的价值）**：原样信任客户端值会同时打开三个口子——**日志注入**（值含 `\n` 可伪造整条日志行、污染审计）、**日志膨胀**（几十 KB 撑爆每行日志）、**身份伪造**（id 是可观测性信任锚）。64 字符 + 字母数字与 `._-` 足以容纳 UUID/ulid/ksuid/hex/traceparent 全部主流形态。

**已知边界（有意接受，已写成测试固化）**：未处理异常由 Starlette 的 `ServerErrorMiddleware` 渲染 500，而它在本中间件**之外**，故该响应**没有** `X-Request-ID` 头；但该请求的日志（访问日志在向上抛之前已记 `status_code=500`）仍带 request_id——§34 的硬要求（日志里必须带）不破。

**测试写法发现（非实现缺陷）**：HTTP 头值在协议层是 latin-1 字节、Starlette 按 latin-1 解码，故客户端传非 ASCII（`中文id`）在中间件眼里是 latin-1 乱码。初版测试辅助函数用 latin-1 编码值，遇非 ASCII 直接抛 `UnicodeEncodeError`——等于**永远测不到这条路径**。改为按 UTF-8 编码成原始字节（忠实模拟线上字节），白名单正好拦住这种乱码形态。

**验证**：`tests/test_request_id.py` **34 passed**（0.47s，全离线）；全量 **747 passed**（713 + 34，零失败零错误）；纯工程增量、无端点行为变更。

## TASK-059 完成 Production Compose（Phase 10 第三个任务）

**范围界定**：按 §4 文件清单落地 `docker-compose.prod.yml`。nginx 服务 / `nginx/nginx.conf` / Gunicorn 启动命令属 TASK-060，**刻意不在本 TASK 引入**（规则 §13：只做当前 TASK）。无应用代码变更、无迁移、无新端点。

**四项用户确认的决策（DECISIONS 039）**：①**独立完整文件**（非 `-f base -f prod` 覆盖式）——compose 对 `ports` 是拼接而非覆盖，无法用覆盖文件摘掉开发版发布的 5433/6389；②**端口内外分离**——postgres/redis 零宿主端口，app 只绑 `127.0.0.1:${APP_PORT:-8000}`；③必需密钥 `${JWT_SECRET_KEY:?}` / `${POSTGRES_PASSWORD:?}` **缺失即拒绝启动**；④nginx/Gunicorn 留 TASK-060。

**配套生产化决策**：独立 compose 项目名 `taskflow-prod`（卷/网络/容器名带前缀，防在开发机上启动生产栈时连到开发库）；不设 `container_name`（与开发栈同名容器冲突且阻碍扩容）；`DEBUG=false`（关闭 SQLAlchemy echo 与 FastAPI debug）；容器日志轮转 10MB×3；Redis `--appendonly yes`（Celery Broker 队列需跨重启存活）；`restart: always` + worker `stop_grace_period: 30s`；**禁止 `env_file: .env`**（宿主 `.env` 的 DATABASE_URL/REDIS_URL 指向 127.0.0.1:5433/6389，注入容器会让容器连不上任何东西）。

**本 TASK 暴露的既有缺口（已修）**：①本地 `.env` 缺 `POSTGRES_USER/PASSWORD/DB`——它一直供宿主运行使用，compose 靠默认值兜底，此前从未暴露，直到 `${VAR:?}` 才把它变成硬错误；②`.env.example` 补 `DEBUG` 与生产必填说明；③`requirements.txt` 补 `PyYAML`（compose 契约测试要解析 YAML，否则 TASK-061 的 CI 会缺包失败）。

- `docker-compose.prod.yml`（新建）：四服务生产定义，共用 `x-app-environment` 锚点（app 与 worker 环境变量完全一致）+ `x-logging` 锚点。
- `tests/test_prod_compose.py`（新建）：**26 项**（文件与项目隔离 6 / 端口暴露面 4 / 生产环境变量 8 / 持久化与存储 3 / 运行保障 5），全离线不启动 Docker。
- `.env`、`.env.example`、`requirements.txt`、`docs/DEPLOYMENT.md`（生产栈操作手册：迁移/启动/换端口/拆除 + 约束清单）。

**真实容器冒烟（Docker，非 pytest）**：`up -d --build` 后四服务 healthy；`docker port` 实证 app 仅 `127.0.0.1:18080->8000`、postgres/redis 无任何宿主端口；卷为 `taskflow-prod_*`（开发栈同时保持 healthy）；`run --rm app alembic upgrade head` → `/health` 返回 `env=production` / `database=up` / `redis=up`；注册 201 → 登录 200 → `/users/me` 200；容器日志为 §33 JSON 十字段（含 `request_id`、`user_id`，无 SQL echo）；原始 socket 连 `192.168.1.84:18080` 超时（反证仅回环可达）；`redis-cli config get appendonly` → `yes`；**失败路径**：缺 `POSTGRES_PASSWORD` / `JWT_SECRET_KEY` 时 compose 报 `required variable ... is missing a value` 且退出码 1；`down -v` 后容器与卷零残留。

**验证**：`tests/test_prod_compose.py` **26 passed**（0.10s）；全量 **773 passed**（747 + 26，3m29s，零失败零错误）；开发库零残留。

**问题与解决**：①三处首轮失败均为**测试写法缺陷**而非实现缺陷——镜像 tag 比较把官方镜像（postgres:16/redis:7）也算进去了（改为只比较带 `build:` 的服务）、`LOG_FORMAT` 在 compose 文件中是未插值的 `${LOG_FORMAT:-auto}`（改为断言默认值文本）、`change-me` 命中的是自己写的注释（改为只在非注释行上检查）。②端口 8080 被本机其他程序占用导致 app 起不来（`Bind for ... port is already allocated`），换 18080 后正常——这正好验证了 `${APP_PORT}` 覆盖设计的价值。③`urllib` 受环境代理影响，改用**原始 socket** 才得到可信的「仅回环可达」反证。

## TASK-060 完成 Nginx/Gunicorn/Uvicorn（Phase 10 第四个任务）

**范围**：§31 规定生产链路 `Client → Nginx → Gunicorn → Uvicorn Worker → FastAPI`，并列出 Nginx 五项职责（反向代理 / 请求体大小限制 / 基础超时 / **静态附件访问** / 基础安全 Header）与 §4 要求的 `nginx/nginx.conf`。四项文档未定义的契约经**用户确认**（DECISIONS 040）：①Nginx 是容器服务且是**唯一对外入口**（app 连回环端口一并删除）；②§31 的「静态附件访问」实现为**不直出**；③仅 HTTP 80（TLS 由上游终止，证书不进仓库）；④固定 compose 子网 `172.28.0.0/24`。另新增 DECISIONS 041（Gunicorn 进程模型）与 042（真实客户端 IP 的信任模型）。

**实现**
- `nginx/nginx.conf`（**新建**，§4 文件清单）：反代（`upstream app_backend` + keepalive 32）、`client_max_body_size 12m`（**粗粒度外圈**，严格大于应用 `MAX_UPLOAD_SIZE`，避免超限上传拿到 HTML 错误页而非 §26 JSON 信封）、六个超时、三个安全 Header 带 `always`、`server_tokens off`、`Host $host`（非 `$http_host`）、`X-Request-ID $http_x_request_id` 透传、日志进 `/dev/stdout`（格式含 `rid=$http_x_request_id`，两层日志可凭同一 id 串联）、本地健康探针 `location = /nginx-health`；**`X-Forwarded-For $remote_addr` 覆盖写入**（不是 `$proxy_add_x_forwarded_for`）。
- `app/core/client_ip.py`（**新建**）：`parse_trusted_proxies`（逗号分隔 IP/CIDR，单 IP 自动补掩码，非法项跳过并告警，`lru_cache`）+ `resolve_client_ip`（**三条同时成立**才采信该头：开关开启、对端在信任网段内、该头恰为一个合法 IP；否则回落到对端地址）。含 IPv4-mapped IPv6 归一。
- `app/core/config.py`：`trust_proxy_headers=False`、`trusted_proxy_ips=""`（**默认关闭**，未配置反代的环境行为与 TASK-046 完全一致）。
- `app/core/middleware.py`：`_client_ip` 改为调用上述判定（限流身份与日志共用一处逻辑）；访问日志**新增 `client_ip` 字段**（反代后只记对端地址的话日志全是 nginx 的地址，没有区分度）。
- `docker-compose.prod.yml`：新增 `nginx` 服务（`nginx:1.27-alpine`、只读挂载配置、`${NGINX_HTTP_PORT:-80}:80`、等 app healthy、探 `/nginx-health`）；**删除 app 的宿主端口**；app 启动命令切 `gunicorn ... --worker-class=uvicorn.workers.UvicornWorker --workers=${WEB_CONCURRENCY:-2} --timeout=60 --graceful-timeout=30`（**不开** `--access-logfile`，避免与应用 §33 访问日志重复）；注入 `TRUST_PROXY_HEADERS=true` / `TRUSTED_PROXY_IPS=172.28.0.0/24` / `FORWARDED_ALLOW_IPS=""`（关掉 ASGI 侧改写，让应用成为唯一判定点）；顶层声明固定子网。
- `.env.example`：补四个相关配置项与说明。`requirements.txt` 已含 `gunicorn`（此前已备）。

**验证**
- `tests/test_client_ip.py` **26 passed**（全离线）；`tests/test_nginx_config.py` **32 passed**（全离线）；`tests/test_prod_compose.py` 按新暴露面更新后 **26 passed**；`tests/test_logging.py` **42 passed**（含新增的文本格式 `client_ip` 断言）；**全量 832 passed**（773 + 59，3m00s，零失败零错误）；开发库零残留。
- **真实容器冒烟**（重建镜像，`NGINX_HTTP_PORT=18081`，五服务 healthy）：
  - **端口暴露面**：`docker port` 实证**只有 nginx**（`0.0.0.0:18081->80`），app / worker / postgres / redis 全部「未发布任何宿主端口」。
  - **XFF 覆盖（关键）**：宿主带 `X-Forwarded-For: 1.2.3.4` 经 nginx 请求 → 应用访问日志 `client_ip=172.28.0.1`（= nginx 的 `$remote_addr`），**伪造值未穿透**。
  - **信任网段采信（关键）**：从 compose 网络内容器（对端 `172.28.0.x` ∈ 信任网段）直连 `app:8000` 并带 `X-Forwarded-For: 203.0.113.7` → 日志 `client_ip=203.0.113.7`（**DECISIONS 018 遗留约束解除**：反代后 IP 维度限流不再退化为共享配额）。
  - **网段外不采信**：容器内直连（对端 `127.0.0.1` ∉ 网段）带 `X-Forwarded-For: 203.0.113.9` → 日志 `client_ip=127.0.0.1`；同时证明 **`FORWARDED_ALLOW_IPS=""` 确实关掉了 uvicorn 的改写**（否则 uvicorn 会因默认信任 127.0.0.1 而把它改成转发头的值）。
  - **附件不被直出（IDOR 反证）**：在共享卷里放置 `probe-secret.txt` 后经 nginx 请求 `/probe-secret.txt` 与 `/storage/probe-secret.txt` 均 **404 JSON**（文件确实存在却取不到），证明 §31 的「静态附件访问」没有被实现成绕过鉴权。
  - **§31 其余职责**：三个安全 Header 在 404/401 上也带；`server_tokens off`（`Server: nginx` 无版本号）；2KB 请求体正常透传（401），13MB 被 nginx 拦为 **413**（其 error log 记 `client intended to send too large body: 13631496 bytes`）。
  - **Gunicorn**：容器 PID 1 的 cmdline 即 `gunicorn app.main:app --worker-class=uvicorn.workers.UvicornWorker --workers=2 ...`（已验证该模块在容器 Linux 环境可用；Windows 宿主因 `fcntl` 无法导入，这也是 Gunicorn 只能跑在容器里的原因）。
  - **§34/§22 经反代仍成立**：客户端传入 `X-Request-ID: e2e-trace-0001` 被原样回传、无值时服务端生成；`/api/v1` 响应带 `X-RateLimit-Limit=60 / Remaining=56`，`/health` 不带（限流只覆盖 `/api/v1`）；业务闭环 注册 201 → 登录 200 → `/users/me` 200。
  - **拆除与残留**：`down -v` 后 prod 容器 / 卷 / 网络**全清**，开发栈（4 服务）全程 healthy 未受影响。
- **过程中遇到的问题**：①`nginx:1.27-alpine` 镜像拉取被上游镜像站截断（`short read: expected N bytes but got 0: unexpected EOF`），连续重试后成功（属网络环境问题，非配置问题）；②`grep` 类断言两次失败**都是测试写法问题**（`server {` 被跨行正则吞进上一条指令的匹配、`access_log off`（健康探针）被误当成重复声明），已修正解析器与断言；③应用侧**真实缺口两处**：一是 `resolve_client_ip` 初版只对「采信路径」做 IPv4-mapped 归一，回落路径仍返回 `::ffff:203.0.113.7`（由本 TASK 测试捕获并修复）；二是**文本日志漏字段**——访问日志新增的 `client_ip` 只在生产 JSON 里出现，开发文本格式不渲染它（`TextFormatter` 对额外字段是白名单），**pytest 测不出**（用例只断言 JSON 负载），是开发容器冒烟发现的；已把 `client_ip` 加入白名单，并补一项断言防止回归（日志模块 41 → 42 项）。
- **文档产物**：`docs/DEPLOYMENT.md` 大幅补全（反代层、真实 IP 配置、TLS 现状与后续接入点、两个健康探针的区别）；`docs/TESTING.md` 新增「Nginx 反代与真实客户端 IP（TASK-060）」章节并订正 TASK-059 章节中已过时的两条断言；`docs/DECISIONS.md` 新增 040/041/042 并为 039 补「TASK-060 更新」；TASKS.md 勾选 TASK-060。

## TASK-061 完成 GitHub Actions CI（Phase 10 第五个任务）

**范围**：§4 指定文件路径 `.github/workflows/ci.yml`，§44 要求流水线至少执行「安装依赖 → lint → pytest → docker build」，§37 允许时加 Alembic migration test。四项文档未定义的契约经**用户确认**（DECISIONS 043）：①lint 门槛用 ruff **经典默认规则集** `E4/E7/E9/F`（不引入 I/UP/B/S）；②**不启用 `ruff format`** 作为格式门禁；③CI **含迁移可逆性验证**（`upgrade head → downgrade base → upgrade head`）；④docker build 只构建应用镜像、**不推送**。

**实现**
- `.github/workflows/ci.yml`（**新建**，161 行）：三 job。`lint` 装 `requirements-dev.txt` 后 `ruff check .`；`test` 带 `postgres:16` / `redis:7` 两个 service（**端口映射为 5433 / 6389**）、先跑迁移三步再 `pytest`；`docker-build` 执行 `docker build --tag taskflow-app:ci .`。另含最小权限（`contents: read`）、`concurrency` 取消同分支旧 run、每个 job 的 `timeout-minutes`、`workflow_dispatch`。
- `requirements-dev.txt`（**新建**）：`-r requirements.txt` + `ruff==0.16.7`（`==` 钉死）。**刻意不把 ruff 并进 `requirements.txt`**——那是 Dockerfile 装进生产镜像的文件，lint 工具进镜像既是死重量也让「生产镜像装了什么」无法单独审计。
- `pyproject.toml`：新增 `[tool.ruff]`（`target-version = "py313"`，与 `python:3.13-slim` 对齐）与 `[tool.ruff.lint] select = ["E4","E7","E9","F"]`。**规则集显式写死**：实测同一份代码在 ruff 0.16.7 下，不写 `select` 报 219 项、写成本集报 36 项——依赖默认值等于把「CI 是否通过」交给 CI 当天装到的版本决定。
- `tests/test_ci_workflow.py`（**新建**，35 项，全离线）：把 CI 必须成立的性质固化成断言（触发事件 / 最小权限 / job 与步骤顺序 / Python 版本与 Dockerfile 交叉校验 / ruff 版本与规则集钉死 / **service 端口契约** / 配置等价性 / 迁移三步顺序 / 不含任何发布动作）。
- **应用代码的 lint 修复（36 项，全部为真实缺陷，非风格问题）**：未用导入 / 重复导入（重定义）/ 歧义变量名 / 无效 f-string / 未用变量。33 项由 `ruff check --fix` 自动修复；另 4 处先逐条核对上下文再手工改——`app/api/v1/attachments.py`（函数内重复导入 `quote`，保留模块级那份）、`app/crud/notification.py`（`from sqlalchemy import desc, select, update, update`，`update` 写了两遍）、`app/api/v1/logs.py`（推导式变量 `l` 改名）、`tests/test_rbac_crud.py`（文件末尾悬挂的重复 `UserRole` 导入，其 `# noqa: E402` 随之删除）。**自动修会顺手删导入**，而有的导入是为模块级副作用存在的，故未全盘交给 `--fix`。

**验证**
- `ruff check .` → `All checks passed!`（exit 0）。
- `tests/test_ci_workflow.py` **35 passed**（0.19s，全离线）；全量 pytest **867 passed**（832 + 35，零失败零错误）；开发库零残留。
- **迁移可逆性真实验证**（本 TASK 最重要的一次实证）：用真实应用镜像起容器，**仅靠环境变量**（不挂 `.env`）把 `DATABASE_URL` 指向一次性探针库，跑 `alembic upgrade head` → `downgrade base` → `upgrade head`：三步 exit 全 0，业务表数 **16 → 0 → 16**；容器内 `ls -a /app` 实证**没有 `.env`**（前提成立）；探针库用后即删，`pg_database` 只剩 `taskflow`。这一步不能只靠本地验证——本机**永远有 `.env`**，所以「没有 `.env` 时 alembic 还能不能跑」这条路径（CI 的既有状态）从未被覆盖过。
- **配置等价性核查**：逐字段对比 `.env` 与 `Settings` 默认值，真正的差异只有三处（`DATABASE_URL` / `REDIS_URL` 默认值是 compose 服务名 `postgres:5432` / `redis:6379`、`JWT_SECRET_KEY` 默认 `change-me`），CI 恰好显式设了这三个——CI 与本地只差「谁提供 Postgres / Redis」。该结论已固化为断言（含反向断言：多设一个键也会红，因为那会引入第三种配置，让「CI 绿 ⇒ 本地绿」悄悄失效）。
- **docker build 真实验证**：按 CI 的命令（`docker build --tag taskflow-app:ci .`）执行，exit 0，镜像产出（9 步全绿，构建上下文 41KB）；验证后 `docker rmi` 删除该镜像，本机只剩 TASK-059/060 的 `taskflow-app:latest` / `:prod`。
- **GitHub Actions 首跑全绿**（run #1，commit `594bf53`，2026-09-15T12:33:53Z → 12:37:07Z，约 3m14s）：三个 job 全部 `success`；`Tests (pytest)` 的步骤序列实证为 `Initialize containers`（两个 service 容器真正起来）→ `Install dependencies` → `Verify migrations are reversible` → `Run full test suite` —— 即 service 端口映射、环境变量与迁移三步在**真实 runner** 上同样成立（这正是本地验证不到的那部分）。`workflow_dispatch` 之外无需任何人工干预。

**问题与解决**
- 本机 **PyPI 清华镜像没有 ruff**，`pip install ruff` 找不到包；改用官方源 + 本地代理装成功（`--index-url https://pypi.org/simple --proxy http://127.0.0.1:7897`）。这条只影响本机开发，CI 上无此问题；已记入 DEPLOYMENT.md。
- **`on:` 被 PyYAML 读成布尔 `True`**（YAML 1.1 把 `on`/`off`/`yes`/`no` 当布尔值）：契约测试若直接 `doc["on"]` 会 KeyError。已在 `_triggers()` 里同时接受两种键并注明这是 PyYAML 的既知行为，不是 workflow 写错了。
- **契约测试的端口扫描有个自指陷阱**：测试自身当然会提到 5433 / 6389，若不排除自己，「扫描 tests 目录」的断言会自我指涉。已跳过本文件，并剔除整行注释（注释里的地址是叙述性的）。
- 本 TASK **未发现既有实现缺陷**——三处需要判断的地方都是「测试写法/解析」层面的问题（见上两条），与应用代码无关。

**文档产物**：`docs/DEPLOYMENT.md` 新增 CI 章节（三 job 各做什么、端口为何是 5433/6389、迁移可逆性验证、本地如何跑同一套 lint）；`docs/TESTING.md` 新增「CI workflow 契约测试（TASK-061）」章节并订正全量用例数；`docs/DECISIONS.md` 新增 043；TASKS.md 勾选 TASK-061。

## TASK-062 完成完整测试与质量检查（Phase 10 第六个任务）

**范围**：§57 的「质量」9 条验收清单、§26 响应规范、§45–§49 性能与安全要求、Phase 14 测试目标。四项文档未定义的口径经**用户确认**（DECISIONS 044）：①覆盖率**只做本地基线 + 文档记录，不进 CI 门禁**；②§57 清单**双产物**——静态可判定的写成契约测试，整体结论写成 `docs/QUALITY.md`；③未覆盖行**只补有价值的分支**，`__repr__` 之类跳过；④文档矛盾**订正并留痕**。另加一条由排查推出的：⑤开发库残留**逐表核对**（不再沿用「上轮说过零残留」）。

**实现**
- `tests/test_quality_checks.py`（**新建**，12 项，全离线）：把「架构与质量必须成立的性质」做成静态断言（AST 解析 + OpenAPI schema 内省）——Router 不得 import CRUD、Model 不得反向依赖上层、Router 不得直接构造 SQL、Service 不得依赖 HTTP 传输类型（唯一豁免 `UploadFile` 且白名单化）、**全模型零 `relationship()`**、全部出参 schema 无密码字段、每个 `AppError` 子类都声明具体 4xx（覆盖 400/401/403/404/409/413/415/429）、handler 已注册且渲染 `{"detail": ...}`、所有带 `limit` 的端点必须 `le=100` 且默认值不超上限、`skip` 必须 `ge=0`、`Settings` 的**声明默认值**不含真实密钥。
- `tests/test_query_efficiency.py`（**新建**，2 项）：N+1 的**运行时**护栏——用 SQLAlchemy `before_cursor_execute` 事件统计 SELECT 条数，断言 3 个任务与 12 个任务的列表请求**语句数相等**，且访问 `task_assignees` 的语句恰好 1 条并含 `IN (`。两次测量各用独立 project（同一 team），避免第二次请求拿到 3+12=15 行。与静态断言互补：静态侧挡住「加回 `relationship()`」，运行时侧挡住「把批量查询拆回循环」（后者不新增任何 `relationship()`，静态检查看不见）。
- `tests/test_storage_guards.py`（**新建**，42 项，离线）：存储层安全边界单元测试。其中一条把「盘符规则在当前字符集下不可达」这一事实写成**可执行断言**（monkeypatch 放松 `_SAFE_KEY_RE` 后该规则仍触发），使这条纵深防御分支既被覆盖、其不可达性也被记录。
- `tests/test_quality_gaps.py`（**新建**，24 项）：覆盖率排查中「有价值但未覆盖」的分支——附件落库失败时**回滚事务 + 删物理文件**的双重一致性、注册的并发 409、非 owner/admin 移除成员 → 403、通知派发失败**吞掉但记日志**、限流关闭时零 Redis 往返、lifespan 释放连接池、`/health` 依赖挂掉降级 200、跨项目「我的任务」数据原语；收尾补的 8 项：文件名净化空输入 / 不可用扩展名截断、非超限存储故障原样上抛、`Retry-After` 下界、可信代理判定 fail-safe、非 `/api/v1` 路径零限流开销、限流身份降级为 IP、访问日志对畸形 Token 记 null、登出无可用 jti 时零写操作、删除根级对象不误删存储根。
- **生产代码修复 2 处**：`app/services/auth.py`（`register_user` 的 `try/except IntegrityError` 原来只包住 `commit`，而冲突由 `create_user` 内部 `flush` 抛出 → 并发注册失败方拿 500 而非 409；改为把 `create_user(...)` 与 `commit` 一起纳入 `try`）；`app/core/logging_config.py`（`SensitiveDataFilter` 只在 `msg` 是 `str` 时脱敏，而 `LogRecord.getMessage()` 会对任何 msg 做 `str()` → `logger.info({"password": "..."})` 把字典 repr 原样写进生产 JSON 日志；改为无 args 时对任何类型走 `redact_text(str(msg))`，并让 `_KV_RE` 键名两侧允许可选引号以覆盖 repr/JSON 写法）。
- **测试代码修复 3 处**：`tests/test_task_transition_api.py` / `tests/test_notification_api.py` / `tests/test_notification_e2e.py`（teardown 均未清 `operation_logs`，而该表 `user_id` 刻意无外键 → 不被 `delete(User)` 级联。全量运行后残留 **507 行**，全是 `task:transition`；逐文件测量定位到这三个文件，每轮分别泄漏大量 / 2 行 / 1 行。三个 teardown 均已补齐并清空存量孤儿行）；`tests/test_notification_task.py`（`test_missing_idempotency_key_generates_one` 的辅助函数把显式的 `None` 也换成前缀 key，导致被测的**自动生成分支从未执行**——假绿；引入哨兵 `_UNSET` 区分「未传」与「传了 None」）。
- `pyproject.toml`：新增 `[tool.coverage.run]`（`source = ["app"]`、`branch = true`）与 `[tool.coverage.report]`（`show_missing = true`、`exclude_also = ["def __repr__"]`）。排除清单**只列真实存在**的项——`if TYPE_CHECKING:` / `raise NotImplementedError` 实测 0 处，故不预先豁免（一条空转的排除规则会在将来悄悄藏住新代码）。
- `requirements-dev.txt`：加 `pytest-cov==7.1.0`（`==` 钉死；**不进** `requirements.txt`——那是生产镜像装的）。
- `docs/QUALITY.md`（**新建**）：质量基线与验收对照——测试规模与覆盖率双口径、§57 逐条证据、§26 对照、§45–§49 对照、Phase 14 对照、5 处发现的问题、7 项偏差与未完成项、刻意排除清单、本地复现步骤。

**验证**
- 全量 **956 passed**（59 个测试文件，869 个 `def test_*`；0 failed / 0 error / 0 skipped），带覆盖率的全量运行约 3m13s。
- **覆盖率：2373 语句 / 1 未覆盖 / 358 分支 / 0 分支半覆盖 → 99.96% 行、100% 分支**。分层：`api/v1` 274/0、`core` 441/0、`crud` 343/0、`db` 38/0、`models` 238/0、`schemas` 91/0、`services` 724/1、`tasks` 177/0、`main.py` 47/0。**双口径披露**：把被排除的 16 个 `__repr__`（32 条语句）计入后是 2405 / 33 / **98.63%**——「99.96%」这个数字依赖于该配置，不披露就是误导。
- 唯一未覆盖行：`app/services/attachment.py:179`（`_UploadReader.readable()`，starlette 协议要求的纯声明式方法），属刻意不测（Phase 14 明令禁止「为了数字而测试没有业务价值的代码」）。
- `ruff check .` → `All checks passed!`（exit 0）。
- **开发库逐表核对**（13 张业务表）：全部 **0 行**，含清空 507 行存量孤儿 `operation_logs`。
- 新增 4 个模块的用例：`test_storage_guards.py` 42 + `test_quality_gaps.py` 24 + `test_quality_checks.py` 12 + `test_query_efficiency.py` 2 = **80**。

**问题与解决**
- **并发注册的 409 兜底不可达**（生产缺陷）：只有**真实并发**（`asyncio.gather` 两个真注册）才暴露——用 mock 让 `commit` 抛错的写法会「验证成功」，却与真实故障路径无关；而这正是原实现让兜底不可达的原因（冲突在 `flush` 而非 `commit`）。
- **非字符串日志消息绕过脱敏**（生产缺陷，§48 敏感日志泄露）：由追问覆盖率数字追出——`logging_config.py:178->182` 的**分支半覆盖**说明「msg 不是字符串且无 args」这条路从未走过，而它恰好是泄露路径。实测确认 `{"password": "hunter2"}` 原样落进 JSON 日志后修复。
- **审计日志永久堆积**（测试污染，3 个文件）：`operation_logs.user_id` 刻意无外键（TASK-039 决策：审计日志要比用户活得久），因此**不被 `delete(User)` 级联**——此前各轮宣称的「零残留」检查的都是各自关心的那几张表，这张从未被核对过。逐表核对立刻暴露 507 行（全是 `task:transition`）；再用「跑单文件、比对前后行数」的逐文件测量，最终定位到**三个**泄漏源（`test_task_transition_api.py` 为主，另两个通知测试各 1～2 行/轮）。这条的教训比缺陷本身重要：**「零残留」若不逐表核对，就只是一句未被验证过的假设**。
- **假绿测试**：`test_missing_idempotency_key_generates_one` 的辅助函数让被测分支从未执行，绿灯证明的是别的事。这类假绿比失败更危险，因为它给出的安全感是错的。
- **`int(3.7)` 会截断而非抛错**：写「畸形 `sub`」用例时先入为主地以为浮点会引发 `TypeError`，实测 `int(3.7) == 3`，断言被自己的错误假设打红；改用真正会抛错的形态（`"3.5"` / `[]`）。
- **同一文件的两个 Edit 并行发出会丢更新**：本机实测 `app/core/logging_config.py` 的两处并行 Edit 只生效了一处（后写覆盖先写），表现为「改了但断言仍失败」。改为**串行**发 Edit 后一致。
- **`pytest-cov` 不在 PyPI 清华镜像**：与 ruff 同样需官方源 + 代理安装（`--index-url https://pypi.org/simple --proxy http://127.0.0.1:7897`），已记入 `docs/QUALITY.md` 的复现步骤。

**文档产物**：`docs/QUALITY.md`（**新建**，本 TASK 主产物）；`docs/API_CONTRACT.md` 订正第 340 行的分页信封描述（原写法与同文件其余 6 处及实现逐一矛盾）；`docs/PROJECT_SPEC.md` 技术栈订正为 Python 3.13 并写明本地 venv 3.14.6 的偏差风险；`docs/ARCHITECTURE.md` 性能原则订正为「显式批量 IN 查询」并说明 §46 原文本就允许批量查询；`docs/TESTING.md` 新增「覆盖率基线与质量契约（TASK-062）」章节；`docs/DECISIONS.md` 新增 044；`docs/TASKS.md` 勾选 TASK-062 并记录 `pg_trgm`/`tsvector` 遗留项。

## TASK-064 完成数据库搜索索引 `pg_trgm` / `tsvector`（Phase 10；落实 TASK-062 的 §57 遗留项）

**范围与编号**：TASK-062 的质量检查把「§57 数据库清单的 `pg_trgm` 与 `docs/DB_SCHEMA.md` 的 `tsvector` 均未落地」记为遗留项（当时 `keyword` 用 `ILIKE '%x%'`，无索引，随 `tasks` 行数线性劣化）。本 TASK 处理它，并把同轮浮现的第二个问题——**`docs/PROGRESS.md` 的进度行第四次「编辑报成功但内容没落盘」**（TASK-048/049/051/062）——一并根治。两项口径经**用户确认**（DECISIONS 045）：①搜索索引**按 §14 原文两者都实现**（trigram 索引 + `search_vector` 生成列），`keyword` 查询**语义不变**、仍走标题 `ILIKE`；②防丢机制做成**契约测试 + 检查脚本**（CI 自动拦截），而不是写一条靠人自觉的 SOP。编号挂在 TASK-063 之后但按用户指示先执行。

**实现**
- `app/models/task.py`：新增 `search_vector` 列——`TSVECTOR` + `Computed(SEARCH_VECTOR_SQL, persisted=True)`（DB 端 `GENERATED ALWAYS AS (...) STORED`，应用只读；`Computed` 让 SQLAlchemy 自动把它排除在 INSERT/UPDATE 之外，无需 Service 配合）；`__table_args__` 新增 `ix_tasks_title_trgm`（`postgresql_using="gin"` + `ops={"title": "gin_trgm_ops"}`）与 `ix_tasks_search_vector`（GIN）。把列与索引声明在 ORM 上是刻意的：否则 `alembic revision --autogenerate` 会把它们当成「库里多出来的东西」而生成一条 `drop_column`。
- `migrations/versions/6765bdcfa73e_add_task_search_indexes_and_search_vector.py`（**新建**，autogenerate 后手工调整）：`CREATE EXTENSION IF NOT EXISTS pg_trgm` **先于**建索引（`gin_trgm_ops` 这个 operator class 由扩展提供，顺序反了会直接报错）；`op.add_column` 建生成列；两个 `create_index`。`downgrade` **逆序**（先索引、后列）且**刻意不 `DROP EXTENSION`**——扩展是数据库级对象，一次表级回滚不应连带拆掉可能被别处依赖的全局扩展，配合 `IF NOT EXISTS` 保持幂等可重放。
- `tests/test_task_search_indexes.py`（**新建**，14 项）：三层守护——**离线声明层**（生成列 `persisted=True`、表达式含 `to_tsvector('simple'` 与 title/description、`insert(Task).values(...)` 编译结果不含 `search_vector`、两个索引的 GIN/`gin_trgm_ops` 声明）；**真实落库层**（`pg_extension` 有 `pg_trgm`、`is_generated='ALWAYS'` 且 `data_type='tsvector'`、`pg_indexes` 定义含 `USING gin (search_vector)` 与 `gin_trgm_ops`、插入任务后 DB 自动填好且 description 也在向量里、改标题后向量自动重算）；**执行计划层**（`ILIKE '%login%'` 走 `ix_tasks_title_trgm`、中文 `ILIKE '%登录缺陷%'` 同样走它、`search_vector @@ tsquery` 走 `ix_tasks_search_vector`）。
- `tests/test_task_search_indexes.py::test_chinese_substring_matches_ilike_but_not_the_full_text_index`：把「`keyword` 继续走 `ILIKE`」的**依据**固化成断言——`to_tsvector('simple')` 不做中文分词，`修复登录缺陷` 会成为**单个 token**，于是 `to_tsquery('simple','登录')` 命中 0 条而 `ILIKE '%登录%'` 命中 1 条。若将来有人把 `keyword` 改到 `search_vector` 上，中文检索会静默失效，此断言立刻变红。pg_trgm 按字符组切分、与语言无关，这才是中文场景可用的组合。
- `scripts/check_docs.py`（**新建**）：把「核验 `docs/PROGRESS.md`」变成一条可执行命令（退出码 0/1 + 逐条打印矛盾）。校验 6 条不变量：`## Current Task` 以 `TASK-NNN` 开头且该任务存在并已勾选；`## Completed` 与 `docs/TASKS.md` 的已勾选任务**集合与顺序都相同**；`## Completed` 的**最后一条**就是 `## Current Task`（这条正是四次事故的落点）；`## Next` 指向 TASKS.md 中第一个未勾选任务；`## Current Phase` 与 Current Task 所属 Phase 一致；结构坏掉（解析不出任务条目/缺章节）不得静默通过。
- `tests/test_docs_consistency.py`（**新建**，12 项）：第一层断言**仓库真实的两个文档一致**（CI 的 pytest 会在每次提交时执行，等于自动门禁）；第二层用**合成文档**构造 9 种矛盾（Completed 少最后一条 / 漏中间条目 / Next 指回已完成 / Phase 不匹配 / Current Task 未勾选 / Current Task 不存在 / 章节内容丢了 `TASK-NNN` 前缀 / 缺章节 / 无任务条目），断言检查器**真的会报出来**——没有这一层，一个「永远返回空列表」的假检查器也能让第一层通过，那正是本项目在别处踩过的假绿。
- `tests/test_task_model.py`：`test_tasks_column_set` 的列集断言加入 `search_vector`（tasks 表合法地多了一列，TASK-031 的严格相等断言必须同步）。
- `.github/workflows/ci.yml`：把注释里写死的「13 个迁移」改为「全部迁移」，避免新增迁移后注释立刻过期。

**验证**
- `tests/test_task_search_indexes.py` **14 passed**；`tests/test_docs_consistency.py` **12 passed**；`scripts/check_docs.py` 退出码 0（输出「docs/TASKS.md 与 docs/PROGRESS.md 一致」）。
- **执行计划硬证据**（真实 PG 16.15，`SET LOCAL enable_seqscan = off`）：`ILIKE '%login%'` → `Bitmap Index Scan on ix_tasks_title_trgm`；`ILIKE '%登录%'`（中文 2 字）与 `'%登录缺陷%'`（4 字）同样走该索引；`search_vector @@ to_tsquery('simple','login')` → `Bitmap Index Scan on ix_tasks_search_vector`。生产默认 `plan_cache_mode=auto` 下**绑定参数**形式也走索引（另在 `force_custom_plan` / `force_generic_plan` 下复核可用性）。
- **落库实证**：`information_schema` 显示 `is_generated='ALWAYS'`、`data_type='tsvector'`、生成表达式为 `to_tsvector('simple'::regconfig, ((COALESCE(title,'')::text || ' '::text) || COALESCE(description,''::text)))`；`pg_indexes` 显示 `USING gin (title gin_trgm_ops)` 与 `USING gin (search_vector)`；`pg_extension` 有 `pg_trgm 1.6`。
- **中文 tokenization 实证**：`'Fix Login Bug'` → `'bug':3 'fix':1 'login':2`；`'修复登录缺陷'` → `'修复登录缺陷':1`（整串一个 token，这就是 tsvector 不参与 `keyword` 的原因）。
- **迁移可逆性（CI 等价）**：在**一次性探针库**上复现 CI 的三步 `upgrade head → downgrade base → upgrade head`，三步均 OK，往返后 16 张业务表齐全、`search_vector` 为 `tsvector`、`pg_trgm=1.6`、tasks 的 5 个 `ix_tasks_*` 索引全部存在；探针库用完即删（`DROP DATABASE ... WITH (FORCE)`），**开发库全程未参与**。另在开发库做定向 `downgrade -1 → upgrade head` 往返验证。
- 全量测试与 lint 结果见提交信息；开发库逐表核对零残留。

**问题与解决**
- **`literal_binds` 编译要用 asyncpg dialect**：用 psycopg2 dialect 编译会把 `%login%` 转义成 `%%login%%`，塞进 `text()` 不还原——双写通配符恰好在 LIKE 语义下等价，于是测试**看起来是绿的**，但断言里的 SQL 与被测 SQL 已经对不上。改用 `postgresql.asyncpg.dialect()` 后字面量正确。
- **`AsyncSession` 没有 `exec_driver_sql`**：那是 `Connection` 的方法，改用 `session.execute(text(...))`。
- **小表直接 `EXPLAIN` 会假阴性**：测试库 `tasks` 只有个位数行，优化器必然选顺序扫描——直接 EXPLAIN 会得出「索引没被用」的错误结论。统一 `SET LOCAL enable_seqscan = off`，把断言限定在「索引对该查询形状**可用**」（这才是索引的意义；真实数据量下选不选它是成本决策）。这一条已写进测试模块 docstring 与本节，避免后人误读。
- **探针脚本路径多套了一层 `dirname`**：`os.path.dirname(os.path.dirname(__file__))` 把项目根算成了上一级，alembic 报 `No 'script_location' key found in configuration`——错误信息指向配置，真实原因是 cwd 错了。

**文档产物**：`docs/DB_SCHEMA.md`（任务表新增 `search_vector` 行与搜索索引说明、「Task 索引」与「PostgreSQL 能力」两节标记为已实现）；`docs/QUALITY.md`（D5 从「未实现」改为「已由 TASK-064 实现」并保留原记录）；`docs/DECISIONS.md` 新增 045；`docs/TESTING.md` 新增两节（搜索索引测试策略、文档一致性护栏）；`docs/TASKS.md` 新增 TASK-064 条目并把 TASK-062 的遗留项标记为已处理。

## TASK-063 完成 README 与面试技术难点（Phase 10 收尾，项目最后一个 TASK）

**目标**：交付两份**可核查**的文档——`README.md` 给读者全貌，`docs/INTERVIEW.md` 给逐问追问；并让它们的每一个数字与结构声明都受 CI 断言约束，而不是靠人记得更新。

**实现**
- `README.md` 由 60 行重写为 849 行，覆盖规格 §Phase 17 列出的 19 个部分：项目介绍 / 技术栈 / 系统架构 / 目录结构 / ER 图（mermaid，16 表 20 外键 + 删除策略说明）/ 核心业务流程（登录、创建任务、状态流转、附件上传、通知异步化）/ API 文档（40 操作 + 统一响应与错误码表 + 列表查询约定）/ 环境配置 / Docker 启动（开发栈与生产栈）/ 数据库迁移 / 测试 / CI / 性能优化 / Redis 限流原理 / Celery 原理 / JWT 原理 / 状态机设计 / 项目难点（10 条）/ 解决方案（逐条给出落点与「怎么证明」）。
- `docs/INTERVIEW.md`（**新建**，632 行）：规格 §56 的 9 个领域 35 问逐条作答，每条先给**一句话结论**，其余锚定本项目的文件 / 决策号 / 测试名；**不掩盖缺口**（如 Access Token 黑名单只定义了 key 未接入校验链路、状态流转未加行锁）。
- `scripts/check_docs.py` 扩三组规则：README ↔ 规格（19 个必需部分）、README ↔ TASKS/PROGRESS/QUALITY（进度前沿 / 当前 Phase / 基线数字）、INTERVIEW ↔ §56（9 领域 + 35 问**逐字**比对）；另加两条文件系统事实核对（迁移数、测试文件数）。
- `tests/test_readme.py`（**新建**，27 项）：守护仓库现状之外，把 README 的结构性声明与**代码事实**对齐——表/外键/唯一约束/CHECK 对 `Base.metadata`，操作数与 `/api/v1` 路径数对 `app.openapi()`，目录模块数 / 迁移数 / 测试文件数对文件系统，相对链接必须可解析；12 个反向用例逐条证明规则真的会报错；并断言契约正则仍能在 README 中匹配。

**验证**
- 全量 `pytest -q --cov --cov-report=term-missing` → **1011 passed**（0 failed / 0 error / 0 skipped），62 个测试文件 / 924 个 `def test_*`；覆盖率 **2376 语句 / 1 未覆盖 / 358 分支 / 0 分支半覆盖 → 99.96% 行、100% 分支**，**与 TASK-064 后完全一致**（本 TASK 未改 `app/`，这是覆盖率表应有的行为）。
- `ruff check .` → `All checks passed!`；`python scripts/check_docs.py` → 退出码 0。
- README 结构性声明与事实逐项相符：`Base.metadata` 16 表 / 20 外键 / 8 唯一约束 / 3 CHECK；`app.openapi()` 40 操作 / 25 条 `/api/v1` 路径；`app/api/v1` 9、`app/crud` 12、`app/models` 16、`app/schemas` 10、`app/services` 13 个模块；迁移 14；测试文件 62。
- 开发库逐表核对：仅 RBAC 种子字典表非空（roles 2 / permissions 22 / role_permissions 32，属**种子数据**），其余 13 张业务表 0 行。

**问题与解决**
- **护栏第一次运行就抓到两处**：①README 仍写着「61 个测试文件」，而新增本模块后实际是 62——正是它该抓的漂移；②README 里「3 个测试文件的 teardown 漏洞并补齐」被 `(\d+) 个测试文件` 误读成「总共有 3 个测试文件」。后者是**检查器自身的歧义**，用 `(?!的)` 负向先行断言修掉，并在注释里写明「同类歧义请改写措辞，不要把正则复杂化」。
- **`## Next` 的收尾分支原先无人管**：原实现只在「还有未勾选任务」时断言 Next 指向第一个未勾选项；本 TASK 是最后一个任务，`pending` 变空后 Next 即便还写着 `TASK-063` 也**不会报错**——「已经做完了」没人写下来，而检查器静默通过。已改为「禁止再指向任何 TASK」，并补正反两条用例。
- **README 里「共 25 条路径」有歧义**（40 个操作中 38 个在 `/api/v1` 下，而总路径含 `/` 与 `/health` 共 27 条）：改写为「共 25 条 `/api/v1` 路径」，并把该措辞写成受断言约束的声明——歧义与漂移一并消除。

**文档产物**：`README.md`（重写）、`docs/INTERVIEW.md`（新建）、`scripts/check_docs.py`（扩规则）、`tests/test_readme.py`（新建）、`tests/test_docs_consistency.py`（补 2 项）、`docs/QUALITY.md`（加基线声明行 + D8 扩展 + §57 工程化行）、`docs/DECISIONS.md`（046）、`docs/TESTING.md`（护栏章节 + 基线）；本文件的 `Project Status` 转为 Completed、`Next` 改为声明全部完成。

## 规则
只有真实完成并验证后才能勾选 Completed。
