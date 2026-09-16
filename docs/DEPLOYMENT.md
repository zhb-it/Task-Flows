# Deployment

## Development
Docker Compose 至少包含：
- postgres
- redis
- api
- celery_worker
- celery_beat（TASK-089：维护任务周期调度器）

## Production
推荐：
Client -> Nginx -> Gunicorn + Uvicorn Worker -> FastAPI

### 生产栈：`docker-compose.prod.yml`（TASK-059 / TASK-060）

**独立完整文件**，不与开发版叠加（`ports` 在 compose 多文件合并时是拼接而非覆盖，
无法靠覆盖文件摘掉开发版发布的宿主端口，理由见 DECISIONS 039）：

```bash
# 1) 首次部署：执行迁移（容器不会自动迁移）。
#    TASK-095 起运行时连接是非超管角色 taskflow_app（受 RLS 约束），而迁移
#    需要建角色/策略/表——必须显式以 POSTGRES_USER 超管身份执行迁移：
docker compose -f docker-compose.prod.yml run --rm \
  -e "DATABASE_URL=postgresql+asyncpg://${POSTGRES_USER:-postgres}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB:-taskflow}" \
  app alembic upgrade head

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

### 数据库运行时角色（TASK-095，RLS 兜底生效的前提）

PostgreSQL RLS 对超级用户**始终绕过**——应用继续用 `postgres` 连接，兜底就
形同虚设。迁移 `b8d4f2a6c9e1` 创建运行时角色 `taskflow_app`（LOGIN、非超管、
受全部 12 张业务表的 `tenant_isolation` RLS 策略约束），dev/prod compose 的
app / celery_worker / celery_beat 三服务 `DATABASE_URL` 已切换到它：

- **迁移/测试继续走超管**（迁移要建角色、策略、表；测试 teardown 清理不能被
  fail-closed 拦截）——所以上面的迁移命令显式覆盖 `DATABASE_URL`。
- **角色由迁移创建**：先迁移、后启动（本就是既有前提）；角色不存在时运行时
  连接会明确失败（`role "taskflow_app" does not exist`），不会静默裸奔。
- **密码轮换**：开发缺省 `taskflow_app`（`TASKFLOW_APP_DB_PASSWORD` 可覆盖）。
  生产流程：`ALTER ROLE taskflow_app WITH PASSWORD '...'`（超管执行）→ 在
  env 文件设 `TASKFLOW_APP_DB_PASSWORD` → 重启运行时服务。
- **应用层语义**：租户上下文（认证注入的 ContextVar）决定每个事务的
  `SET LOCAL app.tenant_id`；无租户上下文的路径（登录前认证查询、Celery
  维护任务）以 `app.tenant_bypass='on'` 放行——RLS 拦的是「租户内请求漏加
  条件」，不是系统任务。绕过作用域的跨租户查询只有
  `bypass_tenant_scope()`（`app/core/tenant_context.py`）一个显式出口，
  进入即记审计日志。

### 维护任务调度（TASK-089，§61）

`celery_beat` 服务（dev/prod 两套 compose 均有，与 app 同镜像、独立命令
`celery -A app.tasks.celery_app beat`）按 `beat_schedule` 周期投递两项维护任务：

| 任务 | 默认时刻（UTC） | 说明 |
|---|---|---|
| `archive_operation_logs` | 每日 19:30（≈ 北京时间 03:30，低位时段） | 超期日志主表 → 归档表；随后按 `ARCHIVE_FINAL_RETENTION_DAYS`（默认 365 天，按 `archived_at` 计）清理归档表终态 |
| `cleanup_expired_attachments` | 每小时第 45 分 | 回收 storage 卷中的孤儿物理文件 |

- 间隔经 `.env` 可配：`ARCHIVE_SCHEDULE_HOUR` / `ARCHIVE_SCHEDULE_MINUTE` /
  `CLEANUP_SCHEDULE_MINUTE` / `ARCHIVE_FINAL_RETENTION_DAYS`。
- ⚠ **beat 必须单实例**：多副本 beat 会重复投递同一条任务。任务幂等
  （TASK-051）只保证重复执行无副作用，不保证不浪费队列/worker 资源。
  celery_beat 服务刻意不可扩展；扩容只发生在 celery_worker 上。
- beat 无 healthcheck（`inspect` 探的是 worker）；存活监督靠 `restart: always`
  与容器日志。调度正确性由 `tests/test_beat_schedule.py` 契约测试钉住。
- 验证下一次执行时间：`docker compose -f docker-compose.prod.yml exec celery_beat
  celery -A app.tasks.celery_app inspect scheduled`（需 worker 在跑才能看到条目）。

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
应用（TASK-088，规格 §32）——「进程活着」与「依赖可用」是两种语义，探针各司其职：

| 端点 | 语义 | 正常 | 依赖不可用 |
|---|---|---|---|
| `/health/live` | liveness：进程活着即成功，**不探测任何依赖**。重启决策依据 | 200 | 恒 200 |
| `/health/ready` | readiness：依赖全部可用才放行流量。摘除流量（而非重启）的依据 | 200 | **503**，body 含 `database`/`redis` 各项明细 |
| `/health/db` | PostgreSQL 单依赖明细，定位「谁挂了」 | 200 | **503** |
| `/health/redis` | Redis 单依赖明细，同上 | 200 | **503** |
| `/health` | 兼容端点：恒 200，body 报 `database`/`redis` up/down。既有监控依赖此行为，不变 | 200 | 200（`status: degraded`） |

- compose 的 app healthcheck 探 `/health/ready`（依赖抖动时容器标记 unhealthy）；
- 入口 nginx 探自有的 `/nginx-health`，**刻意不探上游**（见下文 nginx 小节）；
- 全部探针端点免认证、不限流；单次探测超时由 `HEALTH_PROBE_TIMEOUT` 控制（默认 2 秒）。

代理：
- `/nginx-health`（nginx 本地，不依赖上游）

## 指标与监控（TASK-090，§1「日志与指标」）

`GET /metrics` 输出 Prometheus 文本格式（`prometheus_client`，不自造格式），由 `METRICS_ENABLED` （默认 **false**）控制——暴露内部结构与流量画像，运维先评估暴露面再打开。三条暴露面纪律：

- **不经 nginx 暴露**：生产唯一入口只代理 `/` 与 `/api/`，app 容器不发布宿主端口——即使开关打开，外网也够不到；
- **不占限流配额**：限流只作用于 `/api/v1` 前缀，15s 间隔的抓取探针不消耗业务额度；
- **依赖故障不连坐**：Redis/DB 不可达时采集按 0/缺失降级，`/metrics` 自身不 500。

指标集（前缀 `taskflow_`）：HTTP 请求计数/延迟直方图（标签为 **路由模板**，非原始路径——UUID 不进标签，404 统一 `unmatched`）、进行中请求数、Redis 命令延迟、DB 连接池占用、Celery 队列深度与任务成功/失败/重试计数（worker 经 Redis 中转）、维护任务最后成功时间戳（`taskflow_maintenance_last_success_timestamp{task=...}`）。

抓取配置与告警规则草案见 `deploy/prometheus/`（`prometheus.yml` + `alerts.yml`：应用下线、5xx 率、连接池耗尽、Redis 慢、队列积压、维护任务停摆）。告警阈值是保守起点，上线后按真实负载调优。

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
pip install -r requirements-dev.txt   # 含 ruff + pytest-cov（版本均已在文件里钉死）
ruff check .                          # 与 CI 的 lint job 完全相同
pytest                                # 与 CI 的 test job 相同（需本机 PG 5433 / Redis 6389）
pytest --cov --cov-report=term-missing   # 覆盖率（仅本地；CI 不跑，见下）
```

注意：**PyPI 清华镜像既没有 ruff、也没有 pytest-cov**，若本机 pip 指向镜像源需显式换
官方源（`--index-url https://pypi.org/simple`，必要时再带 `--proxy`）。

覆盖率（TASK-062）**只在本地测量，不进 CI 门禁**：CI 的 pytest job 不传 `--cov`、不设
`fail_under`。理由与当前基线见 `docs/QUALITY.md`；配置在 `pyproject.toml` 的
`[tool.coverage.*]`（`source = ["app"]`、`branch = true`）。

规则集与版本都写死在仓库里（`pyproject.toml` 的 `[tool.ruff.lint] select`、
`requirements-dev.txt` 的 `ruff==`），因此「CI 是否通过」只取决于提交内容，与 CI
当天装到哪个版本无关。

