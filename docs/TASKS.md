# TaskFlow Pro 开发任务

## Phase 1：项目基础设施
- [x] TASK-001 初始化 Git 与 Python 项目骨架
- [x] TASK-002 配置基础依赖与环境变量
- [x] TASK-003 创建 FastAPI 应用与基础配置
- [x] TASK-004 配置 PostgreSQL Docker 服务
- [x] TASK-005 配置 Redis Docker 服务
- [x] TASK-006 配置 SQLAlchemy Async Session/Base
- [x] TASK-007 初始化 Alembic
- [x] TASK-008 实现 `/health`
- [x] TASK-009 启动 Compose 并验证 API/PostgreSQL/Redis
- [x] TASK-010 第一次 Git Commit

## Phase 2：用户与认证
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

## Phase 3：RBAC
- [x] TASK-021 Role/Permission Model
- [x] TASK-022 RBAC Migration/CRUD
- [x] TASK-023 权限依赖
- [x] TASK-024 Service 资源级权限
- [x] TASK-025 RBAC 测试

## Phase 4：团队与项目
- [x] TASK-026 Team/TeamMember
- [x] TASK-027 团队 CRUD
- [x] TASK-028 成员邀请/删除
- [x] TASK-029 Project Model/CRUD/Service/Router
- [x] TASK-030 团队与项目权限测试

## Phase 5：任务核心
- [x] TASK-031 Task Model/Migration
- [x] TASK-032 Task Schema/CRUD
- [x] TASK-033 Task Service
- [x] TASK-034 Task API
- [x] TASK-035 Task 查询过滤/分页/排序
- [x] TASK-036 TaskAssignee 多人分配

## Phase 6：状态机与审计
- [x] TASK-037 状态机规则
- [x] TASK-038 Transition API
- [x] TASK-039 OperationLog
- [x] TASK-040 状态机与审计测试

## Phase 7：评论与附件
- [x] TASK-041 Comment
- [x] TASK-042 Attachment
- [x] TASK-043 上传/下载权限与安全校验
- [x] TASK-044 评论/附件测试

## Phase 8：Redis 与 Celery
- [x] TASK-045 Redis 连接与 Key 约定
- [x] TASK-046 ZSET + Lua 滑动窗口限流
- [x] TASK-047 限流测试
- [x] TASK-048 Celery App/Worker
- [x] TASK-049 通知异步任务
- [x] TASK-050 日志归档/附件清理任务
- [x] TASK-051 幂等、重试与任务测试

## Phase 9：通知
- [x] TASK-052 Notification Model（建模部分已提前于 TASK-049 完成，见 DECISIONS 029；本 TASK 补 Model 检查测试，见 DECISIONS 034）
- [x] TASK-053 通知 Service/API（查询/标记已读端点 + 业务派发点接线，见 DECISIONS 035）
- [x] TASK-054 通知 read-all / 标记全部已读（响应体返回标记条数 `{"marked": N}`，见 DECISIONS 036）
- [x] TASK-055 通知端到端测试（真实派发全链路验收，见 TESTING「通知端到端测试（TASK-055）」）

## Phase 10：工程化
- [x] TASK-056 结构化日志（JSON 格式 + 出口脱敏 + 访问日志中间件，见 DECISIONS 037）
- [x] TASK-057 Request ID（`X-Request-ID` 单一头 + 客户端值白名单校验 + 独立最外层中间件，见 DECISIONS 038）
- [x] TASK-058 Dockerfile
- [x] TASK-059 Production Compose（独立完整文件 `docker-compose.prod.yml` + 端口内外分离 + 密钥 fail-fast，见 DECISIONS 039）
- [x] TASK-060 Nginx/Gunicorn/Uvicorn（唯一入口反代 + 覆盖式 `X-Forwarded-For` + 信任网段判定 + Gunicorn/UvicornWorker，见 DECISIONS 040/041/042）
- [x] TASK-061 GitHub Actions CI（三 job：ruff lint / pytest（service 端口对齐测试硬编码的 5433+6389，含迁移可逆性验证）/ docker build；ruff 版本与规则集钉死，见 DECISIONS 043）
- [x] TASK-062 完整测试与质量检查（956 passed；2373 语句 / 1 未覆盖 / 358 分支 → 99.96% 行、100% 分支，仅本地测量不进 CI 门禁；新增 4 个测试模块 80 用例：存储安全守卫 / 有价值分支 / 质量契约 / N+1 运行时护栏；改动 2 处生产缺陷——并发注册 409 兜底不可达、非字符串日志消息绕过脱敏；订正 3 处文档矛盾。完整结论见 `docs/QUALITY.md`，决策见 DECISIONS 044）
  - ✅ **原遗留项已由 TASK-064 处理**：§57 数据库清单的 `pg_trgm` 与 `docs/DB_SCHEMA.md` 的 `tsvector` 当时均未落地（`keyword` 用 `ILIKE '%x%'`、无索引、随行数线性劣化）。现已补齐扩展、trigram 索引与全文检索生成列。当时记录见 `docs/QUALITY.md` 第 8 节 D5（已同步更新为「已实现」）。
- [x] TASK-064 数据库搜索索引 `pg_trgm` / `tsvector`（落实 §57 与 §14；**编号晚于 TASK-063 但按用户指示先于它执行**）
  - 目标：消除 `keyword` 搜索 `ILIKE '%x%'` 的顺序扫描劣化，并补齐 §57 声明的两项数据库能力。
  - 依赖：TASK-031（tasks 表）、TASK-035（keyword 查询）、TASK-062（发现该缺口）。
  - 涉及文件：`app/models/task.py`、`migrations/versions/6765bdcfa73e_*.py`、`tests/test_task_search_indexes.py`、`tests/test_docs_consistency.py`、`scripts/check_docs.py`、`tests/test_task_model.py`（列集断言）、docs 六件、`.github/workflows/ci.yml`（注释订正）。
  - 实现要求：`CREATE EXTENSION pg_trgm`（先于建索引）；`tasks.search_vector` 为 `GENERATED ALWAYS AS (...) STORED` 的 `tsvector`（`to_tsvector` 必须用两参数 IMMUTABLE 形式）；`ix_tasks_title_trgm`（`GIN` + `gin_trgm_ops`）与 `ix_tasks_search_vector`（`GIN`）；**`keyword` 查询语义不变**（仍是标题 `ILIKE`）。
  - 验收标准：真实库中扩展已装、列为 `is_generated='ALWAYS'` 的 tsvector、两索引为 GIN 且带 `gin_trgm_ops`；`EXPLAIN` 实证 `ILIKE '%x%'` 走 `ix_tasks_title_trgm`、`search_vector @@ tsquery` 走 `ix_tasks_search_vector`；迁移 `upgrade → downgrade base → upgrade` 往返无损（CI 等价验证）；开发库零残留。
  - 附带交付：`scripts/check_docs.py` + `tests/test_docs_consistency.py`——把「提交前核验 PROGRESS 三处」变成 CI 自动拦截的断言，根治 TASK-048/049/051/062 四度复发的文档静默丢失。
  - 测试要求：新增用例覆盖离线声明层、真实落库层、执行计划层、中文非分词边界、keyword 语义未变五类；并含反向用例证明一致性检查器不是空转。
- [x] TASK-063 README 与面试技术难点（README 按规格 §Phase 17 的 19 个必需部分重写为仓库门面；新建 `docs/INTERVIEW.md` 逐条作答规格 §56 的 9 领域 35 问；两者一并纳入文档护栏，见 DECISIONS 046）
  - 目标：把「项目做了什么、为什么这么做、怎么证明」写成**可核查**的两份文档——README 面向读者全貌，INTERVIEW.md 面向逐问追问；并让它们的每一个数字/结构声明都受 CI 断言约束，而不是靠人记得更新。
  - 依赖：TASK-001~062（README 必须如实描述全部已交付能力）、TASK-064（文档护栏机制与搜索索引章节）。
  - 涉及文件：`README.md`（重写）、`docs/INTERVIEW.md`（**新建**）、`scripts/check_docs.py`（扩 3 组规则）、`tests/test_readme.py`（**新建**）、`tests/test_docs_consistency.py`（补「全部完成后 `## Next`」边界用例）、`docs/QUALITY.md`（基线声明行）、`docs/TASKS.md`/`docs/PROGRESS.md`/`docs/DECISIONS.md`/`docs/TESTING.md`。
  - 实现要求：README 覆盖 §Phase 17 全部 19 个部分；**所有数字取自真实仓库**（迁移数、测试文件数、表/外键/约束数、OpenAPI 操作数与路径数、模块数），不凭印象；INTERVIEW.md 的 35 条题干**逐字照抄** §56（改写会让「其实是另一个问题」蒙混过去），答案锚定本项目的文件、决策号或测试名而非通用八股，且不掩盖未实现项。
  - 验收标准：`scripts/check_docs.py` 退出码 0；README 的结构性声明与 ORM `metadata` / OpenAPI schema / 文件系统逐一相符；INTERVIEW.md 覆盖 9 领域 35 问且题干与 §56 逐字一致；README 内相对链接全部可解析；README 与 QUALITY 的基线数字一致。
  - 测试要求：`tests/test_readme.py` 除守护仓库现状外，每条规则都要配**反向用例**（合成输入弄坏它并断言真的报错）；并断言契约正则仍在 README 中可匹配——否则改写措辞即可让检查静默失效。

## Phase 11：前端工程化
- [x] TASK-065 前端项目初始化（规格 §60「第一阶段：项目初始化」）
  - 目标：建立 `frontend/` 工程骨架——Vue 3 + TypeScript + Vite + Vue Router + Pinia + Axios + Element Plus + ESLint + Prettier 全部可用。
  - 依赖：TASK-001~064（后端契约是前端的事实来源）。
  - 涉及文件：`frontend/package.json`、`tsconfig.json`、`vite.config.ts`、`vitest.config.ts`、`eslint.config.js`、`prettier.config.js`、`index.html`、`src/env.d.ts`、`.env.development`、`.env.production`、`.gitignore`、`public/favicon.svg`。
  - 实现要求：技术栈版本落到 `package.json` 并锁住 Node 版本下限；开发环境 API 基地址用**相对路径** + Vite 代理（后端无 CORS，见 DECISIONS 047）；环境变量只允许非敏感项。
  - 验收标准：`npm install` 成功；`npm run dev` 能打开页面且代理指向 `http://127.0.0.1:8000`。
  - 测试要求：配置本身由 `npm run typecheck` / `lint` 间接守护（配置文件是 TS/JS 源码，语法或类型错误会直接失败）。
- [x] TASK-066 前端基础框架与布局（规格 §61「第二阶段：基础框架」）
  - 目标：搭起系统主框架与认证布局，让「登录 → 进主框架 → 侧边栏/顶栏/面包屑 → 路由切换」这条链路真实可跑。
  - 依赖：TASK-065。
  - 涉及文件：`src/main.ts`、`src/App.vue`、`src/layouts/{BasicLayout,AuthLayout}.vue`、`src/components/layout/{AppSidebar,AppHeader,AppBreadcrumb,UserMenu,NotificationBell}.vue`、`src/components/common/PagePlaceholder.vue`、`src/router/{routes,index,guards}.ts`、`src/types/{common,router}.ts`、`src/stores/{auth,notification}.ts`、`src/utils/{request,storage,permission,format}.ts`、`src/api/{auth,notification}.ts`、`src/composables/usePermission.ts`、`src/views/**`。
  - 实现要求：菜单项从路由表派生（唯一事实来源）；面包屑由 `meta.title` + 菜单前缀匹配生成，不额外维护 breadcrumb 字段；请求层统一解信封、自动带令牌、401 单飞刷新、错误归一；`hasPermission` 保留落点但不据此隐藏功能（后端无权限查询端点，隐藏按钮不等于安全）。
  - 验收标准：类型检查 / lint / 单测 / 构建全绿；侧边栏每个入口都能解析到真实路由；未登录访问受保护页面跳登录页并带回跳地址；`/403`、`/404`、`/500` 三个错误页齐备。
  - 测试要求：`frontend/tests/unit/` 四个模块——`storage`（键名与降级契约）、`permission`（AND/OR 语义对齐后端 `require_permission`）、`request`（自省 adapter 验证解信封 / 令牌头 / 错误归一）、`router`（菜单可达性 + 守卫跳转与凭证清理）。
