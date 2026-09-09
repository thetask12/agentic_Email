# Google Sheets Setup (Primary Database)

See `docs/sheet-schema.md` for the exact tab names, column order, and enums
— this file covers only the setup steps.

## 1. Enable APIs
In [Google Cloud Console](https://console.cloud.google.com):
1. Create or select a project.
2. **APIs & Services → Library** → enable **Google Sheets API** and
   **Google Drive API**.

## 2. Create a Service Account
1. **IAM & Admin → Service Accounts → Create Service Account**. Any name.
2. Open it → **Keys → Add Key → Create new key → JSON**. A JSON file
   downloads — keep it private, never commit it.

## 3. Fill in `.env`
From the downloaded JSON:
- `client_email` → `GOOGLE_SERVICE_ACCOUNT_EMAIL`
- `private_key` → `GOOGLE_SERVICE_ACCOUNT_PRIVATE_KEY` (keep the `\n`
  escape sequences exactly as they appear in the JSON, wrapped in quotes)

## 4. Create the Sheet
1. Create a new Google Sheet.
2. Copy its ID from the URL: `docs.google.com/spreadsheets/d/<ID>/edit`.
3. Put that ID into `GOOGLE_SHEETS_ID`.
4. **Share** the Sheet with the service account's `client_email` as
   **Editor**. Without this share step, both the backend and Apps Script
   will fail to read/write.

## 5. Tabs are created automatically
The backend's `BaseRepository.ensure_worksheet()`
(`backend/app/repositories/base.py`) creates any missing tab (with the
correct header row, frozen) the first time it's used — you do not need to
manually create the 20 tabs, though you may if you prefer to review the
schema up front (copy tab names/headers from `docs/sheet-schema.md`).

## Concurrency / race-condition notes
Both the FastAPI backend (via the Sheets API) and Google Apps Script (via
`SpreadsheetApp`, running directly against the same Sheet) can write
concurrently. Mitigations in place:
- Every entity has its own UUID (never the physical spreadsheet row) as
  its identifier — see `backend/app/utils/ids.py` and
  `apps-script/Utils.gs::generateId`.
- Apps Script workers (`QueueWorker.gs`, `FollowUpWorker.gs`,
  `ReplyScanner.gs`) acquire `LockService.getScriptLock()` before
  processing, and re-check each row's status immediately before mutating
  it, so two triggers can't double-send the same queue item.
- The backend retries transient Sheets API errors with exponential backoff
  (`backend/app/integrations/sheets_client.py`, via `tenacity`).

## Scalability limitation (documented, not hidden)
Google Sheets is not built for high-volume concurrent writes or very large
datasets (tens of thousands of rows start to slow down `get_all_records`).
This system is designed for the stated use case (targeted regional outreach
campaigns), not high-volume mass-mailing. See `docs/troubleshooting.md`.
