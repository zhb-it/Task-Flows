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

### 生产栈：`docker-compose.prod.yml`（TASK-059 / TASK-060）

**独立完整文件**，不与开发版叠加（`ports` 在 compose 多文件合并时是拼接而非覆盖，
无法靠覆盖文件摘掉开发版发布的宿主端口，理由见 DECISIONS 039）：

```bash
# 1) 首次部署：执行迁移（容器不会自动迁移）
docker compose -f docker-compose.prod.yml run --rm app alembic upgrade head

# 2) 启动
docker compose -f docker-compose.prod.yml --env-file .env up -d --build

# 3) 换对外端口（宿主 80 被占用、或本机与开发栈并行验证时）
NGINX_HTTP_PORT=18081 docker compose -f docker-compose.prod.yml --env-file .env up -d

# 4) 拆除（-v 连数据卷一起删；生产环境慎用）
docker compose -f docker-compose.prod.yml down -v
```

- **compose 项目名** = `taskflow-prod`：容器 / 网络 / 数据卷都带前缀
  （`taskflow-prod_*`），与开发栈（`task-flow_*`）完全隔离，不会误连开发库。
- **端口暴露（TASK-060 起）**：**只有 nginx 发布宿主端口**（`${NGINX_HTTP_PORT:-80}:80`）。
  postgres / redis **不发布任何端口**；app 也**不发布端口**——TASK-059 时的
  `127.0.0.1:8000` 已被删除，因为它会让同机进程绕过反代直连应用并伪造
  `X-Forwarded-For`（理由见 DECISIONS 040）。
- **必需密钥**：`JWT_SECRET_KEY`、`POSTGRES_PASSWORD` 使用 `${VAR:?}` 必填语法，
  未设置或为空时 compose **直接拒绝启动**——不静默沿用开发默认密钥。
  已知边界：`${VAR:?}` 拦不住「设置成了弱值」，需人工确认密钥强度。
- **生产开关**：`APP_ENV=production`（§33 结构化 JSON 日志）、`DEBUG=false`
  （关闭 FastAPI debug 与 SQLAlchemy echo）、`LOG_REQUESTS=true`、
  `RATE_LIMIT_ENABLED=true`。
- **运行保障**：`restart: always`、容器日志轮转（10MB × 3 个文件）、
  Redis 开启 AOF（Celery Broker 队列需跨重启存活）、worker 与 app
  `stop_grace_period: 30s`（与 Gunicorn `--graceful-timeout=30` 对齐）。
- **不注入宿主 `.env`**：容器内地址由 compose 用服务名拼装；注入宿主 `.env`
  （`DATABASE_URL` 指向 `127.0.0.1:5433`）会让容器连不上任何东西。

### 反代层：Nginx + Gunicorn（TASK-060，§31）

```text
Client → nginx(host:${NGINX_HTTP_PORT:-80}) → app:8000(Gunicorn + UvicornWorker) → FastAPI
```

- **配置文件**：`nginx/nginx.conf`，以只读方式挂载到容器的
  `/etc/nginx/nginx.conf`（它是**部署配置**而不是应用源码）。
- **Nginx 承担**：反向代理、请求体大小限制（`client_max_body_size 12m`，**粗粒度
  外圈**，业务上限仍由应用 `MAX_UPLOAD_SIZE` 判定并返回 JSON 信封）、基础超时、
  基础安全 Header（`nosniff` / `X-Frame-Options` / `Referrer-Policy`，带 `always`）、
  `server_tokens off`。
- **附件不由 Nginx 直出**：§31 的「静态附件访问」在本项目被有意实现为**不直出**
  ——附件是私有资源，直出会绕过 TASK-043 的权限链（IDOR）。理由见 DECISIONS 040。
- **代理自身的健康探针**：`GET /nginx-health`（nginx 本地返回，不依赖上游），
  与应用的 `/health` 分开，便于区分「入口挂了」和「后端重启中」。
- **Gunicorn**：`--worker-class=uvicorn.workers.UvicornWorker`、
  `--workers=${WEB_CONCURRENCY:-2}`、`--timeout=60`、`--graceful-timeout=30`。
  不开自带访问日志（访问日志已由应用按 §33 输出，避免重复，见 DECISIONS 041）。

#### 真实客户端 IP（反代后必须配，否则 IP 维度限流退化）

