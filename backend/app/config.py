"""Configuration management for the NetExec Test Manager."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql://postgres:postgres@localhost:5438/netexec_tests"
    redis_url: str = "redis://localhost:6381/0"
    github_token: str

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

    # Empire C2 (for empire_exec e2e tests)
    empire_host: str = "127.0.0.1"
    empire_port: int = 1337
    empire_username: str = "empireadmin"
    empire_password: str = "password123"

    # Default repository (owner/name format)
    default_repo: str = "Pennyw0rth/NetExec"

    # GitHub Webhooks (disabled by default)
    webhook_enabled: bool = False
    webhook_secret: str = ""
    webhook_auto_test_events: str = "opened,synchronize"
    webhook_repo_filter: str = "Pennyw0rth/NetExec"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=False)


settings = Settings()


def reload_settings() -> None:
    """Re-read .env and environment variables into the existing settings object.

    Mutates in-place so all modules that imported `settings` see the update.
    Infrastructure settings (DATABASE_URL, REDIS_URL) take effect on next restart.
    """
    fresh = Settings()
    for field_name in fresh.model_fields:
        setattr(settings, field_name, getattr(fresh, field_name))
