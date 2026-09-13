# Changelog

## [Unreleased]

### Added
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
- `requirements.txt`：`passlib[bcrypt]==1.7.4` → `pwdlib[argon2]==0.3.1`。原因：实测 passlib 1.7.4 与已安装的 bcrypt 5.0.0 **不兼容**（`AttributeError: module 'bcrypt' has no attribute '__about__'`，`CryptContext.hash()` 直接抛 `ValueError: password cannot be longer than 72 bytes`），无法完成哈希；改用项目文档 §20 明确推荐的 pwdlib / Argon2id。（TASK-014）
