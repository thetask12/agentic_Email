"""Activity logging (System.txt sections 65-66). Every meaningful action
writes one ACTIVITY_LOG row so the lead timeline is complete and auditable."""
import json

from app.repositories.repositories import activity_log_repo, lead_repo
from app.utils.ids import new_id
from app.utils.time_utils import iso_now


async def log_activity(*, lead_id: str | None, company_id: str | None, activity_type: str,
                        description: str, metadata: dict | None = None, created_by: str = "system") -> dict:
    record = {
        "activity_id": new_id("activity"),
        "lead_id": lead_id or "",
        "company_id": company_id or "",
        "activity_type": activity_type,
        "description": description,
        "metadata": json.dumps(metadata or {}, ensure_ascii=False),
        "created_at": iso_now(),
        "created_by": created_by,
    }
    created = await activity_log_repo.create(record)
    if lead_id:
        await lead_repo.update(lead_id, {"last_activity_at": iso_now()})
    return created
