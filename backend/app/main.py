"""FastAPI entrypoint — Job Outreach API backend."""
import logging
from contextlib import asynccontextmanager

import gspread
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config.settings import get_settings
from app.job_outreach.routes import router as job_outreach_router
from app.job_outreach.settings_store import ensure_seeded as job_outreach_ensure_seeded
from app.job_outreach.scheduler import start_scheduler as start_job_outreach_scheduler, stop_scheduler_task as stop_job_outreach_scheduler
from app.proxy import mount_frontend_proxy

settings = get_settings()
logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
logger = logging.getLogger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Job Outreach backend — openai_configured=%s tavily_configured=%s",
                settings.openai_configured, settings.tavily_configured)

    # Job Outreach module — personal job-application system, own sheet/
    # scheduler (see backend/app/job_outreach/). Its background loop is
    # always alive but only does work while the persisted automation_running
    # flag (SETTINGS tab) is true — see job_outreach/scheduler.py.
    await job_outreach_ensure_seeded()
    start_job_outreach_scheduler()

    yield
    stop_job_outreach_scheduler()
    logger.info("Shutting down Job Outreach backend")


app = FastAPI(
    title="Job Outreach API",
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
    minute per user. The Job Outreach module's sheets client
    (app/job_outreach/sheets.py) raises this same gspread exception type, so
    a burst of activity can still surface an opaque 500 with no message
    without this handler. Surface a clear, actionable message instead."""
    status = getattr(exc.response, "status_code", 500) if getattr(exc, "response", None) else 500
    is_quota = status == 429
    logger.warning("Google Sheets API error on %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(
        status_code=503 if is_quota else 502,
        content={
            "detail": (
                "Google Sheets API quota exceeded (60 requests/minute/user default limit). "
                "This is expected under heavy activity — wait a minute and retry."
                if is_quota
                else "Google Sheets API request failed. Check that the sheet is shared with "
                     "the service account and try again."
            ),
            "quota_exceeded": is_quota,
        },
    )


app.include_router(job_outreach_router)


@app.get("/api")
async def api_root():
    return {"service": "Job Outreach API", "status": "running"}


# Must be mounted LAST: this is a catch-all that forwards any request not
# matched by the /api/* routers above to the Next.js frontend (see
# backend/app/proxy.py). Only active when FRONTEND_INTERNAL_URL is set,
# i.e. inside the combined single-container Docker image.
mount_frontend_proxy(app)
