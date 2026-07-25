from decimal import Decimal
from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="APP_",
        env_file="../.env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "AI Raktárkezelő"
    environment: str = Field(default="development", alias="APP_ENV")
    secret_key: str = "development-only-change-me-at-least-32-bytes"
    database_url: str = "sqlite:///./ai_raktar_dev.db"
    cors_origins: str = "http://localhost:5173,http://localhost:8080"
    access_token_minutes: int = 15
    refresh_token_days: int = 14
    bootstrap_organization: str = "Mintabolt"
    bootstrap_organization_slug: str = "mintabolt"
    bootstrap_admin_email: str = "admin@example.com"
    bootstrap_admin_password: str = "ChangeMe-2026!"
    max_upload_mb: int = 25
    max_document_pages: int = 50
    object_store_backend: str = "local"
    object_store_local_path: str = "./data/objects"
    s3_endpoint_url: str = "http://localhost:9000"
    s3_access_key: str = "ai-raktar"
    s3_secret_key: str = "change-this-minio-password"
    s3_bucket: str = "ai-raktar-documents"
    s3_region: str = "us-east-1"
    virus_scan_enabled: bool = False
    clamav_host: str = "localhost"
    clamav_port: int = 3310
    clamav_timeout_seconds: int = 30
    redis_url: str = "redis://localhost:6379/0"
    ai_provider: str = "disabled"
    ollama_base_url: str = "https://ollama.com"
    ollama_api_key: SecretStr = SecretStr("")
    ollama_model: str = "gemma4:31b"
    ai_prompt_version: str = "goods-receipt-v1"
    ai_structured_output_enabled: bool = False
    ai_timeout_seconds: int = 120
    ai_max_retries: int = 3
    ai_retry_base_seconds: int = 30
    ai_circuit_failure_threshold: int = 3
    ai_circuit_cooldown_seconds: int = 60
    ai_confidence_threshold: float = 0.9
    ai_lexical_match_threshold: float = 0.88
    ai_quantity_outlier_threshold: float = 10000
    ai_max_image_side: int = 1800
    ai_worker_poll_seconds: int = 5
    vrp_max_upload_mb: int = 15
    vrp_max_rows: int = 10000
    vrp_scheduler_poll_seconds: int = 30
    email_inbound_domain: str = "inbound.localhost"
    email_webhook_secret: SecretStr = SecretStr("")
    email_webhook_max_age_seconds: int = 300
    email_max_message_mb: int = 30
    email_max_attachments: int = 20
    email_imap_enabled: bool = False
    email_imap_host: str = ""
    email_imap_port: int = 993
    email_imap_username: str = ""
    email_imap_password: SecretStr = SecretStr("")
    email_imap_mailbox: str = "INBOX"
    email_imap_use_ssl: bool = True
    email_imap_poll_seconds: int = 60
    plugin_api_version: str = "1"
    plugin_job_timeout_seconds: int = 60
    plugin_max_retries: int = 3
    plugin_dispatcher_poll_seconds: int = 5
    plugin_dispatch_batch_size: int = 100
    plugin_rate_limit_per_minute: int = 120
    inventory_approval_threshold: Decimal = Decimal("100")

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
