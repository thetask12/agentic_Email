"""Suppression list checks (System.txt sections 83-85). Checked before every
send/queue creation, at both the email-level and company-level."""
from app.repositories.repositories import suppression_repo
from app.utils.ids import new_id
from app.utils.time_utils import iso_now


async def is_suppressed(email: str, company_id: str | None = None) -> bool:
    email = (email or "").strip().lower()
    rows = await suppression_repo.list_all()
    for r in rows:
        if str(r.get("email", "")).strip().lower() == email:
            return True
        if company_id and str(r.get("company_id", "")) == company_id and r.get("email", "") == "":
            return True  # company-level suppression (blank email = whole company)
    return False


async def suppress(email: str, *, company_id: str | None = None, reason: str = "MANUAL",
                    source: str = "manual") -> dict:
    record = {
        "suppression_id": new_id("suppression"),
        "email": (email or "").strip().lower(),
        "company_id": company_id or "",
        "reason": reason,
        "source": source,
        "created_at": iso_now(),
    }
    return await suppression_repo.create(record)
