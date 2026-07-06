from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, field_validator, model_validator
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
    refresh_cookie_name: str = "refresh_token"

    email_verification_ttl_hours: int = 24
    password_reset_ttl_minutes: int = 30
    password_min_length: int = 12
    password_max_length: int = 1024

    mail_host: str | None = None
    mail_port: int = 587
    mail_username: str | None = None
    mail_password: str | None = None
    mail_from_email: str | None = None
    mail_from_name: str = "Project W"
    mail_starttls: bool = True
    mail_timeout_seconds: int = 10

    redis_url: str | None = None

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

    @field_validator(
        "jwt_access_ttl_minutes",
        "jwt_refresh_ttl_days",
        "email_verification_ttl_hours",
        "password_reset_ttl_minutes",
        "password_min_length",
        "password_max_length",
        "mail_port",
        "mail_timeout_seconds",
    )
    @classmethod
    def validate_positive_int(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("value must be positive")
        return value

    @model_validator(mode="after")
    def validate_secret_strength(self) -> "Settings":
        if self.password_max_length < self.password_min_length:
            raise ValueError("password_max_length must be greater than password_min_length")

        if self.app_env in {"production", "staging"}:
            weak_values = {
                "change-me-in-env",
                "replace-with-a-long-random-secret",
                "replace-with-a-long-random-pepper",
            }
            for field_name in ("jwt_secret_key", "password_pepper"):
                value = getattr(self, field_name)
                if value in weak_values or len(value) < 32:
                    raise ValueError(f"{field_name} must be a strong secret outside local/test")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
