"""Compact local discovery inventory and source-backed concept validation."""
import json
import math
import re
from collections import defaultdict, deque
from typing import Any
from uuid import UUID, uuid5

from app.concept_schemas import ConceptProposals, ConceptRequestCreate
from app.blooper_detection import find_blooper_evidence
from app.take_quality import production_chatter_reason

MAX_SOURCES = 60
MAX_INVENTORY_CHARACTERS = 36_000


def _sample(items: list[Any], limit: int) -> list[Any]:
    if not items:
        return []
    # Progressive coverage: a tight global budget still sees beginnings and
    # endings before filling in the middle of each long recording.
    target = min(limit, len(items))
    indices = [0]
    if target > 1:
        indices.append(len(items) - 1)
    intervals = deque([(0, len(items) - 1)])
    while len(indices) < target and intervals:
        left, right = intervals.popleft()
        middle = (left + right) // 2
        if middle not in indices:
            indices.append(middle)
        if middle - left > 1:
            intervals.append((left, middle))
        if right - middle > 1:
            intervals.append((middle, right))
    return [items[index] for index in indices]


def balanced_sources(rows: list[dict], focus: str, limit: int = MAX_SOURCES) -> list[dict]:
    """Prefer explicit focus; otherwise spread the bounded view across upload groups."""
    words = set(re.findall(r"[a-z0-9]{3,}", focus.lower())) - {"the", "and", "from", "with", "reel", "make", "video", "about"}
    def score(row):
        text = " ".join(str(row.get(key) or "") for key in ("display_name", "source_name", "project_name", "notes", "tags")).lower()
        return sum(word in text for word in words), bool(row.get("favorite"))
    unique = {}
    # SQL presents a reviewed canonical first within each verified hash group.
    for row in rows:
        unique.setdefault(row["sha256"], row)
    groups = defaultdict(deque)
    for row in sorted(unique.values(), key=score, reverse=True):
        groups[str(row["project_id"])].append(row)
    ranked_groups = sorted(groups.values(), key=lambda group: score(group[0]), reverse=True)
    chosen = []
    while ranked_groups and len(chosen) < limit:
        next_groups = []
        for group in ranked_groups:
            chosen.append(group.popleft())
            if group:
                next_groups.append(group)
            if len(chosen) == limit:
                break
        ranked_groups = next_groups
    return chosen


def public_inventory(inventory: dict) -> dict:
    assets = []
    for source in inventory["assets"]:
        assets.append({"asset_id": source["asset_id"], "name": source["library_name"][:96],
                       "project": source["project_name"][:48], "mime_type": source["mime_type"],
                       "role": source["library_role"], "notes": source["notes"][:64],
                       "tags": [tag[:32] for tag in source["tags"][:5]], "used_in_jobs": source["job_uses"],
                       "category": source.get("library_category", "auto"),
                       "recognized_text": source.get("recognized_text", [])})
    return {"focus": inventory.get("focus", ""), "audience": inventory.get("audience", ""), "reel_kind": inventory.get("reel_kind", "story"),
            "assets": assets, "evidence": inventory["evidence"], "recent_concepts": inventory.get("recent_concepts", [])}


