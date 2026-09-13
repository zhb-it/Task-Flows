# TaskFlow Pro

生产级团队任务协作平台后端。

## 技术栈

- Python（本机开发环境）
- FastAPI、Pydantic v2、SQLAlchemy 2.0、Alembic
- PostgreSQL 16、Redis 7、Celery
- JWT、pytest、Docker、GitHub Actions

当前处于 Phase 2 用户与认证，已提供 `POST /api/v1/auth/register`、`POST /api/v1/auth/login`、`GET /api/v1/users/me`；完整接口清单见 [`docs/API_CONTRACT.md`](docs/API_CONTRACT.md)。

## 本地环境

```text
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy .env.example .env
```

`.env` 仅用于本机，不要提交。仓库模板为 `.env.example`。

## 文档

规格与架构见 [`docs/`](docs/)。任务与进度见 [`docs/TASKS.md`](docs/TASKS.md) 与 [`docs/PROGRESS.md`](docs/PROGRESS.md)。
