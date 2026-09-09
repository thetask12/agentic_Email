# CLAUDE.md — Botivate AI Job Intelligence & Outreach System

This file is kept up to date as the system is built. Read this before making
changes so context isn't lost across sessions.

## Source of truth
- `System.txt` — full original spec (140+ requirements). Do not contradict it.
- `docs/sheet-schema.md` — exact Google Sheet tabs/columns/enums used by
  backend, Apps Script, and frontend. All three must stay in sync with this.
- `.env.example` — all required environment variables.

## Architecture
```
backend/        FastAPI app (Python 3.11+, see backend/requirements.txt)
  app/config/       Settings (env-driven, see settings.py)
  app/models/       Enums / dataclasses mirroring docs/sheet-schema.md
  app/schemas/      Pydantic request/response schemas
  app/repositories/ Google Sheets CRUD (gspread), one repo class per tab
  app/services/      Business logic (dedup, scoring, queueing, suppression)
  app/sources/        Job source connectors (Naukri/Indeed/LinkedIn/Google CSE/etc.)
  app/agents/          OpenAI-backed agents (job extraction, company research,
                        opportunity scoring, email generation, reply analysis)
  app/api/             FastAPI routers, one per resource
  app/workers/          Background/async tasks triggered from API (search run)
  app/integrations/    OpenAI client wrapper, Google Search client, Apps Script bridge
  app/utils/            ids, time, location normalization, sanitization
apps-script/     Google Apps Script project (paste into script.google.com)
  Code.gs, Config.gs, SheetRepository.gs, EmailSender.gs, QueueWorker.gs,
  FollowUpWorker.gs, ReplyScanner.gs, EventLogger.gs, Utils.gs
frontend/        Next.js 14 (App Router) + TS + Tailwind + shadcn/ui
docs/            Setup docs (one per integration) + architecture.md
tests/           Backend pytest suite
```

## Non-negotiable rules (from System.txt)
- Google Sheets is the primary DB. Apps Script is the ONLY thing that actually
  sends email or scans Gmail — the FastAPI backend never sends email directly.
- `EMAIL_TEST_MODE=true` during development: ALL outgoing mail is redirected
  to `TEST_EMAIL`. Every email event must record `test_mode: true` when this
  is on. **Currently `false` in production (real sending is live as of
  2026-08-27) — see "Outreach automation" section below for the live state.**
- Never fabricate DELIVERED/OPENED/CLICKED/REPLIED unless a real signal (Gmail
  API / Apps Script event) produced it. If unknown, show
  "SENT — DELIVERY STATUS UNKNOWN" / "OPEN TRACKING NOT AVAILABLE".
- Follow-ups are user-scheduled by default (no auto date-picking) unless the
  user explicitly turns on automation. A reply always cancels pending
  follow-ups for that lead (reason `REPLIED`).
- Every entity has a UUID (`ids.py` helpers), never a spreadsheet row number.
- Idempotency: queue items and replies must not be double-processed (Apps
  Script uses `LockService` + status guards).
- No mock/fake data unless `MOCK_MODE=true` is explicitly set.

