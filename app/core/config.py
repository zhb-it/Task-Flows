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


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (one per process)."""
    return Settings()
