"""
Central application configuration loaded from environment variables.
Never hardcode secrets. Never expose these values to the frontend directly.
"""
from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # OpenAI
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    # Google Search — DEPRECATED, kept only so old .env files don't break
    # pydantic-settings parsing. Job discovery now uses Tavily (see
    # tavily_api_key below); this integration is no longer called.
    google_search_api_key: str = ""
    google_search_engine_id: str = ""

    # Tavily Search (job discovery web search)
    tavily_api_key: str = ""

    # Google Sheets
    google_sheets_id: str = ""
    google_service_account_email: str = ""
    google_service_account_private_key: str = ""

    # Sender identity
    botivate_sender_email: str = ""
    botivate_sender_name: str = "Satyendra Kumar Tandan"
    botivate_website_url: str = "https://botivate.in"
    autorocket_website_url: str = "https://autorocket.botivate.in"

    # Apps Script bridge
    apps_script_web_app_url: str = ""
    apps_script_shared_secret: str = ""

    # Safety
    email_test_mode: bool = True
    test_email: str = ""
    mock_mode: bool = False

    # Queue / follow-up limits
    queue_batch_size: int = 10
    queue_max_attempts: int = 3
    max_follow_ups: int = 4

    # Backend
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    backend_cors_origins: str = "http://localhost:3000"
    api_auth_token: str = ""
    log_level: str = "INFO"

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.backend_cors_origins.split(",") if o.strip()]

    @property
    def sheets_configured(self) -> bool:
        return bool(
            self.google_sheets_id
            and self.google_service_account_email
            and self.google_service_account_private_key
        )

    @property
    def openai_configured(self) -> bool:
        return bool(self.openai_api_key)

    @property
    def google_search_configured(self) -> bool:
        return bool(self.google_search_api_key and self.google_search_engine_id)

    @property
    def tavily_configured(self) -> bool:
        return bool(self.tavily_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
