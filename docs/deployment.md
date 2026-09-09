# Deployment (Render, Docker, single Web Service)

Per project decision: **one Render Web Service**, built from the root
`Dockerfile`, serving **both** the FastAPI backend and the Next.js frontend
behind a **single public port**. No `render.yaml` is used — configure the
service directly in the Render dashboard.

## How the single container works

```
                         Render Web Service (one public port: $PORT)
                                        │
                                        ▼
                              FastAPI (uvicorn) ── binds $PORT
                                 │                 │
                          /api/*, /docs      everything else
                                 │                 │
                                 ▼                 ▼
                        backend route handlers   reverse-proxied to
                                                  Next.js standalone
                                                  server (127.0.0.1:3000,
                                                  internal only)
```

- `start.py` (repo root) is the container's entrypoint. It launches the
  Next.js standalone server on an internal port (`FRONTEND_INTERNAL_PORT`,
  default 3000) and then launches `uvicorn` bound to `$PORT` (the port
  Render injects — do not hardcode a port in the dashboard, Render sets it).
- `backend/app/proxy.py` mounts a catch-all route in FastAPI, registered
  **after** all `/api/*` routers, that forwards any non-API request to the
  internal Next.js server. This is why the frontend's API client
  (`frontend/src/lib/api.ts`) defaults to same-origin (`""`) requests in
  production — both apps are reached through the one exposed port.
- If either the frontend or backend process crashes, `start.py` tears the
  other down and exits non-zero so Render's health checks correctly detect
  and restart the service instead of running in a half-broken state.

## Render setup steps

1. Push this repository to GitHub (the existing `origin` remote, or
   wherever you want Render to build from).
2. In the Render dashboard: **New > Web Service** → connect the repo.
3. **Runtime**: Docker. Render will detect the root `Dockerfile`
   automatically — leave the Dockerfile path as `Dockerfile` and the
   Docker build context as the repo root.
4. **Instance type**: any plan with at least 512MB RAM to start (both
   Next.js and FastAPI run in the same container).
5. **Environment variables**: add every variable from `.env.example` in the
   Render service's Environment tab (Render encrypts these; never commit a
   real `.env` file — see `.gitignore`). Do **not** set `PORT` yourself —
   Render injects it automatically and `start.py`/uvicorn read it.
6. **Health check path**: `/api/health`.
7. Deploy. Render builds the multi-stage `Dockerfile` (frontend build →
   backend deps → final runtime image) and starts the container via
   `python3 start.py`.

## Local development (NOT inside Docker)

Run the two apps separately, each against its own port, exactly as before:

```bash
# backend
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# frontend (separate terminal)
cd frontend
npm install
# .env.local: NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
npm run dev
```

## Building/testing the combined image locally (optional)

```bash
docker build -t botivate-app .
docker run -p 8000:8000 --env-file .env botivate-app
# open http://localhost:8000
```

## Notes / limitations

- Google Apps Script is a separate deployment (script.google.com) — see
  `docs/apps-script.md`. It is not part of this Docker image.
- Google Sheets, OpenAI, and Google Custom Search calls happen from the
  backend process inside this same container; no additional services are
  required.
- Scaling to multiple container instances is not recommended as-is: the
  in-process SSE event bus (`backend/app/services/event_bus.py`) and the
  Google Sheets write path assume a single backend process. Keep this
  service at one instance unless that is re-architected.
