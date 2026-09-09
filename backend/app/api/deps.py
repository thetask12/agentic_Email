"""Shared API dependencies: optional bearer-token auth (System.txt 81 — never
expose secrets, but an internal API token is reasonable for a private tool)."""
from fastapi import Header, HTTPException
from app.config.settings import get_settings


async def verify_api_token(authorization: str | None = Header(default=None)) -> None:
    settings = get_settings()
    if not settings.api_auth_token:
        return  # no auth configured — open for local dev
    expected = f"Bearer {settings.api_auth_token}"
    if authorization != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")
