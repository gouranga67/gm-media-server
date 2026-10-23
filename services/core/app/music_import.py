import argparse
import hashlib
import json
import os
import shutil
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

from psycopg.types.json import Jsonb

from app.config import get_settings
from app.database import connection
from app.media_analysis import READ_ONLY_MODE, ensure_capacity, probe_media


ALLOWED_EXTENSIONS = {".aac", ".flac", ".m4a", ".mp3", ".ogg", ".wav"}
ALLOWED_PLATFORMS = {"all_social", "facebook", "instagram", "linkedin", "tiktok", "youtube"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _https_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc:
        raise argparse.ArgumentTypeError("license source must be an https URL")
    return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Import one explicitly licensed, non-synthetic music track into GM Studio."
    )
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--artist", default="")
    parser.add_argument("--mood", required=True)
    parser.add_argument("--energy", choices=("low", "medium", "high"), required=True)
    parser.add_argument("--bpm", type=float)
    parser.add_argument("--license-name", required=True)
    parser.add_argument("--license-source-url", type=_https_url, required=True)
    parser.add_argument(
        "--license-proof",
        required=True,
        help="Receipt, licence file reference, or other evidence retained by the operator.",
    )
    parser.add_argument("--attribution", default="")
    parser.add_argument(
        "--platform",
        action="append",
        choices=sorted(ALLOWED_PLATFORMS),
        required=True,
        dest="platforms",
    )
    parser.add_argument(
        "--commercial-use-confirmed",
        action="store_true",
        help="Confirm that the recorded licence permits the intended commercial use.",
    )
    return parser


def main() -> None:
    arguments = _parser().parse_args()
    if not arguments.commercial_use_confirmed:
        raise SystemExit("refusing import without --commercial-use-confirmed")
    if not arguments.title.strip() or not arguments.mood.strip() or not arguments.license_name.strip():
        raise SystemExit("title, mood, and licence name cannot be blank")
    source = arguments.source.resolve(strict=True)
    if not source.is_file() or source.suffix.lower() not in ALLOWED_EXTENSIONS:
        raise SystemExit("source must be a supported audio file")
    if arguments.bpm is not None and not 30 <= arguments.bpm <= 240:
        raise SystemExit("BPM must be between 30 and 240")

    settings = get_settings()
    ensure_capacity(settings)
    probe = probe_media(source, settings.analysis_command_timeout_seconds)
    if not any(stream.get("type") == "audio" for stream in probe.get("streams", [])):
        raise SystemExit("the imported file does not contain an audio stream")
    duration = float(probe.get("format", {}).get("duration_seconds") or 0)
    if duration <= 0:
        raise SystemExit("the imported track has no measurable duration")
    digest = _sha256(source)
    with connection() as database:
        existing = database.execute(
            "SELECT id, title FROM music_tracks WHERE sha256 = %s",
            (digest,),
        ).fetchone()
    if existing is not None:
        print(json.dumps({"status": "already_imported", **existing}, default=str, indent=2))
        return

    track_id = uuid4()
    relative = Path("music") / str(track_id) / f"source{source.suffix.lower()}"
    destination = settings.media_root / relative
    destination.parent.mkdir(parents=True, exist_ok=False)
    temporary = destination.with_name(f".{destination.name}.part")
    try:
        with source.open("rb") as input_file, temporary.open("xb") as output_file:
            shutil.copyfileobj(input_file, output_file, length=1024 * 1024)
            output_file.flush()
            os.fsync(output_file.fileno())
        temporary.chmod(READ_ONLY_MODE)
        os.replace(temporary, destination)
        with connection() as database:
            row = database.execute(
                """
                INSERT INTO music_tracks (
                    id, title, artist, storage_key, sha256, duration_seconds,
                    mood, energy, bpm, license_name, license_source_url,
                    license_proof, commercial_use, synthetic_media,
                    allowed_platforms, attribution
                ) VALUES (
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, true, false, %s, %s
                )
                RETURNING id, title, artist, duration_seconds, mood, energy,
                          license_name, allowed_platforms, attribution
                """,
                (
                    track_id,
                    arguments.title.strip(),
                    arguments.artist.strip(),
                    relative.as_posix(),
                    digest,
                    duration,
                    arguments.mood.strip(),
                    arguments.energy,
                    arguments.bpm,
                    arguments.license_name.strip(),
                    arguments.license_source_url,
                    arguments.license_proof.strip(),
                    Jsonb(sorted(set(arguments.platforms))),
                    arguments.attribution.strip(),
                ),
            ).fetchone()
        print(json.dumps({"status": "imported", **row}, default=str, indent=2))
    except Exception:
        temporary.unlink(missing_ok=True)
        destination.unlink(missing_ok=True)
        try:
            destination.parent.rmdir()
        except OSError:
            pass
        raise


if __name__ == "__main__":
    main()
