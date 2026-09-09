# Security

## Secrets
- `OPENAI_API_KEY`, `GOOGLE_SERVICE_ACCOUNT_PRIVATE_KEY`,
  `GOOGLE_SEARCH_API_KEY`, `APPS_SCRIPT_SHARED_SECRET`, `API_AUTH_TOKEN`
  live only in `.env` (git-ignored) locally, or Render's encrypted
  environment variable store in production. They are read only by
  `backend/app/config/settings.py` and never returned by any API response
  or embedded in frontend bundles (Next.js only exposes `NEXT_PUBLIC_*`
  vars to the client, and none of the secrets use that prefix).
- Apps Script secrets (`APPS_SCRIPT_SHARED_SECRET`, optional
  `OPENAI_API_KEY` fallback) live in Script Properties, never in the
  Google Sheet itself (System.txt rule #81) and never in source code.
- If any credential is ever pasted into a chat, ticket, or commit, treat it
  as burned — rotate it immediately rather than assuming it's safe because
  it "looks internal."

## Authentication
- `backend/app/api/deps.py::verify_api_token` supports an optional bearer
  token (`API_AUTH_TOKEN`) for the whole API — unset by default for local
  development, should be set in production if the deployed URL is not
  otherwise access-controlled.
- The `/api/replies/webhook` endpoint requires the
  `X-Apps-Script-Secret` header to match `APPS_SCRIPT_SHARED_SECRET`
  when that secret is configured.
- The Apps Script Web App bridge (`doGet`/`doPost` in `Code.gs`) checks the
  same shared secret before running any worker on demand.

## HTML sanitization
Inbound reply HTML bodies are sanitized in `apps-script/Utils.gs::sanitizeHtml`
before being written to the Sheet (strips `<script>`/`<style>`/`<iframe>`/
`<object>`/`<embed>`, `on*` handlers, `javascript:` URLs). The frontend
should still treat `body_html` as untrusted and avoid `dangerouslySetInnerHTML`
without an additional client-side sanitizer (e.g. DOMPurify) — this is
defense in depth, not a single point of trust.

## No direct frontend email sending
The frontend never calls anything that sends mail. It can only create/
approve/queue records; Apps Script (`QueueWorker.gs`/`FollowUpWorker.gs`)
is the sole sender (System.txt rule #114).

## Suppression enforcement
Checked at multiple layers before any send: email-level and company-level
in `SUPPRESSION_LIST` (`backend/app/services/suppression_service.py`), and
independently re-checked inside Apps Script's `QueueWorker`/`FollowUpWorker`
under `LockService` immediately before sending — so even a race between the
backend and a scheduled Apps Script trigger cannot bypass suppression.

## CORS
`BACKEND_CORS_ORIGINS` restricts which origins may call the API directly
(relevant mainly for local dev where frontend/backend run on different
ports; in the combined Docker deployment they share an origin and CORS is
not exercised for normal browser traffic).
