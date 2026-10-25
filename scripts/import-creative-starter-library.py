#!/usr/bin/env python3
"""Download and import the pinned, rights-reviewed starter catalogue over the private API."""

import argparse
import hashlib
import io
import json
import mimetypes
import os
from pathlib import Path
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile


ROOT = Path(__file__).resolve().parents[1]
MAX_DOWNLOAD_BYTES = 110 * 1024 * 1024


def default_base_url():
    if os.environ.get("GM_MEDIA_URL"):
        return os.environ["GM_MEDIA_URL"].rstrip("/")
    values = {}
    path = ROOT / ".env"
    if path.exists():
        for line in path.read_text().splitlines():
            if line.strip() and not line.lstrip().startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip().strip('"').strip("'")
    return values.get("APP_ORIGIN", "http://127.0.0.1:3000").rstrip("/") + "/api/media"


def checked_bytes(data, expected):
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError("download checksum differs from the reviewed starter catalogue")
    return data


def asset_bytes(item, cache):
    url = item["download_url"]
    if urllib.parse.urlparse(url).scheme != "https":
        raise ValueError("starter downloads require HTTPS")
    path = cache / hashlib.sha256(url.encode()).hexdigest()
    if not path.exists():
        request = urllib.request.Request(url, headers={"User-Agent": "GM-Studio-starter-library/1.0"})
        with urllib.request.urlopen(request, timeout=120) as response:
            data = response.read(MAX_DOWNLOAD_BYTES + 1)
        if len(data) > MAX_DOWNLOAD_BYTES:
            raise ValueError("starter download exceeds its size limit")
        checked_bytes(data, item["download_sha256"])
        temporary = path.with_suffix(".part")
        temporary.write_bytes(data)
        temporary.replace(path)
    data = checked_bytes(path.read_bytes(), item["download_sha256"])
    if item.get("archive_member"):
        # Read one reviewed member; never extract arbitrary archive paths.
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            member = archive.getinfo(item["archive_member"])
            if member.file_size > MAX_DOWNLOAD_BYTES:
                raise ValueError("archive member exceeds its size limit")
            data = archive.read(member)
    return checked_bytes(data, item["sha256"])


def import_asset(base_url, item, data):
    metadata = {key: item[key] for key in (
        "kind", "filename", "title", "creator", "purpose", "tags", "license_name",
        "license_source_url", "license_proof", "attribution", "mood", "energy",
    ) if key in item}
    metadata.update(allowed_platforms="all_social", commercial_use_confirmed="true")
    request = urllib.request.Request(
        base_url + "/creative-assets/import?" + urllib.parse.urlencode(metadata),
        data=data, method="POST",
        headers={"Content-Type": mimetypes.guess_type(item["filename"])[0] or "application/octet-stream"},
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            result = json.load(response)
            return "imported", result["asset"]["id"]
    except urllib.error.HTTPError as error:
        payload = error.read(4096).decode(errors="replace")
        if error.code == 409 and "this exact creative file is already in the library" in payload:
            return "already_imported", None
        raise RuntimeError(f"import failed ({error.code}): {payload}") from error


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=default_base_url())
    parser.add_argument("--cache-dir", type=Path, default=Path(tempfile.gettempdir()) / "gm-studio-starter-library")
    parser.add_argument("--download-only", action="store_true", help="Verify downloads without changing the server")
    args = parser.parse_args()
    args.cache_dir.mkdir(parents=True, exist_ok=True)
    catalogue = json.loads((ROOT / "docs/creative-starter-library.json").read_text())
    counts = {"imported": 0, "already_imported": 0, "downloaded": 0}
    for item in catalogue["assets"]:
        data = asset_bytes(item, args.cache_dir)
        if args.download_only:
            state = "downloaded"
        else:
            state, _ = import_asset(args.base_url.rstrip("/"), item, data)
        counts[state] += 1
        print(f"{state}: {item['title']}", flush=True)
    print(json.dumps({"status": "passed", **counts, "model_calls": 0}, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, zipfile.BadZipFile) as error:
        print(f"Starter library import stopped: {error}. Rerunning safely skips completed imports.", file=sys.stderr)
        raise SystemExit(1)