- [x] TASK-067 前端认证（规格 §62「第三阶段：认证」）
  - 目标：登录 / 注册 / 令牌管理 / 401 自动刷新 / 路由守卫 / 登出，全部对接真实后端。
  - 依赖：TASK-065、TASK-066。
  - 涉及文件：`src/views/auth/{Login,Register}.vue`、`src/views/profile/Profile.vue`、`src/stores/auth.ts`、`src/api/auth.ts`、`src/utils/request.ts`、`src/router/guards.ts`。
  - 实现要求：登录后立即拉 `/users/me`（登录响应只有令牌）；Refresh Token 轮换导致旧令牌失效，因此并发 401 必须**共享同一次刷新**，否则会把用户踢下线；登出用 `tokenStorage` 里的**最新** Refresh Token 撤销，撤销失败也照常清本地（后端幂等语义）；前端不发明后端没有的密码长度规则。
  - 验收标准：登录成功进首页、失败给出可读提示；刷新页面后登录态保持（令牌在 localStorage，用户资料补拉）；令牌失效时清凭证并跳登录页；个人中心展示的字段与 `UserRead` 一致。
  - 测试要求：`tests/unit/request.spec.ts` 覆盖令牌头与错误归一；`tests/unit/router.spec.ts` 覆盖「令牌失效 → 清凭证 + 回跳地址」；密码长度规则以注释说明「后端无约束」而非静默发明。
- [x] TASK-068 前端工程验证与文档（对应规格 §81「开发完成定义」）
  - 目标：把前端工程的可验证性与契约差异落成文档，使「前端做了什么 / 不能做什么」都有据可查。
  - 依赖：TASK-065~067。
  - 涉及文件：`frontend/README.md`（新建）、`docs/FRONTEND_API_MAPPING.md`（新建）、`docs/TASKS.md`、`docs/PROGRESS.md`、`docs/DECISIONS.md`（047）、根 `README.md`（进度前沿与 Phase 声明）。
  - 实现要求：① 后端端点对照以 `app.openapi()` 导出结果为准（25 条 `/api/v1` 路径 / 38 个操作），不凭印象；② 规格与后端的每处不一致逐条记录「规格说法 / 后端事实 / 前端处理」；③ 需要后端配合的未决项单独成表；④ 占位页清单写清楚，避免「漏做」与「按计划后做」混淆。
  - 验收标准：`npm run typecheck`、`npm run lint`、`npm run test`、`npm run build` 四项全绿；`python scripts/check_docs.py` 退出码 0；后端全量 pytest 仍全绿（前端不得影响后端）。
  - 测试要求：前端单测四项模块全绿；后端 `tests/test_docs_consistency.py` 与 `tests/test_readme.py` 覆盖本 TASK 修改的文档声明（进度前沿、Phase 号、数字声明）。

## Phase 12：前端业务页面
- [x] TASK-069 首页 Dashboard（规格 §63「第四阶段：Dashboard」）
  - 目标：实现首页 Dashboard，用真实后端端点展示团队/项目/通知/日志概览；对后端未提供的「任务统计」「全局最近任务」做诚实降级（不编造接口）。
  - 依赖：TASK-065~068（框架、请求层、类型与 API 模块约定）。
  - 涉及文件：`src/views/dashboard/Dashboard.vue`（重写，移除占位）、`src/types/{team,project,log}.ts`（新建，对齐 `app/schemas/team.py`/`project.py`/`operation_log.py`）、`src/api/{team,project,log}.ts`（新建，封装 `listTeams`/`listProjects`/`listMyLogs`）。
  - 实现要求：① 四张统计卡片数据来自 `GET /teams`、`GET /projects`、`GET /notifications`（前端统计未读）、`GET /logs` 四个真实端点；② 两个列表「最近通知」「最近项目」分别链到 `/notifications` 与 `/projects/:id`；③ 每个概览独立加载、独立容错（某项 403 或缺数据只让那一块报错，不影响其余卡片）；④ 规格 §11.2 的「任务统计」与全局「最近任务」依赖后端聚合接口，但 `GET /tasks` 要求 `project_id` 必填且无跨项目统计端点（`docs/FRONTEND_API_MAPPING.md` §4-D7/D8、§6-Q2），按规格 §57「禁止猜 API」——页面顶部提示条写明限制，不伪造它们。
  - 验收标准：`typecheck`/`lint`/`test`/`build` 四项全绿（37 单测不变）；Dashboard 真实渲染团队/项目/通知/日志概览；被后端卡住的部分在界面明示。
  - 测试要求：沿用现有 `tests/unit/` 四类单测（storage/permission/request/router）门禁；网络层 mock 留待规格 阶段14 测试阶段统一实装，本阶段不新增伪造后端行为的组件测试。

- [x] TASK-070 团队模块（规格 §12/§13/§14/§15「团队列表 / 详情 / 成员管理」）
  - 目标：实现团队模块三个页面，全部走真实后端端点；对后端没有的能力做诚实降级（不编造接口）。
  - 依赖：TASK-065~069（框架、请求层、类型与 API 模块约定；`teamApi`/`projectApi` 已就绪）。
  - 涉及文件：`src/types/team.ts`（扩展 Team/TeamCreate/TeamUpdate/TeamMember/TeamMemberInvite）、`src/api/team.ts`（扩展 createTeam/getTeam/updateTeam/deleteTeam/listMembers/inviteMember/removeMember）、`src/views/team/TeamList.vue`（列表+创建+客户端搜索+删除）、`src/views/team/TeamDetail.vue`（详情：基本信息/成员/项目/编辑设置+任务统计降级提示）、`src/views/team/TeamMembers.vue`（成员表格+邀请+移除）。
  - 实现要求：① 列表 `GET /teams`、创建 `POST /teams`、删除 `DELETE /teams/{id}`（删除按钮仅对 `owner_id === 当前用户` 显示，数据驱动非猜权限）；② 详情 `GET /teams/{id}`+`GET /teams/{id}/members`+`GET /projects` 按 `team_id` 过滤展示项目，「任务统计」受 `§4-D7/D8`·`§6-Q2` 阻塞，页面提示条明示不编造；③ 成员管理 `GET/POST /teams/{id}/members`、`DELETE /teams/{id}/members/{user_id}`，邀请按 `user_id`（非邮箱，见 `§4-D6`）、role 仅 admin/member；④ 当前用户角色从成员列表 `role` 字段读取，驱动「邀请/移除/编辑」按钮显隐（数据驱动，不依赖不存在的权限集合端点，见 `§4-D4`）；⑤ 后端没有「修改成员角色」端点，「角色调整」走「移除后重邀」，页面已注明。
  - 验收标准：`typecheck`/`lint`/`test`/`build` 四项全绿（37 单测不变）；团队三个页面真实渲染并接后端；被后端卡住处界面明示。
  - 测试要求：沿用现有 `tests/unit/` 四类单测门禁；端到端登录态渲染仍受本机安全策略（口令字面量）拦截，按既定口径不绕过，团队页只做结构与四门校验验证。

- [x] TASK-071 项目模块（规格 §16/§17/§18/§19「项目列表 / 创建 / 详情 / 设置」）
  - 目标：实现项目模块三个页面，全部走真实后端端点；对后端没有的字段（status、成员数、任务数、进度）与能力（搜索/状态筛选/分页总数）做诚实降级（不编造接口）。
  - 依赖：TASK-065~070（框架、请求层、类型与 API 模块约定；`projectApi`/`teamApi` 已就绪）。
  - 涉及文件：`src/types/project.ts`（扩展 Project/ProjectCreate/ProjectUpdate）、`src/api/project.ts`（扩展 createProject/getProject/updateProject/deleteProject）、`src/views/project/ProjectList.vue`（卡片列表+客户端搜索+团队筛选+创建）、`src/views/project/ProjectDetail.vue`（四标签：任务列表/看板占位、项目成员=复用团队成员接口、项目设置=跳转）、`src/views/project/ProjectSettings.vue`（PATCH/DELETE+二次确认）。
  - 实现要求：① 列表 `GET /projects`（limit:100 全量，客户端搜索/团队筛选，因后端无搜索与 total）、创建 `POST /projects`（team_id 取自有 `GET /teams`，必填）、删除 `DELETE /projects/{id}`（后端 OWNER/ADMIN 校验，前端按钮常显）；② 详情 `GET /projects/{id}`+标签栏，任务列表/看板标签为阶段 8 占位（PagePlaceholder），「项目成员」标签用 `GET /teams/{team_id}/members`（`team_id` 来自项目，项目无独立成员端点），「项目设置」标签跳转设置页；③ 设置页 `PATCH /projects/{id}`（name 必填、description 显式 null 清空）+ `DELETE /projects/{id}`（ElMessageBox 二次确认）；④ ProjectRead 无 `status`、无成员数/任务数/进度字段，规格 §16.1 卡片的「成员：N / 任务：N / 78%」与「状态筛选」无法展示，列表页顶部 `el-alert` 明示诚实降级、不伪造统计端点。
  - 验收标准：`typecheck`/`lint`/`test`/`build` 四项全绿（37 单测不变）；项目三页面真实渲染并接后端；被后端卡住处界面明示。
  - 测试要求：沿用现有 `tests/unit/` 四类单测门禁；端到端登录态渲染仍受本机安全策略（口令字面量）拦截，按既定口径不绕过，项目页只做结构与四门校验验证。

- [x] TASK-072 任务模块（规格 §20~§27「任务列表 / 创建 / 详情 / 看板 / 编辑 / 流转 / 分配」）
  - 目标：实现任务模块四个页面（列表 / 创建 / 详情 / 看板），全部走真实后端端点；对后端没有的跨项目「我的任务」全局视图做诚实降级（不编造接口）。
  - 依赖：TASK-065~071（`taskApi`/`projectApi`/`teamApi` 已就绪）。
  - 涉及文件：`src/types/task.ts`（新建：Task/TaskCreate/TaskUpdate/TaskTransition/TaskListParams + 状态机/枚举标签）、`src/api/task.ts`（新建：listTasks/getTask/createTask/updateTask/deleteTask/transitionTask/listAssignees/addAssignee/removeAssignee）、`src/views/task/TaskList.vue`（表格+客户端搜索+优先级/状态筛选+排序+分页）、`src/views/task/TaskBoard.vue`（HTML5 拖拽看板走 transition 端点）、`src/views/task/TaskDetail.vue`（transition 下拉/编辑抽屉/分配成员/删除）、`src/views/task/TaskCreate.vue`（创建表单无 status/assignee）。
  - 实现要求：① `GET /tasks` 的 `project_id` 必填（无默认值），列表/看板均为「按项目」作用域；跨项目「我的任务」后端无端点（`§4-D7/D8`·`§6-Q2`），页面用「项目选择器 + assignee_id=当前用户」诚实表达、顶部 `el-alert` 明示，不伪造全局端点；② 状态流转只能走 `POST /tasks/{id}/transition`（状态机 `TRANSITIONS` 白名单仅前端提示，真实合法性以后端为准；`task:transition` 功能权限 admin-only，普通成员流转可能 403，由请求层提示）；看板拖拽临时移动、失败回滚；③ `TaskCreate` 无 `status`/`assignee`，创建后 `POST /tasks/{id}/assignees` 指派，负责人下拉来自 `GET /teams/{team_id}/members`（`team_id` 取自 `ProjectRead`）；④ 评论/附件/日志标签为阶段 9/10/13 占位（PagePlaceholder），不编造后端不存在的评论/附件/日志端点。
  - 验收标准：`typecheck`/`lint`/`test`/`build` 四项全绿（37 单测不变）；任务四页面真实渲染并接后端；被后端卡住处界面明示。
  - 测试要求：沿用现有 `tests/unit/` 四类单测门禁；端到端登录态渲染仍受本机安全策略（口令字面量）拦截，按既定口径不绕过，任务页只做结构与四门校验验证。

- [x] TASK-073 评论模块（规格 §28「任务评论」）
  - 目标：在任务详情内实现评论区块（查看 / 添加 / 删除自己的评论），全部走真实后端端点；对后端「功能级 `comment:delete` 仅 admin」的权限口径做诚实降级（不臆测权限集隐藏按钮）。
  - 依赖：TASK-072（任务详情页 `TaskDetail.vue` 已就绪，评论原为阶段 9 占位）。
  - 涉及文件：`src/types/comment.ts`（新建：Comment / CommentCreate / CommentListParams，对齐 `app/schemas/comment.py`）、`src/api/comment.ts`（新建：`commentApi.listComments/createComment/deleteComment`）、`src/views/task/TaskDetail.vue`（评论占位替换为真实区块）。
  - 实现要求：① 列表 `GET /tasks/{task_id}/comments`（功能级 `task:read`），`CommentRead` 内嵌 `username` 直接渲染作者名，不额外查用户；② 发表 `POST /tasks/{task_id}/comments`（`comment:create`，种子数据成员可用），textarea 限 2000 字（对齐 `CommentCreate` 的 `max_length`）并带字数统计；③ 删除 `DELETE /comments/{comment_id}`——按规格 §28「删除自己的评论」，仅对 `comment.user_id === 当前用户` 的评论显示删除钮（数据驱动，非臆测权限集）；功能级 `comment:delete` 种子**仅 admin 持有**且先于资源级判定执行，故普通成员删自己的评论也会 403，由请求层统一提示，不提前隐藏按钮（`§4-D4`，见 DECISIONS 052）；④ 评论独立加载、独立容错（读取失败只让评论区空/报错，不连累任务主体）；⑤ 附件/操作日志仍为阶段 10/13 占位（PagePlaceholder），不编造端点。
  - 验收标准：`typecheck`/`lint`/`test`/`build` 四项全绿（37 单测不变）；评论区块真实渲染并接后端；权限口径在界面/文档明示。
  - 测试要求：沿用现有 `tests/unit/` 四类单测门禁；端到端登录态渲染仍受本机安全策略（口令字面量）拦截，按既定口径不绕过，评论区块只做结构与四门校验验证。

