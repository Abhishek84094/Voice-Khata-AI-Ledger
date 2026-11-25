"""Core configuration and settings."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_SHOP_ID = "00000000-0000-0000-0000-000000000001"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "INFO"

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/voice_khata"
    ledger_key: str = ""
    jwt_secret: str = "default_secret_for_dev_mode_only"

    sarvam_api_key: str = ""
    groq_api_key: str = ""
    gnani_api_key: str = ""

    shopkeeper_default_language: str = "hi-IN"
    transcript_policy: str = "both"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
