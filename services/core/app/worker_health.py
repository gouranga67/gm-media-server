import json
import time

from redis import Redis

from app.config import get_settings


def main() -> None:
    settings = get_settings()
    client = Redis.from_url(settings.redis_url, decode_responses=True)
    payload = client.get(settings.worker_heartbeat_key)
    client.close()
    if payload is None:
        raise SystemExit("worker heartbeat is missing")
    heartbeat = json.loads(payload)
    age = time.time() - float(heartbeat["unix_time"])
    if age > settings.worker_heartbeat_ttl_seconds:
        raise SystemExit(f"worker heartbeat is stale ({age:.1f}s)")


if __name__ == "__main__":
    main()
