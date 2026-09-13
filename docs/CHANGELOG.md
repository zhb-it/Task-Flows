# Changelog

## [Unreleased]

### Added
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
