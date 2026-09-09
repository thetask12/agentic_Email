"""
Google Sheets client for the Job Outreach module, pointed at its OWN sheet
(JOB_OUTREACH_SHEET_ID) and OWN service account
(JOB_OUTREACH_SERVICE_ACCOUNT_EMAIL/_PRIVATE_KEY) — never the main system's
GOOGLE_SHEETS_ID / GOOGLE_SERVICE_ACCOUNT_*.

This is a small adapted copy of app/integrations/sheets_client.py's
SheetsClient rather than a reuse of that exact class: the original is a
module-level singleton (SheetsClient.instance()) permanently bound to the
main system's Sheet via app.config.settings.get_settings(). Reusing it as-is
would either require mutating that singleton to point at a different sheet
(unsafe — the main system's live scheduler/repositories depend on it staying
pointed at the old sheet) or parameterizing its constructor (a change to
shared code outside this package, against the "only ADD, never modify
existing files outside job_outreach/" constraint). Duplicating the ~90 lines
here keeps the two systems fully isolated at the cost of a small amount of
repetition — the retry/backoff logic and method shapes are intentionally
identical so behavior matches exactly.
"""
from __future__ import annotations

import logging
from typing import Any

import gspread
from google.oauth2.service_account import Credentials
from tenacity import retry, stop_after_attempt, retry_if_exception_type, wait_exponential_jitter

from app.job_outreach.config import get_job_outreach_settings

logger = logging.getLogger("job_outreach.sheets_client")

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]

RETRYABLE_EXC = (gspread.exceptions.APIError, ConnectionError, TimeoutError)


def _is_quota_error(exc: BaseException) -> bool:
    if not isinstance(exc, gspread.exceptions.APIError):
        return False
    try:
        return exc.response.status_code == 429
    except AttributeError:
        return False


def _wait_for_sheets_error(retry_state):
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    if exc is not None and _is_quota_error(exc):
        return 65 + (retry_state.attempt_number - 1) * 5
    return wait_exponential_jitter(initial=0.5, max=8)(retry_state)


class JobOutreachSheetsClient:
    """Same header-mapped CRUD surface as the main system's SheetsClient,
    bound to the Job Outreach sheet/service account instead."""

    _instance: "JobOutreachSheetsClient | None" = None

    def __init__(self) -> None:
        settings = get_job_outreach_settings()
        if not settings.sheets_configured:
            self._gc = None
            self._sh = None
            logger.warning("Job Outreach Google Sheets not configured — running in stub mode")
            return
        creds = Credentials.from_service_account_info(
            {
                "type": "service_account",
                "client_email": settings.job_outreach_service_account_email,
                "private_key": settings.job_outreach_service_account_private_key.replace("\\n", "\n"),
                "token_uri": "https://oauth2.googleapis.com/token",
            },
            scopes=SCOPES,
        )
        self._gc = gspread.authorize(creds)
        self._sh = self._gc.open_by_key(settings.job_outreach_sheet_id)
        self._ws_cache: dict[str, gspread.Worksheet] = {}

    @classmethod
    def instance(cls) -> "JobOutreachSheetsClient":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @property
    def configured(self) -> bool:
        return self._sh is not None

    def worksheet(self, name: str) -> gspread.Worksheet:
        if not self.configured:
            raise RuntimeError("Job Outreach Google Sheets is not configured (missing env vars)")
        if name not in self._ws_cache:
            self._ws_cache[name] = self._sh.worksheet(name)
        return self._ws_cache[name]

    def ensure_worksheet(self, name: str, headers: list[str]) -> gspread.Worksheet:
        if not self.configured:
            raise RuntimeError("Job Outreach Google Sheets is not configured (missing env vars)")
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
    def update_row_simple(self, sheet_name: str, row_number: int, headers: list[str], record: dict[str, Any]) -> None:
        ws = self.worksheet(sheet_name)
        values = [record.get(h, "") for h in headers]
        last_col_a1 = gspread.utils.rowcol_to_a1(1, len(headers))
        col_letters = "".join(filter(str.isalpha, last_col_a1))
        ws.update(f"A{row_number}:{col_letters}{row_number}", [values], value_input_option="RAW")
