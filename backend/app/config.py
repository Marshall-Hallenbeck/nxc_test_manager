"""Configuration management for the NetExec Test Manager."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql://postgres:postgres@localhost:5438/netexec_tests"
    redis_url: str = "redis://localhost:6381/0"
    github_token: str | None = None

    # Default test targets
    default_target_hosts: str = ""
    default_target_username: str = ""
    default_target_password: str = ""

    # Email notifications (disabled by default)
    email_enabled: bool = False
    smtp_server: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = "netexec-tests@example.com"
    smtp_to: str = "admin@example.com"

    # Container settings
    container_timeout: int = 1800  # 30 minutes
    container_memory_limit: str = "2g"
    celery_workers: int = 3

    # GitHub Webhooks (disabled by default)
    webhook_enabled: bool = False
    webhook_secret: str = ""
    webhook_auto_test_events: str = "opened,synchronize"
    webhook_repo_filter: str = "Pennyw0rth/NetExec"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False
    )


settings = Settings()
