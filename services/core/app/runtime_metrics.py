"""Bounded, local worker measurements. Never include prompts or command output."""

from __future__ import annotations

import json
import fcntl
import math
import os
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

EVENT_LIMIT = 240
SNAPSHOT_LIMIT = 200_000


def _safe_events(events: Any) -> list[dict[str, Any]]:
    """An allowlist keeps accidental prompts, paths and command output out."""
    if not isinstance(events, list):
        return []
    safe = []
    for item in events[-EVENT_LIMIT:]:
        if not isinstance(item, dict) or not isinstance(item.get("stage"), str):
            continue
        if item.get("status") not in {"ok", "failed"}:
            continue
        if not all(isinstance(item.get(key), (int, float)) and not isinstance(item[key], bool)
                   and 0 <= item[key] <= 1e12 and math.isfinite(item[key])
                   for key in ("started_at", "seconds")):
            continue
        safe.append({"stage": item["stage"][:64], "status": item["status"],
                     "started_at": item["started_at"], "seconds": item["seconds"],
                     "did_work": bool(item.get("did_work", item["status"] == "ok"))})
    return safe


@contextmanager
def measure_task(stage: str, media_root: Path | None) -> Iterator[dict[str, Any]]:
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


def _persist_event(event: dict[str, Any], media_root: Path | None) -> None:
    if media_root is None:
        return
    temporary = None
    try:
        directory = media_root / "analysis" / "runtime"
        directory.mkdir(parents=True, exist_ok=True)
        # Read/merge on disk instead of resetting the history after a worker
        # restart. API and worker processes share the same short file lock.
        with (directory / "worker.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            path = directory / "worker.json"
            try:
                if path.stat().st_size > SNAPSHOT_LIMIT:
                    raise ValueError("runtime snapshot exceeds its bound")
                old = json.loads(path.read_text())
                events = _safe_events(old.get("events")) if isinstance(old, dict) else []
            except (OSError, ValueError):
                events = []
            events = (events + _safe_events([event]))[-EVENT_LIMIT:]
            with tempfile.NamedTemporaryFile(mode="w", dir=directory, prefix=".worker-", delete=False) as output:
                temporary = Path(output.name)
                json.dump({"version": 1, "generated_at": time.time(), "events": events}, output)
            temporary.chmod(0o644)
            os.replace(temporary, path)
    except (OSError, ValueError, TypeError):
        # Diagnostics must not fail a successful edit or analysis.
        pass
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def performance_snapshot(media_root: Path) -> dict[str, Any]:
    path = media_root / "analysis" / "runtime" / "worker.json"
    if not path.exists():
        return {"version": 1, "state": "pending", "events": [], "stages": {}}
    if path.stat().st_size > SNAPSHOT_LIMIT:
        raise ValueError("runtime snapshot exceeds its bound")
    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        raise ValueError("runtime snapshot must be an object")
    events = _safe_events(data.get("events"))
    stages: dict[str, Any] = {}
    for name in sorted({item["stage"] for item in events}):
        values = sorted(
            item["seconds"]
            for item in events
            if item["stage"] == name and item.get("did_work") and item["status"] == "ok"
        )
        if values:
            stages[name] = {
                "samples": len(values),
                "median_seconds": values[len(values) // 2],
                "p95_seconds": values[min(len(values) - 1, int(len(values) * 0.95))],
            }
    return {
        "version": 1,
        "generated_at": data.get("generated_at"),
        "state": "ready",
        "events": events,
        "stages": stages,
        "note": "Bounded recent execution times; excludes queue wait and hosted-model billing.",
    }


@contextmanager
def measure_processing(stage: str):
    from app.config import get_settings

    try:
        root = get_settings().media_root
    except ValueError:
        # Source-only tests and standalone tooling may not load service secrets.
        root = None
    with measure_task(stage, root) as timing:
        timing["did_work"] = True
        yield timing
