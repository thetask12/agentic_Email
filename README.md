# Job Outreach System

A personal job-application automation system for Prabhat Kumar Singh: it
searches the web for Indian (and remote-international) companies hiring for
AI Engineer / Agentic AI Developer / AI Developer roles, discovers each
company's official contact email, and sends a short cold-application email
with a resume attached — one email per company, no follow-ups, no CRM.

See `CLAUDE.md` for full architecture, non-negotiable rules, and current
build/deployment status.

## What this is
- A **FastAPI backend** (`backend/app/job_outreach/`) that searches for job
  postings via Tavily, researches companies, discovers + classifies official
  contact emails with OpenAI (only `GENERIC`/`FOUNDER` addresses accepted),
  generates a short application email, and queues it for sending.
- A **Google Sheet** database (`docs/job-outreach-schema.md` — 8 tabs) as
  the system of record, including the Start/Stop automation flag.
- A **Google Apps Script** project (`apps-script-job-outreach/`) — the only
  component that actually sends email — which processes the queue and
  attaches the resume PDF from Google Drive.
- A **Next.js frontend** with a single dashboard page showing automation
  status and Start/Stop controls.

## Project structure
```
backend/                    FastAPI app (Python) — job_outreach/ is the only module
frontend/                   Next.js app (TypeScript, Tailwind)
apps-script-job-outreach/   Google Apps Script project (paste into script.google.com, or `clasp push`)
docs/job-outreach-schema.md Sheet schema reference
Dockerfile                  Single-image build serving both frontend + backend
start.py                    Process supervisor used by the Docker image
```

## Quick start (local development)

**Backend:**
```bash
cd backend
pip install -r requirements.txt
cp ../.env.example ../.env   # fill in real values
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

## Production deployment
Docker, single Web Service (both frontend and backend in one container, one
exposed port) — deployed directly from the root `Dockerfile` against
whatever host you point it at (Render, a VPS, etc.). No `render.yaml` is
used.

## Safety defaults (do not change casually)
- `JOB_OUTREACH_EMAIL_TEST_MODE=true` — every outgoing email is redirected
  to `JOB_OUTREACH_TEST_EMAIL` regardless of the real recipient, until
  deliberately turned off for real sending.
- Only official `GENERIC`/`FOUNDER` company emails are ever used as an
  outreach recipient — `HR`/`DEPARTMENT`/`UNKNOWN` addresses are rejected.
- A company is never emailed twice (suppression list).
- No fabricated delivery/open/click status is ever shown.
