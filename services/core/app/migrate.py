import time
from pathlib import Path

import psycopg

from app.config import get_settings


MIGRATION_DIRECTORY = Path(__file__).resolve().parent.parent / "migrations"


def connect_with_retry(attempts: int = 30) -> psycopg.Connection:
    settings = get_settings()
    for attempt in range(1, attempts + 1):
        try:
            return psycopg.connect(settings.database_url)
        except psycopg.OperationalError:
            if attempt == attempts:
                raise
            time.sleep(2)
    raise RuntimeError("database connection retry loop ended unexpectedly")


def apply_migrations() -> None:
    with connect_with_retry() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version text PRIMARY KEY,
                applied_at timestamptz NOT NULL DEFAULT now()
            )
            """
        )

        applied = {
            row[0]
            for row in connection.execute("SELECT version FROM schema_migrations").fetchall()
        }

        for migration_path in sorted(MIGRATION_DIRECTORY.glob("*.sql")):
            version = migration_path.name
            if version in applied:
                continue
            sql = migration_path.read_text(encoding="utf-8")
            with connection.transaction():
                connection.execute(sql)
                connection.execute(
                    "INSERT INTO schema_migrations (version) VALUES (%s)",
                    (version,),
                )
            print(f"applied migration {version}", flush=True)


if __name__ == "__main__":
    apply_migrations()
