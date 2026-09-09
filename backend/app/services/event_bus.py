"""
In-process SSE event bus for real-time search-run progress (System.txt
section 95). Each search run gets its own asyncio.Queue; the
/api/search/{run_id}/stream endpoint subscribes and forwards events until
the run completes. This is intentionally simple (single-process) — see
docs/architecture.md for scale-out notes (Sheets is not built for
concurrent multi-instance writes anyway).
"""
from __future__ import annotations

import asyncio
import json
from collections import defaultdict


class EventBus:
    def __init__(self) -> None:
        self._queues: dict[str, list[asyncio.Queue]] = defaultdict(list)

    def subscribe(self, run_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._queues[run_id].append(q)
        return q

    def unsubscribe(self, run_id: str, q: asyncio.Queue) -> None:
        if q in self._queues.get(run_id, []):
            self._queues[run_id].remove(q)

    async def publish(self, run_id: str, event_type: str, data: dict) -> None:
        payload = json.dumps(data, ensure_ascii=False)
        for q in list(self._queues.get(run_id, [])):
            await q.put({"event": event_type, "data": payload})

    async def close(self, run_id: str) -> None:
        for q in list(self._queues.get(run_id, [])):
            await q.put({"event": "done", "data": "{}"})
        self._queues.pop(run_id, None)


event_bus = EventBus()
