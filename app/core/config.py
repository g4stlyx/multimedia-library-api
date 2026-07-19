from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Project W API"
    app_env: Literal["local", "test", "staging", "production"] = "local"
    app_base_url: str = "http://localhost:8000"
    web_base_url: str = "http://localhost:3000"
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

    tmdb_api_key: str | None = None
    rawg_api_key: str | None = None
    google_books_api_key: str | None = None
    open_library_user_agent: str | None = None
    open_library_contact_email: str | None = None
    spotify_client_id: str | None = None
    spotify_client_secret: str | None = None

    provider_timeout_seconds: int = 10
    provider_max_retries: int = 2

    cloudflare_r2_account_id: str | None = None
    cloudflare_r2_access_key_id: str | None = None
    cloudflare_r2_secret_access_key: str | None = None
    cloudflare_r2_bucket: str | None = None
    cloudflare_r2_public_base_url: str | None = None

    profile_image_max_bytes: int = 5 * 1024 * 1024
    max_request_body_bytes: int = 6 * 1024 * 1024
    profile_image_max_dimension: int = 4096
    profile_image_max_pixels: int = 16_000_000
    import_max_file_bytes: int = 5 * 1024 * 1024
    import_max_rows: int = 10_000
    import_max_concurrent_jobs_per_user: int = 2
    import_worker_lease_seconds: int = 900
    import_worker_poll_seconds: int = 2
    backup_encryption_key: str | None = None
    backup_email_recipient: str | None = None
    backup_max_runtime_minutes: int = 120
    backup_worker_lease_seconds: int = 10_800
    backup_worker_poll_seconds: int = 10



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
        "provider_timeout_seconds",
        "provider_max_retries",
        "profile_image_max_bytes",
        "max_request_body_bytes",
        "profile_image_max_dimension",
        "profile_image_max_pixels",
        "import_max_file_bytes",
        "import_max_rows",
        "import_max_concurrent_jobs_per_user",
        "import_worker_lease_seconds",
        "import_worker_poll_seconds",
        "backup_max_runtime_minutes",
        "backup_worker_lease_seconds",
        "backup_worker_poll_seconds",
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

        if self.backup_worker_lease_seconds <= self.backup_max_runtime_minutes * 60:
            raise ValueError("backup_worker_lease_seconds must exceed backup_max_runtime_minutes")

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
