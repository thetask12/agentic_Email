"""
OpenAI client wrapper using structured outputs (response_format=json_schema)
per System.txt rule 88 — never parse unreliable free-form JSON when
structured outputs are available.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from openai import OpenAI

from app.config.settings import get_settings

logger = logging.getLogger("openai_client")

_client: OpenAI | None = None


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
    schema: dict[str, Any],
    schema_name: str,
) -> dict[str, Any] | None:
    """Call OpenAI with a strict JSON schema. Returns None if OpenAI is not configured
    or the call fails — callers must handle None (e.g. leave status PENDING/UNANALYZED,
    never fabricate a result)."""
    client = get_client()
    if client is None:
        logger.warning("OpenAI not configured — skipping %s", schema_name)
        return None
    settings = get_settings()
    try:
        response = client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {"name": schema_name, "schema": schema, "strict": True},
            },
            temperature=0.3,
        )
        content = response.choices[0].message.content
        return json.loads(content)
    except Exception as exc:  # pragma: no cover - network dependent
        logger.error("OpenAI call failed for %s: %s", schema_name, exc)
        return None
