"""Dashboard + analytics aggregation (System.txt sections 4, 76-79, 132-133).
All numbers are computed live from the sheet-backed repositories — never
fabricated or cached with stale placeholder values."""
from collections import Counter, defaultdict

from app.models.enums import QueueStatus, LeadStatus, FollowUpStatus
from app.repositories.repositories import (
    job_repo, company_repo, lead_repo, email_draft_repo, email_queue_repo, reply_repo,
    follow_up_repo, conversation_repo,
)
from app.utils.time_utils import is_due, days_overdue, date_range_bounds, parse_iso
from app.config.settings import get_settings


async def get_dashboard() -> dict:
    settings = get_settings()
    jobs = await job_repo.list_all()
    companies = await company_repo.list_all()
    leads = await lead_repo.list_all()
    drafts = await email_draft_repo.list_all()
    queue = await email_queue_repo.list_all()
    replies = await reply_repo.list_all()
    follow_ups = await follow_up_repo.list_all()
    conversations = await conversation_repo.list_all()

    qualified_jobs = [j for j in jobs if str(j.get("is_qualified")).lower() in ("true", "1")]

    sent = [q for q in queue if q.get("status") == QueueStatus.SENT.value]
    failed = [q for q in queue if q.get("status") == QueueStatus.FAILED.value]
    approved_drafts = [d for d in drafts if d.get("status") in ("APPROVED", "QUEUED", "SENT")]
    queued = [q for q in queue if q.get("status") == QueueStatus.PENDING.value]

    fu_due_today = [f for f in follow_ups if f.get("status") in (FollowUpStatus.SCHEDULED.value, FollowUpStatus.DUE.value)
                    and is_due(f.get("scheduled_at", ""))]
    fu_sent = [f for f in follow_ups if f.get("status") == FollowUpStatus.SENT.value]
    fu_overdue = [f for f in fu_due_today if days_overdue(f.get("scheduled_at", "")) > 0]

    active_conversations = [c for c in conversations if c.get("status") == "ACTIVE"]
    interested = [l for l in leads if l.get("status") in ("INTERESTED", "MEETING_REQUESTED")]
    meetings = [l for l in leads if l.get("status", "").startswith("MEETING")]
    not_interested = [l for l in leads if l.get("status") == "NOT_INTERESTED"]
    bounced = [l for l in leads if l.get("status") == "BOUNCED"]
    suppressed = [l for l in leads if l.get("status") == "SUPPRESSED"]

    today_start, today_end = date_range_bounds("today")

    def in_today(iso_str: str) -> bool:
        if not iso_str:
            return False
        try:
            dt = parse_iso(iso_str)
            return today_start <= dt < today_end
        except ValueError:
            return False

    today_jobs = [j for j in jobs if in_today(j.get("created_at", ""))]
    today_companies = [c for c in companies if in_today(c.get("created_at", ""))]
    today_leads = [l for l in leads if in_today(l.get("created_at", ""))]
    today_sent = [q for q in sent if in_today(q.get("sent_at", ""))]
    today_replies = [r for r in replies if in_today(r.get("received_at", ""))]
    today_fu_due = [f for f in fu_due_today]
    today_meetings = [r for r in replies if r.get("reply_type") == "MEETING_REQUEST" and in_today(r.get("received_at", ""))]

    pipeline_counts = Counter(l.get("status", "") for l in leads)

    return {
        "email_test_mode": settings.email_test_mode,
        "totals": {
            "total_jobs": len(jobs),
            "total_qualified_jobs": len(qualified_jobs),
            "total_companies": len(companies),
            "total_leads": len(leads),
            "emails_found": len({l.get("contact_id") for l in leads if l.get("contact_id")}),
            "emails_approved": len(approved_drafts),
            "emails_queued": len(queued),
            "emails_sent": len(sent),
            "emails_failed": len(failed),
            "replies_received": len(replies),
            "follow_ups_due": len(fu_due_today),
            "follow_ups_sent": len(fu_sent),
            "active_conversations": len(active_conversations),
            "interested_leads": len(interested),
            "meeting_requests": len(meetings),
            "not_interested": len(not_interested),
            "bounced": len(bounced),
            "suppressed": len(suppressed),
        },
        "today": {
            "jobs_found": len(today_jobs),
            "new_companies": len(today_companies),
            "new_leads": len(today_leads),
            "emails_sent": len(today_sent),
            "replies_received": len(today_replies),
            "follow_ups_due": len(today_fu_due),
            "meetings_requested": len(today_meetings),
        },
        "follow_up_alerts": {
            "due_today": len(fu_due_today) - len(fu_overdue),
            "overdue": len(fu_overdue),
            "upcoming": len([f for f in follow_ups if f.get("status") == FollowUpStatus.SCHEDULED.value
                              and not is_due(f.get("scheduled_at", ""))]),
        },
        "pipeline": dict(pipeline_counts),
    }


