from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "ReconFlow API"
    app_env: str = "development"
    api_prefix: str = "/api"
    database_url: str = "postgresql://postgres.qzexwdzkykkzklbtxyjf:Di23ks67haMall@aws-0-ap-south-1.pooler.supabase.com:5432/postgres"
    jwt_secret_key: str
    jwt_algorithm: Literal["HS256"] = "HS256"
    jwt_access_token_minutes: int = 30
    cors_origins: list[str] = ["http://localhost:5173"]
    upload_dir: Path = Path("./storage/uploads")
    max_upload_size_mb: int = 50
    llm_api_key: str | None = None
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        # Render Postgres connection strings use postgresql://; select the
        # psycopg v3 driver explicitly because it is the installed driver.
        if isinstance(value, str) and value.startswith("postgres://"):
            return "postgresql+psycopg://" + value.removeprefix("postgres://")
        if isinstance(value, str) and value.startswith("postgresql://"):
            return "postgresql+psycopg://" + value.removeprefix("postgresql://")
        return value

    @field_validator("jwt_secret_key")
    @classmethod
    def validate_jwt_secret(cls, value: str) -> str:
        if len(value) < 32:
            raise ValueError("JWT_SECRET_KEY must contain at least 32 characters")
        return value

    @field_validator("jwt_access_token_minutes")
    @classmethod
    def validate_token_lifetime(cls, value: int) -> int:
        if value < 1 or value > 1440:
            raise ValueError("JWT_ACCESS_TOKEN_MINUTES must be between 1 and 1440")
        return value

    @field_validator("max_upload_size_mb")
    @classmethod
    def validate_upload_size(cls, value: int) -> int:
        if value < 1 or value > 1024:
            raise ValueError("MAX_UPLOAD_SIZE_MB must be between 1 and 1024")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()