- [x] TASK-074 附件模块（规格 §29「任务附件」）
  - 目标：在任务详情内实现附件区块（上传 / 列表 / 下载 / 删除自己的上传），全部走真实后端端点；前端预检只为即时反馈，真值以后端裁决（D13）。
  - 依赖：TASK-072（任务详情页已就绪，附件原为阶段 10 占位）；TASK-073（同页评论区块已落地的独立加载模式可复用）。
  - 涉及文件：`src/types/attachment.ts`（新建：Attachment，对齐 `app/schemas/attachment.py`）、`src/api/attachment.ts`（新建：`attachmentApi.listAttachments/uploadAttachment/downloadAttachment/deleteAttachment` + 预检常量 `MAX_UPLOAD_SIZE/ALLOWED_EXTENSIONS/ACCEPT_ATTR/isAllowedFile`）、`src/utils/format.ts`（加 `formatFileSize`）、`src/utils/request.ts`（加 `http.getBlob`，附件下载返回文件流而非信封）、`src/views/task/TaskDetail.vue`（附件占位替换为真实区块）。
  - 实现要求：① 列表 `GET /tasks/{task_id}/attachments`（功能级 `task:read`），`AttachmentRead` 内嵌 `uploader` 直接渲染上传者；② 上传 `POST /tasks/{task_id}/attachments`（`attachment:upload`，种子数据成员可用）——`multipart/form-data` 字段名固定 `file`、`FormData` 不手写 `Content-Type`；`el-upload` 自定义 `http-request` 走 `attachmentApi`，`before-upload` 按后端白名单预检大小（10 MiB）与扩展名（图片/文档/压缩包），带 `onUploadProgress` 进度条；预检通过不代表后端接受，413/415/400 由后端裁决、请求层提示；③ 下载 `GET /attachments/{id}`（`attachment:download`）——响应是**文件流**而非 `{data,message}` 信封，走 `http.getBlob` 后用临时 `<a download>` 保存；④ 删除 `DELETE /attachments/{id}`（`attachment:upload` + 上传者或团队 OWNER/ADMIN）——仅对 `uploader_id === 当前用户` 的附件显示删除钮（数据驱动；成员对自家附件有 `attachment:upload`，可删）；⑤ 附件独立加载、独立容错（读取失败只让附件区空/报错，不连累任务主体）；⑥ 操作日志仍为阶段 13 占位，不编造端点。
  - 验收标准：`typecheck`/`lint`/`test`/`build` 四项全绿（37 单测不变）；附件区块真实渲染并接后端；上传/下载/删除权限口径在界面/文档明示。**注**：前端 `build` 在 `dist/assets` 超过 50 个文件后会触发沙箱批量删除守卫，须带 `CODEBUDDY_SAFE_DELETE_ENABLED=0` 运行（见 `frontend/README.md`）。
  - 测试要求：沿用现有 `tests/unit/` 四类单测门禁；端到端登录态渲染仍受本机安全策略（口令字面量）拦截，按既定口径不绕过，附件区块只做结构与四门校验验证。

- [x] TASK-075 通知模块（规格 §30/§31「通知 / 顶部消息通知」）
  - 目标：实现通知收件箱页（查看 / 标记已读 / 全部标记已读），全部走真实后端端点；对后端「无未读筛选、无 link 字段」做诚实降级（不编造接口、不解析正文猜资源 id）。
  - 依赖：TASK-065~068（`notificationApi`、`stores/notification.ts`、`NotificationBell.vue` 在阶段 1/2 已就绪）。
  - 涉及文件：`src/views/notification/NotificationList.vue`（占位替换为真实收件箱）、`src/types/notification.ts`（补类型中文标签映射 `NOTIFICATION_TYPE_LABELS`/`notificationTypeLabel`）、`src/api/notification.ts`（`listNotifications` 增可选 `options` 参数）、`src/stores/notification.ts`（预览请求传 `silent: true`，使注释与行为一致）。
  - 实现要求：① 列表 `GET /notifications`（skip/limit，最新在前），「全部 / 未读 / 已读」三页签为**客户端过滤**（后端无 `is_read` 查询参数，`§4-D9`）；② 单条 `PATCH /notifications/{id}/read` 与全部 `PATCH /notifications/read-all` **经 store 调用**，顶栏铃铛与列表共享同一份数据，避免角标滞后；③ 分页仅「上一页 / 下一页」（响应无 total，满页视为可能有下一页并如实提示）；④ 「点击通知跳转对应资源」（规格 §30）**不实现**——`NotificationRead` 无 link/resource_id 字段，资源 id 仅以文本嵌在 `content`（如「任务 #123 …」），前端不解析正文字符串猜 id（与后端文案强耦合且 `team_invited` 等类型无 id 可解析），顶部 `el-alert` 明示（`§4-D15`，见 DECISIONS 054）；⑤ 类型标签以真实契约为准：后端实际写入小写 `task_assigned`/`task_status_changed`（`app/services/task.py`），与规格 §30 的大写写法不一致，未知类型原样回退不做语义猜测。
  - 验收标准：`typecheck`/`lint`/`test`/`build` 四项全绿（37 单测不变）；通知页真实渲染并接后端；降级点在界面/文档明示。
  - 测试要求：沿用现有 `tests/unit/` 四类单测门禁；端到端登录态渲染仍受本机安全策略（口令字面量）拦截，按既定口径不绕过，通知页只做结构与四门校验验证。

- [x] TASK-076 权限模块（规格 §34/§35/§36/§69「RBAC 前端权限 / 权限控制原则 / 路由权限 / 第十阶段：权限」）
  - 目标：对照 §69 六项清单（路由权限/菜单权限/按钮权限/用户角色/权限判断/403 页面）完成能力审计并落地唯一可诚实实现的部分；功能级权限控制受 §4-D4「无权限集合端点」阻塞，按既定纪律降级、不臆造权限表。
  - 依赖：TASK-065~075（`utils/permission.ts`/`usePermission.ts`/`guards.ts`/403 页在阶段 1/2 已具备；`teamApi.listMembers` 在 TASK-070 就绪）。
  - 涉及文件：`src/views/profile/Profile.vue`（新增「我的团队与角色」区块）。
  - 实现要求：① 「用户角色」以唯一诚实形态落地——个人中心新增「我的团队与角色」区块：`GET /teams`（limit 100）+ 逐团队 `GET /teams/{id}/members` 找 `user_id === 当前用户` 的 `role`（owner/admin/member），每个团队独立容错（单个失败只显示「未知」，不连累其余）；顶部注明「后端不暴露全局角色与权限集合（§4-D4），角色只能按团队展示」；② 其余五项审计结论落文档（FRONTEND_API_MAPPING §7 + DECISIONS 055）：403 页面（阶段 1 已有路由与页面）、路由认证守卫（阶段 2 `guards.ts`）、权限判断工具（`utils/permission.ts` + `usePermission.ts`，10 项单测）均已具备；**按权限的菜单/按钮/路由控制不做**——权限集合恒为空且按 §4-D4 不据此隐藏任何入口（规格 §35「隐藏按钮 ≠ 安全」），后端 403/404 兜底，待后端补「我的权限集合」端点（§6-Q1）后再接线。
  - 验收标准：`typecheck`/`lint`/`test`/`build` 四项全绿（37 单测不变）；团队角色区块真实渲染并接后端；阻塞项在界面/文档明示。
  - 测试要求：沿用现有 `tests/unit/` 四类单测门禁；端到端登录态渲染仍受本机安全策略（口令字面量）拦截，按既定口径不绕过，个人中心只做结构与四门校验验证。

- [x] TASK-077 操作日志（规格 §32「操作日志」/§44，阶段 13）
  - 目标：`OperationLogList.vue` 占位替换为真实日志页，接 `GET /logs` 当前用户时间线；§32 的筛选/操作人/IP 等超出真实契约的部分按既定纪律降级并在页面明示（登记 §4-D16）。
  - 依赖：TASK-069（`logApi.listMyLogs` 已在 Dashboard 概览使用）。
  - 涉及文件：`src/views/operation-log/OperationLogList.vue`（重写）、`src/types/log.ts`（补 action/资源类型中文标签）、`src/api/log.ts`（补 `listResourceLogs`）。
  - 实现要求：① 列表 `GET /logs`（skip/limit，`limit` 上限 100，响应裸数组无 total）→ 分页仅「上一页/下一页」，以「本页取满 pageSize」推断有无下一页；② 操作类型 / 时间筛选做在**当前已取回的页**上（后端无筛选参数），页面注明「仅作用于当前页」；③ 不设「操作人」列（时间线即本人）与「IP」列（`OperationLogRead` 无 IP 字段），顶部 `el-alert` 明示；④ `payload` 按已知三种 action 收窄为人类可读描述（`task:transition` → 状态 x→y 用 `TASK_STATUS_LABELS`；`comment:delete` → 任务 #x 中的评论 #y；`attachment:delete` → 任务 #x 的附件「名」），未知 action 原样展示、payload 走 JSON 兜底；⑤ `api/log.ts` 补 `listResourceLogs`（`GET /logs/{resource_type}/{resource_id}` 资源级日志备用）。
  - 验收标准：`typecheck`/`lint`/`test`/`build` 四项全绿（37 单测不变）；日志页真实渲染并接后端；降级项在界面/文档明示。
  - 测试要求：沿用现有 `tests/unit/` 四类单测门禁；端到端登录态渲染仍受本机安全策略（口令字面量）拦截，按既定口径不绕过，日志页只做结构与四门校验验证。

## Phase 13：前端测试（规格 §59 阶段 14 / §71）

- [x] TASK-078 前端单元测试补齐（规格 §59「阶段 14 测试」/ §71「第十二阶段：测试」的单元测试部分）
  - 目标：§71 单元测试重点五项（utils / composables / stores / permission / format）中，permission（permission.spec 10 项）与部分 utils（storage/request）已具备，补齐 format、composables、stores 三个缺口，把纯逻辑契约钉进测试。
  - 依赖：TASK-065~077（被测对象：`utils/format.ts`、`composables/usePermission.ts`、`stores/auth.ts`、`stores/notification.ts`）。
  - 涉及文件：`tests/unit/format.spec.ts`、`tests/unit/composables-usePermission.spec.ts`、`tests/unit/store-auth.spec.ts`、`tests/unit/store-notification.spec.ts`（新建）。
  - 实现要求：① `format.spec`：空值/非法值降级、`formatDateTime` 输出形状（与时区无关断言）、`formatRelativeTime` 五档边界（`vi.setSystemTime` 固定「现在」）、`formatFileSize` 1024 进制与小数位收敛规则；② `composables-usePermission.spec`：钉住「权限集合恒为空」（§4-D4）——`can`/`canAny` 对任何权限返回 false、空参时 AND 恒真/OR 恒假；③ `store-auth.spec`：mock `authApi`，钉住令牌唯一事实来源是 storage、登录失败不留半截状态、登出撤销失败不阻塞本地清理、无令牌不发起撤销；④ `store-notification.spec`：mock `notificationApi`，钉住未读数前端统计、预览请求必须带 `silent: true`（防 TASK-075 修正项回退）、预览失败静默清空、标记已读本地同步翻转、reset 防串号。
  - 验收标准：`typecheck`/`lint`/`build` 全绿；`test` 全绿且用例数 37 → **70**（8 个 spec 文件）。
  - 测试要求：新用例全部为纯逻辑/纯 store 测试，不依赖真实后端；§71 的组件测试与 E2E 按真实组件形态与既定口径降级（见 DECISIONS 057），不在本 TASK 伪造。

## Phase 14：前端部署（规格 §59 阶段 15 / §56）

