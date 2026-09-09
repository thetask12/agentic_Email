# CLAUDE.md — Job Outreach System

This file is kept up to date as the system evolves. Read this before making
changes so context isn't lost across sessions.

## History

This repo originally hosted a different system — "Botivate AI Job
Intelligence & Outreach", a sales-outreach tool built for Botivate Services
LLP (job discovery, lead scoring, CRM pipeline, follow-ups, reply tracking,
deployed on a Hostinger VPS). That entire system has been fully removed
(backend agents/routers/services/sources, the `apps-script/` project, its
Sheet schema docs, and the corresponding frontend pages/components). This
repo now exclusively hosts the personal Job Outreach system described below.

## What this system is

A standalone personal job-application tool for the repo owner (Prabhat
Kumar Singh) applying to companies himself: it searches for Indian/
remote-India-friendly companies hiring for AI/Agentic-AI roles, discovers an
official contact email for each, and sends exactly ONE short cold-
application email (resume PDF attached) per company — no follow-ups, no
lead scoring, no CRM pipeline. Never emails the same company twice
(SUPPRESSION_LIST). No Botivate/AutoRocket branding anywhere in this
module's code, config, UI, or email content.

- **Fixed roles searched**: "AI Engineer", "Agentic AI Developer",
  "AI Developer".
- **Fixed locations searched**: Bangalore, Hyderabad, Pune, Chennai,
  Gurugram, Noida, Delhi, New Delhi, Mumbai, Raipur, Surat, Ahmedabad,
  Jaipur, "Remote (India)", plus remote-international postings (Singapore,
  UAE, USA, UK) explicitly open to remote/India candidates.
- **Official-email-only filter**: a discovered email must classify as
  `GENERIC` or `FOUNDER`; `HR`/`DEPARTMENT`/`UNKNOWN` means the company is
  dropped (same as "no email found"). See
  `backend/app/job_outreach/email_discovery.py` and `service.py`.
- **Sender identity**: `prabhatkumarsictc12@gmail.com` — a personal Gmail
  account, not a company inbox. The Job Outreach Apps Script project
  (`apps-script-job-outreach/`) MUST be authorized/have its triggers
  installed under this exact Google account — `GmailApp.sendEmail()` always
  sends from whichever account authorized the triggers, regardless of any
  config value.
- **Google Sheet**: ID `1iJXsPZdBCVmExx6l4DIzSHC2jdxCRJz2-naBXdTLoww` (see
  `docs/job-outreach-schema.md` for the full tab/column schema — SETTINGS,
  JOB_LISTINGS, COMPANIES, EMAIL_QUEUE, EMAIL_EVENTS, SUPPRESSION_LIST,
  SEARCH_RUNS, ACTIVITY_LOG). Bootstrapped via
  `scripts/setup_job_outreach_sheet.py` (idempotent — creates missing tabs/
  headers, seeds SETTINGS, never touches existing tabs).

## House rules (non-negotiable)

- Google Sheets is the database — this module's OWN sheet + service
  account, via `backend/app/job_outreach/sheets.py`
  (`JobOutreachSheetsClient`). Never a spreadsheet row number as an
  identifier — every entity has a UUID (`app/utils/ids.py`).
- Apps Script is the ONLY thing that actually sends email — the FastAPI
  backend never sends email directly. `apps-script-job-outreach/
  QueueWorker.gs` sends whatever is PENDING in EMAIL_QUEUE independently of
  the backend scheduler's Start/Stop state.
- `JOB_OUTREACH_EMAIL_TEST_MODE` defaults `true`: while true, every
  outgoing application email is redirected to `JOB_OUTREACH_TEST_EMAIL`,
  and every EMAIL_QUEUE/EMAIL_EVENTS row this module writes records
  `test_mode: true`. Currently `true` in the local `.env` (still being
  verified end-to-end) — flip only when ready for real sends.
- Idempotency: a company is never emailed twice (SUPPRESSION_LIST check
  before queueing).
- No mock/fake data — the module has no `MOCK_MODE` flag; if the Sheet
  isn't configured (`sheets_configured` is false), repositories log a
  warning and hold no persistence rather than fabricating rows.

## Architecture

```
backend/
  app/main.py            FastAPI entrypoint — mounts job_outreach's router
                          and starts/stops its scheduler in the lifespan;
                          mounts the frontend proxy last.
  app/proxy.py            Generic reverse proxy: forwards non-/api/* requests
                          to the internal Next.js server (single-container
                          Docker deploy). Not Job-Outreach-specific.
  app/config/settings.py  Generic infra settings (CORS, host/port, log
                          level) + the shared OpenAI/Tavily keys used by
                          app/integrations/.
  app/integrations/       openai_client.py, web_search.py (Tavily) — shared,
                          generic AI/search wrappers the Job Outreach module
                          calls into directly.
  app/utils/              ids.py, time_utils.py — small stateless helpers
                          shared with job_outreach.
  app/job_outreach/       The entire Job Outreach module:
    config.py               JobOutreachSettings (own pydantic-settings class,
                             JOB_OUTREACH_* env vars, independent of
                             app.config.settings).
    sheets.py                JobOutreachSheetsClient (own Sheet/service
                             account, independent of app.integrations).
    repositories.py          Per-tab CRUD (company_repo, email_queue_repo,
                             settings_repo, etc.) over the Sheet.
    settings_store.py        Typed helpers over the SETTINGS tab
                             (automation_running flag, daily cap/counter).
    search.py                Job search via Tavily.
    email_discovery.py        Official contact email discovery.
    email_generator.py        Cold-application email generation.
    service.py                Orchestrates one search-and-outreach cycle;
                             start()/stop()/get_status().
    scheduler.py              Always-alive asyncio background loop
                             (15-min cadence), gated by automation_running.
    routes.py                 FastAPI router mounted at /api/job-outreach
                             (start/stop/status/companies/queue).
apps-script-job-outreach/  Separate Apps Script project (Config, Utils,
                          SheetRepository, EmailSender, QueueWorker,
                          EventLogger, Code — menu/triggers only, no
                          follow-up worker or reply scanner).
frontend/        Next.js (App Router) + TS + Tailwind — a single Dashboard
                  page showing the Job Outreach automation Start/Stop card.
docs/
  job-outreach-schema.md  Exact Sheet tabs/columns/enums this module
                          implements against. Keep in sync with
                          repositories.py and the frontend.
```

