# Architecture

## High-level flow (System.txt section 1)
```
Job Search (user input: title/state/city/date/experience/sources)
  → Source Manager (site:-scoped Google Custom Search per source)
  → JobExtraction agent (OpenAI, structured output)
  → location filter + dedup
  → COMPANIES upsert → CompanyResearch agent → EmailDiscovery agent
  → CONTACTS
  → LEADS + OpportunityAnalysis agent (automation signals, score)
  → EMAIL_DRAFTS (EmailGeneration agent, personalization from verified facts only)
  → human approval (frontend: Approve/Reject/Regenerate)
  → EMAIL_QUEUE (backend creates row; never sends directly)
  → Apps Script QueueWorker actually sends via GmailApp
  → EMAIL_EVENTS (SENT/FAILED)
  → Apps Script ReplyScanner detects inbound replies on tracked threads
  → backend ReplyAnalysis agent classifies reply
  → follow-ups auto-cancelled on reply; lead status updates
  → user schedules further follow-ups (date/time always user-chosen)
  → Apps Script FollowUpWorker sends due follow-ups
  → complete activity timeline + analytics
```

## Why Google Sheets + Apps Script (not a traditional DB + cron)
System.txt mandates this explicitly (rule #19, #55, #114): Google Sheets is
the primary database (human-editable, zero extra infra), and Google Apps
Script is the only component with a first-class, already-authorized Gmail
identity — it can send mail and read the inbox without OAuth token
management in the backend. The FastAPI backend is deliberately **never**
given Gmail-sending capability; it only creates/reads Sheet rows via the
Sheets API.

## Component map
```
backend/app/
  config/settings.py         env-driven Settings singleton
  models/enums.py            all enums (mirrors docs/sheet-schema.md)
  utils/                     ids (UUID+prefix), time, location normalization
  integrations/
    sheets_client.py         gspread wrapper, header-mapped CRUD, retries
    openai_client.py         structured_completion() — json_schema, strict
    google_search.py         Custom Search JSON API client
  repositories/               one class per Sheet tab (repositories.py)
  agents/                      job_extraction, company_research,
                               opportunity_analysis, email_generation,
                               reply_analysis — each a thin OpenAI wrapper
  sources/source_manager.py    site:-scoped query builder per job source
  prompts/email_master_template.py   the fixed cold-email template text
  services/
    activity_service            ACTIVITY_LOG writes
    event_bus                   in-process SSE pub/sub for search runs
    suppression_service          SUPPRESSION_LIST checks
    email_queue_service           draft -> EMAIL_QUEUE (never sends)
    follow_up_service            schedule/cancel, auto-cancel-on-reply
    reply_service                 ingest_reply() — the reply pipeline
    search_service                 orchestrates the full discovery pipeline
    analytics_service             dashboard + analytics aggregation
    bootstrap_service              seeds default templates/settings/sources
  api/*_routes.py               FastAPI routers, one per resource
  proxy.py                       reverse-proxies non-API routes to Next.js
                                 (combined single-container deployment only)
  main.py                        app wiring, CORS, router mounting order

apps-script/                   see docs/apps-script.md
frontend/                      Next.js 16 App Router, see docs/deployment.md
```

## Real-time updates
`backend/app/services/event_bus.py` is an in-process `asyncio.Queue`-based
pub/sub, one queue set per `run_id`. `GET /api/search/{run_id}/stream`
(SSE via `sse-starlette`) subscribes and forwards events emitted during
`search_service.execute_search()` (source_status, job_found, company_found,
email_found, lead_created, email_generated) — every event corresponds to an
actual row written that run; nothing is synthesized for display (rule #94).

**Scale-out note**: because this is in-process, the backend must run as a
single instance for the SSE stream to reach a client connected to the same
process that's running the search. This matches the single-container
Render deployment. If multi-instance scaling is ever needed, replace the
event bus with a shared pub/sub (Redis, etc.) — not implemented here since
it's outside the stated scope.

## Auditability chain (System.txt rule #80)
Every email is traceable: `JOBS.job_id → LEADS.job_id`,
`COMPANIES.company_id → LEADS.company_id`,
`LEADS.lead_id → EMAIL_DRAFTS.lead_id → EMAIL_QUEUE.email_id →
EMAIL_EVENTS.email_id`, and `REPLIES.email_id`/`REPLIES.lead_id` close the
loop back to the originating lead. `FOLLOW_UPS.original_email_id` links
every follow-up back to the initial email. No table is written without at
least a `lead_id` or `company_id` foreign key (see each repository's
`HEADERS` in `backend/app/repositories/repositories.py`).