- [x] TASK-079 前端镜像与生产栈接入（规格 §59「阶段 15 Docker / Nginx」/ §56「生产环境架构」）
  - 目标：前端以多阶段构建产出静态镜像（node 构建 → nginx 托管 dist），接入 TASK-060 的生产栈——入口 Nginx 按 §56 分流：`/` → 前端镜像、`/api/` → FastAPI，暴露面维持「只有 Nginx 对外」。
  - 依赖：TASK-078（四门全绿的构建产物）、后端 TASK-060（生产栈唯一入口 nginx、固定子网 172.28.0.0/24 与 `tests/test_nginx_config.py` 契约）。
  - 涉及文件：`frontend/Dockerfile`、`frontend/nginx.conf`、`frontend/.dockerignore`（新建）；`nginx/nginx.conf`、`docker-compose.prod.yml`（接入）；`tests/test_nginx_config.py`、`tests/test_prod_compose.py`（契约演进）。
  - 实现要求：① `frontend/Dockerfile` 多阶段（node:22-alpine 执行 `npm ci` + `npm run build` → nginx:1.27-alpine 只携带 dist 与 frontend/nginx.conf），基础镜像钉版本；② `frontend/nginx.conf` 只做静态托管——history 回退（`try_files ... /index.html`，路由是 `createWebHistory`）、`/assets/` 按 content hash 永久缓存、index.html no-cache、安全头；**不做 API 反代**（安全语义只有入口一份拷贝）；③ 入口 `nginx/nginx.conf`：新增 `upstream frontend_backend`，原 `location /` 的应用反代整体挪进 `location /api/`（前端基地址即 `/api/v1`），新 `location /` 转发前端；④ compose 增加 `frontend` 服务（构建自 `./frontend`、镜像 `taskflow-frontend:prod`、不发布宿主端口、healthcheck 探自有 `/nginx-health`、restart always + 日志轮转），nginx `depends_on` 增加 frontend healthy；⑤ 契约测试演进：`proxy_pass` 路由表断言（`/api/`→app、`/`→frontend）、`keepalive` 两条、frontend 服务/文件层断言（多阶段 FROM 钉版本、SPA 回退、前端层无 proxy_pass、.dockerignore 排除 node_modules/dist）。
  - 验收标准：配置契约测试（`test_nginx_config.py` + `test_prod_compose.py`）全绿；全量后端回归无新增失败；`taskflow-frontend:prod` 镜像在本机 Docker 真实构建成功；生产栈冒烟验证 `/` 返回 SPA 入口、`/api/v1` 链路可用、暴露面仅 nginx、`down -v` 零残留。
  - 测试要求：本 TASK 不新增应用逻辑代码，测试 = 静态契约测试 + 真实 Docker 构建/冒烟；前端四门（typecheck/lint/test/build）不因新增部署文件受影响（不跑在前端门禁内）。

## Phase 15：前端优化（规格 §59 阶段 16 / §74）

- [x] TASK-080 前端优化：Element Plus 按需引入与死依赖清理（规格 §59 阶段 16 / §74「前端性能要求」）
  - 目标：落实 §74「组件按需加载」——主产物不再携带全量 Element Plus；顺手清理已声明的死依赖。
  - 依赖：TASK-078（测试基线）、TASK-079（部署链路使用 dist，体积变化需复验）。
  - 涉及文件：`frontend/package.json`、`package-lock.json`、`vite.config.ts`、`src/main.ts`、`src/App.vue`、`tsconfig.json`、`components.d.ts`（插件生成、入库）。
  - 实现要求：① `vite.config.ts` 引入 `unplugin-vue-components` + `ElementPlusResolver`（模板 `el-*` 标签与 `v-loading` 指令编译期按需解析，生成类型钉在 `components.d.ts`）；② `main.ts` 移除 `app.use(ElementPlus)` 全量注册与全量 CSS，命令式 API（ElMessage/ElMessageBox/ElNotification/ElLoading）样式集中补引并写明增量口径；③ locale 改 `<el-config-provider>` 根组件下发；④ 删除零引用依赖 echarts；⑤ `chunkSizeWarningLimit` 回到默认 500 kB（超线即警告）。
  - 验收标准：四门全绿（typecheck/lint/test/build）；主 chunk 显著缩减且构建无体积警告；静态核对「模板用到的 `el-*` 标签 ⊆ components.d.ts 解析集」；dev server 转换产物抽检确认组件/`v-loading` 指令/样式配对按需引入；`el-message`/`el-loading` 样式与 zh-cn locale 在产物中存在。
  - 测试要求：不新增应用逻辑；既有 70 项单测不回退；验证手段 = 四门 + 产物静态核对 + dev 转换产物抽检（运行时浏览器冒烟受既定安全策略口径约束不绕过）。

## Phase 16：RBAC 权限闭环（TASK-081~084）

- [x] TASK-081 注册默认绑定 member 角色 + 存量回填
  - 目标：消除「普通成员登录即权限不足」的根因——注册用户零角色 = 零权限，所有功能级守卫一律 403。
  - 依赖：TASK-015（注册）、TASK-022（RBAC 种子）。
  - 涉及文件：`app/services/auth.py`、`migrations/versions/e3a7c1f9b2d4_backfill_member_role.py`（新建）、`tests/test_register.py`。
  - 实现要求：① `register_user` 在与 `create_user` **同一事务**内绑定 `member` 角色；② `member` 角色缺失（库未到 Alembic head）时抛 `RuntimeError` 快速失败，不允许静默产出零权限用户；③ 数据迁移把存量无角色用户补绑 `member`（只补 `user_roles` 为空的用户；`ON CONFLICT DO NOTHING` 幂等；downgrade 显式 no-op——无法区分回填的与应用侧绑定的 member）。
  - 验收标准：注册后用户角色恰为 `[member]`；新 member 登录后挂 `team:read` 守卫的端点 200、`team:create` 403；并发注册 409 语义不回归。
  - 测试要求：`test_register.py` 增默认角色断言与功能级守卫端到端断言；全量回归无新增失败。
- [x] TASK-083 我的权限集合与权限矩阵端点
  - 目标：前端按钮级显隐与权限页有真实数据源（关闭 D4/Q1）。
  - 依赖：TASK-023（权限判定）、TASK-022（种子）。
  - 涉及文件：`app/api/v1/users.py`、`app/api/v1/permissions.py`（新建）、`app/api/v1/__init__.py`、`app/services/rbac.py`（新建）、`app/schemas/user.py`、`app/schemas/role.py`（新建）、`tests/test_rbac_admin_api.py`（新建）。
  - 实现要求：① `GET /users/me/permissions` 仅需登录，返回当前用户有效权限名集合（与 `require_permission` 同一数据源 `get_user_permissions`，去重、字典序）；② `GET /permissions` 返回角色-权限矩阵，守卫选 **user:update**（种子中仅 admin 持有）——矩阵是 RBAC 管理面配置，member 的 `user:read` 是协作语义，不应顺带看到全部配置；③ Router 不直接 import CRUD（`services/rbac.py` 承载矩阵装配）；④ 权限名统一字典序输出，与 me/permissions 顺序契约一致。
  - 验收标准：member 调 me/permissions 得种子 10 项；member 调矩阵 403、admin 200 且 admin 角色 22 项。
  - 测试要求：`test_rbac_admin_api.py` 10 项覆盖上述断言 + 未认证 401。
- [x] TASK-082 用户-角色管理端点（admin）
  - 目标：admin 能在界面上给用户授/撤角色（此前只能手改数据库）。
  - 依赖：TASK-081（默认角色语义）。
  - 涉及文件：`app/api/v1/users.py`、`app/services/user.py`、`app/crud/user.py`（get_users 已有）、`app/schemas/user.py`、`tests/test_rbac_admin_api.py`。
  - 实现要求：① `GET /users`（user:read，skip/limit 分页，单查询批量带角色名，不 N+1）；② `GET/PUT /users/{user_id}/roles`——GET 挂 user:read，PUT 挂 user:update；③ PUT 为**全量替换**语义（不在清单中的既有授权被撤销、缺失的补授），Service 层 commit（写路径事务边界在 Service）；④ 守卫：目标用户/角色名不存在 → 404；**禁止操作自己的角色** → 403（没有「至少一个 admin」的全局不变量，允许自我降权等于一键锁死系统）；⑤ 路由声明顺序：`/users/me/*` 在 `/users/{user_id}/*` 之前。
  - 验收标准：admin 替换角色后 GET 与 PUT 视角一致（按 Role.id 排序）；member PUT 403；未知角色/用户 404；改自己 403。
  - 测试要求：`test_rbac_admin_api.py` 覆盖上述全部路径。
- [x] TASK-084 前端权限闭环：权限页 + usePermission 真实数据 + 菜单权限过滤
  - 目标：前端与后端 RBAC 能力对齐，权限页从「能力审计」升级为真实管理（关闭 D4 前端侧）。
  - 依赖：TASK-081/082/083（端点）。
  - 涉及文件：`src/api/permission.ts`、`src/types/permission.ts`（新建）；`src/stores/auth.ts`、`src/composables/usePermission.ts`、`src/utils/request.ts`（增 put）、`src/router/routes.ts`、`src/components/layout/AppSidebar.vue`、`src/views/permission/PermissionManage.vue`（新建）；`tests/unit/{store-auth,composables-usePermission,router}.spec.ts`（演进）。
  - 实现要求：① auth store 登录/守卫拉用户资料时**并行**拉 `/users/me/permissions`，失败归空集合不阻塞登录；② `usePermission` 改为 store 只读视图，`can/canAny` 语义不变；③ 新增「权限管理」页：角色-权限矩阵（只读）+ 用户角色分配（编辑对话框，PUT 全量替换）；两区块都以 `can('user:update')` 控制，无权限时 el-alert 诚实说明；④ 菜单项支持 `requiresAnyPermission`，侧边栏按真实权限过滤入口（隐藏只管入口观感，后端 403 兜底）；⑤ 403 仍由统一拦截器提示，不做页面级跳转（member 权限已够日常使用，403 场景收敛）。
  - 验收标准：四门全绿（typecheck/lint/test/build）；admin 登录可见「权限管理」菜单且可改角色；member 不可见且直输 URL 得到降级提示。
  - 测试要求：store 权限并行拉取与失败降级、composable 响应式判定、路由表演进断言；单测 72 项不回退。

## Phase 17：找人体验与占位清理（TASK-085~087）

- [x] TASK-085 `GET /users` 增加 `q` 搜索参数
  - 目标：邀请成员/分配角色场景的「按名字找人」——裸自增 id 列表无法定位用户，管理员无从判断某个 id 对应哪个成员（用户反馈）。
  - 依赖：TASK-082（GET /users）。
  - 涉及文件：`app/crud/user.py`、`app/services/user.py`、`app/api/v1/users.py`、`tests/test_rbac_admin_api.py`。
  - 实现要求：① `q` 为可选 Query（max_length=64），按用户名/邮箱做子串、大小写不敏感匹配（与任务搜索同款 `ILIKE '%q%'` 口径）；② 空串/纯空白视同不过滤；③ 与列表同权（user:read），不新增权限项；④ 结果仍按 id 升序，分页语义不变。
  - 验收标准：q 按用户名命中（含大写查询）与邮箱子串命中；无命中 → 空列表（不是 404）；空白 q 列出全量。
  - 测试要求：`test_rbac_admin_api.py` 增 2 项（搜索语义 + 未认证 401）。
- [x] TASK-086 前端邀请成员改为用户选择器
  - 目标：消灭「手填数字 ID」交互——选择器直接展示用户名、邮箱与 id，选中值即 user_id。
  - 依赖：TASK-085（q 参数）。
  - 涉及文件：`frontend/src/api/permission.ts`（listUsers 加 q）、`frontend/src/views/team/TeamMembers.vue`、`frontend/src/views/permission/PermissionManage.vue`。
  - 实现要求：① 邀请对话框改 el-select 远程搜索（filterable+remote）：打开预载前 50 个用户，输入关键词搜用户名/邮箱，选项展示 `用户名（#id · 邮箱）`；② 权限页用户列表加「按用户名/邮箱搜索」（回车/按钮触发）；③ 搜索失败清空候选不阻塞对话框，错误由请求层统一提示；④ 同步更新 TeamMembers「已知限制」文案。
  - 验收标准：四门全绿；admin 在邀请对话框可按名字/邮箱选中目标用户完成邀请。
  - 测试要求：既有 72 项单测不回退（选择器数据行为由后端契约 12 项覆盖；组件测试口径见 DECISIONS 057）。
