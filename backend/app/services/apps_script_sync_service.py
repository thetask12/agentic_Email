"""
Pushes a small, explicit set of config values from the backend's own
environment (Render env vars) into the Apps Script project's Script
Properties, so an operator only has to change TEST_EMAIL/EMAIL_TEST_MODE/
BOTIVATE_SENDER_EMAIL/BOTIVATE_SENDER_NAME in ONE place (Render) instead of
also manually editing Script Properties in the Apps Script editor.

This is a one-way push (backend -> Apps Script), called on backend startup.
Apps Script itself still owns SHEET_ID/APPS_SCRIPT_SHARED_SECRET/etc. -
only the four keys below are ever synced, and only if both
APPS_SCRIPT_WEB_APP_URL and APPS_SCRIPT_SHARED_SECRET are configured (this
is a best-effort convenience, not a hard dependency - if it fails, Apps
Script just keeps whatever values are already set in its Script
Properties, exactly as before this existed).
"""
from __future__ import annotations

import logging

import httpx

from app.config.settings import get_settings

logger = logging.getLogger("apps_script_sync")


async def sync_config_to_apps_script() -> None:
    settings = get_settings()
    if not settings.apps_script_web_app_url:
        logger.info("APPS_SCRIPT_WEB_APP_URL not set — skipping Apps Script config sync")
        return

    payload = {
        "action": "sync_config",
        "secret": settings.apps_script_shared_secret,
        "TEST_EMAIL": settings.test_email,
        "EMAIL_TEST_MODE": "true" if settings.email_test_mode else "false",
        "BOTIVATE_SENDER_EMAIL": settings.botivate_sender_email,
        "BOTIVATE_SENDER_NAME": settings.botivate_sender_name,
    }
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.post(settings.apps_script_web_app_url, json=payload)
            resp.raise_for_status()
            data = resp.json()
        if data.get("ok"):
            logger.info("Apps Script config sync applied: %s", data.get("applied"))
        else:
            logger.warning("Apps Script config sync rejected: %s", data.get("error"))
    except httpx.HTTPError as exc:
        logger.warning(
            "Apps Script config sync failed (%s) — Apps Script keeps its existing "
            "Script Property values, no functional impact beyond staying out of sync.", exc,
        )
    except ValueError:
        logger.warning("Apps Script config sync: non-JSON response from Web App URL")
