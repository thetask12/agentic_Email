"""
In-process cancellation registry for active search runs, mirroring the
event_bus.py pattern (single-process, no external broker needed — see
docs/architecture.md for scale-out notes). A run_id is added here the
instant POST /api/search/{run_id}/stop is called, and execute_search()'s
loop checks it after every processed result, so cancellation is immediate
rather than waiting on the next Sheets round-trip.
"""
from __future__ import annotations

_cancelled_run_ids: set[str] = set()


def request_cancellation(run_id: str) -> None:
    _cancelled_run_ids.add(run_id)


def is_cancelled(run_id: str) -> bool:
    return run_id in _cancelled_run_ids


def clear(run_id: str) -> None:
    _cancelled_run_ids.discard(run_id)
