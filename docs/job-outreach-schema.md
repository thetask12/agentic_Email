# Job Outreach — Google Sheet Schema (Source of Truth)

Separate, standalone system from the original job-intelligence/sales-outreach
system (see `docs/sheet-schema.md` for that one — untouched, unrelated).

This system: candidate (Prabhat Kumar Singh) applies for AI/Agentic AI roles
by discovering companies hiring for those roles and emailing them directly
with a resume attached. No sales pitch, no lead scoring, no Botivate/AutoRocket
branding anywhere in this module.

Spreadsheet ID provided via `JOB_OUTREACH_SHEET_ID`. One spreadsheet, one tab
per entity, header row = row 1 (frozen), data starts row 2.

## Tabs

1. SETTINGS
2. JOB_LISTINGS
3. COMPANIES
4. EMAIL_QUEUE
5. EMAIL_EVENTS
6. SUPPRESSION_LIST
7. SEARCH_RUNS
8. ACTIVITY_LOG

## SETTINGS
`key | value | description | updated_at`

Rows (seeded on bootstrap):
- `automation_running` — `"true"` / `"false"` — whether the Start/Stop
  automation loop is currently active. This is the single source of truth
  the frontend Start/Stop buttons and the backend scheduler both read/write.
- `daily_email_cap` — max new emails queued per calendar day (default `100`,
  adjustable).
- `emails_sent_today` — running counter, reset at midnight IST.
- `emails_sent_date` — IST date (YYYY-MM-DD) the counter above applies to.

## JOB_LISTINGS
`job_id | source | job_title | company_name | location | city | state | country | is_remote | description | job_url | posted_date | run_id | created_at`

- `job_id`: UUID.
- `source`: e.g. `TAVILY`.
- `is_remote`: `true` / `false`.

## COMPANIES
`company_id | company_name | normalized_name | official_website | domain | contact_email | email_type | email_source_url | email_confidence | research_status | created_at | updated_at`

- `company_id`: UUID.
- `email_type`: `GENERIC | FOUNDER | HR | DEPARTMENT | UNKNOWN` (same
  official-email-only filter rule as the other system: only `GENERIC` or
  `FOUNDER` are accepted as the outreach recipient — `HR`/`DEPARTMENT`/
  `UNKNOWN` are rejected, company dropped).
- `research_status`: `PENDING | RESEARCHING | COMPLETED | FAILED | NOT_FOUND`.

## EMAIL_QUEUE
`queue_id | company_id | job_id | recipient_email | sender_email | subject | body | html_body | status | attempts | max_attempts | scheduled_at | sent_at | message_id | thread_id | error_message | test_mode | created_at | updated_at`

- `queue_id`: UUID.
- `status`: `PENDING | PROCESSING | SENT | RETRY | FAILED | CANCELLED`.
- Exactly one email per company — no follow-ups in this system (mirrors the
  "one initial cold email, period" decision from the original system).

## EMAIL_EVENTS
`event_id | queue_id | company_id | event_type | message_id | thread_id | test_mode | metadata | created_at`

- `event_type`: `QUEUED | SENT | FAILED | BOUNCED | REPLIED` (REPLIED
  recorded for audit only if ReplyScanner is ever added — no automated
  action taken on it, per the "replies handled manually" precedent).

## SUPPRESSION_LIST
`suppression_id | company_id | company_name | domain | reason | created_at`

- Prevents ever emailing the same company twice across runs.
- `reason`: `ALREADY_APPLIED | INVALID_EMAIL | MANUAL`.

## SEARCH_RUNS
`run_id | job_title | city | is_remote | results | qualified | companies_found | emails_queued | status | started_at | completed_at | error_message`

- `status`: `PENDING | RUNNING | COMPLETED | FAILED`.
- One run = one (job_title, city) combination attempt.

## ACTIVITY_LOG
`log_id | event | details | created_at`

- Free-form audit trail (run started/stopped, cap reached, errors), same
  spirit as the original system's ACTIVITY_LOG but scoped to this module.

## Roles searched (fixed set)
- `AI Engineer`
- `Agentic AI Developer`
- `AI Developer`

## Locations searched (fixed set)
India (onsite + remote): Bangalore, Hyderabad, Pune, Chennai, Gurugram,
Noida, Delhi, New Delhi, Mumbai, Raipur, Surat, Ahmedabad, Jaipur, plus
"Remote (India)".

Remote-international (only postings explicitly open to remote/India
candidates): Singapore, UAE, USA (remote-only), UK.

## Sender identity
- `prabhatkumarsictc12@gmail.com` — Apps Script triggers for this module
  must be authorized under this Google account (GmailApp always sends as
  whichever account installed the triggers, regardless of config value).
- No company/brand name in the sender display name or email body — this is
  a personal job-application system, not a business outreach system.

## Email content rules
- Plain-text style (no inline images, no banners, no signature GIF).
- Subject: `Application: {{job_title}}` (no candidate name in the subject).
- Body: short intro mentioning experience duration and role progression
  (no employer/company name disclosed), 3 bullet highlights, resume
  attached, plain signature (name, phone, email, LinkedIn, GitHub).
- Resume PDF attached from a fixed Google Drive file
  (`RESUME_DRIVE_FILE_ID` Apps Script property).
