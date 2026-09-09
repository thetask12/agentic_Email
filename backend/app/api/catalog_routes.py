"""Read-only catalog endpoints: jobs, companies. (Leads/emails/etc. have their own files.)"""
from fastapi import APIRouter, HTTPException, Query

from app.repositories.repositories import job_repo, company_repo, lead_repo, contact_repo

router = APIRouter(prefix="/api", tags=["catalog"])


@router.get("/jobs")
async def list_jobs(state: str | None = None, city: str | None = None, source: str | None = None,
                     search: str | None = None, limit: int = Query(200, le=1000)):
    items = await job_repo.list_all()
    if state:
        items = [j for j in items if j.get("state", "").lower() == state.lower()]
    if city:
        items = [j for j in items if j.get("city", "").lower() == city.lower()]
    if source:
        items = [j for j in items if j.get("source") == source]
    if search:
        s = search.lower()
        items = [j for j in items if s in j.get("job_title", "").lower() or s in j.get("company_name", "").lower()]
    items.sort(key=lambda r: r.get("created_at", ""), reverse=True)
    return {"items": items[:limit], "total": len(items)}


@router.get("/jobs/{job_id}")
async def get_job(job_id: str):
    job = await job_repo.get_by_id(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job


@router.get("/companies")
async def list_companies(state: str | None = None, search: str | None = None,
                          limit: int = Query(200, le=1000)):
    items = await company_repo.list_all()
    if state:
        items = [c for c in items if c.get("state", "").lower() == state.lower()]
    if search:
        s = search.lower()
        items = [c for c in items if s in c.get("company_name", "").lower() or s in c.get("domain", "").lower()]
    items.sort(key=lambda r: r.get("created_at", ""), reverse=True)
    return {"items": items[:limit], "total": len(items)}


@router.get("/companies/{company_id}")
async def get_company(company_id: str):
    company = await company_repo.get_by_id(company_id)
    if not company:
        raise HTTPException(404, "Company not found")
    jobs = await job_repo.find_where(company_id=company_id)
    contacts = await contact_repo.find_where(company_id=company_id)
    leads = await lead_repo.find_where(company_id=company_id)
    return {**company, "jobs": jobs, "contacts": contacts, "leads": leads}
