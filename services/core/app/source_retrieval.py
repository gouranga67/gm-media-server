"""Bounded lexical retrieval over stored evidence; no recognition or model calls.

Matches indicate words/aliases, never verified pictured identity or a claim.
The same vocabulary ranks concept sources, recorded passages and preview panels.
"""
import re
import unicodedata
from dataclasses import dataclass


_STOP = set("a an the and or of to for from in on at by with about into as is are was were be been it its this that these those i me my we our you your they their them he she his her us can could would should will please make create new reel reels video videos edit editing footage clip clips concept concepts idea ideas use using want give show tell story stories interesting good best like some all any available library recorded based out come up surprise something things".split())
_STOP.update("have has had do does did not no existing through then than very most more less only also own another different possible need help know get got lets let take takes recording recordings".split())


def _words(text):
    return re.findall(r"[^\W_]+", unicodedata.normalize("NFKC", str(text or "")).casefold())


@dataclass(frozen=True)
class FocusQuery:
    terms: tuple[str, ...] = ()
    products: tuple[tuple[str, ...], ...] = ()

    @property
    def search_text(self):
        # Terms are normalized words, not user-supplied query operators.
        return " OR ".join(f'"{term}"' for term in self.terms)


def focus_query(text, products=()):
    normalized = " " + " ".join(_words(text)) + " "
    terms = list(dict.fromkeys(w for w in _words(text) if len(w) >= 3 and w not in _STOP))[:24]
    groups = []
    for product in list(products or [])[:100]:
        names = tuple(dict.fromkeys(" ".join(_words(name)) for name in
            [product.get("name", ""), *(product.get("aliases") or [])[:20]] if str(name).strip()))
        if any(name and f" {name} " in normalized for name in names):
            groups.append(names)
            terms.extend(w for name in names for w in name.split() if len(w) >= 3 and w not in _STOP)
        if len(groups) >= 8:
            break
    return FocusQuery(tuple(dict.fromkeys(terms))[:32], tuple(groups))


def match_score(text, query):
    if not query.terms:
        return 0
    words = _words(text)
    normalized = " " + " ".join(words) + " "
    return len(set(words).intersection(query.terms)) + 3 * sum(
        any(name and f" {name} " in normalized for name in group) for group in query.products)


def source_score(source, query, transcript_rank=0):
    if not query.terms:
        return 0
    evidence = source.get("source_evidence") or {}
    library = evidence.get("library") or {}
    metadata = " ".join(str(source.get(key) or library.get(alias) or "") for key, alias in (
        ("display_name", "name"), ("library_name", "name"), ("source_name", "name"),
        ("notes", "notes"), ("tags", "tags"), ("project_name", "project")))
    stored_ocr = (((source.get("manifest") or {}).get("derived") or {}).get("ocr") or {}).get("lines")
    ocr = source.get("recognized_text") or evidence.get("recognized_text") or stored_ocr or []
    if not isinstance(ocr, list):
        ocr = []
    recognized = " ".join(str(line.get("text", "") if isinstance(line, dict) else line)[:500] for line in ocr[:40])
    speech = max((match_score(segment.get("text", ""), query) for segment in (source.get("transcript_segments") or [])
                  if isinstance(segment, dict)), default=0)
    # Repeating a term many times cannot manufacture greater relevance.
    return match_score(metadata, query) + match_score(recognized, query) + max(speech, 2 if transcript_rank else 0)


def focused_passages(passages, query, fallback, limit=12):
    """Keep focused speech, close neighbours, and source orientation/endings."""
    matches = sorted(((match_score(p["text"], query), i, p) for i, p in enumerate(passages)),
                     key=lambda item: item[0], reverse=True)
    if not matches or not matches[0][0]:
        return fallback(passages, limit)
    selected, seen = [], set()
    def add(item):
        if item["evidence_id"] not in seen and len(selected) < limit:
            selected.append(item)
            seen.add(item["evidence_id"])
    for score, index, passage in matches[:2]:
        if not score:
            break
        add(passage)
        if index > 0 and 0 <= passage["start"] - passages[index - 1]["end"] <= 0.65:
            add(passages[index - 1])
        if index + 1 < len(passages) and 0 <= passages[index + 1]["start"] - passage["end"] <= 0.65:
            add(passages[index + 1])
    add(passages[0])
    add(passages[-1])
    for score, _, passage in matches:
        if score:
            add(passage)
    for passage in fallback(passages, limit):
        add(passage)
    return selected


# GIN-indexed, scoped to already-permitted active sources. Avoid annotations
# exclude ranking evidence as well as later selectable passages.
FOCUSED_TRANSCRIPT_SQL = """
WITH focus AS (SELECT websearch_to_tsquery('simple', %s) AS terms)
SELECT s.asset_id, max(ts_rank_cd(s.search_vector, focus.terms)) AS text_rank
FROM asset_catalog_segments s CROSS JOIN focus
WHERE s.asset_id=ANY(%s) AND s.segment_kind='transcript'
  AND s.search_vector @@ focus.terms
  AND NOT EXISTS (
    SELECT 1 FROM asset_range_annotations a
    WHERE a.asset_id=s.asset_id AND a.role='avoid'
      AND a.start_seconds < s.end_seconds AND a.end_seconds > s.start_seconds
  )
GROUP BY s.asset_id
"""
