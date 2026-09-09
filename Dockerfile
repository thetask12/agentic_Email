# =============================================================================
# Botivate AI Job Intelligence & Outreach System — single-image production build
# =============================================================================
# Renders as ONE Render Web Service: this image runs both the FastAPI backend
# and the Next.js frontend in a single container, listening on the single
# public $PORT Render assigns. A tiny Python entrypoint (start.py) starts
# uvicorn (FastAPI) on an internal port and the Next.js standalone server on
# another internal port, and FastAPI itself reverse-proxies every non-/api
# request through to Next.js — so only one port is ever exposed externally.
#
# Build:  docker build -t botivate-app .
# Run:    docker run -p 8000:8000 --env-file .env botivate-app
# =============================================================================

# ---------- Stage 1: build the Next.js frontend ----------
FROM node:20-slim AS frontend-build
WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install

COPY frontend/ ./
# The frontend calls the backend via relative /api/* paths in production
# (see frontend/src/lib/api.ts — NEXT_PUBLIC_API_BASE_URL defaults to ""
# when unset, and both services share one origin behind the single port),
# so no build-time API URL is required.
ENV NEXT_PUBLIC_API_BASE_URL=""
RUN npm run build

# ---------- Stage 2: install backend Python dependencies ----------
FROM python:3.12-slim AS backend-build
WORKDIR /app/backend

RUN apt-get update && apt-get install -y --no-install-recommends gcc \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---------- Stage 3: final runtime image ----------
FROM python:3.12-slim AS runtime
WORKDIR /app

# Node.js runtime (for `next start` on the standalone build) + tini for clean
# signal handling of the two child processes.
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl gnupg tini \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# --- Backend ---
COPY --from=backend-build /install /usr/local
COPY backend/ /app/backend/

# --- Frontend (Next.js standalone output) ---
# `output: "standalone"` (set in frontend/next.config.ts) produces a minimal
# server bundle at .next/standalone that only needs node + the copied
# static/public assets to run, without node_modules.
COPY --from=frontend-build /app/frontend/.next/standalone /app/frontend
COPY --from=frontend-build /app/frontend/.next/static /app/frontend/.next/static
COPY --from=frontend-build /app/frontend/public /app/frontend/public

COPY start.py /app/start.py

ENV PYTHONUNBUFFERED=1 \
    BACKEND_INTERNAL_PORT=8001 \
    FRONTEND_INTERNAL_PORT=3000 \
    PORT=8000

EXPOSE 8000

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python3", "/app/start.py"]
