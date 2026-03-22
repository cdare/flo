from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="FLO_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    env: str = "development"
    log_level: str = "info"

    # LLM
    cheap_model: str = "gpt-4o-mini"
    premium_model: str = "gpt-4o"

    # Memory
    max_messages: int = 20

    # Google APIs
    google_credentials_path: str = "credentials.json"
    google_token_path: str = "token.json"

    # Search
    search_provider: str = "tavily"
    search_api_key: str = ""

    @property
    def is_production(self) -> bool:
        return self.env == "production"


def get_settings() -> Settings:
    return Settings()
