# Gmail Setup

There is **no SMTP password, app password, or OAuth client secret to
configure for Gmail in this system.** Sending and reply-scanning happen
exclusively through Google Apps Script's built-in `GmailApp` / (optional)
advanced Gmail API service, running already-authorized as whichever Google
account you sign into when you authorize the Apps Script project — see
`docs/apps-script.md` for the full setup.

## What "connecting Gmail" means here
1. Decide which Google account will send outreach (e.g. a Botivate
   Workspace mailbox). Put its address in `BOTIVATE_SENDER_EMAIL`
   (`.env`, for reference/display) **and** as the `BOTIVATE_SENDER_EMAIL`
   Script Property when running `setupConfig()` in Apps Script.
2. Open script.google.com **while signed in as that account** (or bind the
   script from within a Sheet you access as that account), paste in the
   `apps-script/` files, and run `setupConfig()` — the authorization
   prompt that appears grants the script permission to send mail and read
   the inbox **as that account**. That's the entire "Gmail credential"
   step.
3. During development, keep `EMAIL_TEST_MODE=true` (both in the backend
   `.env` and the Apps Script `EMAIL_TEST_MODE` Script Property) with
   `TEST_EMAIL` set to a separate testing inbox — every send is redirected
   there regardless of the lead's real email, so no real company is ever
   contacted accidentally (System.txt rule #82, #139).

## Never do this
- Do not create/paste a Gmail "app password" anywhere in this project —
  nothing here reads one.
- Do not put any Gmail credential in the `.env` file beyond the plain
  sender address (`BOTIVATE_SENDER_EMAIL`) used for display/reference.
- If a Gmail app password was ever generated for some other purpose and
  accidentally shared, revoke it immediately at
  myaccount.google.com → Security → App passwords.

## Reply scanning
`ReplyScanner.gs` scans Gmail threads carrying the `SENT_LABEL` (applied
automatically to every thread this script sends), identifies inbound
messages, and — if `BACKEND_WEBHOOK_URL` is configured — POSTs them to the
backend for OpenAI analysis; otherwise it stores a local fallback row with
`reply_type=UNKNOWN` for later backfill. See `docs/apps-script.md` and
`docs/replies.md`.

## Limitations
- Gmail/Workspace sending quotas apply (varies by account type/history) —
  the queue worker's batch size and cadence are intentionally conservative
  (see `apps-script/Config.gs` defaults).
- Delivery and open tracking are **not** reliably available through
  GmailApp — see `docs/email-tracking.md`.
