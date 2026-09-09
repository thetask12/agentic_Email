# Reply Tracking

## Detection (never subject-only matching)
`apps-script/ReplyScanner.gs` scans Gmail threads carrying the `SENT_LABEL`
(applied automatically when `EmailSender.gs` sends a campaign email) —
thread membership is already a strictly stronger signal than subject
matching (System.txt rule #101/#24 explicitly forbid subject-only
matching). Within each such thread, any message not from
`BOTIVATE_SENDER_EMAIL` is treated as inbound. If the Advanced Gmail
Service is enabled, `In-Reply-To`/`References` headers are also captured
for additional header-level confidence (left blank, never fabricated, if
the advanced service isn't enabled).

## Idempotency
Two independent guards ensure a message is never processed twice:
1. A Script Property (`lastMsg:<threadId>`) tracks the last processed
   message per thread.
2. Before creating a `REPLIES` row, both Apps Script and the backend
   (`reply_service.ingest_reply`) check for an existing row with the same
   `message_id` and return the existing row instead of duplicating.

## Analysis pipeline
1. Apps Script POSTs the new reply to `${APPS_SCRIPT_WEB_APP_URL}` — sorry,
   to the **backend's** `BACKEND_WEBHOOK_URL` (`/api/replies/webhook`),
   authenticated by `APPS_SCRIPT_SHARED_SECRET`.
2. `backend/app/services/reply_service.ingest_reply` calls
   `backend/app/agents/reply_analysis.analyze_reply` (OpenAI, structured
   output) to get `reply_type`, `sentiment`, `summary`, `lead_status`,
   `recommended_next_action`, `suggested_response`, `priority`.
3. Unsubscribe/stop-request detection (`detect_unsubscribe`) runs as a
   **deterministic keyword check first**, regardless of OpenAI
   availability, so suppression always works even if the AI call fails.
4. The lead's status updates, pending follow-ups are cancelled
   (`cancel_all_pending_for_lead`), and a `CONVERSATIONS` row is
   created/updated.
5. If the webhook is unreachable, `ReplyScanner.gs` writes a local
   fallback `REPLIES` row with `reply_type=UNKNOWN` (never a fabricated
   classification) for the backend or a human to backfill later.

## Suggested response — never auto-sent
`reply.suggested_response` is a draft only. Per System.txt rule #60/#127,
`AUTO_REPLY` defaults to `false` and no code path sends it automatically —
the frontend's Copy/Edit/Send buttons on `/inbox/[id]` require the user to
actually create+approve+queue a reply email through the normal email flow.

## Reply types
`INTERESTED, REQUEST_FOR_DETAILS, MEETING_REQUEST, POSITIVE, NEUTRAL,
NOT_INTERESTED, ASK_LATER, OUT_OF_OFFICE, BOUNCE, UNSUBSCRIBE, UNKNOWN` —
see `docs/sheet-schema.md` for the canonical enum.
