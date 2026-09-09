# Follow-up System

## User-controlled by default
Per System.txt rules #31, #123, #127: the user picks every follow-up's
date/time explicitly. `POST /api/follow-ups` requires `scheduled_at` in the
request body — nothing in the backend ever invents a date. An
`AUTO_FOLLOWUP_AUTOMATION` setting exists in the `SETTINGS` sheet
(default `false`) as the documented hook for future automation, but no
code path currently reads it to auto-schedule; the AI may only ever
*recommend* ("Follow-up recommended") via UI copy the frontend chooses to
show — it must never silently create a `FOLLOW_UPS` row.

## Sequence
`FOLLOW_UPS.sequence_number` is caller-supplied (Initial=implicit via
`EMAIL_QUEUE`, then 1/2/3/4 for follow-ups). `MAX_FOLLOW_UPS` (default 4,
`.env` / `SETTINGS`) is enforced in
`backend/app/services/follow_up_service.schedule_follow_up` — scheduling a
5th active follow-up for the same lead raises an error.

## Auto-cancel on reply
`backend/app/services/reply_service.ingest_reply` calls
`follow_up_service.cancel_all_pending_for_lead(lead_id, reason="REPLY_RECEIVED")`
for every reply, cancelling every `SCHEDULED`/`DUE`/`QUEUED` follow-up for
that lead. The same logic exists independently in
`apps-script/ReplyScanner.gs::cancelPendingFollowUpsForLead_` as a local
fallback for when the backend webhook is unreachable (see
`docs/replies.md`). This satisfies rule #15/#41/#124 — no unnecessary
follow-up is ever sent after a reply.

## Sending path
The backend never sends a follow-up directly (rule #114). Two ways a
follow-up gets sent:
1. **User clicks "Send Now"** (`POST /api/follow-ups/{id}/send-now`) — the
   backend re-checks for replies/suppression, then pushes a row into
   `EMAIL_QUEUE` (kind=`FOLLOW_UP`), which Apps Script's `QueueWorker`
   actually sends on its next run.
2. **Scheduled time arrives** — Apps Script's `FollowUpWorker` (runs every
   15 minutes) finds `SCHEDULED`/`DUE` rows whose `scheduled_at <= now`,
   re-checks reply/suppression/cancellation/`MAX_FOLLOW_UPS`, and either
   queues or skips per `apps-script/FollowUpWorker.gs`.

## Statuses
`DRAFT → SCHEDULED → DUE → QUEUED → SENT`, with `CANCELLED`/`SKIPPED`/
`FAILED` as exits at any point. `DUE` is a derived state — either the
backend's `follow_up_service.mark_due_follow_ups()` or Apps Script's own
due-check at send time.

## Frontend visibility
`/follow-ups` supports filters exactly matching System.txt #33 (Today,
Tomorrow, This Week, Next 7 Days, Overdue, Custom range) and #37/#126 user
actions (Schedule, Reschedule, Cancel, Send Now, Edit, Skip). `/follow-
ups/calendar` renders scheduled/due/sent/cancelled follow-ups on a month
grid per #34.
