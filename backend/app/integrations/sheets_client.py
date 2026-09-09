"""
Google Sheets client wrapper. Provides header-mapped row CRUD on top of
gspread, with retries for transient API failures (rule 136: "If Google
Sheets API fails: retry").

Design notes:
- Each worksheet's row 1 is the header (see docs/sheet-schema.md). We never
  rely on column position outside this mapping so column reordering in the
  sheet UI doesn't silently corrupt data.
- Every entity has its own UUID column (e.g. job_id) — that column is used
  as the lookup key, never the physical row index (rule 64).
- gspread calls are synchronous; FastAPI route handlers call these through
  `run_in_threadpool` (see repositories/base.py) to avoid blocking the
  event loop.
"""
from __future__ import annotations

import logging
from typing import Any

import gspread
from google.oauth2.service_account import Credentials
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type, wait_exponential_jitter

from app.config.settings import get_settings

logger = logging.getLogger("sheets_client")

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]

RETRYABLE_EXC = (gspread.exceptions.APIError, ConnectionError, TimeoutError)


def _is_quota_error(exc: BaseException) -> bool:
    """Google Sheets enforces a default 60 requests/minute/user quota
    (gspread.exceptions.APIError with HTTP 429). A busy search run can
    exhaust it within seconds; the short exponential backoff used for
    ordinary transient errors (max ~8s per attempt, 4 attempts) is nowhere
    near the ~60s the quota window actually needs to reset, so a quota hit
    would previously exhaust all 4 attempts in under 30s and abort the
    entire search run - even though the quota would have cleared 30s
    later. See _wait_for_sheets_error below for the longer backoff applied
    specifically to this case."""
    if not isinstance(exc, gspread.exceptions.APIError):
        return False
    try:
        return exc.response.status_code == 429
    except AttributeError:
        return False


def _wait_for_sheets_error(retry_state):
    """Quota errors (429) get a long, mostly-fixed wait (~65s, the quota
    window plus margin) so a retry actually lands after the per-minute
    limit resets. Any other retryable error (network blip, etc.) falls
    back to the normal short exponential backoff."""
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    if exc is not None and _is_quota_error(exc):
        return 65 + (retry_state.attempt_number - 1) * 5
    return wait_exponential_jitter(initial=0.5, max=8)(retry_state)