async def get_analytics(date_from: str | None = None, date_to: str | None = None) -> dict:
    leads = await lead_repo.list_all()
    queue = await email_queue_repo.list_all()
    replies = await reply_repo.list_all()
    follow_ups = await follow_up_repo.list_all()
    companies = await company_repo.list_all()
    jobs = await job_repo.list_all()

    sent = [q for q in queue if q.get("status") == QueueStatus.SENT.value]

    leads_by_state = Counter()
    for l in leads:
        company = next((c for c in companies if c.get("company_id") == l.get("company_id")), None)
        if company and company.get("state"):
            leads_by_state[company["state"]] += 1

    leads_by_source = Counter()
    for l in leads:
        job = next((j for j in jobs if j.get("job_id") == l.get("job_id")), None)
        if job and job.get("source"):
            leads_by_source[job["source"]] += 1

    leads_by_job_title = Counter()
    for l in leads:
        job = next((j for j in jobs if j.get("job_id") == l.get("job_id")), None)
        if job and job.get("job_title"):
            leads_by_job_title[job["job_title"]] += 1

    def by_day(rows: list[dict], field: str) -> dict:
        counts: dict[str, int] = defaultdict(int)
        for r in rows:
            ts = r.get(field, "")
            if not ts:
                continue
            try:
                day = parse_iso(ts).date().isoformat()
                counts[day] += 1
            except ValueError:
                continue
        return dict(sorted(counts.items()))

    reply_rate = (len(replies) / len(sent) * 100) if sent else 0.0
    positive_replies = [r for r in replies if r.get("sentiment") == "POSITIVE" or r.get("reply_type") in ("INTERESTED", "MEETING_REQUEST", "POSITIVE")]
    meetings = [r for r in replies if r.get("reply_type") == "MEETING_REQUEST"]

    return {
        "leads_by_state": dict(leads_by_state),
        "leads_by_source": dict(leads_by_source),
        "leads_by_job_title": dict(leads_by_job_title),
        "emails_by_day": by_day(sent, "sent_at"),
        "replies_by_day": by_day(replies, "received_at"),
        "follow_ups_by_day": by_day([f for f in follow_ups if f.get("status") == "SENT"], "sent_at"),
        "reply_rate": round(reply_rate, 1),
        "positive_reply_rate": round((len(positive_replies) / len(sent) * 100) if sent else 0.0, 1),
        "meeting_rate": round((len(meetings) / len(sent) * 100) if sent else 0.0, 1),
        "total_leads": len(leads),
        "total_sent": len(sent),
        "opportunity_score_distribution": _score_buckets(leads),
        "pipeline": dict(Counter(l.get("status", "") for l in leads)),
    }


def _score_buckets(leads: list[dict]) -> dict:
    buckets = {"0-25": 0, "26-50": 0, "51-75": 0, "76-100": 0}
    for l in leads:
        try:
            score = int(l.get("botivate_opportunity_score") or 0)
        except (TypeError, ValueError):
            score = 0
        if score <= 25:
            buckets["0-25"] += 1
        elif score <= 50:
            buckets["26-50"] += 1
        elif score <= 75:
            buckets["51-75"] += 1
        else:
            buckets["76-100"] += 1
    return buckets
