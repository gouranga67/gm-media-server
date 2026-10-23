import os

from app.config import get_settings


MEDIA_UID = 10001
MEDIA_GID = 10001
MEDIA_DIRECTORIES = (
    "originals",
    "proxies",
    "analysis",
    "previews",
    "exports",
    "templates",
    "quarantine",
)


def main() -> None:
    settings = get_settings()
    media_root = settings.media_root
    media_root.mkdir(parents=True, exist_ok=True)
    os.chown(media_root, MEDIA_UID, MEDIA_GID)
    for directory_name in MEDIA_DIRECTORIES:
        directory = media_root / directory_name
        directory.mkdir(parents=True, exist_ok=True)
        os.chown(directory, MEDIA_UID, MEDIA_GID)

    settings.upload_root.mkdir(parents=True, exist_ok=True)
    os.chown(settings.upload_root, MEDIA_UID, MEDIA_GID)

    auth_root = settings.chatgpt_credential_path.parent
    auth_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chown(auth_root, MEDIA_UID, MEDIA_GID)
    auth_root.chmod(0o700)


if __name__ == "__main__":
    main()
