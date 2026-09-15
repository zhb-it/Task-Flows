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

### 生产栈：`docker-compose.prod.yml`（TASK-059）

**独立完整文件**，不与开发版叠加（`ports` 在 compose 多文件合并时是拼接而非覆盖，
无法靠覆盖文件摘掉开发版发布的宿主端口，理由见 DECISIONS 039）：

```bash
# 1) 首次部署：执行迁移（容器不会自动迁移）
docker compose -f docker-compose.prod.yml run --rm app alembic upgrade head

# 2) 启动
docker compose -f docker-compose.prod.yml --env-file .env up -d --build

# 3) 本地与开发栈并行验证时换宿主端口，避免抢占 8000
APP_PORT=18080 docker compose -f docker-compose.prod.yml --env-file .env up -d

# 4) 拆除（-v 连数据卷一起删；生产环境慎用）
docker compose -f docker-compose.prod.yml down -v
```

- **compose 项目名** = `taskflow-prod`：容器 / 网络 / 数据卷都带前缀
  （`taskflow-prod_*`），与开发栈（`task-flow_*`）完全隔离，不会误连开发库。
- **端口暴露**：postgres / redis **不发布任何宿主端口**；app 只绑
  `127.0.0.1:${APP_PORT:-8000}`。对外暴露由 Nginx 承担（TASK-060）。
- **必需密钥**：`JWT_SECRET_KEY`、`POSTGRES_PASSWORD` 使用 `${VAR:?}` 必填语法，
  未设置或为空时 compose **直接拒绝启动**——不静默沿用开发默认密钥。
  已知边界：`${VAR:?}` 拦不住「设置成了弱值」，需人工确认密钥强度。
- **生产开关**：`APP_ENV=production`（§33 结构化 JSON 日志）、`DEBUG=false`
  （关闭 FastAPI debug 与 SQLAlchemy echo）、`LOG_REQUESTS=true`、
  `RATE_LIMIT_ENABLED=true`。
- **运行保障**：`restart: always`、容器日志轮转（10MB × 3 个文件）、
  Redis 开启 AOF（Celery Broker 队列需跨重启存活）、worker `stop_grace_period: 30s`。
- **不注入宿主 `.env`**：容器内地址由 compose 用服务名拼装；注入宿主 `.env`
  （`DATABASE_URL` 指向 `127.0.0.1:5433`）会让容器连不上任何东西。

## 配置
环境变量放 `.env`；仓库只提交 `.env.example`。

## 健康检查
- `/health`
- `/health/db`
- `/health/redis`

## CI
GitHub Actions 至少执行：
安装依赖 -> lint -> pytest -> docker build。
