"""Application configuration loaded from environment / `.env`.

Uses pydantic-settings so every value can be overridden by an environment
variable. Only `.env.example` is committed; the local `.env` is gitignored.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Application
    app_env: str = "development"
    app_name: str = "TaskFlow Pro"
    app_version: str = "0.1.0"
    debug: bool = True

    # Database / Redis
    database_url: str = "postgresql+asyncpg://postgres:postgres@postgres:5432/taskflow"
    redis_url: str = "redis://redis:6379/0"

    # 健康探针（TASK-088）：单次依赖探测的延迟上界（秒）。
    # 探针必须快速失败——编排器靠它判断实例生死，一个挂起的探测比失败的探测更有害。
    health_probe_timeout: float = 2.0

    # 指标端点（§1「日志与指标」/ TASK-090）。
    # 默认关闭：/metrics 暴露内部结构与流量画像，运维先评估暴露面再打开；
    # 打开后也只在应用端口可用（compose 里 app 不发布宿主端口，生产唯一入口
    # nginx 不代理 /metrics，见 DEPLOYMENT.md 监控章节），不占限流配额。
    metrics_enabled: bool = False

    # Celery（§23 / TASK-048）
    # broker / backend 留空时回落到 redis_url（DECISIONS 026）：
    # §21 规定 Redis 同时充当 Celery Broker 与 Backend，与限流共用同一实例即可，
    # 不为本项目规模引入第二个 Redis。
    celery_broker_url: str = ""
    celery_result_backend: str = ""
    # 规则 §8 要求异步任务必须有 timeout。规格未给数值，取保守默认并可覆盖。
    celery_task_soft_time_limit: int = 300
    celery_task_time_limit: int = 600
    # 结果保留时长：结果只是调试辅助，不参与业务正确性（幂等在任务侧保证）。
    celery_result_expires: int = 3600

    # Rate limit（§22 滑动窗口）
    # 规格未给出具体数值，这里采用可经 .env 覆盖的默认值（见 DECISIONS 015）。
    # window_seconds 同时作为 ZSET key 的 TTL：窗口内没有新请求时键自动回收。
    rate_limit_requests: int = 60
    rate_limit_window_seconds: int = 60
    rate_limit_enabled: bool = True

    # 反向代理信任边界（§31 / TASK-060）
    # 生产链路是 Client → Nginx → Gunicorn → Uvicorn，若始终取 TCP 对端地址，
    # 则所有匿名请求的对端都是 Nginx，「按 IP 限流」会退化为共享一份配额
    # （DECISIONS 018 遗留约束）。这里用一个**默认关闭**的显式开关来解：
    #   - trust_proxy_headers=False（默认）→ 与 TASK-046 行为完全一致；
    #   - 开启时必须同时给出 trusted_proxy_ips（逗号分隔的 IP/CIDR，通常是
    #     compose 网段），否则**不采信**该头（fail-safe）。
    # 判定逻辑集中在 app/core/client_ip.py。
    trust_proxy_headers: bool = False
    trusted_proxy_ips: str = ""

    # Auth
    jwt_secret_key: str = "change-me"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # Uploads
    upload_dir: str = "storage"
    max_upload_size: int = 10485760

    # Logging（§33 / TASK-056）
    # §33 规定「生产环境采用结构化日志格式」，未给级别与开关；采用可经 .env
    # 覆盖的默认值（DECISIONS 037）。
    # log_format: auto（默认，按 app_env 推导：production→json、其余→text）| json | text
    log_level: str = "INFO"
    log_format: str = "auto"
    # 请求访问日志（method/path/status_code/duration）开关：测试默认关闭以避免
    # 海量访问日志刷屏，生产建议开启。
    log_requests: bool = True

    # Maintenance tasks（§23 / TASK-050：日志归档 + 附件清理）
    # 规格未给数值，采用可经 .env 覆盖的默认值（DECISIONS 031/032）。
    # 归档保留期：operation_logs 超过该天数的行迁入 operation_logs_archive。
    log_archive_retention_days: int = 90
    # 孤儿附件最小年龄（秒）：storage 卷中物理存在但 DB 无对应记录的文件，
    # 且修改时间早于 now-min_age 才清理——给正常删除流程留竞争缓冲，避免
    # 误删「正在上传 / 刚删任务尚未回收」的文件（DECISIONS 032）。
    attachment_orphan_min_age_seconds: int = 3600
    # 归档批大小：每批独立事务搬 N 行，避免长事务锁主表 / 触发 soft timeout。
    maintenance_batch_size: int = 1000

    # Beat 调度（§61 / TASK-089：两项维护任务的周期登记）
    # Celery 时区为 UTC（celery_app.conf）。默认错峰：
    #   归档 19:30 UTC ≈ 北京时间 03:30（每日低位时段）；
    #   清理每小时第 45 分（不与整点任务、归档时刻重合）。
    # 存储期限最小化（§61）：归档表不是终点——archived_at 超过
    # archive_final_retention_days 天的行被删除，审计数据也有保留上限。
    archive_schedule_hour: int = 19
    archive_schedule_minute: int = 30
    cleanup_schedule_minute: int = 45
    archive_final_retention_days: int = 365


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (one per process)."""
    return Settings()
