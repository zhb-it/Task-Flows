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

## TASK 执行规则
每个 TASK 必须包含：目标、依赖、涉及文件、实现要求、验收标准、测试要求。
一次只执行一个 TASK；测试未通过不得标记完成。
