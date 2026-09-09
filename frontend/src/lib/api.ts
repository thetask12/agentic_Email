// Typed fetch client for the Botivate backend API.
//
// In the combined single-container deployment (Render), the frontend and
// backend share one origin — FastAPI proxies non-API requests to Next.js
// (see backend/app/proxy.py) — so NEXT_PUBLIC_API_BASE_URL is left unset
// and API_BASE resolves to "" (same-origin relative /api/* calls).
// In local development, set NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
// (see .env.example) to point at a separately-running backend.
const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "";

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
      cache: "no-store",
    });
  } catch {
    throw new ApiError("Could not reach the backend. Is it running?", 0);
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch {
      // ignore
    }
    throw new ApiError(detail, res.status);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined }),
  patch: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "PATCH", body: body ? JSON.stringify(body) : undefined }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
};

export const fetcher = <T = unknown>(path: string): Promise<T> => api.get<T>(path);

export function apiBase() {
  return API_BASE;
}

export function qs(params: Record<string, string | number | boolean | undefined | null>): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "") sp.set(k, String(v));
  }
  const s = sp.toString();
  return s ? `?${s}` : "";
}