- [x] TASK-087 项目详情页任务/看板 Tab 接真实组件（清除阶段 8 遗留占位）
  - 目标：任务模块（TASK-072）早已实现，但项目详情页「任务列表/任务看板」两个 Tab 仍渲染阶段 8 时期的 PagePlaceholder——用户在项目内看不到任务，只见「待实现」占位（用户反馈截图）。
  - 依赖：TASK-072（TaskList/TaskBoard）。
  - 涉及文件：`frontend/src/views/task/TaskList.vue`、`frontend/src/views/task/TaskBoard.vue`（加可选 props）、`frontend/src/views/project/ProjectDetail.vue`。
  - 实现要求：① 两个任务组件新增可选 `initialProjectId`（存在且在可见列表中时预选该项目，否则回落第一个项目）与 `embedded`（隐藏页内大标题，避免与外层 Tab 标签重复）；② ProjectDetail 两个 Tab 改为 `lazy` 内嵌真实组件并传入当前项目 id；③ 移除 ProjectDetail 对 PagePlaceholder 的引用；④ 不改路由与「我的任务」独立页行为（props 均可选，缺省路径与原版一致）。
  - 验收标准：四门全绿；项目详情 → 任务列表/看板 Tab 直接展示该项目的任务与看板。
  - 测试要求：既有 72 项单测不回退（props 可选、缺省行为不变）；生产冒烟确认产物不再含「阶段 8（任务模块，待实现）」文案。

## Phase 18：生产可靠性地基（TASK-088~092）

> 依据：`docs/ENTERPRISE_READINESS.md`（缺口 A1/A2/A3/B8/B9/C1/C7/C8）。
> 这一 Phase 与租户形态无关，先做能立刻降低上线风险，也为 Phase 19 的结构性改造
> 提供可观测性（改造期间最需要的就是指标与健康检查）。

- [x] TASK-088 健康检查补齐与存活/就绪分离
  - 目标：关闭规格 §32 欠债——补齐 `/health/db`、`/health/redis`，并新增 `/health/live` 与 `/health/ready`，把「进程活着」与「依赖可用」两种语义分开。
  - 依赖：无。
  - 涉及文件：`app/main.py`、`app/core/config.py`（如需探针超时配置）、`tests/test_health.py`（新建）、`docker-compose.yml`、`docker-compose.prod.yml`、`docs/DEPLOYMENT.md`。
  - 实现要求：① `/health/live` 恒 200（仅进程）；② `/health/ready` 在依赖不可用时返回 503，body 给出各项明细；③ `/health/db`、`/health/redis` 单依赖明细；④ **既有 `/health` 行为不变**（向后兼容：已有测试与 compose healthcheck 依赖它）；⑤ compose 的 app healthcheck 切到 `/health/ready`，nginx 保持探自有端点；⑥ 订正 `docs/DEPLOYMENT.md` 第 96–100 行的漂移（文档列了三个端点，代码只有 `GET /health` 一个）。
  - 验收标准：四个端点语义各自成立；停掉 PostgreSQL 后 `/health/ready` 返回 503，而 `/health/live`、`/health` 仍 200 且 `/health` 的 body 标 `database: down`；`/health` 既有响应结构未变。
  - 测试要求：`tests/test_health.py` 覆盖四项正常路径 + DB 不可用 / Redis 不可用 / 两者都不可用三种降级路径（用可注入探针打桩，不真停容器）；含「探针端点免认证」断言。

- [x] TASK-089 Celery Beat 周期调度与归档终态保留
  - 目标：关闭 **C1**——`archive_operation_logs` 与 `cleanup_expired_attachments` 目前在生产**永远不会执行**（`app/` 内 `beat|crontab|beat_schedule` 0 命中、两个 compose 均无 `celery_beat`、唯一调用点在 `tests/`）。
  - 依赖：无（任务本身的重试/幂等/超时已完成并有 13+2 项测试）。
  - 涉及文件：`app/tasks/celery_app.py`、`app/core/config.py`、`docker-compose.yml`、`docker-compose.prod.yml`、`tests/test_beat_schedule.py`（新建）、`tests/test_maintenance_tasks.py`（补终态清理用例）、`docs/DEPLOYMENT.md`。
  - 实现要求：① `beat_schedule` 登记两项维护任务，间隔经 `.env` 可配，默认错峰（归档走每日低位时段、清理每小时）；② 两个 compose 增 `celery_beat` 服务（同镜像、独立命令、`restart: always`、日志轮转），配置注释写明**beat 必须单实例**（多副本会重复投递，幂等只保证无副作用、不保证不浪费队列）；③ 归档任务补**归档表终态保留策略**（保留 N 天后删除，N 可配），一并处理合规上的「存储期限最小化」；④ 维护任务的 `last_success_timestamp` 交给 TASK-090 的指标暴露。
  - 验收标准：真实 compose 栈上两个任务被 beat **自动**触发并落库/删文件；`celery -A app.tasks.celery_app inspect scheduled` 能看到下一次执行时间；归档表超出保留期的行被清理。
  - 测试要求：`beat_schedule` 契约测试（两项都在、间隔合法、callable 可解析且与任务函数名一致）；沿用既有幂等用例；新增「归档表终态清理」用例。

- [ ] TASK-090 指标端点与 5xx 统一信封
  - 目标：关闭 **A3**（规格 §1 的交付清单写着「日志与指标」，指标 0 实现）与 **B9**（5xx 不走统一信封、不进结构化日志）。
  - 依赖：TASK-088（复用健康探针）、TASK-089（维护任务时间戳）。
  - 涉及文件：`app/main.py`、`app/core/metrics.py`（新建）、`app/core/middleware.py`、`app/core/exceptions.py`、`app/core/config.py`、`requirements.txt`、`deploy/prometheus/`（新建：抓取配置 + 告警规则草案）、`tests/test_metrics.py`（新建）。
  - 实现要求：① `/metrics` 输出 Prometheus 文本格式（用 `prometheus_client`，**不自造格式**）；② 指标集：请求总数与延迟直方图（按 method + **路由模板** + status，必须用模板而非原始路径，否则 UUID 会把标签基数打爆）、进行中请求数、DB 连接池占用、Redis 操作延迟、Celery 队列深度与任务成功/失败计数、限流触发次数、维护任务 `last_success_timestamp`；③ `/metrics` 默认**不经 nginx 暴露**，仅在 `.env` 显式开启时可用，且不占限流配额；④ 全局 `Exception` handler → §26 统一信封（对外不含堆栈）+ 结构化 `exc_info` 日志并带 `request_id`。
  - 验收标准：`/metrics` 含上述指标且内容类型正确；故意制造未捕获异常时返回 JSON 信封、日志有 `request_id` 关联的 error 记录、响应体不含堆栈；两条不同 id 的请求不产生两个标签值。
  - 测试要求：指标端点契约（内容类型、关键指标名存在、路由标签不含原始 id）；500 信封用例（结构断言 + 不泄露堆栈）；标签基数用例。

- [ ] TASK-091 生产配置自检
  - 目标：关闭 **B8**——`debug=True`、`jwt_secret_key="change-me"`、连接串里的 `postgres:postgres` 让「不配任何环境变量也能跑起来」，这是企业部署事故的常见来源。
  - 依赖：无。
  - 涉及文件：`app/core/config.py`、`app/main.py`、`tests/test_config_production_guards.py`（新建）。
  - 实现要求：`APP_ENV=production` 时启动自检并**拒绝启动**：`DEBUG=true`；`jwt_secret_key` 为默认值或长度不足；`DATABASE_URL` 含默认口令；开了 `TRUST_PROXY_HEADERS` 但 `TRUSTED_PROXY_IPS` 为空。报错必须点名**哪一个**配置项有问题，不是笼统的 "invalid config"。
  - 验收标准：四种错配各自拒绝启动且报错点名；合法配置正常启动；`APP_ENV=development` 不受影响。
  - 测试要求：四条错配各 1 项拒绝用例 + 1 条合法放行 + 1 条「开发环境不检查」。

- [ ] TASK-092 文档语义护栏：端点声明 ↔ OpenAPI
  - 目标：关闭 **C8**——护栏不含「文档里声明的端点必须真实存在」，所以 A1 那类漂移能长期存活。
  - 依赖：TASK-088（否则护栏会立刻抓到 A1 的漂移——这正是它该有的行为）。
  - 涉及文件：`scripts/check_docs.py`、`tests/test_docs_consistency.py`、`docs/DEPLOYMENT.md`。
  - 实现要求：新增不变量——文档中形如 `` `GET /xxx` `` 的端点声明必须存在于 `app.openapi()`；README 声明的健康检查端点集合与代码一致。
  - 验收标准：护栏 exit 0；把一个未实现的端点写进文档能立刻报错。
  - 测试要求：用合成文档构造矛盾，断言检查器**真的会报**（延续 `docs/QUALITY.md` 第 8 节 D8 的「不空转」原则）。

## Phase 19：多租户地基（TASK-093~100）

> 用户已确认目标形态为**多租户 SaaS**。这是本项目**唯一一处结构性改造**，其余 Phase 都是加法。
> 顺序放在可靠性之后、身份之前：Phase 18 与租户无关且能立刻降低风险；Phase 20 的认证与
> 权限必须建立在租户模型之上，否则同样的改动要做两遍。

- [ ] TASK-093 租户模型与生命周期
  - 目标：引入 `tenants` 实体，确立「平台 → 租户 → 用户/团队/项目」的顶层边界。
  - 依赖：无。
  - 涉及文件：`app/models/tenant.py`（新建）、`migrations/versions/*_create_tenants.py`（新建）、`app/schemas/tenant.py`（新建）、`app/crud/tenant.py`（新建）、`app/services/tenant.py`（新建）、`app/api/v1/tenants.py`（新建）、`app/api/v1/__init__.py`、`tests/test_tenant_model.py`（新建）、`docs/DB_SCHEMA.md`。
  - 实现要求：① `tenants` 表：id / name / slug / status（active / suspended / deleted）/ 配额列（成员数上限、存储上限，具体列在 `docs/DB_SCHEMA.md` 定稿）/ created_at / updated_at；② `slug` 全局 UNIQUE；③ 状态转换白名单（active ↔ suspended、→ deleted 单向），不允许绕过；④ 平台管理员身份与租户管理员**严格区分**；⑤ 本 TASK 只做模型 + 迁移 + CRUD/Service 骨架，不接业务表。
  - 验收标准：迁移 upgrade/downgrade 往返无损；CHECK 约束拒绝非法状态；slug 冲突 409；平台管理员可创建/停用租户。
  - 测试要求：离线模型断言（列集、约束、索引）+ DB 集成（UNIQUE 冲突、CHECK 拒绝、状态机白名单、级联行为）。

- [ ] TASK-094 业务表租户化与存量回填
  - 目标：把 `tenant_id` 落到全部需要归属的业务表，并给出存量数据的一次性归属方案。
  - 依赖：TASK-093。
  - 涉及文件：`app/models/*.py`（业务模型）、`migrations/versions/*_add_tenant_id.py`（新建）、`migrations/versions/*_backfill_default_tenant.py`（新建）、`tests/test_tenant_columns.py`（新建）、`docs/DB_SCHEMA.md`。
  - 实现要求：① 需要归属的**每一张**业务表加 `tenant_id` FK→`tenants`，NOT NULL 通过「先加可空列 → 回填 → 置 NOT NULL」三步迁移达成；② **原先的全局 UNIQUE 必须租户化**（`users.username`、`users.email` 等改为 `(tenant_id, ...)` 复合 UNIQUE），否则租户 A 的用户名会挡住租户 B 的同名用户——具体清单在 `docs/DB_SCHEMA.md` 与迁移里定稿；③ 回填迁移创建一个默认租户并把全部存量行挂上去，`downgrade` 显式 no-op 并注明理由；④ 索引一律以 `tenant_id` 为前导列；⑤ 附件存储路径改为按租户分目录。
  - 验收标准：真实库中每张业务表都有 NOT NULL 的 `tenant_id` 且带 FK；复合 UNIQUE 生效（两个租户可存在同名 username、同租户内冲突）；回填后零孤儿行；迁移往返无损。
  - 测试要求：列集与约束断言；「同名跨租户可共存、同租户内冲突」的正反用例；回填脚本的幂等性与零孤儿断言。

- [ ] TASK-095 租户上下文与数据访问作用域
  - 目标：让「忘记带 `tenant_id` 条件」在结构上不可能——这是多租户最核心的隔离保证。
  - 依赖：TASK-094。
  - 涉及文件：`app/core/tenant_context.py`（新建）、`app/core/deps.py`、`app/crud/*.py`、`migrations/versions/*_row_level_security.py`（新建）、`tests/test_tenant_isolation.py`（新建）。
  - 实现要求：① 请求级 `ContextVar` 保存当前租户（由认证依赖注入），请求结束时在 `finally` 内还原；② CRUD 的列表/详情/写路径统一走「租户作用域」辅助（查询自动带 `tenant_id`、INSERT 自动注入），不依赖各 router 自觉；③ **PostgreSQL RLS 作为兜底**（`current_setting('app.tenant_id')` + 策略），应用层出 bug 时仍不越界——纵深防御，不是为了炫技（项目规则 §6）；④ 给出「绕过作用域」的**唯一**显式出口（平台管理员跨租户查询），集中在一处便于审查。
  - 验收标准：A 租户令牌请求 B 租户资源一律 404（与既有「不存在/无权不可区分」契约一致）；故意构造漏加条件的查询仍被 RLS 拦住；平台管理员跨租户查询走显式出口且被审计。
  - 测试要求：跨租户越权矩阵（读写删 × A→B）；RLS 兜底用例（直连库设 `app.tenant_id` 验证策略）；ContextVar 并发不串号。

