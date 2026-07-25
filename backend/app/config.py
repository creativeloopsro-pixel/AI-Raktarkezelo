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

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
