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


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (one per process)."""
    return Settings()
