"""
FastAPI router for the Job Outreach module — mounted under /api/job-outreach
in app/main.py, additively (does not touch any existing router).
"""
from __future__ import annotations

from fastapi import APIRouter

from app.job_outreach import service
from app.job_outreach.repositories import company_repo, email_queue_repo

router = APIRouter(prefix="/api/job-outreach", tags=["job-outreach"])


@router.post("/start")
async def start_automation():
    await service.start()
    return await service.get_status()


@router.post("/stop")
async def stop_automation():
    await service.stop()
    return await service.get_status()


@router.get("/status")
async def status():
    return await service.get_status()


@router.get("/companies")
async def list_companies(limit: int = 100):
    items = await company_repo.list_all()
    items.sort(key=lambda r: r.get("created_at", ""), reverse=True)
    return {"items": items[:limit], "total": len(items)}


@router.get("/queue")
async def list_queue(limit: int = 100):
    items = await email_queue_repo.list_all()
    items.sort(key=lambda r: r.get("created_at", ""), reverse=True)
    return {"items": items[:limit], "total": len(items)}
