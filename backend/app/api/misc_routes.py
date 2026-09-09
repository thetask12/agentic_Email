from fastapi import APIRouter, HTTPException

from app.repositories.repositories import (
    activity_log_repo, campaign_repo, settings_repo, job_repo, lead_repo, email_queue_repo, reply_repo,
    search_run_repo, company_repo, contact_repo, email_draft_repo, email_event_repo,
)
from app.schemas.requests import SettingsPatchRequest
from app.services.analytics_service import get_dashboard, get_analytics
from app.services.apps_script_sync_service import sync_config_to_apps_script
from app.services.daily_search_scheduler import emails_remaining_today, DAILY_TOTAL_EMAIL_CAP
from app.utils.ids import new_id
from app.config.settings import get_settings

router = APIRouter(prefix="/api", tags=["misc"])


@router.get("/activity")
async def list_activity(lead_id: str | None = None, company_id: str | None = None,
                         activity_type: str | None = None, limit: int = 300):
    items = await activity_log_repo.list_all()
    if lead_id:
        items = [a for a in items if a.get("lead_id") == lead_id]
    if company_id:
        items = [a for a in items if a.get("company_id") == company_id]
    if activity_type:
        items = [a for a in items if a.get("activity_type") == activity_type]
    items.sort(key=lambda r: r.get("created_at", ""), reverse=True)
    return {"items": items[:limit], "total": len(items)}


@router.get("/campaigns")
async def list_campaigns():
    items = await campaign_repo.list_all()
    return {"items": items, "total": len(items)}


@router.get("/campaigns/{campaign_id}")
async def get_campaign(campaign_id: str):
    campaign = await campaign_repo.get_by_id(campaign_id)
    if not campaign:
        raise HTTPException(404, "Campaign not found")
    jobs = await job_repo.find_where(job_title=campaign.get("job_title", ""))
    leads = await lead_repo.list_all()
    queue = await email_queue_repo.list_all()
    replies = await reply_repo.list_all()
    return {
        **campaign,
        "funnel": {
            "jobs": len(jobs),
            "leads": len(leads),
            "emails_sent": len([q for q in queue if q.get("status") == "SENT"]),
            "replies": len(replies),
            "interested": len([l for l in leads if l.get("status") in ("INTERESTED", "MEETING_REQUESTED")]),
            "meetings": len([r for r in replies if r.get("reply_type") == "MEETING_REQUEST"]),
        },
    }


@router.post("/campaigns")
async def create_campaign(name: str, description: str = "", job_title: str = "", state: str = "",
                           city: str = "", sources: str = "", template_id: str = ""):
    return await campaign_repo.create({
        "campaign_id": new_id("campaign"), "name": name, "description": description,
        "job_title": job_title, "state": state, "city": city, "sources": sources,
        "template_id": template_id, "status": "DRAFT",
    })


@router.get("/analytics")
async def analytics(date_from: str | None = None, date_to: str | None = None):
    return await get_analytics(date_from, date_to)


@router.get("/dashboard")
async def dashboard():
    return await get_dashboard()


@router.get("/settings")
async def get_settings_route():
    items = await settings_repo.list_all()
    settings = get_settings()
    return {
        "values": {s["key"]: s["value"] for s in items},
        "env": {
            "email_test_mode": settings.email_test_mode,
            "mock_mode": settings.mock_mode,
            "max_follow_ups": settings.max_follow_ups,
            "queue_batch_size": settings.queue_batch_size,
            "queue_max_attempts": settings.queue_max_attempts,
            "sheets_configured": settings.sheets_configured,
            "openai_configured": settings.openai_configured,
            "web_search_configured": settings.tavily_configured,
        },
    }


@router.patch("/settings")
async def patch_settings(req: SettingsPatchRequest):
    for key, value in req.values.items():
        existing = await settings_repo.get_by_id(key)
        if existing:
            await settings_repo.update(key, {"value": value})
        else:
            await settings_repo.create({"key": key, "value": value, "description": ""})
    items = await settings_repo.list_all()
    return {"values": {s["key"]: s["value"] for s in items}}


@router.post("/settings/sync-apps-script")
async def sync_apps_script_now():
    """Manually re-push TEST_EMAIL/EMAIL_TEST_MODE/sender identity to Apps
    Script's Script Properties (also runs automatically on backend
    startup) — use this after changing Render env vars without redeploying,
    or to confirm the sync actually reached Apps Script."""
    await sync_config_to_apps_script()
    return {"status": "sync triggered — check Apps Script execution logs for the result"}