def compact_inventory(rows: list[dict], segments: list[dict], payload: ConceptRequestCreate, recent: list[dict] | None = None) -> dict:
    sources = []
    by_asset = defaultdict(list)
    bloopers = payload.reel_kind == "bloopers"
    clues = find_blooper_evidence(segments) if bloopers else {}
    for segment in segments:
        text = " ".join(str(segment.get("text") or "").split())
        start, end = float(segment["start_seconds"]), float(segment["end_seconds"])
        if not math.isfinite(start + end) or start < 0 or len(text) > 900 or end - start <= 0 or end - start > 25:
            continue
        if bloopers and int(segment["id"]) not in clues:
            continue
        if not bloopers and (len(text) < 12 or end - start < 0.5 or production_chatter_reason(text)):
            continue
        by_asset[str(segment["asset_id"])].append({
            "evidence_id": int(segment["id"]), "asset_id": str(segment["asset_id"]),
            "start": start, "end": end, "text": text, **clues.get(int(segment["id"]), {}),
        })
    for row in rows:
        manifest = row.get("manifest") or {}
        derived = manifest.get("derived") or {}
        sources.append({"asset_id": str(row["id"]), "sha256": row["sha256"],
                        "source_name": row["source_name"], "library_name": row["display_name"],
                        "project_name": row["project_name"], "mime_type": row["mime_type"],
                        "library_role": row["media_role"], "notes": str(row.get("notes") or "")[:400],
                        "library_category": row.get("media_category") or "auto",
                        "recognized_text": [line["text"] for line in (derived.get("ocr") or {}).get("lines", [])[:12]],
                        "tags": row.get("tags") or [], "job_uses": int(row.get("job_uses") or 0),
                        "_preview_key": derived.get("preview") or derived.get("thumbnail"),
                        "_contact_sheet_key": derived.get("contact_sheet"),
                        "has_video": str(row["mime_type"]).startswith("video/"),
                        "_visual_available": bool(derived.get("preview") or derived.get("thumbnail") or derived.get("contact_sheet")),
                        "_storage_key": row.get("storage_key")})
    inventory = {"focus": payload.focus, "audience": payload.audience, "reel_kind": payload.reel_kind,
                 "assets": sources, "evidence": [], "recent_concepts": (recent or [])[:6]}
    used = len(json.dumps(public_inventory(inventory), ensure_ascii=False))
    eligible = [source for source in sources if source["has_video"] and source["library_role"] != "broll"]
    queues = []
    for source in eligible:
        passages = by_asset[source["asset_id"]]
        if not passages:
            continue
        # Retain candidate anchors before contextual passages under a tight budget.
        sampled = (_sample([item for item in passages if item.get("blooper_candidate")], 8)
                   + _sample([item for item in passages if not item.get("blooper_candidate")], 4)) if bloopers else _sample(passages, 12)
        queues.append(deque(sampled))
    # Round-robin means a long first recording cannot crowd every other source out.
    while queues:
        next_queues = []
        for queue in queues:
            segment = queue.popleft()
            size = len(json.dumps(segment, ensure_ascii=False)) + 2
            if used + size <= MAX_INVENTORY_CHARACTERS:
                inventory["evidence"].append(segment); used += size
            if queue:
                next_queues.append(queue)
        queues = next_queues
    return inventory


def load_inventory(database: Any, payload: ConceptRequestCreate) -> tuple[dict, dict]:
    where = "AND EXISTS (SELECT 1 FROM library_collection_assets m WHERE m.asset_id=a.id AND m.collection_id=%s)" if payload.collection_id else ""
    rows = database.execute(f"""
        SELECT a.id, a.project_id, a.source_name, a.mime_type, a.sha256, a.storage_key,
               p.name AS project_name, i.manifest,
               COALESCE(m.display_name,a.source_name) AS display_name,
               COALESCE(m.media_role,'auto') AS media_role, COALESCE(m.notes,'') AS notes,
               COALESCE(m.media_category,'auto') AS media_category,
               COALESCE(m.tags,ARRAY[]::text[]) AS tags, COALESCE(m.favorite,false) AS favorite,
               (SELECT count(*) FROM job_assets ja WHERE ja.asset_id=a.id) AS job_uses
        FROM assets a JOIN projects p ON p.id=a.project_id
        JOIN asset_ingests i ON i.asset_id=a.id AND i.status='ready'
        JOIN asset_catalogs c ON c.asset_id=a.id AND c.status='ready'
        LEFT JOIN asset_library_metadata m ON m.asset_id=a.id
        LEFT JOIN asset_duplicate_reviews d ON d.sha256=a.sha256
        WHERE a.status='ready' AND a.library_status='active' AND a.sha256 IS NOT NULL
          AND (a.mime_type LIKE 'video/%%' OR a.mime_type LIKE 'image/%%') {where}
        ORDER BY (a.id=d.canonical_asset_id) DESC NULLS LAST, a.created_at DESC, a.id
    """, (payload.collection_id,) if payload.collection_id else ()).fetchall()
    chosen = balanced_sources(list(rows), payload.focus)
    if not chosen:
        return {"assets": [], "evidence": []}, {"unique_sources_available": 0, "sources_considered": 0, "speech_passages": 0}
    segments = database.execute("""
        SELECT id, asset_id, start_seconds, end_seconds, text FROM asset_catalog_segments
        WHERE asset_id=ANY(%s) AND segment_kind='transcript'
        ORDER BY asset_id, start_seconds, segment_index
    """, ([row["id"] for row in chosen],)).fetchall()
    prior = database.execute("SELECT concepts FROM reel_concept_requests WHERE status='ready' AND reel_kind=%s AND (%s::uuid IS NULL OR collection_id=%s) ORDER BY created_at DESC LIMIT 3", (payload.reel_kind, payload.collection_id, payload.collection_id)).fetchall()
    recent = [{"title": option["title"][:100], "speech_evidence_ids": [beat["evidence_id"] for beat in option["script"][:10]]}
              for row in prior for option in row["concepts"]][:6]
    inventory = compact_inventory(chosen, list(segments), payload, recent=recent)
    coverage = {"unique_sources_available": len({row["sha256"] for row in rows}),
                "sources_considered": len(chosen), "speech_passages": len(inventory["evidence"]),
                "inventory_character_limit": MAX_INVENTORY_CHARACTERS,
                "scope": "collection" if payload.collection_id else "library"}
    if payload.reel_kind == "bloopers":
        coverage["possible_blooper_passages"] = sum(bool(item.get("blooper_candidate")) for item in inventory["evidence"])
    return inventory, coverage


