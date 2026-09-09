"""
Reverse proxy: forwards any request that isn't one of our own API routes
through to the internal Next.js server. This lets a single FastAPI process
be the only publicly exposed port in the single-container Render deployment
(see /start.py and /Dockerfile) while still serving the full Next.js app.

Only mounted when FRONTEND_INTERNAL_URL is set (i.e. inside the combined
Docker image). In local development, run the frontend separately with
`npm run dev` and it talks to the backend directly via
NEXT_PUBLIC_API_BASE_URL — this proxy is not needed there.
"""
import os
import logging

import httpx
from fastapi import FastAPI, Request, Response

logger = logging.getLogger("proxy")


def mount_frontend_proxy(app: FastAPI) -> None:
    frontend_url = os.environ.get("FRONTEND_INTERNAL_URL")
    if not frontend_url:
        return

    client = httpx.AsyncClient(base_url=frontend_url, timeout=30.0)

    @app.api_route("/{full_path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"])
    async def proxy_to_frontend(full_path: str, request: Request) -> Response:
        url = httpx.URL(path=f"/{full_path}", query=request.url.query.encode("utf-8"))
        headers = {k: v for k, v in request.headers.items() if k.lower() not in ("host", "content-length")}
        body = await request.body()
        try:
            upstream = await client.request(
                request.method, url, headers=headers, content=body,
            )
        except httpx.HTTPError as exc:
            logger.error("Frontend proxy request failed: %s", exc)
            return Response(content="Frontend unavailable", status_code=502)

        excluded = {"content-encoding", "transfer-encoding", "connection"}
        response_headers = {k: v for k, v in upstream.headers.items() if k.lower() not in excluded}
        return Response(content=upstream.content, status_code=upstream.status_code, headers=response_headers)
