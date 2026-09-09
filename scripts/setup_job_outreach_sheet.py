#!/usr/bin/env python3
"""
One-time (idempotent) setup script for the Job Outreach Google Sheet.

Creates the 8 tabs documented in docs/job-outreach-schema.md with their
exact header rows (row 1, frozen), leaving any tab that already exists
untouched, and seeds the SETTINGS tab with its 4 documented rows.

This is a standalone script — NOT part of the FastAPI app import graph — so
it deliberately duplicates a small amount of gspread bootstrapping rather
than importing backend/app/job_outreach modules (those pull in
pydantic-settings/FastAPI-adjacent packages this script doesn't need, and
importing across the backend/ package boundary from scripts/ would require
sys.path surgery for no real benefit).

Usage:
    python scripts/setup_job_outreach_sheet.py <path-to-service-account.json>

    or set the service account JSON path via env var:
    JOB_OUTREACH_SERVICE_ACCOUNT_JSON=/path/to/file.json python scripts/setup_job_outreach_sheet.py

Requires: gspread, google-auth (pip install gspread google-auth).
"""
from __future__ import annotations

import datetime
import os
import sys

SHEET_ID = "1iJXsPZdBCVmExx6l4DIzSHC2jdxCRJz2-naBXdTLoww"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]

# Exact tab -> header row mapping, per docs/job-outreach-schema.md.
TABS: dict[str, list[str]] = {
    "SETTINGS": ["key", "value", "description", "updated_at"],
    "JOB_LISTINGS": [
        "job_id", "source", "job_title", "company_name", "location", "city", "state",
        "country", "is_remote", "description", "job_url", "posted_date", "run_id", "created_at",
    ],
    "COMPANIES": [
        "company_id", "company_name", "normalized_name", "official_website", "domain",
        "contact_email", "email_type", "email_source_url", "email_confidence",
        "research_status", "created_at", "updated_at",
    ],
    "EMAIL_QUEUE": [
        "queue_id", "company_id", "job_id", "recipient_email", "sender_email", "subject",
        "body", "html_body", "status", "attempts", "max_attempts", "scheduled_at", "sent_at",
        "message_id", "thread_id", "error_message", "test_mode", "created_at", "updated_at",
    ],
    "EMAIL_EVENTS": [
        "event_id", "queue_id", "company_id", "event_type", "message_id", "thread_id",
        "test_mode", "metadata", "created_at",
    ],
    "SUPPRESSION_LIST": [
        "suppression_id", "company_id", "company_name", "domain", "reason", "created_at",
    ],
    "SEARCH_RUNS": [
        "run_id", "job_title", "city", "is_remote", "results", "qualified",
        "companies_found", "emails_queued", "status", "started_at", "completed_at",
        "error_message",
    ],
    "ACTIVITY_LOG": ["log_id", "event", "details", "created_at"],
}

# Fixed UTC+5:30 offset (same convention as backend/app/services/
# daily_search_scheduler.py's IST constant) rather than zoneinfo, since
# "Asia/Kolkata" tzdata is not guaranteed to be present on every machine
# this script runs on (e.g. Windows without the `tzdata` pip package).
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))


def _today_ist_date() -> str:
    return datetime.datetime.now(IST).date().isoformat()


def main() -> int:
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError as exc:
        print(
            "ERROR: gspread/google-auth are not installed in this Python environment.\n"
            f"  ({exc})\n"
            "Install them (pip install gspread google-auth) and re-run this script, or run it "
            "on a machine/container where backend/requirements.txt is already installed "
            "(per root CLAUDE.md, this Windows dev box's local pip install is not expected to "
            "work with the pinned versions)."
        )
        return 1

    json_path = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("JOB_OUTREACH_SERVICE_ACCOUNT_JSON")
    if not json_path:
        print(
            "ERROR: no service account JSON path given.\n"
            "Usage: python scripts/setup_job_outreach_sheet.py <path-to-service-account.json>\n"
            "   or: JOB_OUTREACH_SERVICE_ACCOUNT_JSON=<path> python scripts/setup_job_outreach_sheet.py"
        )
        return 1
    if not os.path.isfile(json_path):
        print(f"ERROR: service account JSON file not found: {json_path}")
        return 1

    print(f"Authenticating with service account: {json_path}")
    creds = Credentials.from_service_account_file(json_path, scopes=SCOPES)
    gc = gspread.authorize(creds)

    print(f"Opening spreadsheet: {SHEET_ID}")
    print(f"  (service account: {creds.service_account_email})")
    try:
        sh = gc.open_by_key(SHEET_ID)
    except (gspread.exceptions.APIError, PermissionError) as exc:
        print(
            f"ERROR: could not open spreadsheet {SHEET_ID}: {exc}\n"
            f"Make sure the sheet has been shared with {creds.service_account_email} "
            "(Editor access) — Share button on the Sheet, paste that email, set role to Editor."
        )
        return 1

    existing_titles = {ws.title for ws in sh.worksheets()}
    created: list[str] = []
    skipped: list[str] = []

    for tab_name, headers in TABS.items():
        if tab_name in existing_titles:
            skipped.append(tab_name)
            continue
        ws = sh.add_worksheet(title=tab_name, rows=1000, cols=max(26, len(headers) + 2))
        ws.append_row(headers, value_input_option="RAW")
        ws.freeze(rows=1)
        created.append(tab_name)
        print(f"  created tab: {tab_name} ({len(headers)} columns)")

    # Seed SETTINGS rows (only if SETTINGS was just created, or existing rows
    # for these specific keys are missing — idempotent either way).
    settings_ws = sh.worksheet("SETTINGS")
    existing_settings_rows = settings_ws.get_all_records(default_blank="")
    existing_keys = {r.get("key") for r in existing_settings_rows}

    seed_rows = [
        ("automation_running", "false", "Whether the Start/Stop automation loop is currently active."),
        ("daily_email_cap", "100", "Max new application emails queued per calendar day."),
        ("emails_sent_today", "0", "Running counter of emails queued today, reset at midnight IST."),
        ("emails_sent_date", _today_ist_date(), "IST date (YYYY-MM-DD) the counter above applies to."),
    ]
    seeded = []
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    for key, value, description in seed_rows:
        if key in existing_keys:
            continue
        settings_ws.append_row([key, value, description, now_iso], value_input_option="RAW")
        seeded.append(key)

    print("\n=== Summary ===")
    print(f"Tabs created:  {created or '(none — all already existed)'}")
    print(f"Tabs skipped (already existed): {skipped or '(none)'}")
    print(f"SETTINGS rows seeded: {seeded or '(none — all already existed)'}")
    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