@router.post("/settings/resend-test-mode-emails")
async def resend_test_mode_emails(limit: int | None = None):
    """ONE-TIME MIGRATION UTILITY (per explicit user instruction, 2026-08-27):
    while EMAIL_TEST_MODE was on, every queued email was actually delivered
    to TEST_EMAIL instead of the real recipient — the real company inboxes
    never received anything, even though EMAIL_QUEUE/EMAIL_EVENTS recorded
    them as SENT. Now that real sending is live, those rows need to go out
    for real. This finds every EMAIL_QUEUE row created while test_mode was
    true and still in SENT status, and resets it to PENDING (clearing the
    prior send metadata) so Apps Script's queue worker picks it up again on
    its next 1-minute run and sends it to the actual recipient this time.
    Real-mode rows (test_mode=false) are left untouched — this never
    touches or duplicates a genuinely already-sent real email, since the
    existing recipient-level duplicate guard in search_service.py works off
    EMAIL_DRAFTS existing, not this queue status.

    `limit`: per explicit user instruction, these backlog resends count
    against the SAME daily total-email cap as the automated daily search
    (see daily_search_scheduler.py's DAILY_TOTAL_EMAIL_CAP). By default
    (limit unset) this resets only however many rows are still allowed
    today given what's already been queued today from any source — call it
    again on later days and it picks up where it left off, never exceeding
    the shared daily cap. Pass an explicit `limit` only to intentionally
    override that (e.g. for a controlled manual test)."""
    if limit is None:
        limit = await emails_remaining_today()
        if limit <= 0:
            return {"reset_count": 0, "remaining_backlog": None,
                    "reset_items": [], "note": f"today's {DAILY_TOTAL_EMAIL_CAP}-email cap already reached"}
    items = await email_queue_repo.list_all()
    reset = []
    for item in items:
        if len(reset) >= limit:
            break
        is_test_row = str(item.get("test_mode", "")).strip().lower() in ("true", "1")
        if is_test_row and item.get("status") == "SENT":
            await email_queue_repo.update(item["queue_id"], {
                "status": "PENDING",
                "test_mode": False,
                "attempts": 0,
                "sent_at": "",
                "message_id": "",
                "thread_id": "",
                "error_message": "",
            })
            reset.append({"queue_id": item["queue_id"], "recipient_email": item.get("recipient_email", "")})
    remaining = len([
        i for i in items
        if str(i.get("test_mode", "")).strip().lower() in ("true", "1") and i.get("status") == "SENT"
    ]) - len(reset)
    return {"reset_count": len(reset), "remaining_backlog": max(remaining, 0), "reset_items": reset}


@router.post("/settings/reset-all-data")
async def reset_all_data(confirm: str = ""):
    """ONE-TIME ADMIN UTILITY (per explicit user instruction, 2026-08-27):
    wipes every data row (header row kept) from SEARCH_RUNS, JOBS,
    COMPANIES, CONTACTS, LEADS, EMAIL_DRAFTS, EMAIL_QUEUE, EMAIL_EVENTS.
    Used to start completely fresh after the EMAIL_QUEUE sheet was
    accidentally emptied by hand and needed a clean, consistent restart
    across every related tab rather than a partial manual restore.

    Requires ?confirm=yes to actually run, as a guard against an accidental
    call — this is irreversible (no soft-delete/undo on the Sheets side)."""
    if confirm != "yes":
        raise HTTPException(400, "Pass ?confirm=yes to actually wipe all data — this cannot be undone.")

    repos_to_clear = [
        ("SEARCH_RUNS", search_run_repo),
        ("JOBS", job_repo),
        ("COMPANIES", company_repo),
        ("CONTACTS", contact_repo),
        ("LEADS", lead_repo),
        ("EMAIL_DRAFTS", email_draft_repo),
        ("EMAIL_QUEUE", email_queue_repo),
        ("EMAIL_EVENTS", email_event_repo),
    ]
    cleared = []
    for name, repo in repos_to_clear:
        await repo.clear_all()
        cleared.append(name)
    return {"cleared": cleared, "note": "Header rows kept. Restart the backend/search fresh."}


@router.get("/health")
async def health():
    settings = get_settings()
    return {
        "status": "ok",
        "sheets_configured": settings.sheets_configured,
        "openai_configured": settings.openai_configured,
        "web_search_configured": settings.tavily_configured,
        "email_test_mode": settings.email_test_mode,
        "mock_mode": settings.mock_mode,
    }