- [ ] TASK-096 RBAC 租户化
  - 目标：把当前**全局**的 admin/member 角色体系改成租户隔离——否则一个租户的 admin 能管另一个租户。
  - 依赖：TASK-095。
  - 涉及文件：`app/models/role.py`、`app/models/user_role.py`、`app/models/role_permission.py`、`migrations/versions/*_tenantize_rbac.py`（新建）、`app/crud/role.py`、`app/crud/permission.py`、`app/services/rbac.py`、`app/api/v1/permissions.py`、`app/api/v1/users.py`、`tests/test_rbac_tenant.py`（新建）。
  - 实现要求：① 角色与授权关系带 `tenant_id`；② 种子（admin/member + 22 项权限）按租户复制，新租户创建时自动播种；③ `GET /users/me/permissions` 返回**当前租户内**的有效权限集合；④ 权限矩阵端点只看本租户；⑤ 平台管理员不自动获得租户内权限（避免横向放大）。
  - 验收标准：租户 A 的 admin 对租户 B 的资源无任何额外能力；新租户创建后立即有完整种子；切换租户时 `me/permissions` 结果随之变化。
  - 测试要求：跨租户角色越权矩阵；种子播种幂等；`me/permissions` 与 `require_permission` 同一数据源断言（延续 TASK-083 的口径）。

- [ ] TASK-097 认证与租户绑定
  - 目标：令牌必须携带租户身份，且登录/切换租户语义明确。
  - 依赖：TASK-096。
  - 涉及文件：`app/core/security.py`、`app/core/deps.py`、`app/services/auth.py`、`app/api/v1/auth.py`、`app/schemas/auth.py`、`app/crud/refresh_token.py`、`tests/test_auth_tenant.py`（新建）。
  - 实现要求：① Access/Refresh Token 增加租户声明并在校验时强制与资源租户一致；② 用户属于多个租户时的登录语义（登录选择租户 / 切换租户换取新令牌）；③ Refresh Token 记录绑定租户，轮换不跨租户；④ **不允许一个令牌横跨两个租户**——切换租户必须换取新令牌并使旧令牌作用域明确；⑤ 前端配合见 TASK-100。
  - 验收标准：跨租户使用令牌被拒（401/404 不可区分）；切换租户后新令牌只对本租户生效；同一用户在两租户的权限互不影响。
  - 测试要求：令牌缺租户声明 / 声明与资源不符的拒绝用例；切换租户链路端到端；refresh 轮换不跨租户。

- [ ] TASK-098 租户成员与邀请
  - 目标：把「用户 → 租户」的加入链路做实（邀请、加入、移除、状态）。
  - 依赖：TASK-097。
  - 涉及文件：`app/models/tenant_member.py`（新建）、`app/schemas/tenant.py`、`app/services/tenant.py`、`app/api/v1/tenants.py`、`tests/test_tenant_members.py`（新建）。
  - 实现要求：① 用户与租户的成员关系（角色、状态 invited/active/suspended）；② 邀请用一次性令牌（投递走 TASK-110 的邮件；本轮先支持平台管理员代加入 + 结构化日志留痕）；③ 同一用户可属于多个租户，用户名唯一性按 TASK-094 的复合 UNIQUE 口径；④ 移除成员时其在本租户内的资源处置策略明确（转移/保留），写进 `docs/DB_SCHEMA.md`。
  - 验收标准：邀请 → 加入 → 移除全链路可跑；被移除后立即失去该租户全部访问权；重复邀请幂等。
  - 测试要求：成员状态机、越权移除（非本租户管理员 403/404）、移除后权限立即失效。

- [ ] TASK-099 租户级配置与配额执行
  - 目标：让配额**真的被执行**，而不是数据库里躺着几个数字。
  - 依赖：TASK-098。
  - 涉及文件：`app/services/quota.py`（新建）、`app/core/middleware.py`、`app/services/team.py`、`app/services/task.py`、`app/services/storage.py`、`app/core/exceptions.py`、`tests/test_tenant_quota.py`（新建）。
  - 实现要求：① 成员数 / 存储量 / 限流档位三类配额的可配置执行；② 超限返回专用错误与文案，且在创建路径上**前置**校验；③ 存储量统计口径明确（含附件实际占用与孤儿文件）；④ 限流档位按租户分级，与 TASK-102 的登录专项限流衔接。
  - 验收标准：成员数达上限后邀请被拒；存储超限后上传被拒；不同租户可配不同限流档位且互不影响。
  - 测试要求：边界值（刚好达上限、超一个）、并发创建不越过配额、配额变更立即生效。

- [ ] TASK-100 跨租户隔离回归与前端租户切换
  - 目标：把隔离性质固化成回归矩阵，并让前端在租户语境下可用。
  - 依赖：TASK-093~099。
  - 涉及文件：`tests/test_tenant_isolation_matrix.py`（新建）、`frontend/src/stores/auth.ts`、`frontend/src/api/auth.ts`、`frontend/src/api/tenant.ts`（新建）、`frontend/src/views/tenant/TenantSettings.vue`（新建）、`frontend/src/components/layout/AppHeader.vue`、`frontend/src/router/routes.ts`、`frontend/tests/unit/*.spec.ts`。
  - 实现要求：① 后端回归矩阵覆盖「**全部**资源型端点 × 跨租户访问」，不只取样；② 前端增加租户切换器（多租户用户）与租户设置页（本租户信息、成员、配额用量）；③ 切换租户即换令牌，前端不得缓存跨租户数据（store 必须重置）；④ 关闭前端既有的与租户相关的降级项。
  - 验收标准：后端隔离矩阵全绿；前端四门全绿；切换租户后列表/详情全部刷新，无上一个租户的残留数据。
  - 测试要求：隔离矩阵覆盖全部资源型端点；前端 store 切换重置的单测。

## Phase 20：身份与安全硬化（TASK-101~106）

> 用户已确认档位为「本地账号加固 + MFA + 企业目录（OIDC/LDAP）」。这一 Phase 决定
> 「账号体系」能否过采购与安全评审。

- [ ] TASK-101 密码策略与改密/重置
  - 目标：关闭 **B1**——`app/schemas/user.py` 里 `password: str` 是裸字段（无长度、无复杂度、无弱口令校验），且全仓库无密码找回路径。
  - 依赖：无（改密与强度校验不依赖邮件；重置的投递接 TASK-110）。
  - 涉及文件：`app/schemas/user.py`、`app/services/auth.py`、`app/api/v1/auth.py`、`app/core/config.py`、`app/crud/refresh_token.py`、`tests/test_password_policy.py`（新建）、`docs/SECURITY.md`。
  - 实现要求：① 强度校验：最小长度（默认 12，可配）+ 至少 3 类字符 + 常见弱口令表 + 不得包含用户名/邮箱（大小写不敏感）；② `POST /auth/change-password`（需旧密码，改后**吊销该用户全部 refresh token**）；③ 重置流程骨架（一次性令牌的生成/校验/消费，投递通道在 TASK-110 接邮件，本轮先支持管理员触发 + 结构化日志留痕）；④ 校验在 **Schema 层与 Service 层都做**（Schema 拦早、Service 兜底，堵住绕过 Schema 的调用路径）。
  - 验收标准：弱口令 422 且文案说明原因；改密后旧 refresh token 全部失效；重置令牌一次性。
  - 测试要求：强度矩阵逐条（长度/字符类/弱口令/含用户名）；改密后令牌失效端到端；重置令牌重复使用被拒；并发改密不产生半截状态。

- [ ] TASK-102 登录防护：失败计数、锁定与专项限流
  - 目标：关闭 **B2**——暴力破解目前只靠全站统一 `60/60s` 兜底，登录端点没有更严格的独立配额。
  - 依赖：无（限流档位与 TASK-099 衔接）。
  - 涉及文件：`app/services/auth.py`、`app/core/middleware.py`、`app/core/redis_keys.py`、`tests/test_login_protection.py`（新建）。
  - 实现要求：① 失败计数按 `username` 与按 `IP` 双维度落 Redis（带 TTL）；② 超阈值（默认 5 次 / 15 分钟，可配）→ 锁定（默认 15 分钟，可配），返回 429 且文案**不泄露账号是否存在**；③ 登录端点独立限流档位；④ 成功登录清零计数；⑤ 安全事件结构化日志（供 TASK-120 的告警消费）；⑥ 锁定必须可观测、可解除（管理员解锁入口或自动到期）。
  - 验收标准：达阈值后即使密码正确也被拒；到期自动恢复；不同 IP 打同一账号同样触发账号维度锁定；成功路径无额外延迟开销。
  - 测试要求：阈值边界、锁定期间正确密码被拒、解锁后恢复、计数成功清零、「不泄露账号存在性」文案断言。

- [ ] TASK-103 JWT 硬化与会话管理
  - 目标：关闭 **A4 / B4 / B5**——`jwt_blacklist_key()` 只定义了 Key 没接校验链路；令牌无 `iss`/`aud`/`kid`；无 refresh 重用检测；无会话列表、「强制下线」无处可做。
  - 依赖：TASK-101（改密要能失效令牌）、TASK-097（令牌租户声明）。
  - 涉及文件：`app/core/security.py`、`app/core/config.py`、`app/core/deps.py`、`app/services/auth.py`、`app/api/v1/auth.py`、`app/schemas/auth.py`、`app/crud/refresh_token.py`、`tests/test_jwt_hardening.py`（新建）、`tests/test_session_management.py`（新建）、`docs/DECISIONS.md`。
  - 实现要求：① 加 `iss`/`aud` 并在校验时强制；② 多密钥 `kid` + 验证窗口（新密钥签发、旧密钥在 TTL 内仍可验签），给出轮换 runbook；③ **接上 Access Token 黑名单**（`app/core/redis_keys.py::jwt_blacklist_key` 的落地，TTL ≥ 剩余寿命）：登出 / 禁用 / 改密 / 会话下线时写入；④ **Refresh 重用检测**：已撤销 jti 被再次使用 → 吊销该用户**全部** refresh token + 安全事件日志；⑤ 会话端点 `GET /auth/sessions`、`DELETE /auth/sessions/{id}`、`POST /auth/logout-all`。
  - 验收标准：登出后旧 Access Token **立即** 401（不再等 TTL 到期）；禁用账号后令牌立即失效；复用一个已轮换的 refresh token → 全族吊销且有日志；会话列表可列出并下线指定会话。
  - 测试要求：黑名单命中/未命中/TTL 过期；`iss`/`aud` 缺失或错误被拒；`kid` 轮换窗口（新密钥签、旧密钥验仍通过）；重用检测的全族吊销断言；会话列表越权断言（A 看不到 B 的会话）。
  - 风险与代价（必须写进 DECISIONS）：黑名单意味着**每个认证请求多一次 Redis 往返**。当前限流已在热路径访问 Redis，边际成本可控；但要明确与真实需求的绑定（项目规则 §7），并**显式**给出 Redis 不可用时的行为（建议 fail-open + warning，与限流同一取舍）——这条取舍不能默认。

- [ ] TASK-104 传输与浏览器安全硬化
  - 目标：关闭 **B6**——`Content-Security-Policy` 0 命中、TLS 未落地、安全头不完整。
  - 依赖：无。
  - 涉及文件：`nginx/nginx.conf`、`frontend/nginx.conf`、`docker-compose.prod.yml`、`docs/DEPLOYMENT.md`、`tests/test_nginx_config.py`。
  - 实现要求：① CSP 先 `Report-Only` 观察再切强制，并在文档里给出「从报告到强制」的判定标准；② 补 `Permissions-Policy` / `COOP` / `COEP`；③ TLS **二选一落地并写清**：(a) 本层 `listen 443 ssl` + 证书挂载 + HSTS，或 (b) 交付上游 LB 的等价配置要求与验收清单——两层不能都以为对方在管。
  - 验收标准：真实栈冒烟——CSP 报告模式下的违规项已逐条解释；安全头在 2xx/4xx/5xx 上都存在（`always` 语义）；TLS 路径按所选方案可验证（`openssl s_client` 或上游配置清单）。
  - 测试要求：安全头契约（两层各 4–5 条）；CSP 指令集断言；若选 (b)，断言「不发 HSTS」这一**有意**行为不被后人误加。

