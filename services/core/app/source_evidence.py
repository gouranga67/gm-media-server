"""Shared evidence vocabulary. Recognition, mentions and human facts stay distinct."""
from __future__ import annotations

import csv
import hashlib
import io
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

EVIDENCE_VERSION = "1.0"


def image_ocr(path: Path, timeout: int = 25) -> dict[str, Any]:
    if not shutil.which("tesseract"):
        return {"status": "unavailable", "method": "tesseract", "lines": []}
    try:
        result = subprocess.run(["tesseract", str(path), "stdout", "-l", "eng", "tsv"],
                                stdin=subprocess.DEVNULL, capture_output=True, text=True,
                                timeout=timeout, check=True)
        if len(result.stdout) > 1_000_000:
            raise ValueError("OCR response exceeds its bound")
        groups: dict[tuple[str, ...], list[dict[str, Any]]] = {}
        image_width = image_height = 0
        for row in csv.DictReader(io.StringIO(result.stdout), delimiter="\t"):
            if row.get("level") == "1":
                image_width, image_height = int(row["width"]), int(row["height"])
            if row.get("level") != "5" or not row.get("text", "").strip():
                continue
            confidence = float(row["conf"])
            if confidence < 60:
                continue
            key = tuple(row[field] for field in ("page_num", "block_num", "par_num", "line_num"))
            groups.setdefault(key, []).append({"text": row["text"].strip(), "confidence": confidence,
                **{field: int(row[field]) for field in ("left", "top", "width", "height")}})
        lines = []
        for words in list(groups.values())[:80]:
            left, top = min(w["left"] for w in words), min(w["top"] for w in words)
            right = max(w["left"] + w["width"] for w in words)
            bottom = max(w["top"] + w["height"] for w in words)
            line_text = " ".join(w["text"] for w in words)[:500]
            lines.append({"id": hashlib.sha256(f"{left}:{top}:{line_text}".encode()).hexdigest()[:16],
                          "text": line_text,
                          "confidence": round(sum(w["confidence"] for w in words) / len(words), 1),
                          "box": [left, top, right-left, bottom-top],
                          "normalized_box": [round(left / image_width, 5), round(top / image_height, 5),
                              round((right-left) / image_width, 5), round((bottom-top) / image_height, 5)]
                              if image_width and image_height else None})
        return {"status": "ready", "method": "tesseract-eng", "image_key": path.name, "lines": lines,
                "image_width": image_width, "image_height": image_height,
                "note": "Recognized text, not verified product claims or a complete visual description."}
    except (OSError, ValueError, subprocess.SubprocessError):
        return {"status": "failed", "method": "tesseract-eng", "lines": []}


def complete_thoughts(segments: list[dict[str, Any]], limit: int = 24) -> list[dict[str, Any]]:
    if limit <= 0:
        return []
    thoughts = []
    for segment in segments:
        words = segment.get("words") or []
        if not words:
            words = [{"start": segment.get("start", 0), "end": segment.get("end", 0), "text": segment.get("text", "")}]
        group: list[dict[str, Any]] = []
        for word in words:
            group.append(word)
            text = " ".join(str(w.get("text", "")).strip() for w in group).strip()
            if re.search(r"[.!?][\"']?$", str(word.get("text", "")).strip()):
                _append_thought(thoughts, group, text, True)
                group = []
        if group:
            _append_thought(thoughts, group, " ".join(str(w.get("text", "")).strip() for w in group), False)
    if len(thoughts) <= limit:
        return thoughts
    if limit == 1:
        return thoughts[:1]
    # Explicitly balanced, including the ending, rather than a prefix cutoff.
    return [thoughts[round(n * (len(thoughts)-1)/(limit-1))] for n in range(limit)]


def _append_thought(items: list[dict], words: list[dict], text: str, complete: bool) -> None:
    start, end = float(words[0].get("start", 0)), float(words[-1].get("end", 0))
    if text.strip() and 0 <= start < end:
        key = hashlib.sha256(f"{start}:{end}:{text}".encode()).hexdigest()[:16]
        items.append({"id": key, "start": start, "end": end, "text": text.strip()[:1200],
                      "punctuated_end": complete, "kind": "recognized_speech"})


def shared_evidence(asset: dict, metadata: dict, manifest: dict,
                    transcript: list[dict], products: list[dict] | None = None,
                    annotations: list[dict] | None = None) -> dict[str, Any]:
    ocr = manifest.get("derived", {}).get("ocr") or {}
    text = " ".join([*(str(s.get("text", "")) for s in transcript),
                     *(str(l.get("text", "")) for l in ocr.get("lines", [])),
                     str(metadata.get("display_name") or ""), str(metadata.get("notes") or "")]).casefold()
    mentioned = []
    for product in products or []:
        names = [product["name"], *(product.get("aliases") or [])]
        if any(re.search(r"(?<!\w)" + re.escape(name.casefold()) + r"(?!\w)", text) for name in names if name.strip()):
            mentioned.append({"id": str(product["id"]), "name": product["name"],
                              "evidence": "text_mention", "visual_identity_verified": False})
    return {"version": EVIDENCE_VERSION, "source_hash": asset.get("sha256"),
            "library": {"name": str(metadata.get("display_name") or asset.get("source_name") or "")[:255],
                        "role": metadata.get("media_role") or "auto", "category": metadata.get("media_category") or "auto",
                        "tags": (metadata.get("tags") or [])[:25], "notes": str(metadata.get("notes") or "")[:1200]},
            "thoughts": complete_thoughts(transcript),
            "recognized_text": ocr.get("lines", [])[:40], "ocr_status": ocr.get("status", "not_analyzed"),
            "mentioned_products": mentioned[:12],
            "user_ranges": [{k: (str(v) if k == "id" else v) for k,v in a.items()
                             if k in {"id", "start_seconds", "end_seconds", "role", "note"}}
                            for a in (annotations or [])[:40]],
            "note": "Labels are user metadata; ASR/OCR/mentions can be wrong. Ranges are human annotations. Preserve product referents."}
