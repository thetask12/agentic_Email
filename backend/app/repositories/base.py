"""
Base repository providing header-mapped CRUD over a single Google Sheet tab.
All entity repositories subclass this with SHEET_NAME, HEADERS, ID_FIELD.

MOCK_MODE fallback: when Google Sheets is not configured (e.g. local dev
without credentials) and settings.mock_mode is True, repositories operate
on an in-process list so the API remains usable for UI development. This is
never used to fabricate business data — it is empty until the user creates
records through the API.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any

from starlette.concurrency import run_in_threadpool

from app.config.settings import get_settings
from app.integrations.sheets_client import SheetsClient
from app.utils.time_utils import iso_now

logger = logging.getLogger("repository")

# How long a list_all() snapshot is reused before re-reading the sheet.
# The Google Sheets API defaults to a 60 reads/minute/user quota; every
# GET endpoint that fans out across several sheets (e.g. /api/dashboard
# reads 8 of them) can blow that quota on its own within a couple of
# refreshes, even with zero search activity. A short cache collapses
# repeated reads of the same sheet within this window into one real API
# call, while writes (create/update) still invalidate immediately so
# nothing goes stale for longer than this TTL.
LIST_CACHE_TTL_SECONDS = 8.0


class BaseRepository:
    SHEET_NAME: str = ""
    HEADERS: list[str] = []
    ID_FIELD: str = "id"

    def __init__(self) -> None:
        self.settings = get_settings()
        self._mem_store: list[dict[str, Any]] = []
        self._list_cache: list[dict[str, Any]] | None = None
        self._list_cache_at: float = 0.0
        self._use_sheets = self.settings.sheets_configured
        if self._use_sheets:
            self.client = SheetsClient.instance()
            try:
                self.client.ensure_worksheet(self.SHEET_NAME, self.HEADERS)
            except Exception as exc:  # pragma: no cover - network dependent
                logger.error("Failed to ensure worksheet %s: %s", self.SHEET_NAME, exc)
        else:
            self.client = None
            if not self.settings.mock_mode:
                logger.warning(
                    "Sheets not configured and MOCK_MODE is off — %s repository has no persistence",
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
        """Best-effort row number guess from the cached list_all() snapshot,
        to let find_row_by_id() skip its expensive full-column scan. Never
        forces a fresh sheet read — if there's no cache yet, returns None
        and the caller falls back to the authoritative (more expensive)
        lookup, same as before this optimization existed."""
        if self._list_cache is None:
            return None
        for i, r in enumerate(self._list_cache):
            if r.get(self.ID_FIELD) == id_value:
                return i + 2  # +1 for 1-indexing, +1 for the header row
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
            # Append the new record to the cache in place (if a cache exists)
            # instead of invalidating it — this keeps _row_hint_for() usable
            # for a get_by_id()/update() on this same record immediately
            # after create(), which is the common pattern in the search
            # pipeline (create company -> update with research results).
            # Invalidating here would force every such follow-up call back
            # onto the expensive full-scan path in find_row_by_id().
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
            # Patch the cached copy in place rather than invalidating the
            # whole cache — same rationale as create() above: keeps
            # _row_hint_for() cheap for subsequent calls on this record
            # within the same request/run, without ever serving stale data
            # (the merged dict written here is exactly what's now on the
            # sheet). If the id isn't in the cache (e.g. it was created
            # before this repository instance's cache existed), this is a
            # harmless no-op — the next list_all() still reads fresh.
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
        """Comparison used by find_where(). Booleans need special handling:
        a Python True/False written via create()/update() round-trips
        through Google Sheets as the string "TRUE"/"FALSE" (Sheets' own
        boolean cell rendering) or sometimes "1"/""), never as Python's
        str(True) == "True". A naive str(actual) == str(expected) silently
        never matches a bool filter, which previously made
        find_where(is_default=True) always return [] even though the row
        existed - e.g. email template lookup during a search run silently
        skipped generating any outreach email for every lead."""
        if isinstance(expected, bool):
            actual_str = str(actual).strip().lower()
            return actual_str in ("true", "1") if expected else actual_str in ("false", "0", "")
        return str(actual) == str(expected)

    async def clear_all(self) -> None:
        """Deletes every data row in this sheet (header row kept). Used only
        by the one-time admin reset endpoint (POST /api/settings/reset-all-data)
        — not part of normal application flow."""
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