- [ ] TASK-105 MFA（TOTP）与恢复码
  - 目标：关闭 **B3** 的一半——提供第二因子。
  - 依赖：TASK-102（MFA 校验失败应计入失败计数）。
  - 涉及文件：`app/models/user.py`（+ 迁移）、`app/services/mfa.py`（新建）、`app/api/v1/auth.py`、`app/schemas/auth.py`、`tests/test_mfa.py`（新建）、`frontend/src/views/profile/Profile.vue`。
  - 实现要求：① TOTP 密钥**加密存储**且不入日志；② 绑定流程（二维码 + 校验）、校验（时间窗口容错）、**恢复码**（一次性、加密存储、用后作废）；③ 关闭 MFA 需二次验证；④ 管理员可强制重置某用户的 MFA；⑤ 开关化（`MFA_ENABLED`，默认关，避免把小规模部署搞复杂）。
  - 验收标准：开启后登录需要第二因子；恢复码可用且一次性；错误码被拒且计入 TASK-102 的失败计数。
  - 测试要求：时间窗口容错边界、错误码拒绝、恢复码一次性、密钥不出现在日志与 API 响应。

- [ ] TASK-106 企业目录 SSO（OIDC / LDAP）
  - 目标：关闭 **B3** 的另一半——满足「必须接企业目录才可上线」的场景。
  - 依赖：TASK-097（租户绑定）、TASK-105（登录链路）。
  - 涉及文件：`app/services/oidc.py`（新建）、`app/services/ldap.py`（新建，若确需）、`app/api/v1/auth.py`、`app/core/config.py`、`app/schemas/auth.py`、`tests/test_oidc.py`（新建）、`docs/DEPLOYMENT.md`。
  - 实现要求：① OIDC 授权码流程 + PKCE；② 用户映射按 `sub` 优先、`email` 兜底，关联到既有账号并落到该租户的默认角色（与 TASK-081 的 `member` 口径一致）；③ **租户级 IdP 配置**（每个租户接自己的 IdP）；④ 开关化（默认关，不影响本地账号路径）；⑤ LDAP 视实际需求决定是否实现，若要实现必须明确同步策略与冲突处理。
  - 验收标准：本地假 IdP 上走通登录；首次登录自动建号并落默认角色；IdP 不可用时本地账号路径不受影响。
  - 测试要求：用本地假 IdP（不依赖外网 CI）覆盖授权码流程、`state` 参数校验（CSRF）、`sub` 与 `email` 映射、未知租户拒绝。

## Phase 21：合规与数据治理（TASK-107~108）

> 合规档位按「个人信息保护法 + GDPR 口径」执行；等级保护与行业认证**不作为代码承诺**。

- [ ] TASK-107 数据主体权利与保留策略
  - 目标：关闭 **D11**——无导出、无注销、无保留期声明；叠加 C1 后曾等于「数据永久保留」。
  - 依赖：TASK-089（归档终态清理）。
  - 涉及文件：`app/services/data_subject.py`（新建）、`app/api/v1/users.py`、`app/tasks/maintenance_tasks.py`、`docs/DEPLOYMENT.md`、`tests/test_data_subject.py`（新建）。
  - 实现要求：① 「导出我的数据」（JSON，含任务/评论/附件元数据）；② 注销账号（软删 + 数据处置策略，与租户成员关系一并处理）；③ 每类数据的保留期**有明文声明且由代码执行**（与 TASK-089 的归档终态清理对齐）；④ 隐私声明文本。
  - 验收标准：导出内容完整且**只含本人**数据（越权断言）；注销后不可登录、按策略处置、审计留痕；保留期到期后数据真的被删除。
  - 测试要求：跨租户/跨用户导出越权断言；注销后登录被拒；保留期清理用例。

- [ ] TASK-108 审计日志强化
  - 目标：关闭 **D5**——当前时间线缺「从哪里」（无 IP、无 UA），列表无筛选、无 `total`。
  - 依赖：TASK-105（框架）、TASK-090（统一信封与日志口径）。
  - 涉及文件：`app/models/operation_log.py`（+ 迁移）、`app/services/operation_log.py`、`app/api/v1/logs.py`、`app/crud/operation_log.py`、`tests/test_operation_log_api.py`、`docs/DB_SCHEMA.md`、`docs/SECURITY.md`。
  - 实现要求：① `operation_logs` 增 `ip` / `user_agent`（**IP 属个人信息，保留期与用途必须在文档里写清**）；② `GET /logs` 增筛选参数（类型/时间范围/操作人）与 `total`；③ 归档表查询入口；④ **追加写**权限收敛建议（部署时应用账号不持有 `UPDATE/DELETE`），写进 `docs/DEPLOYMENT.md`。
  - 验收标准：筛选与 `total` 生效；IP/UA 落库且脱敏口径与日志过滤器一致；跨租户查询被拒。
  - 测试要求：筛选组合、`total` 正确性、越权断言、IP 采集在反代下的正确性（复用 `TRUSTED_PROXY_IPS` 语义）。

## Phase 22：产品补齐（TASK-109~118）

> 排序依据：体感影响 × 依赖关系。邮件是基础设施，后面几项依赖它。
> 这一 Phase 决定的是**留存**，可以边用边补——但它也是「不如微信群」这个判断的来源。

- [ ] TASK-109 邮件能力
  - 目标：关闭 **D1**——全仓库 `smtp|send_email|EmailStr` 0 命中，站内通知的到达率等于「用户主动打开」。
  - 待决策：邮件通道（企业自有 SMTP / 云 SES / 两者都要）。本 TASK 按「抽象 + 可插后端，默认企业自有 SMTP」推进；若不符请先改本节。
  - 涉及文件：`app/services/email.py`（新建）、`app/core/config.py`、`app/tasks/notification_tasks.py`、`requirements.txt`、`tests/test_email.py`（新建）。
  - 实现要求：① SMTP 抽象 + 可插后端；② 模板（邀请 / 重置密码 / 通知摘要）；③ 全部经 Celery 队列发送，**不阻塞请求路径**；④ 退信与失败处理（重试 + 终态记录）；⑤ 邮件内容不泄露敏感信息，口径与 `docs/SECURITY.md` 的脱敏要求一致。
  - 验收标准：本地假 SMTP 上能发出三类邮件；SMTP 不可用时任务重试且不阻塞接口；模板渲染含租户与用户上下文。
  - 测试要求：用本地假 SMTP（不依赖外网）覆盖发送、重试、退信分支；模板渲染断言；不泄露敏感字段断言。

- [ ] TASK-110 邀请邮件与密码重置投递
  - 目标：把 TASK-098 / TASK-101 里「骨架已就绪、投递通道待接」的部分接上。
  - 依赖：TASK-098（邀请）、TASK-101（重置令牌）、TASK-109（邮件）。
  - 涉及文件：`app/services/tenant.py`、`app/services/user.py`、`app/tasks/notification_tasks.py`、`tests/test_invite_email.py`（新建）。
  - 实现要求：① 邀请发送一次性链接，过期与重复使用规则明确；② 重置密码发送一次性链接；③ 链接中的令牌**不得进入任何日志**；④ 被邀请人尚未注册时的处理路径明确。
  - 验收标准：邀请 → 收信 → 完成加入全链路可跑；链接过期后失效；令牌不出现在日志与审计记录中。
  - 测试要求：端到端链路、过期与其他用户盗用的拒绝用例、日志不含令牌断言。

- [ ] TASK-111 通知 link / resource_id 与前端跳转
  - 目标：关闭 **D2**——用户看到「任务已分配给你」但点不动，是降级项里最影响体感的一个。
  - 依赖：无。
  - 涉及文件：`app/models/notification.py`（+ 迁移）、`app/schemas/notification.py`、`app/services/task.py`、`frontend/src/types/notification.ts`、`frontend/src/views/notification/NotificationList.vue`、`frontend/src/components/layout/NotificationBell.vue`、`tests/test_notification_api.py`。
  - 实现要求：① 输出侧新增 `resource_type` / `resource_id`（**不破坏既有契约**，前端不必解析正文猜 id）；② 派发点补齐这三项；③ 前端接线跳转并关闭页面上的降级提示（DECISIONS 054 的降级口径随之解除）；④ 目标资源已删除时给出可读兜底。
  - 验收标准：点击通知跳到正确资源；资源不存在时给出可读提示而不是空白页；既有通知契约不回归。
  - 测试要求：字段落库与返回断言、派发点覆盖断言、前端跳转与兜底单测。

- [ ] TASK-112 评论通知与 @提及
  - 目标：关闭 **D3 + D10**——协作回路只补了「分配 + 流转」，评论与提及是核心缺口。
  - 依赖：TASK-111。
  - 涉及文件：`app/services/comment.py`、`app/services/notification.py`、`app/schemas/comment.py`、`frontend/src/views/task/TaskDetail.vue`、`tests/test_comment_notification.py`（新建）。
  - 实现要求：① 评论 → 任务负责人与创建者收到通知；② `@用户名` → 被提及者收到通知（解析规则明确、**不误伤邮箱里的 `@`**）；③ 提及对象必须是本租户可见成员；④ 同一评论不重复轰炸（去重）。
  - 验收标准：评论后相关人收到通知且可跳转；跨租户提及被拒；去重生效。
  - 测试要求：提及解析边界（邮箱、中文名、不存在的用户名）、跨租户提及拒绝、去重。

- [ ] TASK-113 列表 total 与分页口径
  - 目标：关闭 **D4**——8 个列表端点无 `total`，前端只能「上一页/下一页」，且偏移量分页在并发写入下可能跨页重复或漏项。
  - 待决策：显式 `COUNT(*)` 还是迁移 cursor 分页。**按「显式 count + `total`」推进**（当前表规模下可接受），cursor 分页留作容量数据驱动后的优化项。这与 `docs/QUALITY.md` 第 8 节 D1 的记录一致，属于**重新决策**而非顺手改。
  - 依赖：无。
  - 涉及文件：`app/schemas/common.py`（新建或扩展）、8 个 `app/api/v1/*.py`、`app/crud/*.py`、`frontend/src/api/*.ts`、`frontend/src/views/**`、`tests/test_pagination_total.py`（新建）。
  - 实现要求：① 统一分页响应形状（`items` + `total` + `skip`/`limit`），**一次决策全站统一**；② 查询与 `COUNT(*)` 在同一事务内，避免计数与数据不一致；③ 前端改为展示总数与页码；④ 记录 `COUNT(*)` 的代价与迁移 cursor 的触发条件（写进 DECISIONS）。
  - 验收标准：所有列表端点返回 `total` 且与实际行数一致；前端显示「共 N 条」；越权场景不泄露他人总数。
  - 测试要求：`total` 正确性（含筛选条件叠加）、空结果、跨租户不泄露计数、响应形状契约。

- [ ] TASK-114 跨项目「我的任务」与工作台聚合
  - 目标：关闭 **D7**——当前 `GET /tasks` 的 `project_id` 必填，用户要看「我的任务」得先想清楚任务在哪个项目里，违背语义。
  - 依赖：TASK-113（分页口径）、TASK-115（聚合）。
  - 涉及文件：`app/api/v1/tasks.py`、`app/services/task.py`、`app/crud/task.py`、`frontend/src/views/dashboard/Dashboard.vue`、`frontend/src/views/task/TaskList.vue`、`tests/test_my_tasks.py`（新建）。
  - 实现要求：① 新增跨项目任务查询（`assignee_id = 当前用户`，租户内）；② 复用 TASK-113 的分页口径；③ 前端「我的任务」独立视图 + 工作台聚合；④ 关闭前端既有的降级提示。
  - 验收标准：跨项目拉取只含我参与的项目下的任务且只含本租户；分页与筛选生效；前端独立视图可用。
  - 测试要求：跨租户与跨项目可见性、分页、排序；既有 `project_id` 必填路径不回归。

- [ ] TASK-115 项目/团队统计端点
  - 目标：关闭 **D6**——`ProjectRead` 无状态/成员数/任务数/进度，团队负责人看不到「这个项目还剩多少活」。
  - 依赖：无。
  - 涉及文件：`app/api/v1/projects.py`、`app/api/v1/teams.py`、`app/services/project.py`、`app/services/team.py`、`app/schemas/project.py`、`app/schemas/team.py`、`tests/test_project_stats.py`（新建）、`frontend/src/views/project/*.vue`、`frontend/src/views/team/*.vue`。
  - 实现要求：① 任务数按状态聚合、进度口径**明确定义**（写明分母是哪几个状态）；② 单查询聚合，避免 N+1；③ 前端卡片展示真实数字并移除既有降级提示。
  - 验收标准：统计数字与真实数据一致（含零任务项目）；无 N+1（沿用既有运行时护栏）；跨租户不泄露。
  - 测试要求：聚合正确性、零任务与全完成边界、N+1 断言、越权断言。