## Deployment target — DONE, LIVE ON HOSTINGER (not Render)
- **Actual production deployment (as of 2026-08-27): a Hostinger VPS/Cloud
  server with SSH/terminal access**, NOT Render — the user switched targets
  mid-project ("Hostinger pe deploy karna h and wo waise hi kaam karna
  chahaiye jaise av Render se kar raha h"). The Dockerfile/start.py/proxy.py
  architecture below is platform-agnostic (any Docker host), so ZERO code
  changes were needed for the switch — only the deploy commands differ.
  The `docs/deployment.md` Render instructions are now historical/reference
  only for the container architecture itself; the real day-to-day deploy
  flow is the Hostinger commands further down.
- **Server details**: repo cloned at `~/projects/Autorocket_coldmail` on the
  Hostinger box (hostname `srv1501534`, reachable at `mum2.hostingervps.com`
  via the Hostinger web terminal). Docker image + container are both named
  **`autorocket-sales-email-agent`** (per explicit user naming instruction —
  do not rename without asking). Container runs with `-p 8080:8000` (host
  port 8080 → container's internal port 8000) and `--restart unless-stopped`.
  Public server IP: `187.127.131.173` (dashboard reachable at
  `http://187.127.131.173:8080`, subject to change if the VPS IP changes).
- **Redeploy flow** (after pushing new CODE commits to `origin/master`):
  ```bash
  cd ~/projects/Autorocket_coldmail
  git pull origin master
  docker build -t autorocket-sales-email-agent .
  docker rm -f autorocket-sales-email-agent
  docker run -d --name autorocket-sales-email-agent --restart unless-stopped \
    -p 8080:8000 --env-file .env autorocket-sales-email-agent
  ```
  `.env` lives directly on the server (never committed) — was hand-built
  from `.env.example` with real values. IMPORTANT GOTCHA: Docker's
  `--env-file` does NOT support real multi-line values — the multi-line PEM
  `GOOGLE_SERVICE_ACCOUNT_PRIVATE_KEY` had to be rewritten as ONE line with
  literal `\n` escapes inside the quotes (a Python one-liner script was used
  to auto-convert it) or `docker run` fails with
  `invalid env file (.env): variable '...' contains whitespaces`.
- **`.env`-only change flow** (no code changed, just an env var value edited
  directly on the server): skip `git pull`/`docker build` entirely — the
  existing image is still correct, only the container needs to pick up the
  new env file:
  ```bash
  cd ~/projects/Autorocket_coldmail
  docker rm -f autorocket-sales-email-agent
  docker run -d --name autorocket-sales-email-agent --restart unless-stopped \
    -p 8080:8000 --env-file .env autorocket-sales-email-agent
  ```
- **Architecture** (unchanged from the original Render-era design — this is
  why the platform switch was a non-event): root `Dockerfile` (multi-stage:
  build Next.js standalone → install backend deps → final runtime image with
  Node + Python), root `start.py` (process supervisor: launches Next.js
  standalone on an internal port, then uvicorn on `$PORT`), `backend/app/proxy.py`
  (FastAPI catch-all mounted LAST, after all `/api/*` routers, reverse-
  proxying everything else to the internal Next.js server). Frontend's
  `src/lib/api.ts` defaults `API_BASE` to `""` (same-origin) since prod
  shares one origin; local dev still sets `NEXT_PUBLIC_API_BASE_URL` to hit
  a separately-run backend. `next.config.ts` sets `output: "standalone"`.
- Local `pip install` / `npm install` are NOT to be run in this Windows dev
  environment (Python 3.14 here lacks prebuilt wheels for some pinned
  versions; dependency installation happens inside the Docker build on the
  Hostinger server instead). Code is still written and reasoned about
  locally — just not installed/run locally. `npm run build`/`docker build`
  verification, when needed, happens via the Hostinger terminal.
- git remote `origin` already points to
  `https://github.com/teamai-botivate/Autorocket_coldmail.git` — do NOT
  commit or push without the user explicitly asking first. In practice the
  user has approved pushing directly as part of "do/karo" go-aheads once a
  plan is confirmed — but still confirm before any destructive git op.

## Outreach automation (live production behavior, as of 2026-08-27)
- **Sender identity**: `info@botivate.in` (NOT `team.ai@botivate.in`) —
  Apps Script triggers are installed under a fresh Apps Script project bound
  inside `info@botivate.in`'s own Drive (the CEO's account). This was
  necessary because `GmailApp.sendEmail()` always sends from whichever
  Google account authorized/installed the Apps Script triggers, regardless
  of any `BOTIVATE_SENDER_EMAIL` config value — config alone was never
  enough to fix a `team.ai@...` vs `info@...` sender mismatch that was
  debugged at length earlier in the project.
- **`EMAIL_TEST_MODE` is now `false`** (real sending is live) — was
  `true` with `TEST_EMAIL=prabhatkumarsictc7070@gmail.com` during
  development/testing. Toggle via Apps Script's `enableTestMode()` /
  `disableTestMode()` menu utilities (Config.gs) — NOT a single toggle
  function, per explicit user preference for two unambiguous one-click
  actions.
- **Daily automated search** (`backend/app/services/daily_search_scheduler.py`,
  wired into `main.py`'s lifespan, no external scheduler dependency —
  a plain `asyncio` background task): runs automatically every
  `ATTEMPT_INTERVAL_MINUTES` (currently 15 min) within business hours
  (`BUSINESS_HOURS_START_IST`..`BUSINESS_HOURS_END_IST`, currently 09:00-
  21:00 IST — ~48 attempts/day) for a FIXED query —
  `job_title="MIS Executive"`, `state="Chhattisgarh"` — no manual button
  click needed. No attempts run overnight (21:00-09:00 IST). This interval
  was widened from an original 3x/day (09:00/14:00/19:00), then 3-hourly,
  then to the current 15-min cadence per successive explicit user requests
  for faster retries. All attempts in a calendar day share ONE total cap of
  150 newly-queued outreach emails/day (`DAILY_TOTAL_EMAIL_CAP`); each
  attempt only asks for whatever quota remains after earlier attempts/
  resends that same day, and an attempt is skipped entirely once the cap is
  already reached. A shortfall is NEVER carried into tomorrow — every day
  starts a fresh 150 target (explicit user confirmation: "har din fresh
  150 hi target rahe").
- **Official-email-only filter** (`search_service.py`, around the
  `discover_email()` call): a discovered contact email is only accepted as
  the outreach recipient if its AI-classified `email_type` is `GENERIC` or
  `FOUNDER` — `HR`/`DEPARTMENT`/`UNKNOWN` are rejected (the whole lead is
  dropped, same as "no email found"). This was added because the system
  was finding real emails but they were HR/careers inboxes, not the
  company's own official contact address — not the right outreach target.
- **One-time backlog utility** (`POST /api/settings/resend-test-mode-emails`,
  in `misc_routes.py`): moves EMAIL_QUEUE rows that were marked SENT while
  EMAIL_TEST_MODE was still on (i.e. actually delivered only to TEST_EMAIL,
  never the real company) back to PENDING so Apps Script sends them for
  real now. Shares the same daily 150-email cap as the scheduler via
  `daily_search_scheduler.emails_remaining_today()` — call it repeatedly on
  successive days if the backlog exceeds one day's quota; the response's
  `remaining_backlog` field tells you how much is left.
- **One-time full-reset utility** (`POST /api/settings/reset-all-data?confirm=yes`,
  in `misc_routes.py`, backed by `BaseRepository.clear_all()` /
  `SheetsClient.clear_data_rows()`): wipes every data row (header kept)
  from SEARCH_RUNS, JOBS, COMPANIES, CONTACTS, LEADS, EMAIL_DRAFTS,
  EMAIL_QUEUE, EMAIL_EVENTS in one call. Added after the user accidentally
  deleted all rows from just the EMAIL_QUEUE tab by hand (mid-panic while
  trying to stop an in-flight send) and needed every related tab reset
  consistently rather than a partial manual restore. GOTCHA already fixed:
  `clear_data_rows()` must size its delete range off `ws.get_all_values()`
  (actual populated rows), NOT `ws.row_count` (the configured grid size,
  often 1000 regardless of content) — deleting across an already-near-empty
  grid triggers a Sheets API 400 ("not possible to delete all non-frozen
  rows"). Does NOT touch EMAIL_TEMPLATES, FOLLOW_UP_TEMPLATES,
  SOURCE_STATUS, or SETTINGS — those are config/reference tabs, not data,
  and must never be wiped by this endpoint.
- **Signature image**: an animated GIF (`developer@botivate.in.gif` in the
  shared Drive assets folder), NOT a static poster — replaces the old
  static "Satyendra tandan.jpg.jpeg" poster, which itself had replaced the
  original plain-text "Regards, Satyendra Kumar Tandan..." signature
  earlier in the project. Embedded via a PUBLIC Drive URL
  (`getEmailAssetPublicUrl_` in `EmailSender.gs`, using
  `file.setSharing(DriveApp.Access.ANYONE_WITH_LINK, ...)` +
  `https://drive.google.com/uc?export=view&id=...`), NOT the inline
  `cid:`/`inlineImages` blob mechanism used for the other two images
  (AutoRocket banner, Botivate profile) — inline blobs render as a static
  first frame in Gmail/most clients, so only an externally-hosted `<img
  src>` URL actually animates for the recipient. Required widening the
  Apps Script OAuth scope from `drive.readonly` to full `drive` (readonly
  cannot call `setSharing`).
- **Follow-ups**: OFF. The frontend UI for scheduling/viewing follow-ups was
  removed earlier (button/tab/filter on the Leads pages), and no outreach
  email auto-schedules a follow-up — every lead gets exactly one initial
  cold email, period. The Apps Script `processFollowUps` trigger and
  backend follow-up API/repository code were left untouched (per explicit
  "backend/API untouched, UI-only removal" instruction) — they're just
  never fed new work, so they're effectively dormant.
- **Replies**: handled manually. `ReplyScanner.gs` still records inbound
  Gmail replies into the REPLIES/CONVERSATIONS sheets for audit purposes,
  but no automated action is taken on a reply (no auto-classification-driven
  next step, no auto-response) — the CEO checks Gmail directly.

## Status (update this section as work progresses)
- [x] Repo inspected (was empty except System.txt) — plan drafted.
- [x] `docs/sheet-schema.md`, `.env.example`, `backend/app/config/settings.py` created.
- [x] Backend complete: enums/models, utils (ids/time/location), Sheets client
      + repositories (all 20 tabs), OpenAI agents (job extraction, company
      research, email discovery, opportunity analysis, email generation,
      reply analysis), Google Search source manager, services (activity,
      event bus/SSE, suppression, email queue, follow-up, reply ingestion,
      search orchestration, analytics/dashboard, bootstrap/seed), full API
      (search, catalog, leads, emails, templates, follow-ups, replies,
      misc/dashboard/analytics/settings/health), `main.py` wired up.
      Verified `import app.main` succeeds (loosened requirements.txt pins
      for Python 3.14 wheel availability — see requirements.txt).
- [x] Apps Script project complete (9/9 files): Config, Utils,
      SheetRepository, EmailSender, QueueWorker, FollowUpWorker,
      ReplyScanner, EventLogger, Code (triggers/menu/web app bridge).
- [x] Frontend (Next.js 16, App Router) — COMPLETE and verified.
      `npm run build` succeeds (25 routes, 22 static + 3 dynamic, 0 TS
      errors) and `npm run lint` passes with 0 errors (4 harmless
      react-hooks/exhaustive-deps warnings left as-is). All pages from
      System.txt built: dashboard, /search(+[id] SSE live progress),
      /search-runs, /sources, /jobs(+[id]), /companies(+[id]), /leads
      (table+Kanban+[id] detail w/ tabs), /outreach(+sent/not-sent/
      replied), /follow-ups(+calendar), /inbox(+[id] conversation view),
      /email-queue, /campaigns(+[id] funnel), /analytics (Recharts),
      /activity, /settings (templates manager). Full design system under
      src/components/ui/ (Radix + Tailwind + CVA, hand-built, no shadcn
      CLI). Real fixes applied to two genuine bugs found during
      verification: `fetcher` in src/lib/api.ts wasn't generic (caused
      every useSWR<T> call to type as unknown — fixed to
      `<T>(path): Promise<T>`), and `LeadDetail extends Lead` had an
      incompatible `notes` field override (Lead.notes: string vs
      LeadDetail.notes: LeadNote[] — fixed via `Omit<Lead, "notes">`).
      NOTE: on Windows, `npm install` can leave `node_modules/.bin/*.cmd`
      shims missing after antivirus/OneDrive file-lock interference on
      the Desktop path (confirmed cause of repeated `ENOTEMPTY`/missing-
      module errors during this build) — if `npm run build` ever fails
      with "'next' is not recognized", regenerate the shim or just run
      `node node_modules/next/dist/bin/next build` directly. This is a
      Windows-local-dev quirk only; the Linux-based Dockerfile build is
      unaffected.
- [x] Dockerfile + single-container architecture (frontend + backend, one
      port) — DONE, and deployed live on a Hostinger VPS (see Deployment
      target section above), not Render.
- [x] Frontend simplified to 2 pages only (Dashboard + Leads) per explicit
      user instruction — every other route (Job Search, Search Runs,
      Sources, Jobs, Companies, Outreach, Follow-ups, Inbox, Email Queue,
      Campaigns, Analytics, Activity, Settings) was deleted outright, not
      just hidden from nav. Manual-approval-before-send UI was removed
      entirely — every drafted email auto-queues immediately.
- [x] Daily automated outreach live (see "Outreach automation" section
      above): fixed MIS Executive / Chhattisgarh search, 3x/day retry,
      150 emails/day shared cap, official-email-only filter, real sending
      from info@botivate.in with an animated-GIF signature.
- [ ] Remaining docs (architecture/google-sheets/apps-script/gmail/openai/
      search/email-tracking/follow-ups/replies/security/troubleshooting),
      backend tests.

## Commands
- Backend dev (local, Windows — informational only, not run in this dev
  environment per the note above): `cd backend && pip install -r requirements.txt && uvicorn app.main:app --reload`
- Frontend dev: `cd frontend && npm install && npm run dev`
- Tests: `cd backend && pytest`
- **Production redeploy**: see the Hostinger command block under
  "Deployment target" above — this is the actual live deploy flow, run
  from the Hostinger server's own terminal, not from this dev environment.
