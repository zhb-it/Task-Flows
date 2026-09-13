# Changelog

## [Unreleased]

### Added
- 当前登录用户接口 `GET /api/v1/users/me`（TASK-017）：新增 `app/core/deps.py`（认证依赖归 core，符合 ARCHITECTURE.md 的「core：配置、安全、依赖、异常」）——`bearer_scheme = HTTPBearer(auto_error=False)` + `get_current_user`（解析 `Authorization: Bearer`，复用 `decode_access_token`，把 `sub` 转为 int 后交给 Service）+ 可直接用于路由签名的类型别名 `CurrentUser = Annotated[User, Depends(get_current_user)]`；**刻意关闭 `HTTPBearer` 的默认 `auto_error`**，因其默认行为在缺少 Authorization 头时抛 403，与本项目「认证失败 → 401 + `WWW-Authenticate: Bearer`」的规范冲突。新增 `app/services/user.py`（`load_current_user`：subject 指向的用户不存在 → 401（Token 签名有效但账号已不存在，凭证事实失效）；用户存在但 `is_active=false` → 403，与 `authenticate_user` 对禁用账号的处理保持同一语义）；新增 `app/api/v1/users.py`（响应复用 `UserRead`，故永不包含 `password_hash`）；`app/api/v1/__init__.py` 挂载 users 路由。`tests/test_users_me.py` 19 项测试：3 项成功路径（字段与封装结构、不泄露密码、请求不修改用户数据）+ OpenAPI 登记校验 + 1 项缺少 Authorization 头 401 + 4 项非 Bearer 方案 401（`Bearer`/`Bearer `/`Basic`/`Token`）+ 4 项 Token 不可用 401（伪造密钥、已过期、`type=refresh`、4 种非法 `subject` 参数化）+ 3 项账号状态规则（未知用户 401、禁用账号 403、禁用账号不得被报成 401）。
- 登录接口 `POST /api/v1/auth/login`（TASK-016）：`app/core/security.py` 增补 JWT 能力（`create_access_token` 签发 HS256 Access Token，claims 为 `sub`/`type`/`iat`/`exp`，时长取 `ACCESS_TOKEN_EXPIRE_MINUTES`；`decode_access_token` 校验签名与过期并将 PyJWT 异常统一转为 `UnauthorizedError`，同时拒绝 `type != access` 的 Token 以防 Refresh Token 被当作 Access Token 使用）；`app/core/exceptions.py` 增补 `UnauthorizedError`(401，带 `WWW-Authenticate: Bearer`) 与 `ForbiddenError`(403)，`AppError` 支持 `headers`；`app/schemas/auth.py`（`LoginRequest`：`username`+`password`；`TokenResponse`：`access_token`+`token_type=bearer`）；`app/services/auth.py` 增补 `authenticate_user`（**先验证密码再检查账号启用状态**——用户不存在与密码错误返回同一条 401 文案以避免用户名枚举，密码正确但账号禁用则 403）；`app/api/v1/auth.py` 增补 `/login`（200 + `data`/`message` 封装）；`app/main.py` 的 `AppError` 处理器透传 `headers`。`tests/test_login.py` 14 项测试：5 项 JWT 单元测试（往返、过期窗口、错密钥、已过期、`type` 不符）+ 9 项集成测试（200 封装与 `sub` 可解析、不泄露密码、登录不修改用户、错密码 401 且带 `WWW-Authenticate`、未知用户与错密码文案一致、禁用账号 403、禁用账号+错密码仍 401、缺字段 422）。
- 注册接口 `POST /api/v1/auth/register`（TASK-015）：新增 `app/api/__init__.py`、`app/api/v1/__init__.py`（`api_router`，前缀 `/api/v1`）、`app/api/v1/auth.py`（返回 **201 Created** + 成功封装）；`app/services/__init__.py`、`app/services/auth.py`（`register_user`：查重 → `hash_password` → CRUD → **Service 持有事务边界** commit，并捕获 `IntegrityError` 兜住并发注册竞态）；`app/core/exceptions.py`（`AppError` 基类 + `ConflictError`=409）；`app/schemas/common.py`（`SuccessResponse[T]`，对应项目文档 §26 的 `data`+`message` 封装）；`app/main.py` 挂载 `api_router` 并新增 `AppError` → `{"detail": ...}` 统一错误处理。`tests/test_register.py` 9 项集成测试（httpx ASGITransport 走完整 ASGI 链路 + 真实 PostgreSQL，依赖覆盖 `get_db`）：201 与封装结构、响应不泄露明文/`password_hash`、库内为 `$argon2id$` 且可校验、重复用户名/邮箱 409、冲突不产生第二行、缺字段 422。
- `app/core/security.py`：密码哈希与校验模块（项目文档 §20 规定密码验证必须位于此；采用 pwdlib 推荐的 **Argon2id**，提供 `hash_password` / `verify_password`，对畸形哈希返回 `False` 而非抛异常以避免登录流程 500）；`tests/test_security.py` 12 项离线测试（哈希非明文、`$argon2id$` 前缀、长度适配 `String(255)`、随机盐、正确/错误密码、4 种畸形哈希、>72 字节长密码、Unicode 与大小写敏感）（TASK-014）
- `app/schemas/__init__.py`、`app/schemas/user.py`：定义 User Pydantic Schema（`UserBase`/`UserCreate` 含明文 `password` 入参、`UserRead` 剔除 `password_hash` 且 `from_attributes=True`）；`app/crud/__init__.py`、`app/crud/user.py`：异步 CRUD（`create_user` 仅持久化**已哈希**的 `password_hash`，不含哈希逻辑——属 TASK-014；`get_user`/`get_user_by_username`/`get_user_by_email`/`get_users` 分页）；`tests/test_user_crud.py` 离线校验 Schema 不泄露 `password_hash` + 连真实 PostgreSQL 集成测试（读写、双 UNIQUE 约束、分页、超长字段被 DB 拒绝），flush-only 不提交故零污染（TASK-013）
- `migrations/versions/99f0b41687e1_create_users.py`：`alembic revision --autogenerate` 生成 `users` 表迁移（字段/约束与 User 模型一致——id 序列主键、`username`/`email` 双 UNIQUE、`is_active` 默认 `true`、时区时间戳），并在运行中的 Docker PostgreSQL（宿主 5433）上 `alembic upgrade head` 真实建表（已用 `information_schema` 实证：列/主键/双 UNIQUE 约束齐全、行数 0）；`tests/test_alembic.py` 同步更新断言以反映已有迁移（TASK-012）
- `app/models/__init__.py` 与 `app/models/user.py`：定义 `User` ORM 模型（字段严格取自规格 §5.1：`id` BIGINT PK、`username` UNIQUE、`email` UNIQUE、`password_hash`、`is_active`、带时区 `created_at`/`updated_at`）；`migrations/env.py` 增补 `import app.models` 使 Alembic 能 autogenerate；`tests/test_user_model.py` 离线验证列/约束/metadata 注册（TASK-011）
- 全栈 Docker 部署（TASK-009）：`Dockerfile`（python:3.13-slim、非 root 运行、uvicorn）、`.dockerignore`、`docker-compose.yml` 新增 `app` 服务（build + depends_on 健康依赖 + `/health` 健康探针）；实测 `GET /health` 返回 `status=ok, database=up, redis=up`。宿主端口：app 8000、postgres 5433、redis 6389（容器内仍 5432/6379，规避本机 6379 占用）。TASK-058 Dockerfile 随之提前完成并验证。
- `app/main.py` 新增 `/health` 端点（异步探测 PostgreSQL `SELECT 1` 与 Redis `PING`，2s 超时；返回 `status`/`database`/`redis` 状态，进程存活即返回 200）；`tests/test_app.py` 增补 `/health` 断言（TASK-008）
- `alembic.ini`、`migrations/env.py`（异步 env：从 `app.core.config` 注入 `DATABASE_URL`、`target_metadata=Base.metadata`）、`migrations/script.py.mako`、`migrations/versions/.gitkeep`；`tests/test_alembic.py` 离线验证 `alembic history` 可运行（TASK-007）
- `app/db/` 异步数据库模块：`base.py`（`declarative_base`）、`session.py`（异步 `engine` + `async_session_factory` + `get_db` 依赖）；`tests/test_db.py` 离线验证引擎/会话工厂/`get_db` 契约（TASK-006）
- `docker-compose.yml` 增补 redis 服务（`redis:7`、端口 `6379:6379`、命名卷 `redis_data`、healthcheck）（TASK-005）
- `docker-compose.yml`（postgres 服务：`postgres:16`、端口 `5432:5432`、命名卷 `postgres_data`、healthcheck）与 `.env.example` 增补 `POSTGRES_*`（TASK-004）
- FastAPI 应用实例、`app/core/config.py` 配置系统（pydantic-settings 读取 `.env`）、`tests/test_app.py` 冒烟测试、`pyproject.toml`（pytest 配置）（TASK-003）
- `requirements.txt`、`.env.example` 与本地 `.env`（TASK-002）
- Git 仓库初始化、`.venv`、`app/` 与 `tests/` 包骨架、`.gitignore`、简短 README（TASK-001）
- AI Coding project context initialized
- Project specification
- Architecture
- API contract
- Database schema
- Task list
- Progress tracking
- Testing/Security/Deployment conventions
- Cursor rules

### Changed
- 本地 `.env`（gitignored，不入库）：`JWT_SECRET_KEY` 由占位值 `change-me`（9 字节）替换为 **64 字符强随机密钥**。原因：PyJWT 2.14 对 HS256 密钥长度 < 32 字节会抛 `InsecureKeyLengthWarning`（RFC 7518 §3.2），弱密钥可被离线暴力破解，直接威胁 Access Token 的签名有效性。（TASK-016）
- `requirements.txt`：`passlib[bcrypt]==1.7.4` → `pwdlib[argon2]==0.3.1`。原因：实测 passlib 1.7.4 与已安装的 bcrypt 5.0.0 **不兼容**（`AttributeError: module 'bcrypt' has no attribute '__about__'`，`CryptContext.hash()` 直接抛 `ValueError: password cannot be longer than 72 bytes`），无法完成哈希；改用项目文档 §20 明确推荐的 pwdlib / Argon2id。（TASK-014）
