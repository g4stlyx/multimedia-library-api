from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Project W API"
    app_env: Literal["local", "test", "staging", "production"] = "local"
    app_base_url: str = "http://localhost:8000"
    api_prefix: str = "/api/v1"
    log_level: str = "INFO"

    database_url: PostgresDsn = Field(
        default="postgresql+psycopg2://postgres:postgres@localhost:5432/project_w"
    )

    jwt_issuer: str = "project-w-api"
    jwt_audience: str = "project-w-web"
    jwt_secret_key: str = "change-me-in-env"
    jwt_access_ttl_minutes: int = 15
    jwt_refresh_ttl_days: int = 30
    password_pepper: str = "change-me-in-env"

    trust_cloudflare_headers: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("api_prefix")
    @classmethod
    def validate_api_prefix(cls, value: str) -> str:
        if not value.startswith("/"):
            raise ValueError("api_prefix must start with '/'")
        return value.rstrip("/") or "/"


@lru_cache
def get_settings() -> Settings:
    return Settings()