- [ ] TASK-116 SSE 实时通知
  - 目标：关闭 **D8**——通知靠轮询，无推送。
  - 依赖：TASK-099（连接配额）。
  - 涉及文件：`app/api/v1/notifications.py`、`app/core/redis_keys.py`、`app/services/notification.py`、`frontend/src/stores/notification.ts`、`nginx/nginx.conf`、`tests/test_sse.py`（新建）。
  - 实现要求：① SSE（单向、跨代理简单，优先于 WebSocket）；② Redis Pub/Sub 作为多副本下的广播通道；③ 反代需关闭缓冲并放宽读超时（`proxy_buffering off`），写进契约测试；④ 断线重连与心跳；⑤ 连接数上限（与 TASK-099 衔接）。
  - 验收标准：真实栈上通知在 1s 内到达前端；反代配置正确（不缓冲）；断线后自动重连。
  - 测试要求：SSE 事件流契约、越权（只能订自己的通知）、反代配置契约、心跳与超时。

- [ ] TASK-117 批量操作与 CSV 导入导出
  - 目标：关闭 **D9**——无批量指派/流转/删除，无成员导入，无数据导出。
  - 依赖：TASK-099（导出配额）。
  - 涉及文件：`app/api/v1/tasks.py`、`app/services/task.py`、`app/api/v1/teams.py`、`tests/test_bulk_operations.py`（新建）。
  - 实现要求：① 批量指派/流转/删除，**逐条校验权限与状态机**（不走捷径）；② 部分失败时的返回语义明确（成功几条、失败几条、原因）；③ CSV 导入成员的校验与错误行报告；④ 导出受配额约束。
  - 验收标准：批量操作逐条校验生效（含故意混入无权的一条）；部分失败返回可读报告；导入非法行被拒且指出行号。
  - 测试要求：批量越权（混入无权条目必须失败且不产生半截写入）、部分失败语义、导入边界。

- [ ] TASK-118 到期提醒与汇总邮件
  - 目标：关闭 **D3** 的最后一环——任务到期提醒。
  - 依赖：TASK-089（beat）、TASK-109（邮件）。
  - 涉及文件：`app/tasks/notification_tasks.py`、`app/tasks/celery_app.py`、`app/core/config.py`、`tests/test_due_reminders.py`（新建）。
  - 实现要求：① `due_at` 临近/逾期提醒（阈值可配）；② 幂等（同一任务同一阈值只发一次）；③ 汇总邮件按人合并（避免一任务一封）；④ 按租户时区与开关。
  - 验收标准：真实栈上到期任务产生提醒且不重复；关闭开关后不发；汇总邮件按人合并。
  - 测试要求：幂等性、阈值边界、时区处理、开关生效。

## Phase 23：工程化与交付（TASK-119~127）

> 用户已确认交付底座为 **Docker Compose 与 Kubernetes 都要**。K8s 清单必须复用
> TASK-088 的存活/就绪探针语义与 TASK-089 的「beat 单副本」约束。

- [ ] TASK-119 备份与恢复
  - 目标：关闭 **C2**——数据丢失不可逆，当前连 `pg_dump` 都没有（非测试代码 0 命中）。
  - 依赖：TASK-123（附件与对象存储备份）。
  - 涉及文件：`scripts/backup.sh`、`scripts/restore.sh`（新建）、`docker-compose.prod.yml`、`deploy/`（新建）、`docs/DEPLOYMENT.md`、`tests/test_backup_scripts.py`（新建）。
  - 实现要求：① 数据库定时备份 + 附件（与对象存储）备份；② 恢复脚本 + **恢复演练**（写了没跑过不算）；③ **多租户下的恢复粒度**必须明确回答（整库恢复 vs 按租户恢复），并写明能力边界；④ RPO/RTO 写进文档且与调度实际一致。
  - 验收标准：备份产物能在干净栈上完整恢复并跑通冒烟；演练结果写进文档；RPO/RTO 有声明。
  - 测试要求：脚本静态契约（不硬编码口令、失败即非零退出）+ 真实栈上的恢复演练。

- [ ] TASK-120 日志聚合与告警规则
  - 目标：关闭 **C7**——日志质量很高但没有检索与告警，出故障只能 `docker logs` 人肉翻。
  - 依赖：TASK-090（指标）。
  - 涉及文件：`deploy/loki/`（新建）、`deploy/prometheus/`（告警规则）、`docs/DEPLOYMENT.md`、`docs/RUNBOOK.md`（新建）、`tests/test_alert_rules.py`（新建）。
  - 实现要求：① Loki（或 ELK）聚合 + 按 `request_id` 检索；② 告警规则覆盖 5xx 率 / P95 延迟 / 队列积压 / DB 连接池 / 限流触发 / 维护任务未成功；③ **每条告警都有对应 runbook**（现象 → 排查 → 处置）。
  - 验收标准：真实栈上日志可聚合检索；告警规则语法校验通过且每条在 RUNBOOK 里有对应小节。
  - 测试要求：告警规则文件可解析 + 「每条告警都有 runbook」的一对一断言（防止只写规则不写处置）。

- [ ] TASK-121 供应链安全门禁
  - 目标：关闭 **C4**——无镜像扫描、无 SBOM、无依赖更新自动化、无 `pip-audit`/`npm audit` 门禁（全部 0 命中）。
  - 依赖：无。
  - 涉及文件：`.github/workflows/ci.yml`、`.github/dependabot.yml`（新建）、`requirements.txt`、`requirements-dev.txt`、`frontend/package.json`、`tests/test_ci_contract.py`。
  - 实现要求：① dependabot（pip / npm / docker / actions）；② CI 加 `pip-audit` 与 `npm audit`，**允许显式豁免清单**但不允许静默跳过；③ 镜像扫描（trivy）+ SBOM 产出；④ 失败策略：高危阻断、中低危报告。
  - 验收标准：CI 上三类扫描都跑起来；故意引入一个已知漏洞依赖能被拦下；每条豁免都有理由。
  - 测试要求：CI 配置契约断言（job 存在、豁免可追溯）。

- [ ] TASK-122 发布流程与回滚
  - 目标：关闭 **C5**——CI 只验证不部署（取舍正确），但缺 staging、迁移上线门禁、灰度与回滚判定。
  - 依赖：TASK-119（备份是回滚的安全网）。
  - 涉及文件：`.github/workflows/`、`docs/DEPLOYMENT.md`、`docs/RUNBOOK.md`、`docs/CHANGELOG.md`。
  - 实现要求：① staging 环境；② 迁移上线门禁（CI 已验证可逆性，这里补生产实操顺序与失败回退）；③ 发布清单与回滚 runbook；④ 变更记录规范化。
  - 验收标准：staging 可用；发布 → 回滚路径**演练**过；每次发布有记录。
  - 测试要求：发布脚本/流程的静态契约；回滚演练结果记录在文档。

- [ ] TASK-123 附件对象存储与内容嗅探
  - 目标：关闭 **B7 + C3**——`StorageBackend` Protocol 已为对象存储预留但没有第二实现，文件落命名卷导致**单机绑定**，多副本部署前必须先解决。
  - 依赖：TASK-094（租户化存储路径）。
  - 涉及文件：`app/services/storage.py`、`app/core/config.py`、`docker-compose.yml`、`docker-compose.prod.yml`、`requirements.txt`、`tests/test_storage_s3.py`（新建）。
  - 实现要求：① S3/MinIO 后端实现（沿用既有 Protocol，**不改调用方**）；② 本地后端保留为开发默认；③ **magic bytes 内容嗅探**（不信任扩展名与客户端声明的 MIME）；④ 可选 ClamAV 钩子；⑤ 下载/导出配额（与 TASK-099 衔接）；⑥ 租户前缀隔离。
  - 验收标准：真实 MinIO 上上传/下载/删除通；伪装扩展名的文件被嗅探拦下；切换后端不改业务代码。
  - 测试要求：两个后端跑同一套契约用例（本地 + MinIO）；嗅探的正反用例；租户前缀隔离断言。

- [ ] TASK-124 资源 limits、容量估算与 Kubernetes 清单
  - 目标：关闭 **C3** 的交付形态部分——用户已确认 K8s 与 Compose 都要。
  - 依赖：TASK-119（备份）、TASK-123（对象存储，多副本前置）。
  - 涉及文件：`docker-compose.prod.yml`、`deploy/k8s/`（新建：Deployment / Service / Ingress / ConfigMap / Secret / HPA / PDB / NetworkPolicy）、`docs/DEPLOYMENT.md`、`tests/test_k8s_manifests.py`（新建）。
  - 实现要求：① compose 补 `cpus` / `mem_limit`；② K8s 清单：liveness 用 `/health/live`、readiness 用 `/health/ready`（TASK-088 的产出直接落地）、`startupProbe`、HPA、PDB、NetworkPolicy、Secret 管理；③ **Celery Beat 在 K8s 下必须单副本**（与 TASK-089 的约束一致）；④ 容量估算（连接池 × 副本数 vs PostgreSQL `max_connections`）。
  - 验收标准：清单通过 `kubectl --dry-run=server` 或 kubeconform 校验；容量估算有数字与依据；探针语义与 TASK-088 一致。
  - 测试要求：清单静态契约（探针路径、副本数、资源限量、PDB 阈值）；容量估算的算术断言（避免「文档写 100 副本但 PG 只支持 100 连接」）。

- [ ] TASK-125 压测与慢查询基线
  - 目标：关闭 **C6 + A5**——无压测、无慢查询门槛、连接池与容量参数无依据。
  - 依赖：TASK-090（压测观测依赖指标）。
  - 涉及文件：`deploy/k6/`（新建）、`docs/QUALITY.md`、`docs/DEPLOYMENT.md`、`tests/test_pg_indexes.py`。
  - 实现要求：① k6 场景（登录 / 列表 / 任务流转 / 上传）；② 慢查询门槛（`pg_stat_statements` 或日志阈值）+ 对热点查询做 `EXPLAIN ANALYZE` 并留基线；③ 连接池参数按压测数据定，不凭感觉。
  - 验收标准：压测可复现并产出数字；热点查询计划写入文档；连接池参数有依据。
  - 测试要求：索引断言沿用既有口径（`SET LOCAL enable_seqscan=off` 后 `EXPLAIN`——小表直 `EXPLAIN` 必走顺序扫描，是假阴性）。

- [ ] TASK-126 前端错误上报、E2E 与组件测试
  - 目标：解除 **DECISIONS 057** 的三处降级口径（组件测试、登录冒烟、E2E）。
  - 依赖：无。
  - 涉及文件：`frontend/src/main.ts`、`frontend/src/utils/errorReporter.ts`（新建）、`frontend/vitest.config.ts`、`frontend/e2e/`（新建）、`frontend/package.json`、`docs/DECISIONS.md`。
  - 实现要求：① 前端错误上报（带 `request_id` 关联后端日志）；② 组件测试按真实组件形态落地（不再以「非独立组件」为由跳过）；③ Playwright E2E 覆盖登录 → 团队 → 项目 → 任务 → 评论 → 附件主链路；④ **口令字面量**受本机安全策略拦截的问题要在这一轮正面解决（配置化测试凭据），而不是继续挂起。
  - 验收标准：四门全绿 + E2E 可在 CI 上跑；组件测试覆盖 TaskForm/TaskCard 等既有被测对象；DECISIONS 057 的降级条目逐条关闭或给出新的明确理由。
  - 测试要求：E2E 主链路；组件测试；错误上报的字段契约。

- [ ] TASK-127 前端 i18n、a11y 与浏览器支持矩阵
  - 目标：企业多语言与可访问性要求。
  - 依赖：无。
  - 涉及文件：`frontend/src/locales/`（新建）、`frontend/src/main.ts`、`frontend/package.json`、`docs/CONVENTIONS.md`。
  - 实现要求：① i18n（中文 + 英文，文案外置，日期/数字按 locale 格式化）；② a11y（键盘可达、焦点管理、表单标签、对比度）；③ 浏览器支持矩阵明确（含不支持时的降级提示）。
  - 验收标准：四门全绿；语言切换生效且不刷新丢状态；关键流程键盘可完成。
  - 测试要求：文案外置断言（不残留硬编码中文）、locale 切换单测、a11y 静态检查。

## TASK 执行规则
每个 TASK 必须包含：目标、依赖、涉及文件、实现要求、验收标准、测试要求。
一次只执行一个 TASK；测试未通过不得标记完成。