应用只在**三条同时成立**时采信 `X-Forwarded-For`：`TRUST_PROXY_HEADERS=true`、
TCP 对端落在 `TRUSTED_PROXY_IPS` 网段内、该头恰好是一个合法 IP。否则回落到对端地址。
配置错误（开关开着但网段为空）会**向安全侧退化**（不采信），而不是信任任何人
（DECISIONS 042）。

- Nginx 侧用 `$remote_addr` **覆盖**写入该头（不是追加），客户端伪造的值在到达
  应用之前就被替换；
- `TRUSTED_PROXY_IPS` 必须与 prod compose 里声明的固定子网一致
  （契约测试 `tests/test_nginx_config.py` 交叉校验，改一处忘改另一处会直接失败）；
- `FORWARDED_ALLOW_IPS=""` 关掉 uvicorn 的 proxy-headers 改写，让
  `app/core/client_ip.py` 成为**唯一**判定点。

#### TLS

本 TASK 只 `listen 80`：证书不进仓库（私钥入库是反面实践），TLS 由上游负载均衡
或宿主反代终止。相应地**不发 HSTS**（在纯 HTTP 响应上发它既不被浏览器采纳，
也会误导排查者）。若要在本层终止 TLS，需要加入证书挂载与 `listen 443 ssl`，
并届时打开 HSTS。

## 配置
环境变量放 `.env`；仓库只提交 `.env.example`。

## 健康检查
应用：
- `/health`
- `/health/db`
- `/health/redis`

代理：
- `/nginx-health`（nginx 本地，不依赖上游）

## CI

`.github/workflows/ci.yml`（GitHub Actions，TASK-061）三个 job，对应 §44 的四步：

| job | 内容 |
|---|---|
| `lint` | 装 `requirements-dev.txt` → `ruff check .` |
| `test` | Python 3.13 + `postgres:16` / `redis:7` service → 迁移可逆性验证 → 全量 `pytest` |
| `docker-build` | `docker build --tag taskflow-app:ci .`（只验证可构建，**不推送**） |

- **service 端口是 5433 / 6389**，不是默认的 5432 / 6379。测试套件里 40 个文件把
  `127.0.0.1:5433` / `127.0.0.1:6389` 写成模块级常量（本机 5432 被另一个
  PostgreSQL 占用），让 CI 的映射去适配测试，而不是反过来改 40 个测试文件。理由见
  DECISIONS 043。
- **必须显式设 `DATABASE_URL` / `REDIS_URL` / `JWT_SECRET_KEY`**：CI 里没有 `.env`
  （它被 `.gitignore` 与 `.dockerignore` 排除），而 `Settings` 的默认值是容器服务名
  （`postgres:5432` / `redis:6379`），在 runner 上无法解析。这三个键恰好是与代码默认值
  有差异的全部配置项——CI 与本地因此只差「谁提供 Postgres / Redis」。
- **迁移可逆性**：`alembic upgrade head` → `alembic downgrade base` → `alembic upgrade head`
  三步在同一条 shell 里（`set -euo pipefail`，避免「downgrade 悄悄失败、最后一步是 no-op、
  pytest 却在旧库上通过」的假绿）。前两步即 §37 要求的 migration test，最后一步顺便让
  pytest 用真实的迁移产物建表。
- **触发**：`push` 与 `pull_request` 到 `master`，另支持手动 `workflow_dispatch`。权限为
  `contents: read`；同一分支的旧 run 会被新 run 取消。
- **不在 CI 里做的事**：推送镜像（需要 `packages:write` 与 registry 凭据，一个纯验证步骤
  不该带这把钥匙）；起 `docker-compose.prod.yml` 全栈跑 nginx 反代（属部署验证，见
  TESTING.md 的容器冒烟章节）。

### 本地跑与 CI 相同的检查

```bash
pip install -r requirements-dev.txt   # 含 ruff（版本已在文件里钉死）
ruff check .                          # 与 CI 的 lint job 完全相同
pytest                                # 与 CI 的 test job 相同（需本机 PG 5433 / Redis 6389）
```

注意：**PyPI 清华镜像没有 ruff**，若本机 pip 指向镜像源需显式换官方源
（`--index-url https://pypi.org/simple`，必要时再带 `--proxy`）。

规则集与版本都写死在仓库里（`pyproject.toml` 的 `[tool.ruff.lint] select`、
`requirements-dev.txt` 的 `ruff==`），因此「CI 是否通过」只取决于提交内容，与 CI
当天装到哪个版本无关。