def validate_concepts(document: dict, inventory: dict, request_id: UUID) -> list[dict]:
    proposals = ConceptProposals.model_validate(document)
    bloopers = inventory.get("reel_kind") == "bloopers"
    if not bloopers and not proposals.concepts:
        raise ValueError("no supported recorded story was proposed")
    evidence = {item["evidence_id"]: item for item in inventory["evidence"]}
    assets = {item["asset_id"]: item for item in inventory["assets"]}
    output, seen = [], set()
    for index, proposal in enumerate(proposals.concepts):
        ids = [beat.evidence_id for beat in proposal.script]
        if not bloopers and len(ids) < 2:
            raise ValueError("a story needs at least two recorded passages")
        if len(set(ids)) != len(ids) or any(id not in evidence for id in ids):
            raise ValueError("a concept cited unknown or repeated speech evidence")
        script = [{**evidence[beat.evidence_id], "role": beat.role,
                   "source_name": assets[evidence[beat.evidence_id]["asset_id"]]["source_name"],
                   "display_name": assets[evidence[beat.evidence_id]["asset_id"]]["library_name"]}
                  for beat in proposal.script]
        if bloopers and not any(beat.get("blooper_candidate") for beat in script):
            raise ValueError("a blooper concept must cite a possible outtake, not only clean setup")
        seconds = sum(beat["end"] - beat["start"] for beat in script)
        if not 5 <= seconds <= 55 or sum(len(beat["text"]) for beat in script) > 2200:
            raise ValueError("a concept's recorded script does not fit a short complete reel")
        if tuple(ids) in seen:
            raise ValueError("concept options must not repeat the same recorded script")
        seen.add(tuple(ids))
        visual_ids = [str(visual.asset_id) for visual in proposal.visuals]
        if len(set(visual_ids)) != len(visual_ids) or any(id not in assets for id in visual_ids):
            raise ValueError("a concept cited unknown or repeated visual footage")
        visuals = [{"asset_id": str(item.asset_id), "reason": item.reason,
                    "display_name": assets[str(item.asset_id)]["library_name"],
                    "mime_type": assets[str(item.asset_id)]["mime_type"]} for item in proposal.visuals]
        source_ids = list(dict.fromkeys([beat["asset_id"] for beat in script] + visual_ids))
        output.append({"id": str(uuid5(request_id, f"concept-{index}")), "title": proposal.title,
                       "angle": proposal.angle, "script": script, "visuals": visuals,
                       "asset_ids": source_ids, "estimated_seconds": round(seconds, 1),
                       "source_backed": True, "reel_kind": "bloopers" if bloopers else "story"})
    return output


def concept_brief(concept: dict) -> str:
    lines = [f"Selected library concept: {concept['title']}", concept["angle"],
             "Build this selected story using the recorded lines below in this order. Preserve complete words and meaning. Use the supporting pictures where relevant; never invent dialogue or transfer product claims."]
    if concept.get("reel_kind") == "bloopers":
        lines[2] = ("Make a bloopers reel from these recorded outtakes. Keep the mistake, enough setup to understand it, "
                    "and its real reaction or recovery. Keep the selected order and speech in sync; trim empty waiting. "
                    "Never invent a mistake, laughter, dialogue or a reaction. Clues are possible outtakes, not proven errors.")
    lines.extend(f"{beat['role']}: {beat['text']}" for beat in concept["script"])
    lines.extend(f"Supporting picture — {visual['display_name'][:80]}" for visual in concept["visuals"])
    result = "\n".join(lines)
    if len(result) > 4000:
        raise ValueError("selected concept exceeds the brief limit")
    return result
