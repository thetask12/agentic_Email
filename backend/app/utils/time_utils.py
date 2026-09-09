"""UTC timestamp helpers. All stored timestamps are ISO-8601 UTC strings."""
from datetime import datetime, timezone, timedelta


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utcnow().isoformat()


def parse_iso(value: str) -> datetime:
    if not value:
        raise ValueError("empty timestamp")
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def is_due(scheduled_iso: str) -> bool:
    try:
        return parse_iso(scheduled_iso) <= utcnow()
    except ValueError:
        return False


def days_overdue(scheduled_iso: str) -> int:
    try:
        delta = utcnow() - parse_iso(scheduled_iso)
        return max(0, delta.days)
    except ValueError:
        return 0


def date_range_bounds(preset: str, custom_start: str | None = None, custom_end: str | None = None):
    """Return (start, end) datetimes in UTC for a named preset."""
    now = utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if preset == "today":
        return today_start, today_start + timedelta(days=1)
    if preset == "yesterday":
        return today_start - timedelta(days=1), today_start
    if preset == "tomorrow":
        return today_start + timedelta(days=1), today_start + timedelta(days=2)
    if preset == "last_7_days":
        return today_start - timedelta(days=7), today_start + timedelta(days=1)
    if preset == "last_30_days":
        return today_start - timedelta(days=30), today_start + timedelta(days=1)
    if preset == "next_7_days":
        return today_start, today_start + timedelta(days=8)
    if preset == "this_week":
        start = today_start - timedelta(days=today_start.weekday())
        return start, start + timedelta(days=7)
    if preset == "this_month":
        start = today_start.replace(day=1)
        return start, now
    if preset == "last_month":
        first_this = today_start.replace(day=1)
        last_month_end = first_this
        last_month_start = (first_this - timedelta(days=1)).replace(day=1)
        return last_month_start, last_month_end
    if preset == "custom" and custom_start and custom_end:
        return parse_iso(custom_start), parse_iso(custom_end)
    # "all"
    return None, None
