from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path


COPY_BUFFER_BYTES = 4 * 1024 * 1024


@dataclass(frozen=True)
class HardlinkResult:
    bytes_reclaimed: int
    already_shared: bool
    device: int
    inode: int


def _sha256(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    byte_count = 0
    with path.open("rb") as source:
        while chunk := source.read(COPY_BUFFER_BYTES):
            digest.update(chunk)
            byte_count += len(chunk)
    return digest.hexdigest(), byte_count


def share_exact_duplicate_storage(
    canonical: Path,
    duplicate: Path,
    *,
    expected_sha256: str,
    expected_size: int,
) -> HardlinkResult:
    """Atomically replace an exact copy with a hard link to the canonical file.

    Both paths remain valid. The function verifies the bytes immediately before
    replacing anything and refuses cross-filesystem operations.
    """

    if expected_size <= 0:
        raise ValueError("expected size must be positive")
    if len(expected_sha256) != 64 or any(character not in "0123456789abcdef" for character in expected_sha256):
        raise ValueError("expected SHA-256 is invalid")
    if canonical.resolve() == duplicate.resolve():
        raise ValueError("canonical and duplicate paths must differ")
    if not canonical.is_file() or not duplicate.is_file():
        raise FileNotFoundError("canonical or duplicate original is missing")

    canonical_stat = canonical.stat()
    duplicate_stat = duplicate.stat()
    if canonical_stat.st_dev != duplicate_stat.st_dev:
        raise OSError("exact duplicates must be on the same filesystem")
    if canonical_stat.st_ino == duplicate_stat.st_ino:
        digest, byte_count = _sha256(canonical)
        if digest != expected_sha256 or byte_count != expected_size:
            raise ValueError("shared original no longer matches its verified checksum")
        return HardlinkResult(0, True, canonical_stat.st_dev, canonical_stat.st_ino)

    canonical_digest, canonical_size = _sha256(canonical)
    duplicate_digest, duplicate_size = _sha256(duplicate)
    if canonical_digest != expected_sha256 or duplicate_digest != expected_sha256:
        raise ValueError("an original no longer matches its verified checksum")
    if canonical_size != expected_size or duplicate_size != expected_size:
        raise ValueError("an original no longer matches its verified size")

    temporary = duplicate.with_name(f".{duplicate.name}.dedup-{os.getpid()}")
    temporary.unlink(missing_ok=True)
    try:
        os.link(canonical, temporary)
        os.replace(temporary, duplicate)
        directory_fd = os.open(duplicate.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        temporary.unlink(missing_ok=True)

    final_stat = duplicate.stat()
    if final_stat.st_dev != canonical_stat.st_dev or final_stat.st_ino != canonical_stat.st_ino:
        raise OSError("duplicate storage replacement did not produce a shared hard link")
    return HardlinkResult(expected_size, False, final_stat.st_dev, final_stat.st_ino)
