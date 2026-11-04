"""Build-time fetch for the experimental, manually invoked person-cutout lab.

Weights and their Apache-2.0 notice are pinned independently. Runtime inference
does not download models. No source media is sent to this download endpoint.
"""
import hashlib
import os
from pathlib import Path
import urllib.request

REVISION = "48b10fa505aeb51fbd127fc60a5c660040e823b7"
FILENAME = "human_segmentation_pphumanseg_2023mar.onnx"
SIZE = 6163938
SHA256 = "552d8a984054e59b5d773d24b9b12022b22046ceb2bbc4c9aaeaceb36a9ddf24"
LICENSE_SHA256 = "d9cf3b547fa4232fb9285f2db52e909f10f00781aaf64a6d0bb90c55149f1363"


def install(directory=Path("/models")):
    notice = Path(__file__).with_name("PPHumanSeg-LICENSE").read_bytes()
    if hashlib.sha256(notice).hexdigest() != LICENSE_SHA256:
        raise ValueError("cutout model license differs from its pinned notice")
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / FILENAME
    if target.exists() and target.stat().st_size == SIZE and hashlib.sha256(target.read_bytes()).hexdigest() == SHA256:
        (directory / "PPHumanSeg-LICENSE").write_bytes(notice)
        return
    url = f"https://media.githubusercontent.com/media/opencv/opencv_zoo/{REVISION}/models/human_segmentation_pphumanseg/{FILENAME}"
    with urllib.request.urlopen(url, timeout=60) as response:
        data = response.read(SIZE + 1)
    if len(data) != SIZE or hashlib.sha256(data).hexdigest() != SHA256:
        raise ValueError("cutout model differs from its pinned weights")
    temporary = target.with_suffix(f".{os.getpid()}.tmp")
    try:
        temporary.write_bytes(data)
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    (directory / "PPHumanSeg-LICENSE").write_bytes(notice)


if __name__ == "__main__":
    install()
