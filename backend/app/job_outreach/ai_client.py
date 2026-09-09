"""
OpenAI client wrapper for the Job Outreach module using Pydantic BaseModel
structured outputs (client.beta.chat.completions.parse()) instead of raw
JSON-schema dicts — the openai SDK's native Pydantic-model support gives
type-checked, auto-validated results instead of a plain dict the caller has
to trust. Kept as this module's own dedicated helper (not a change to the
shared app/integrations/openai_client.py) so job_outreach stays a
self-contained package with no dependency on that file's behavior.
"""
from __future__ import annotations

import logging
from typing import TypeVar

from openai import OpenAI
from pydantic import BaseModel

from app.config.settings import get_settings

logger = logging.getLogger("job_outreach.ai_client")

_client: OpenAI | None = None

T = TypeVar("T", bound=BaseModel)


def get_client() -> OpenAI | None:
    global _client
    settings = get_settings()
    if not settings.openai_configured:
        return None
    if _client is None:
        _client = OpenAI(api_key=settings.openai_api_key)
    return _client


def structured_completion(
    *,
    system_prompt: str,
    user_prompt: str,
    response_model: type[T],
) -> T | None:
    """Calls OpenAI with a Pydantic model as the strict response schema and
    returns a validated instance of it. Returns None if OpenAI is not
    configured, the call fails, or the model refused to answer — callers
    must handle None (e.g. skip/drop the lead, never fabricate a result)."""
    client = get_client()
    if client is None:
        logger.warning("OpenAI not configured — skipping %s", response_model.__name__)
        return None
    settings = get_settings()
    try:
        completion = client.beta.chat.completions.parse(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format=response_model,
            temperature=0.3,
        )
        message = completion.choices[0].message
        if message.refusal:
            logger.warning("OpenAI refused %s: %s", response_model.__name__, message.refusal)
            return None
        return message.parsed
    except Exception:  # pragma: no cover - network dependent
        logger.exception("OpenAI structured call failed for %s", response_model.__name__)
        return None
