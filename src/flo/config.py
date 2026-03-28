from __future__ import annotations

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="FLO_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Server
    # Default to localhost-only; set FLO_HOST=0.0.0.0 only behind an authenticated proxy
    host: str = "127.0.0.1"
    port: int = 8000
    # Validated enum — prevents silent dev-mode exposure from typos like "prod"
    env: Literal["development", "production", "test"] = "development"
    log_level: str = "info"

    # LLM
    cheap_model: str = "gpt-4o-mini"
    premium_model: str = "gpt-4o"

    # Memory
    max_messages: int = 20

    # Database
    db_path: str = "flo.db"

    # Google APIs
    google_credentials_path: str = "credentials.json"
    google_token_path: str = "token.json"

    # LLM call timeout
    llm_timeout: int = 30  # seconds

    # Search
    search_provider: str = "tavily"
    search_api_key: str = ""

    # Security
    # Optional API key for /chat authentication. When non-empty, all requests to
    # /chat must supply the matching value in the X-API-Key header (issue #1).
    api_key: str = ""
    # Hard cap on incoming message length to prevent unbounded LLM token spend
    # (issue #9)
    max_message_length: int = 4096
    # Allowlist of permitted recipient domains for send_email (empty = allow all,
    # which is insecure; set e.g. "example.com,example.org") (issue #5)
    allowed_email_domains: list[str] = []
    # Allowed CORS origins for browser-based clients (empty = deny all cross-origin
    # requests, which is the secure default for a personal API) (issue #11)
    cors_origins: list[str] = []
    # Per-IP rate limit: maximum requests to /chat per minute (issue #3)
    rate_limit_per_minute: int = 60

    @property
    def is_production(self) -> bool:
        return self.env == "production"


def get_settings() -> Settings:
    return Settings()
