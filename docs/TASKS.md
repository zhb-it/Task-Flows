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
- [ ] TASK-063 README 与面试技术难点

## TASK 执行规则
每个 TASK 必须包含：目标、依赖、涉及文件、实现要求、验收标准、测试要求。
一次只执行一个 TASK；测试未通过不得标记完成。
