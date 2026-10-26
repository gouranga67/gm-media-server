"""A host-shared inference lock; visual service can lock its read-only mount."""
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator
import fcntl


@contextmanager
def inference_slot(media_root: Path) -> Iterator[None]:
    path = media_root / "inference.lock"
    # Existing developer fixtures need no GPU coordination. Production init
    # creates this inode before either service starts.
    if not path.exists():
        yield
        return
    with path.open("rb") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)
