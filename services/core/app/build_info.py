"""Small shared build identity reader; never returns deployment configuration."""
import json
import os


def deployed_build_id(settings):
    try:
        path = settings.appliance_status_path.parent / "build.json"
        if path.stat().st_size < 4096:
            return str(json.loads(path.read_text()).get("commit") or "unknown")[:64]
    except (OSError, ValueError, AttributeError):
        pass
    return os.environ.get("GM_BUILD_ID", "development")