class SheetsClient:
    _instance: "SheetsClient | None" = None

    def __init__(self) -> None:
        settings = get_settings()
        if not settings.sheets_configured:
            self._gc = None
            self._sh = None
            logger.warning("Google Sheets not configured — SheetsClient running in stub mode")
            return
        creds = Credentials.from_service_account_info(
            {
                "type": "service_account",
                "client_email": settings.google_service_account_email,
                "private_key": settings.google_service_account_private_key.replace("\\n", "\n"),
                "token_uri": "https://oauth2.googleapis.com/token",
            },
            scopes=SCOPES,
        )
        self._gc = gspread.authorize(creds)
        self._sh = self._gc.open_by_key(settings.google_sheets_id)
        self._ws_cache: dict[str, gspread.Worksheet] = {}

    @classmethod
    def instance(cls) -> "SheetsClient":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @property
    def configured(self) -> bool:
        return self._sh is not None

    def worksheet(self, name: str) -> gspread.Worksheet:
        if not self.configured:
            raise RuntimeError("Google Sheets is not configured (missing env vars)")
        if name not in self._ws_cache:
            self._ws_cache[name] = self._sh.worksheet(name)
        return self._ws_cache[name]

    def ensure_worksheet(self, name: str, headers: list[str]) -> gspread.Worksheet:
        if not self.configured:
            raise RuntimeError("Google Sheets is not configured (missing env vars)")
        try:
            ws = self._sh.worksheet(name)
        except gspread.exceptions.WorksheetNotFound:
            ws = self._sh.add_worksheet(title=name, rows=1000, cols=max(26, len(headers) + 2))
            ws.append_row(headers, value_input_option="RAW")
            ws.freeze(rows=1)
        self._ws_cache[name] = ws
        return ws

    @retry(reraise=True, stop=stop_after_attempt(3), wait=_wait_for_sheets_error,
           retry=retry_if_exception_type(RETRYABLE_EXC))
    def get_all_records(self, sheet_name: str) -> list[dict[str, Any]]:
        ws = self.worksheet(sheet_name)
        return ws.get_all_records(default_blank="")

    @retry(reraise=True, stop=stop_after_attempt(3), wait=_wait_for_sheets_error,
           retry=retry_if_exception_type(RETRYABLE_EXC))
    def clear_data_rows(self, sheet_name: str) -> None:
        """Deletes every data row (everything below row 1) while leaving the
        header row intact. Used by the one-time admin reset endpoint — see
        misc_routes.py POST /api/settings/reset-all-data.

        Uses the sheet's actual populated row count (get_all_values), NOT
        worksheet.row_count — the latter is the configured GRID size (often
        1000 regardless of content), and calling delete_rows across the
        full empty grid when only the header row has content makes the
        Sheets API reject the request ("not possible to delete all
        non-frozen rows") because it would leave a frozen-only sheet with a
        zero-row body. Only deleting the rows that actually hold data
        avoids that edge case entirely, and is a no-op when the sheet is
        already just the header row."""
        ws = self.worksheet(sheet_name)
        populated_row_count = len(ws.get_all_values())
        if populated_row_count > 1:
            ws.delete_rows(2, populated_row_count)

    @retry(reraise=True, stop=stop_after_attempt(3), wait=_wait_for_sheets_error,
           retry=retry_if_exception_type(RETRYABLE_EXC))
    def append_row(self, sheet_name: str, row: list[Any]) -> None:
        ws = self.worksheet(sheet_name)
        ws.append_row(row, value_input_option="RAW")

    @retry(reraise=True, stop=stop_after_attempt(3), wait=_wait_for_sheets_error,
           retry=retry_if_exception_type(RETRYABLE_EXC))
    def find_row_by_id(self, sheet_name: str, id_column: str, id_value: str,
                        row_hint: int | None = None) -> tuple[int, dict[str, Any]] | None:
        """Return (1-indexed row number, record dict) or None.

        row_hint (optional): a caller-supplied guess at the row number,
        typically derived from a cached get_all_records() snapshot
        (position in that list + 2, accounting for the header row). If the
        hint is correct we do exactly ONE read (row_values(i)) instead of
        the full 3-read scan below (headers + full id column + row) — this
        is what makes update()/get_by_id() cheap on a warm cache. If the
        hint is stale (row shifted since the snapshot, e.g. another process
        wrote to the sheet) we detect the mismatch and fall back to the
        full scan, so correctness never depends on the cache being fresh.
        """
        ws = self.worksheet(sheet_name)
        headers = ws.row_values(1)
        if id_column not in headers:
            return None
        id_col_idx = headers.index(id_column)

        if row_hint is not None:
            row_values = ws.row_values(row_hint)
            if id_col_idx < len(row_values) and row_values[id_col_idx] == id_value:
                record = {headers[j]: (row_values[j] if j < len(row_values) else "") for j in range(len(headers))}
                return row_hint, record
            # Hint was stale — fall through to the authoritative full scan below.

        col_idx = id_col_idx + 1
        col_values = ws.col_values(col_idx)
        for i, v in enumerate(col_values[1:], start=2):
            if v == id_value:
                row_values = ws.row_values(i)
                record = {headers[j]: (row_values[j] if j < len(row_values) else "") for j in range(len(headers))}
                return i, record
        return None

    @retry(reraise=True, stop=stop_after_attempt(3), wait=_wait_for_sheets_error,
           retry=retry_if_exception_type(RETRYABLE_EXC))
    def update_row(self, sheet_name: str, row_number: int, record: dict[str, Any]) -> None:
        ws = self.worksheet(sheet_name)
        headers = ws.row_values(1)
        values = [record.get(h, "") for h in headers]
        ws.update(f"A{row_number}:{gspread.utils.rowcol_to_a1(row_number, len(headers))[:-len(str(row_number))]}{row_number}",
                  [values], value_input_option="RAW")

    def update_row_simple(self, sheet_name: str, row_number: int, headers: list[str], record: dict[str, Any]) -> None:
        ws = self.worksheet(sheet_name)
        values = [record.get(h, "") for h in headers]
        last_col_a1 = gspread.utils.rowcol_to_a1(1, len(headers))
        col_letters = "".join(filter(str.isalpha, last_col_a1))
        ws.update(f"A{row_number}:{col_letters}{row_number}", [values], value_input_option="RAW")
