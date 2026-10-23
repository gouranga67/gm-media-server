#!/usr/bin/env python3
"""Exercise project creation and an interrupted/resumed tus upload over loopback."""

import base64
import hashlib
import http.client
import json
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any


BASE_URL = "http://127.0.0.1:3000"
TEST_MEDIA = b"\x00\x00\x00\x18ftypmp42gm-media-phase-3-upload-check"


def json_request(path: str, method: str = "GET", payload: dict[str, Any] | None = None) -> Any:
    data = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.load(response)


def tus_metadata(values: dict[str, str]) -> str:
    return ",".join(
        f"{key} {base64.b64encode(value.encode()).decode()}" for key, value in values.items()
    )


def connection_for(url: str) -> tuple[http.client.HTTPConnection, str]:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}:
        raise RuntimeError(f"unexpected upload location: {url}")
    return http.client.HTTPConnection(parsed.hostname, parsed.port or 80, timeout=10), parsed.path


def patch_chunk(location: str, offset: int, chunk: bytes) -> int:
    connection, path = connection_for(location)
    connection.request(
        "PATCH",
        path,
        body=chunk,
        headers={
            "Content-Type": "application/offset+octet-stream",
            "Content-Length": str(len(chunk)),
            "Tus-Resumable": "1.0.0",
            "Upload-Offset": str(offset),
        },
    )
    response = connection.getresponse()
    response.read()
    if response.status != 204:
        raise RuntimeError(f"upload PATCH failed with HTTP {response.status}")
    next_offset = int(response.getheader("Upload-Offset", "-1"))
    connection.close()
    return next_offset


def read_offset(location: str) -> int:
    connection, path = connection_for(location)
    connection.request("HEAD", path, headers={"Tus-Resumable": "1.0.0"})
    response = connection.getresponse()
    response.read()
    if response.status != 200:
        raise RuntimeError(f"upload HEAD failed with HTTP {response.status}")
    offset = int(response.getheader("Upload-Offset", "-1"))
    connection.close()
    return offset


def main() -> None:
    stamp = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    project_payload = {
        "id": str(uuid.uuid4()),
        "name": f"Phase 3 verification — {stamp}",
        "brief": "Automated resumable-upload verification; safe to delete later.",
        "privacy_mode": "local_only",
        "ai_copy_allowed": False,
    }
    project = json_request("/api/media/projects", "POST", project_payload)
    retried_project = json_request("/api/media/projects", "POST", project_payload)
    if retried_project["id"] != project["id"]:
        raise RuntimeError("project retry created a duplicate record")

    job_payload = {"id": str(uuid.uuid4()), "recipe": "talking_head"}
    job_path = f"/api/media/projects/{project['id']}/jobs"
    job = json_request(job_path, "POST", job_payload)
    retried_job = json_request(job_path, "POST", job_payload)
    if retried_job["id"] != job["id"]:
        raise RuntimeError("job retry created a duplicate record")

    asset_payload = {
        "id": str(uuid.uuid4()),
        "source_name": "phase-3-check.mp4",
        "mime_type": "video/mp4",
        "byte_size": len(TEST_MEDIA),
    }
    asset_path = f"/api/media/projects/{project['id']}/assets"
    asset = json_request(asset_path, "POST", asset_payload)
    retried_asset = json_request(asset_path, "POST", asset_payload)
    if retried_asset["id"] != asset["id"]:
        raise RuntimeError("asset retry created a duplicate record")

    request = urllib.request.Request(
        f"{BASE_URL}/files",
        data=b"",
        method="POST",
        headers={
            "Tus-Resumable": "1.0.0",
            "Upload-Length": str(len(TEST_MEDIA)),
            "Upload-Metadata": tus_metadata(
                {
                    "assetId": asset["id"],
                    "projectId": project["id"],
                    "filename": "phase-3-check.mp4",
                    "filetype": "video/mp4",
                }
            ),
        },
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        if response.status != 201:
            raise RuntimeError(f"upload creation failed with HTTP {response.status}")
        location = urllib.parse.urljoin(BASE_URL, response.headers["Location"])

    split = len(TEST_MEDIA) // 2
    offset = patch_chunk(location, 0, TEST_MEDIA[:split])
    if read_offset(location) != offset:
        raise RuntimeError("resumed client observed the wrong upload offset")
    final_offset = patch_chunk(location, offset, TEST_MEDIA[offset:])
    if final_offset != len(TEST_MEDIA):
        raise RuntimeError("upload did not reach its expected length")

    expected_hash = hashlib.sha256(TEST_MEDIA).hexdigest()
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        asset = json_request(f"/api/media/assets/{asset['id']}")
        if asset["status"] == "ready":
            if asset["sha256"] != expected_hash:
                raise RuntimeError("registered SHA-256 does not match the uploaded bytes")
            print(
                json.dumps(
                    {
                        "status": "passed",
                        "project_id": project["id"],
                        "job_id": job["id"],
                        "asset_id": asset["id"],
                        "sha256": asset["sha256"],
                    },
                    indent=2,
                )
            )
            return
        if asset["status"] == "failed":
            raise RuntimeError("server failed while finalizing the uploaded asset")
        time.sleep(1)

    raise RuntimeError(f"asset remained in {asset['status']} state after 30 seconds")


if __name__ == "__main__":
    try:
        main()
    except urllib.error.HTTPError as error:
        body = error.read().decode(errors="replace")
        raise SystemExit(f"HTTP {error.code}: {body}") from error
