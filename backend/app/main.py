"""FastAPI entrypoint — Botivate AI Job Intelligence + Outreach System backend."""
import logging
from contextlib import asynccontextmanager

import gspread
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config.settings import get_settings
from app.services.bootstrap_service import seed_defaults
from app.services.apps_script_sync_service import sync_config_to_apps_script
from app.services.daily_search_scheduler import start_daily_search_scheduler, stop_daily_search_scheduler
from app.api import (
    search_routes, catalog_routes, lead_routes, email_routes, template_routes,
    follow_up_routes, reply_routes, misc_routes,
)
from app.proxy import mount_frontend_proxy

settings = get_settings()
logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
logger = logging.getLogger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Botivate backend — sheets_configured=%s openai_configured=%s email_test_mode=%s",
                settings.sheets_configured, settings.openai_configured, settings.email_test_mode)
    await seed_defaults()
    # Push TEST_EMAIL/EMAIL_TEST_MODE/sender identity to Apps Script's own
    # Script Properties so changing these in Render's env vars is enough -
    # see apps_script_sync_service.py. Best-effort: a failure here never
    # blocks startup, it just means Apps Script keeps its last-synced values.
    await sync_config_to_apps_script()
    start_daily_search_scheduler()
    yield
    stop_daily_search_scheduler()
    logger.info("Shutting down Botivate backend")


app = FastAPI(
    title="Botivate AI Job Intelligence & Outreach API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(gspread.exceptions.APIError)
async def sheets_api_error_handler(request: Request, exc: gspread.exceptions.APIError):
    """Google Sheets enforces a default quota of 60 read/write requests per
    minute per user. A burst of leads created by a search run (each lead
    touches several sheet reads/writes) plus normal dashboard/detail
    polling can exceed that quota. Without this handler, the raw gspread
    APIError propagates as an opaque 500 with no message, which is what
    surfaced as "Failed to load resource: 500" / "Could not load data" in
    the browser. Surface a clear, actionable message instead — this is a
    real, expected constraint of using Sheets as the database (see
    docs/troubleshooting.md), not a bug to silently retry away."""
    status = getattr(exc.response, "status_code", 500) if getattr(exc, "response", None) else 500
    is_quota = status == 429
    logger.warning("Google Sheets API error on %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(
        status_code=503 if is_quota else 502,
        content={
            "detail": (
                "Google Sheets API quota exceeded (60 requests/minute/user default limit). "
                "This is expected under heavy search activity — wait a minute and retry."
                if is_quota
                else "Google Sheets API request failed. Check that the sheet is shared with "
                     "the service account and try again."
            ),
            "quota_exceeded": is_quota,
        },
    )


app.include_router(search_routes.router)
app.include_router(catalog_routes.router)
app.include_router(lead_routes.router)
app.include_router(email_routes.router)
app.include_router(template_routes.router)
app.include_router(follow_up_routes.router)
app.include_router(reply_routes.router)
app.include_router(misc_routes.router)


@app.get("/api")
async def api_root():
    return {"service": "Botivate AI Job Intelligence & Outreach API", "status": "running"}


# Must be mounted LAST: this is a catch-all that forwards any request not
# matched by the /api/* routers above to the Next.js frontend (see
# backend/app/proxy.py). Only active when FRONTEND_INTERNAL_URL is set,
# i.e. inside the combined single-container Docker image used on Render.
mount_frontend_proxy(app)
