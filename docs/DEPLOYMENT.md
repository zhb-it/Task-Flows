# Deployment

## Development
Docker Compose 至少包含：
- postgres
- redis
- api
- celery_worker

## Production
推荐：
Client -> Nginx -> Gunicorn + Uvicorn Worker -> FastAPI

## 配置
环境变量放 `.env`；仓库只提交 `.env.example`。

## 健康检查
- `/health`
- `/health/db`
- `/health/redis`

## CI
GitHub Actions 至少执行：
安装依赖 -> lint -> pytest -> docker build。
