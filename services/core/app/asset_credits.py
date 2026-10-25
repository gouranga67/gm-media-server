from pathlib import Path
from typing import Any


def delivery_asset_credits(manifest: dict[str, Any]) -> str:
    assets = list(manifest.get("creative_effects") or [])
    music = manifest.get("music")
    if isinstance(music, dict):
        assets.insert(0, music)
    lines = ["GM Studio — third-party asset credits", ""]
    seen = set()
    for item in assets:
        credit = (str(item.get("title") or "Library asset"),
                  str(item.get("license_name") or "See source"),
                  str(item.get("license_source_url") or ""),
                  str(item.get("attribution") or ""))
        if credit in seen:
            continue
        seen.add(credit)
        lines.extend([credit[0], "Licence: " + credit[1], "Source: " + credit[2], credit[3], ""])
    if any(str(item.get("license_name")) == "Apache-2.0" for item in assets):
        lines.extend(["Apache-2.0 licence text for Noto Emoji image assets:",
                      (Path(__file__).parent / "licenses" / "Apache-2.0.txt").read_text()])
    return "\n".join(lines)
