from dataclasses import dataclass
from pathlib import PurePath
from typing import Any
from uuid import UUID


@dataclass(frozen=True)
class UploadHookFacts:
    event_type: str
    asset_id: UUID
    project_id: UUID
    upload_id: str
    storage_key: str
    byte_size: int
    mime_type: str


def parse_upload_hook(payload: dict[str, Any]) -> UploadHookFacts:
    event_type = str(payload.get("Type", ""))
    event = payload.get("Event")
    if not isinstance(event, dict):
        raise ValueError("hook event is missing")

    upload = event.get("Upload")
    if not isinstance(upload, dict):
        raise ValueError("hook upload is missing")

    metadata = upload.get("MetaData")
    if not isinstance(metadata, dict):
        raise ValueError("upload metadata is missing")

    asset_id = UUID(str(metadata.get("assetId", "")))
    project_id = UUID(str(metadata.get("projectId", "")))
    upload_id = str(upload.get("ID", ""))
    if not upload_id and event_type == "pre-create":
        upload_id = str(asset_id)
    if not upload_id:
        raise ValueError("upload ID is missing")

    storage = upload.get("Storage")
    if not isinstance(storage, dict):
        storage = {}
    storage_key = str(storage.get("Key") or "")
    if not storage_key and storage.get("Path"):
        storage_key = PurePath(str(storage["Path"])).name
    if not storage_key and event_type != "pre-create":
        storage_key = upload_id

    byte_size = int(upload.get("Size", 0))
    if byte_size < 0:
        raise ValueError("upload size cannot be negative")
    mime_type = str(metadata.get("filetype") or metadata.get("mimeType") or "").lower()

    return UploadHookFacts(
        event_type=event_type,
        asset_id=asset_id,
        project_id=project_id,
        upload_id=upload_id,
        storage_key=storage_key,
        byte_size=byte_size,
        mime_type=mime_type,
    )