## Start/Stop mechanism

A persisted `automation_running` flag in the Sheet's own SETTINGS tab
(`backend/app/job_outreach/settings_store.py`), read every tick by an
always-alive asyncio background loop (`backend/app/job_outreach/
scheduler.py`, 15-minute cadence — plain `asyncio`, not APScheduler).
`POST /api/job-outreach/start` / `/stop` just flip the flag; `GET /api/
job-outreach/status` reports `running`, `emails_sent_today`, `daily_cap`.
Stop does NOT cancel already-PENDING EMAIL_QUEUE rows — the separate Apps
Script queue worker (`apps-script-job-outreach/QueueWorker.gs`) keeps
sending those independently; Stop only prevents new search cycles from
starting. Frontend: a "Job Outreach Automation" card on the Dashboard page
(`frontend/src/components/job-outreach/automation-card.tsx`) with two
distinct "Start Automation"/"Stop Automation" buttons (not one toggle).

## Apps Script deployment

`apps-script-job-outreach/` — Config, Utils, SheetRepository, EmailSender,
QueueWorker, EventLogger, Code (menu/triggers only — no doGet/doPost
bridge, no follow-up worker, no reply scanner; out of scope for this
module). Plain-text emails only (no inline images/banners/signature GIF);
the resume PDF is attached via
`DriveApp.getFileById(RESUME_DRIVE_FILE_ID).getBlob()` as a normal
attachment (`drive.readonly` scope is sufficient). See
`apps-script-job-outreach/README.md` for the exact manual `clasp login`/
`clasp create`/`clasp push` steps (Claude Code cannot run these itself —
interactive OAuth requires a browser).

## Env vars

See `.env.example`. Shared/generic: `OPENAI_API_KEY`, `OPENAI_MODEL`,
`TAVILY_API_KEY`, `BACKEND_HOST`, `BACKEND_PORT`, `BACKEND_CORS_ORIGINS`,
`API_AUTH_TOKEN`, `LOG_LEVEL`, `NEXT_PUBLIC_API_BASE_URL`. Job-Outreach-
specific: `JOB_OUTREACH_SHEET_ID`, `JOB_OUTREACH_SERVICE_ACCOUNT_EMAIL`,
`JOB_OUTREACH_SERVICE_ACCOUNT_PRIVATE_KEY` (sensitive — blank in
`.env.example`), `JOB_OUTREACH_SENDER_EMAIL`,
`JOB_OUTREACH_RESUME_DRIVE_FILE_ID`, `JOB_OUTREACH_CANDIDATE_NAME`,
`JOB_OUTREACH_CANDIDATE_PHONE`, `JOB_OUTREACH_CANDIDATE_LINKEDIN`,
`JOB_OUTREACH_CANDIDATE_GITHUB` (public resume info, real defaults are
fine), `JOB_OUTREACH_DAILY_EMAIL_CAP`, `JOB_OUTREACH_EMAIL_TEST_MODE`
(defaults true/safe), `JOB_OUTREACH_TEST_EMAIL`.

## Deployment target

Intended to deploy to a NEW, separate Render service (or any Docker host —
the `Dockerfile`/`start.py`/`app/proxy.py` architecture is platform-
agnostic) — creating that service and entering its env vars is a manual
step the user does in the host's own dashboard; env vars needed there are
exactly the `JOB_OUTREACH_*` list above plus the shared integrations it
also needs (`OPENAI_API_KEY`, `TAVILY_API_KEY`).

## Manual one-time steps still required from the user

None of these can be done by Claude Code: share the Job Outreach Google
Sheet with `JOB_OUTREACH_SERVICE_ACCOUNT_EMAIL`'s `client_email` as Editor;
run `scripts/setup_job_outreach_sheet.py` (or have it run) once the sheet
is shared; `clasp login`/`clasp create`/`clasp push` for
`apps-script-job-outreach/` under `prabhatkumarsictc12@gmail.com`, then run
`setupConfigFromValues()` and `installTriggers()` from the Apps Script
editor; share the resume Drive file with
`prabhatkumarsictc12@gmail.com` (at least Viewer); create the deployment
service and set its env vars.

## Commands

- Backend dev (local, Windows — informational only; `pip install` isn't run
  in this Windows dev environment per historical note — Python 3.14 here
  lacks prebuilt wheels for some packages): `cd backend && pip install -r
  requirements.txt && uvicorn app.main:app --reload`
- Frontend dev: `cd frontend && npm install && npm run dev`
- Tests: `cd backend && pytest`
