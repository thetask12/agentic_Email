"""
Header-mapped CRUD repositories for the Job Outreach Google Sheet tabs (see
docs/job-outreach-schema.md for exact headers). Same BaseRepository pattern
as app/repositories/base.py, adapted to use JobOutreachSheetsClient and this
module's own settings — kept as a self-contained copy (not a subclass of the
existing BaseRepository) so this package never imports from, or depends on
the runtime state of, the main system's repositories/settings.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any

from starlette.concurrency import run_in_threadpool

from app.job_outreach.config import get_job_outreach_settings
from app.job_outreach.sheets import JobOutreachSheetsClient
from app.utils.time_utils import iso_now

logger = logging.getLogger("job_outreach.repository")

# Google Sheets enforces a default 60 read-requests/minute/user quota. This
# module hits SETTINGS very frequently (every automation tick checks
# running/cap/counters several times) and COMPANIES/SUPPRESSION_LIST on every
# candidate lead (dedup checks) — a short cache TTL was previously exhausting
# the quota within a single search cycle. 30s keeps status-polling (every 15s
# from the frontend) fresh enough while cutting repeated full-tab reads
# dramatically during a busy cycle.
LIST_CACHE_TTL_SECONDS = 30.0


class JobOutreachBaseRepository:
    SHEET_NAME: str = ""
    HEADERS: list[str] = []
    ID_FIELD: str = "id"

    def __init__(self) -> None:
        self.settings = get_job_outreach_settings()
        self._mem_store: list[dict[str, Any]] = []
        self._list_cache: list[dict[str, Any]] | None = None
        self._list_cache_at: float = 0.0
        self._use_sheets = self.settings.sheets_configured
        if self._use_sheets:
            self.client = JobOutreachSheetsClient.instance()
            try:
                self.client.ensure_worksheet(self.SHEET_NAME, self.HEADERS)
            except Exception as exc:  # pragma: no cover - network dependent
                logger.error("Failed to ensure worksheet %s: %s", self.SHEET_NAME, exc)
        else:
            self.client = None
            logger.warning(
                "Job Outreach sheets not configured — %s repository has no persistence",
                self.SHEET_NAME,
            )

    @staticmethod
    def _serialize(value: Any) -> Any:
        if isinstance(value, (list, dict)):
            return json.dumps(value, ensure_ascii=False)
        if value is None:
            return ""
        return value

    def _row_from_record(self, record: dict[str, Any]) -> list[Any]:
        return [self._serialize(record.get(h, "")) for h in self.HEADERS]

    def _invalidate_list_cache(self) -> None:
        self._list_cache = None
        self._list_cache_at = 0.0

    async def list_all(self, *, force_refresh: bool = False) -> list[dict[str, Any]]:
        if not self._use_sheets:
            return list(self._mem_store)
        now = time.monotonic()
        if (
            not force_refresh
            and self._list_cache is not None
            and (now - self._list_cache_at) < LIST_CACHE_TTL_SECONDS
        ):
            return self._list_cache
        rows = await run_in_threadpool(self.client.get_all_records, self.SHEET_NAME)
        self._list_cache = rows
        self._list_cache_at = now
        return rows

    async def _row_hint_for(self, id_value: str) -> int | None:
        if self._list_cache is None:
            return None
        for i, r in enumerate(self._list_cache):
            if r.get(self.ID_FIELD) == id_value:
                return i + 2
        return None

    async def get_by_id(self, id_value: str) -> dict[str, Any] | None:
        if self._use_sheets:
            row_hint = await self._row_hint_for(id_value)
            found = await run_in_threadpool(
                self.client.find_row_by_id, self.SHEET_NAME, self.ID_FIELD, id_value, row_hint
            )
            return found[1] if found else None
        for r in self._mem_store:
            if r.get(self.ID_FIELD) == id_value:
                return r
        return None

    async def create(self, record: dict[str, Any]) -> dict[str, Any]:
        record.setdefault("created_at", iso_now())
        record.setdefault("updated_at", iso_now())
        full = {h: record.get(h, "") for h in self.HEADERS}
        if self._use_sheets:
            await run_in_threadpool(self.client.append_row, self.SHEET_NAME, self._row_from_record(full))
            if self._list_cache is not None:
                self._list_cache.append(full)
        else:
            self._mem_store.append(full)
        return full

    async def update(self, id_value: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        patch = dict(patch)
        patch["updated_at"] = iso_now()
        if self._use_sheets:
            row_hint = await self._row_hint_for(id_value)
            found = await run_in_threadpool(
                self.client.find_row_by_id, self.SHEET_NAME, self.ID_FIELD, id_value, row_hint
            )
            if not found:
                return None
            row_number, existing = found
            merged = {**existing, **{k: self._serialize(v) for k, v in patch.items()}}
            await run_in_threadpool(
                self.client.update_row_simple, self.SHEET_NAME, row_number, self.HEADERS, merged
            )
            if self._list_cache is not None:
                for i, r in enumerate(self._list_cache):
                    if r.get(self.ID_FIELD) == id_value:
                        self._list_cache[i] = merged
                        break
            return merged
        for r in self._mem_store:
            if r.get(self.ID_FIELD) == id_value:
                r.update({k: self._serialize(v) for k, v in patch.items()})
                return r
        return None

    @staticmethod
    def _loose_eq(actual: Any, expected: Any) -> bool:
        if isinstance(expected, bool):
            actual_str = str(actual).strip().lower()
            return actual_str in ("true", "1") if expected else actual_str in ("false", "0", "")
        return str(actual) == str(expected)

    async def clear_all(self) -> None:
        if self._use_sheets:
            await run_in_threadpool(self.client.clear_data_rows, self.SHEET_NAME)
        else:
            self._mem_store.clear()
        self._invalidate_list_cache()

    async def find_where(self, **filters: Any) -> list[dict[str, Any]]:
        rows = await self.list_all()
        out = []
        for r in rows:
            if all(self._loose_eq(r.get(k, ""), v) for k, v in filters.items()):
                out.append(r)
        return out

    async def find_one_where(self, **filters: Any) -> dict[str, Any] | None:
        rows = await self.find_where(**filters)
        return rows[0] if rows else None


# ---- One repository class per tab (docs/job-outreach-schema.md) ----


class SettingsRepository(JobOutreachBaseRepository):
    SHEET_NAME = "SETTINGS"
    ID_FIELD = "key"
    HEADERS = ["key", "value", "description", "updated_at"]


class JobListingRepository(JobOutreachBaseRepository):
    SHEET_NAME = "JOB_LISTINGS"
    ID_FIELD = "job_id"
    HEADERS = ["job_id", "source", "job_title", "company_name", "location", "city", "state",
               "country", "is_remote", "description", "job_url", "posted_date", "run_id",
               "created_at"]


class CompanyRepository(JobOutreachBaseRepository):
    SHEET_NAME = "COMPANIES"
    ID_FIELD = "company_id"
    HEADERS = ["company_id", "company_name", "normalized_name", "official_website", "domain",
               "contact_email", "email_type", "email_source_url", "email_confidence",
               "research_status", "created_at", "updated_at"]


class EmailQueueRepository(JobOutreachBaseRepository):
    SHEET_NAME = "EMAIL_QUEUE"
    ID_FIELD = "queue_id"
    HEADERS = ["queue_id", "company_id", "job_id", "recipient_email", "sender_email", "subject",
               "body", "html_body", "status", "attempts", "max_attempts", "scheduled_at",
               "sent_at", "message_id", "thread_id", "error_message", "test_mode", "created_at",
               "updated_at"]


class EmailEventRepository(JobOutreachBaseRepository):
    SHEET_NAME = "EMAIL_EVENTS"
    ID_FIELD = "event_id"
    HEADERS = ["event_id", "queue_id", "company_id", "event_type", "message_id", "thread_id",
               "test_mode", "metadata", "created_at"]


class SuppressionRepository(JobOutreachBaseRepository):
    SHEET_NAME = "SUPPRESSION_LIST"
    ID_FIELD = "suppression_id"
    HEADERS = ["suppression_id", "company_id", "company_name", "domain", "reason", "created_at"]


class SearchRunRepository(JobOutreachBaseRepository):
    SHEET_NAME = "SEARCH_RUNS"
    ID_FIELD = "run_id"
    HEADERS = ["run_id", "job_title", "city", "is_remote", "results", "qualified",
               "companies_found", "emails_queued", "status", "started_at", "completed_at",
               "error_message"]


class ActivityLogRepository(JobOutreachBaseRepository):
    SHEET_NAME = "ACTIVITY_LOG"
    ID_FIELD = "log_id"
    HEADERS = ["log_id", "event", "details", "created_at"]


# Module-level singletons, same convention as app/repositories/repositories.py
# consumers expect (instantiated once, reused across requests).
settings_repo = SettingsRepository()
job_listing_repo = JobListingRepository()
company_repo = CompanyRepository()
email_queue_repo = EmailQueueRepository()
email_event_repo = EmailEventRepository()
suppression_repo = SuppressionRepository()
search_run_repo = SearchRunRepository()
activity_log_repo = ActivityLogRepository()
