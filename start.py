#!/usr/bin/env python3
"""
Single-container process supervisor for Render deployment (per user
instruction: one Docker web service serving both frontend and backend).

Starts:
  1. Next.js standalone server on FRONTEND_INTERNAL_PORT (default 3000).
  2. FastAPI (uvicorn) on PORT (Render's assigned public port, default 8000)
     — this is the ONLY port exposed to the outside world. FastAPI itself
     proxies any request that isn't /api/*, /docs, /openapi.json, or /health
     through to the internal Next.js server (see backend/app/proxy.py).

If either process exits, this script tears down the other and exits with a
non-zero code so Render's health checks / restart policy notice the crash
instead of silently running with a broken half.
"""
import os
import signal
import subprocess
import sys
import time

BACKEND_DIR = os.path.join(os.path.dirname(__file__), "backend")
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "frontend")

PUBLIC_PORT = os.environ.get("PORT", "8000")
FRONTEND_PORT = os.environ.get("FRONTEND_INTERNAL_PORT", "3000")

os.environ["FRONTEND_INTERNAL_URL"] = f"http://127.0.0.1:{FRONTEND_PORT}"

processes: list[subprocess.Popen] = []


def start(cmd: list[str], cwd: str, env: dict) -> subprocess.Popen:
    print(f"[start.py] launching: {' '.join(cmd)} (cwd={cwd})", flush=True)
    proc = subprocess.Popen(cmd, cwd=cwd, env=env)
    processes.append(proc)
    return proc


def shutdown(*_args) -> None:
    print("[start.py] shutting down child processes...", flush=True)
    for p in processes:
        if p.poll() is None:
            p.terminate()
    time.sleep(2)
    for p in processes:
        if p.poll() is None:
            p.kill()
    sys.exit(0)


def main() -> None:
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    frontend_env = dict(os.environ)
    frontend_env["PORT"] = FRONTEND_PORT
    frontend_env["HOSTNAME"] = "127.0.0.1"
    frontend_proc = start(["node", "server.js"], cwd=FRONTEND_DIR, env=frontend_env)

    # Give Next.js a moment to bind before FastAPI starts proxying to it.
    time.sleep(1.5)

    backend_env = dict(os.environ)
    backend_proc = start(
        ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", PUBLIC_PORT],
        cwd=BACKEND_DIR,
        env=backend_env,
    )

    while True:
        for proc, name in ((frontend_proc, "frontend"), (backend_proc, "backend")):
            code = proc.poll()
            if code is not None:
                print(f"[start.py] {name} process exited with code {code} — shutting down", flush=True)
                shutdown()
        time.sleep(2)


if __name__ == "__main__":
    main()
