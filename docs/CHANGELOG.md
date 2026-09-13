# Changelog

## [Unreleased]

### Added
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
