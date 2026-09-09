# Botivate AI Job Intelligence, Outreach & Follow-up Command Center

A complete job-discovery → company-research → lead-qualification →
cold-outreach → email-queue → send-tracking → reply-tracking →
follow-up-management → sales-analytics platform for Botivate Services LLP.

See `System.txt` for the full original specification this system
implements, and `CLAUDE.md` for the current build status.

## What this is
- A **FastAPI backend** that discovers jobs (via Google Custom Search,
  never scraping login/CAPTCHA-gated pages), researches companies, finds
  public business emails, scores automation opportunity with OpenAI,
  drafts personalized cold emails, and exposes a full REST API for a CRM
  frontend.
- A **Next.js frontend** — the "Sales Control Center" — showing every job,
  company, lead, email, reply, and follow-up with full visibility into
  what was sent, what wasn't, what got a reply, and what's due next.
- A **Google Sheets** database (one spreadsheet, ~20 tabs — see
  `docs/sheet-schema.md`) as the system of record.
- A **Google Apps Script** project that is the *only* component that
  actually sends email or reads Gmail — it runs the email queue worker,
  the follow-up worker, and the reply scanner, all against the same
  spreadsheet.

## Project structure
```
backend/        FastAPI app (Python)
frontend/       Next.js 16 app (TypeScript, Tailwind)
apps-script/    Google Apps Script project (paste into script.google.com)
docs/           Setup guides, architecture, schema reference
tests/          (backend/tests/) pytest suite
Dockerfile      Single-image build serving both frontend + backend
start.py        Process supervisor used by the Docker image
```

## Quick start (local development)

**Backend:**
```bash
cd backend
pip install -r requirements.txt
cp ../.env.example ../.env   # fill in values — see docs/ below
uvicorn app.main:app --reload --port 8000
```

**Frontend** (separate terminal):
```bash
cd frontend
npm install
# create frontend/.env.local:
#   NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
npm run dev
```

**Tests:**
```bash
cd backend
pytest
```

## Production deployment
Render, single Docker Web Service (both frontend and backend in one
container, one exposed port). See **`docs/deployment.md`** for exact
steps — no `render.yaml` is used; the service is configured directly in
the Render dashboard against the root `Dockerfile`.

## Setup guides (read in this order for a first-time deployment)
1. `docs/google-sheets.md` — create the spreadsheet + service account.
2. `docs/search.md` — Google Custom Search (job discovery).
3. `docs/openai.md` — OpenAI API key.
4. `docs/gmail.md` + `docs/apps-script.md` — deploy the Apps Script
   project that actually sends mail and scans replies.
5. `docs/deployment.md` — deploy the combined app to Render.

## Deep-dive docs
- `docs/architecture.md` — full pipeline + component map.
- `docs/sheet-schema.md` — exact tab/column/enum reference.
- `docs/email-tracking.md` — what send/delivery/open tracking is (and
  honestly is not) available, and why.
- `docs/follow-ups.md`, `docs/replies.md` — the two most detail-sensitive
  subsystems (user-controlled scheduling, reply-triggered cancellation,
  idempotent reply detection).
- `docs/security.md` — secrets handling, sanitization, suppression.
- `docs/troubleshooting.md` — common issues and where to look.

## Safety defaults (do not change casually)
- `EMAIL_TEST_MODE=true` — every outgoing email is redirected to
  `TEST_EMAIL` regardless of the real recipient, until you deliberately
  flip this for a real campaign.
- `AUTO_SEND=false`, `AUTO_REPLY=false`, `AUTO_FOLLOWUP_AUTOMATION=false`
  (in the `SETTINGS` sheet) — every email requires human approval before
  queueing, AI never auto-sends a reply, and follow-up dates are always
  user-chosen unless you explicitly build/enable automation on top of the
  documented hook.
- `MOCK_MODE=false` — no fabricated data is ever shown; empty states mean
  exactly that.

## Known limitations
See `docs/troubleshooting.md` and `docs/email-tracking.md`. In short: some
job portals block automated access (this system never bypasses
login/CAPTCHA — it only reads publicly indexed search results); email
delivery/open tracking is not reliably available via Gmail and is never
faked; Gmail sending quotas and Apps Script execution limits apply; Google
Sheets has scalability limits at high volume.
