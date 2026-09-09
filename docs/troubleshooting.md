# Troubleshooting

## Backend starts but every list is empty
Check `GET /api/health` — if `sheets_configured: false`, the backend has no
Google Sheets credentials and is running with in-memory (or no) storage
(see `MOCK_MODE` in `backend/app/repositories/base.py`). Fill in
`GOOGLE_SHEETS_ID`, `GOOGLE_SERVICE_ACCOUNT_EMAIL`,
`GOOGLE_SERVICE_ACCOUNT_PRIVATE_KEY` and share the Sheet with the service
account (`docs/google-sheets.md`).

## Search runs find 0 jobs
- Check `GET /api/sources` — sources marked `UNAVAILABLE` mean
  `GOOGLE_SEARCH_API_KEY`/`GOOGLE_SEARCH_ENGINE_ID` are missing or the
  query returned nothing indexed (rare terms, very narrow location).
- Job title + state/city combinations with little public indexing (e.g. a
  very small town) will legitimately return few/no results — this is not
  a bug, see System.txt rule #94 (no fake progress).

## Emails stuck in `PENDING` in EMAIL_QUEUE
The backend only ever creates queue rows — Apps Script's `QueueWorker`
(triggered every 5 minutes, or run manually via the Sheet's "Botivate
Automation" menu) is what actually sends. Verify triggers are installed
(`docs/apps-script.md` step 4) and check the Apps Script project's
**Executions** log for errors.

## Replies never show up in /inbox
1. Confirm `ReplyScanner` is running (Apps Script Executions log, or run
   `Botivate Automation → Scan Replies Now` manually).
2. Confirm the original email's thread actually carries the `SENT_LABEL`
   (`EmailSender.gs` applies it — check the Gmail label exists).
3. If `BACKEND_WEBHOOK_URL` is unset/unreachable, replies land as a local
   fallback row in `REPLIES` with `reply_type=UNKNOWN` rather than not
   appearing at all — check that sheet directly.

## "SENT — DELIVERY STATUS UNKNOWN" everywhere
This is expected, not a bug — see `docs/email-tracking.md`. GmailApp does
not expose reliable delivery confirmation.

## Google Sheets API errors / rate limiting
`backend/app/integrations/sheets_client.py` retries transient errors with
exponential backoff (`tenacity`). Sustained `429`s usually mean too many
concurrent requests against the free Sheets API quota — reduce
`QUEUE_BATCH_SIZE` or the frequency of frontend polling/SSE usage.

## Docker build fails at the frontend stage
Confirm `frontend/package-lock.json` is committed/present (the Dockerfile's
`npm install` step expects it) and that `next.config.ts` still has
`output: "standalone"` — the final image copies `.next/standalone`, which
only exists with that config set.

## Combined container starts but the site 404s
Check container logs for which of the two processes (`node server.js` for
Next.js, `uvicorn` for FastAPI) exited — `start.py` shuts both down and
exits non-zero if either dies, which should surface in Render's logs and
trigger a restart.
