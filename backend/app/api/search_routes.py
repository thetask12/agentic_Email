import asyncio
import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException
from sse_starlette.sse import EventSourceResponse

from app.schemas.requests import SearchRequest
from app.repositories.repositories import search_run_repo, source_status_repo
from app.services.search_service import start_search, execute_search, cancel_run_pending_emails
from app.services.event_bus import event_bus
from app.services.search_cancellation import request_cancellation

router = APIRouter(prefix="/api", tags=["search"])
logger = logging.getLogger("search_routes")


@router.post("/search")
async def create_search(req: SearchRequest, background_tasks: BackgroundTasks):
    run = await start_search(
        job_title=req.job_title, state=req.state, city=req.city,
        date_filter=req.date_filter, experience=req.experience,
        sources=req.sources, result_limit=req.result_limit,
    )
    background_tasks.add_task(_run_safely, run["run_id"])
    return run


async def _run_safely(run_id: str) -> None:
    try:
        await execute_search(run_id)
    except Exception as exc:  # pragma: no cover
        logger.exception("Search run %s failed: %s", run_id, exc)
        await search_run_repo.update(run_id, {"status": "FAILED", "error_message": str(exc)})
        await event_bus.publish(run_id, "search_progress", {"status": "FAILED", "error": str(exc)})
        await event_bus.close(run_id)


@router.post("/search/{run_id}/stop")
async def stop_search(run_id: str):
    """Stop a running search immediately and cancel every not-yet-sent
    email it queued. Whatever leads/companies/emails were already created
    before this call stay as-is - this only prevents the run from finding
    more jobs, and prevents anything still PENDING in EMAIL_QUEUE from
    this run's leads being sent later by Apps Script."""
    run = await search_run_repo.get_by_id(run_id)
    if not run:
        raise HTTPException(404, "Search run not found")
    if run.get("status") not in ("PENDING", "RUNNING"):
        return run  # already finished one way or another — nothing to stop

    request_cancellation(run_id)
    cancelled_count = await cancel_run_pending_emails(run_id)

    updated = await search_run_repo.update(run_id, {"status": "CANCELLED"})
    await event_bus.publish(run_id, "search_progress", {"status": "CANCELLED", "cancelled_emails": cancelled_count})
    await event_bus.close(run_id)
    return {**(updated or run), "cancelled_pending_emails": cancelled_count}


@router.get("/search/{run_id}")
async def get_search(run_id: str):
    run = await search_run_repo.get_by_id(run_id)
    if not run:
        raise HTTPException(404, "Search run not found")
    return run


@router.get("/search")
async def list_searches():
    items = await search_run_repo.list_all()
    items.sort(key=lambda r: r.get("started_at", ""), reverse=True)
    return {"items": items, "total": len(items)}


@router.get("/search/{run_id}/stream")
async def stream_search(run_id: str):
    run = await search_run_repo.get_by_id(run_id)
    if not run:
        raise HTTPException(404, "Search run not found")

    queue = event_bus.subscribe(run_id)

    async def event_generator():
        try:
            if run.get("status") in ("COMPLETED", "FAILED", "CANCELLED"):
                yield {"event": "search_progress", "data": '{"status": "' + run["status"] + '"}'}
                return
            while True:
                item = await queue.get()
                yield item
                if item.get("event") == "done":
                    break
        finally:
            event_bus.unsubscribe(run_id, queue)

    return EventSourceResponse(event_generator())


@router.get("/sources")
async def list_sources():
    items = await source_status_repo.list_all()
    return {"items": items, "total": len(items)}
