from functools import lru_cache

from pydantic import Field
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

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
