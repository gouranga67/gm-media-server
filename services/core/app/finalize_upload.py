import hashlib
import os
import shutil
from pathlib import Path


COPY_BUFFER_BYTES = 4 * 1024 * 1024


def upload_source_path(upload_root: Path, upload_id: str) -> Path:
    """Resolve a tus upload ID without allowing it to become a filesystem path."""

    if not upload_id or Path(upload_id).name != upload_id or "\\" in upload_id:
        raise ValueError("invalid upload ID")
    return upload_root / upload_id


def sha256_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    byte_count = 0
    with path.open("rb") as source:
        while chunk := source.read(COPY_BUFFER_BYTES):
            digest.update(chunk)
            byte_count += len(chunk)
    return digest.hexdigest(), byte_count


def finalize_original(source: Path, destination: Path, expected_size: int) -> str:
    """Copy a completed upload into its write-once original path and hash it."""

    if expected_size <= 0:
        raise ValueError("expected size must be positive")

    if destination.exists():
        digest, byte_count = sha256_file(destination)
        if byte_count != expected_size:
            raise ValueError("existing original size does not match the asset record")
        source.unlink(missing_ok=True)
        source.with_name(f"{source.name}.info").unlink(missing_ok=True)
        return digest

    if not source.is_file():
        raise FileNotFoundError(f"completed upload is missing: {source.name}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.part")
    temporary.unlink(missing_ok=True)

    digest = hashlib.sha256()
    byte_count = 0
    try:
        with source.open("rb") as input_file, temporary.open("xb") as output_file:
            while chunk := input_file.read(COPY_BUFFER_BYTES):
                digest.update(chunk)
                byte_count += len(chunk)
                if byte_count > expected_size:
                    raise ValueError("uploaded file is larger than the asset record")
                output_file.write(chunk)
            output_file.flush()
            os.fsync(output_file.fileno())

        if byte_count != expected_size:
            raise ValueError("uploaded file size does not match the asset record")

        temporary.chmod(0o440)
        os.replace(temporary, destination)
        directory_fd = os.open(destination.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise

    # The tus upload is now a redundant staging copy. It is safe to remove only
    # after the durable original has been fsynced and atomically installed.
    source.unlink(missing_ok=True)
    source.with_name(f"{source.name}.info").unlink(missing_ok=True)
    return digest.hexdigest()
