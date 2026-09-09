"""
Generic infrastructure configuration shared by the whole backend process
(CORS, host/port, logging) plus the shared AI/search provider keys
(OpenAI, Tavily) used by app/integrations/. This is intentionally NOT the
Job Outreach module's own settings — see app/job_outreach/config.py for
that (JOB_OUTREACH_* env vars, its own Google Sheet/service account/sender
identity). Never hardcode secrets here. Never expose these values to the
frontend directly.
"""
from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Shared AI / search providers — used by app/integrations/openai_client.py
    # and app/integrations/web_search.py, which the Job Outreach module calls
    # into directly.
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    tavily_api_key: str = ""

    # Backend / infra
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    backend_cors_origins: str = "http://localhost:3000"
    api_auth_token: str = ""
    log_level: str = "INFO"

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.backend_cors_origins.split(",") if o.strip()]

    @property
    def openai_configured(self) -> bool:
        return bool(self.openai_api_key)

    @property
    def tavily_configured(self) -> bool:
        return bool(self.tavily_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
