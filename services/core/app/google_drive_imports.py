"""Durable Google Drive downloader. Editing and GPU work never wait on cloud transfers."""

import signal
import shutil
import time
from typing import Any

from psycopg.types.json import Jsonb

from app import google_drive as drive
from app.config import get_settings
from app.database import connection


MAX_ATTEMPTS = 5


def recover_stale_imports() -> int:
    with connection() as database:
        result = database.execute(
            """UPDATE google_drive_imports
               SET status = 'pending', lease_expires_at = NULL,
                   next_attempt_at = now(), updated_at = now()
               WHERE status = 'downloading'"""
        )
    return result.rowcount


def claim_import() -> dict[str, Any] | None:
    with connection() as database:
        row = database.execute(
            """SELECT drive_import.*, assets.byte_size,
                      account.refresh_token_ciphertext
               FROM google_drive_imports drive_import
               JOIN assets ON assets.id = drive_import.asset_id
               JOIN google_drive_connections account ON account.id = drive_import.connection_id
               WHERE drive_import.status = 'pending' AND drive_import.next_attempt_at <= now()
                 AND assets.status = 'uploading'
               ORDER BY drive_import.created_at, drive_import.id
               LIMIT 1 FOR UPDATE OF drive_import SKIP LOCKED"""
        ).fetchone()
        if row is None:
            return None
        database.execute(
            """UPDATE google_drive_imports
               SET status = 'downloading', attempts = attempts + 1,
                   lease_expires_at = now() + interval '15 minutes', error = NULL,
                   updated_at = now()
               WHERE id = %s""",
            (row["id"],),
        )
        row["attempts"] = int(row["attempts"]) + 1
        return row


def _fail(item: dict[str, Any], error: drive.GoogleDriveError) -> None:
    retry = error.retryable and not error.reconnect and int(item["attempts"]) < MAX_ATTEMPTS
    delay = min(300, 5 * (2 ** max(0, int(item["attempts"]) - 1)))
    with connection() as database:
        database.execute(
            """UPDATE google_drive_imports
               SET status = %s, next_attempt_at = now() + make_interval(secs => %s),
                   lease_expires_at = NULL, error = %s, updated_at = now()
               WHERE id = %s""",
            ("pending" if retry else "failed", delay if retry else 0, str(error)[:500], item["id"]),
        )
        if not retry:
            database.execute(
                """UPDATE assets SET status = 'failed',
                       metadata = metadata || %s, updated_at = now()
                   WHERE id = %s AND status = 'uploading'""",
                (Jsonb({"google_drive_import_error": str(error)[:500]}), item["asset_id"]),
            )


def process_one_import() -> bool:
    item = claim_import()
    if item is None:
        return False
    settings = get_settings()
    upload_id = f"drive-{item['id']}"
    staging = settings.upload_root / upload_id
    reported = int(item.get("downloaded_bytes") or 0)

    def progress(value: int) -> None:
        nonlocal reported
        if value < int(item["byte_size"]) and value - reported < 16 * 1024 * 1024:
            return
        reported = value
        with connection() as database:
            database.execute(
                """UPDATE google_drive_imports SET downloaded_bytes = %s,
                       lease_expires_at = now() + interval '15 minutes', updated_at = now()
                   WHERE id = %s AND status = 'downloading'""",
                (value, item["id"]),
            )

    try:
        expected = int(item["byte_size"])
        partial = staging.stat().st_size if staging.is_file() else 0
        upload_disk = shutil.disk_usage(settings.upload_root)
        media_disk = shutil.disk_usage(settings.media_root)
        upload_reserve = max(settings.media_min_free_bytes, int(upload_disk.total * settings.media_min_free_percent / 100))
        media_reserve = max(settings.media_min_free_bytes, int(media_disk.total * settings.media_min_free_percent / 100))
        if upload_disk.free - max(0, expected - partial) < upload_reserve or media_disk.free - expected < media_reserve:
            raise drive.GoogleDriveError("Server storage is too full to import this file safely.")
        refresh = drive.decrypt_refresh_token(settings, item["refresh_token_ciphertext"])
        access = drive.refresh_access_token(settings, refresh)
        drive.download_file(access, item["remote_file_id"], staging, int(item["byte_size"]), progress)
        with connection() as database:
            database.execute(
                """UPDATE assets SET status = 'uploaded', tus_upload_id = %s,
                       tus_storage_key = %s, updated_at = now()
                   WHERE id = %s AND status = 'uploading'""",
                (upload_id, upload_id, item["asset_id"]),
            )
            database.execute(
                """UPDATE google_drive_imports SET status = 'downloaded',
                       downloaded_bytes = %s, lease_expires_at = NULL, error = NULL,
                       updated_at = now() WHERE id = %s""",
                (item["byte_size"], item["id"]),
            )
        return True
    except drive.GoogleDriveError as error:
        _fail(item, error)
    except Exception as error:
        _fail(item, drive.GoogleDriveError("The Drive import failed safely and will retry.", retryable=True))
        print(f"google drive import failed: {item['id']}: {type(error).__name__}", flush=True)
    return True


def main() -> None:
    stopping = False

    def stop(*_: object) -> None:
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    recovered = recover_stale_imports()
    if recovered:
        print(f"requeued stale Google Drive imports: {recovered}", flush=True)
    print("google drive importer ready", flush=True)
    while not stopping:
        try:
            worked = process_one_import()
        except Exception as error:
            print(f"google drive importer cycle deferred: {type(error).__name__}", flush=True)
            worked = False
        if not worked:
            time.sleep(2)
    print("google drive importer stopped", flush=True)


if __name__ == "__main__":
    main()
