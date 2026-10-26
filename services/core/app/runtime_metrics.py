"""Bounded, local worker measurements. Never include prompts or command output."""
from __future__ import annotations

import json
import os
import time
from collections import deque
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

EVENT_LIMIT = 240
_events: deque[dict[str, Any]] = deque(maxlen=EVENT_LIMIT)


@contextmanager
def measure_task(stage: str, media_root: Path) -> Iterator[dict[str, Any]]:
    started = time.monotonic()
    event: dict[str, Any] = {"stage": stage, "started_at": time.time(), "status": "ok"}
    try:
        yield event
    except Exception:
        event["status"] = "failed"
        raise
    finally:
        event["seconds"] = round(time.monotonic() - started, 4)
        if event.get("did_work") is not False or event["status"] != "ok":
            _persist_event(event, media_root)


def _persist_event(event: dict[str, Any], media_root: Path) -> None:
    _events.append(event)
    try:
        directory = media_root / "analysis" / "runtime"
        directory.mkdir(parents=True, exist_ok=True)
        temporary = directory / "worker.json.tmp"
        temporary.write_text(json.dumps({"version": 1, "generated_at": time.time(), "events": list(_events)}))
        os.replace(temporary, directory / "worker.json")
    except OSError:
        # Diagnostics must not fail a successful edit or analysis.
        pass

def performance_snapshot(media_root: Path) -> dict[str, Any]:
    path = media_root / "analysis" / "runtime" / "worker.json"
    if not path.exists():
        return {"version": 1, "state": "pending", "events": [], "stages": {}}
    if path.stat().st_size > 200_000:
        raise ValueError("runtime snapshot exceeds its bound")
    data = json.loads(path.read_text())
    events = data.get("events", [])[-EVENT_LIMIT:]
    stages: dict[str, Any] = {}
    for name in sorted({item["stage"] for item in events}):
        values = sorted(item["seconds"] for item in events if item["stage"] == name and item.get("did_work"))
        if values:
            stages[name] = {"samples": len(values), "median_seconds": values[len(values) // 2],
                            "p95_seconds": values[min(len(values) - 1, int(len(values) * .95))]}
    return {**data, "state": "ready", "events": events, "stages": stages,
            "note": "Bounded recent execution times; excludes queue wait and hosted-model billing."}
