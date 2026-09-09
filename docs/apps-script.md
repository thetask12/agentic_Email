# Google Apps Script Setup & Deployment

The Apps Script project (`apps-script/`) is the **only** part of the system
that actually sends email or reads Gmail — the FastAPI backend never sends
mail directly (System.txt rule #114). It also runs the follow-up worker and
the reply scanner.

## 1. Create the script project
1. Open the same Google Sheet used as `GOOGLE_SHEETS_ID`.
2. **Extensions → Apps Script**. This binds the script to that Sheet.
3. Create one script file per file in `apps-script/` (File → New → Script
   file), matching the names exactly: `Config`, `Utils`, `SheetRepository`,
   `EmailSender`, `QueueWorker`, `FollowUpWorker`, `ReplyScanner`,
   `EventLogger`, `Code`. Paste each file's contents in.

## 2. (Recommended) Enable the Advanced Gmail Service
`Services` (+ icon) → **Gmail API** → Add. This unlocks header-level reply
matching (`In-Reply-To`/`References`) in `ReplyScanner.gs`. Not required —
without it, the script still works using thread/label-based matching, which
is already reliable (see the top-of-file comment in `ReplyScanner.gs`).

## 3. Run `setupConfig()`
In the Apps Script editor, select `setupConfig` from the function dropdown
and click **Run**. Authorize the requested scopes (Sheets, Gmail, URL
Fetch) — this authorizes the script to act as whichever Google account you
are logged in as when you click Allow (this should be the Botivate sending
account, e.g. the account you intend to send outreach from).

You'll be prompted for:
- `SHEET_ID` — same as `GOOGLE_SHEETS_ID` in the backend's `.env`.
- `BOTIVATE_SENDER_EMAIL` / `BOTIVATE_SENDER_NAME`.
- `EMAIL_TEST_MODE` (keep `true`) and `TEST_EMAIL`.
- `MAX_FOLLOW_UPS`, `QUEUE_BATCH_SIZE`, `QUEUE_MAX_ATTEMPTS`.
- `BACKEND_WEBHOOK_URL` — your deployed backend's
  `https://<your-backend>/api/replies/webhook` (leave blank until the
  backend is deployed; replies will queue locally as UNKNOWN until then).
- `APPS_SCRIPT_SHARED_SECRET` — make up any random string; put the SAME
  value in the backend's `APPS_SCRIPT_SHARED_SECRET` env var.
- `OPENAI_API_KEY` (optional fallback only — leave blank if the backend
  webhook is reachable; the backend's own OpenAI analysis is preferred).
- `REPLY_SCAN_LABEL` / `SENT_LABEL` — defaults are fine (`Botivate/Sent`).

Re-run `setupConfig()` any time to change values later.

## 4. Install triggers
Run `installTriggers()` once (or use the **Botivate Automation** menu that
appears after reloading the Sheet: `Botivate Automation → Install
Triggers`). This installs:
- `processEmailQueue` every 5 minutes
- `processFollowUps` every 15 minutes
- `scanForReplies` every 10 minutes

Re-running `installTriggers()` is safe — it removes and recreates only its
own triggers first (idempotent).

## 5. (Optional) Deploy as a Web App
Only needed if you want the backend to be able to trigger workers on
demand (in addition to the time-driven triggers above):
1. **Deploy → New deployment → Web app**.
2. Execute as: **Me**. Access: **Anyone with the link** (or your org's
   equivalent restricted option).
3. Copy the deployment URL into the backend's `APPS_SCRIPT_WEB_APP_URL`.
4. Use the same `APPS_SCRIPT_SHARED_SECRET` on both sides.

## 6. Verify
Reload the Sheet — the **Botivate Automation** custom menu should appear
with manual "Run Now" items for each worker, useful for testing without
waiting for the time-driven trigger.

## Testing checklist
1. Keep `EMAIL_TEST_MODE=true` and `TEST_EMAIL` set to your own inbox.
2. Approve and queue a test email in the frontend.
3. Run `Botivate Automation → Run Queue Worker Now` — check `TEST_EMAIL`'s
   inbox for `[TEST MODE - would send to ...]`-prefixed email, and check
   the `EMAIL_QUEUE`/`EMAIL_EVENTS` sheet tabs for the resulting rows.
4. Reply to that test email from `TEST_EMAIL`.
5. Run `Botivate Automation → Scan Replies Now` — check the `REPLIES` tab
   for a new row, and confirm the lead's pending follow-ups were cancelled.

## Limitations (documented, not hidden)
- Gmail/GmailApp does not expose reliable delivery or open tracking — the
  system never fabricates `DELIVERED`/`OPENED` events (see
  `EventLogger.gs` and `docs/email-tracking.md`).
- Gmail sending quotas apply (100/day for consumer accounts, higher for
  Workspace — see Google's current quota documentation) — the queue's
  `QUEUE_BATCH_SIZE` and trigger cadence are intentionally conservative.
- Apps Script execution time limits (6 min/execution for most accounts)
  cap how many queue/follow-up rows can be processed per run — this is why
  `QUEUE_BATCH_SIZE` exists.
