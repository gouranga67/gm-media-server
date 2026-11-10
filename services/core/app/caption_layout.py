"""Local caption finishing. Never rewrite speech or infer a person's name."""

from functools import lru_cache
import re
from pathlib import Path

CAPTION_PRESENTATION_VERSION = "phrase_cards_v2"
CAPTION_MAX_WORDS = 7
CAPTION_MAX_CHARACTERS = 44
CAPTION_MAX_SECONDS = 2.6
_ENDING = re.compile(r'[.!?][\"\u201d\u2019\')\]]*$')
_UNITS = {"million", "billion", "thousand", "dollars", "percent", "%", "ml", "kg", "g", "litres", "liters", "seconds"}


def _quantity_break(left, right):
    return bool(re.search(r"\d[\d,.]*$", left) and right.lower().strip(".,!?") in _UNITS)


def aligned_caption_words(segment):
    """Recover punctuation/case only when every transcript token agrees.

    The segment and word transcript sometimes differ. In that case keep the
    aligned words verbatim rather than attach punctuation to the wrong word.
    """
    words = segment.get("words") or []
    tokens = str(segment.get("text") or "").split()
    normal = lambda text: re.sub(r"[^\w]", "", text.casefold())
    if len(tokens) == len(words) and all(isinstance(w, dict) and normal(t) == normal(str(w.get("text") or "")) for t, w in zip(tokens, words)):
        return [{**word, "text": token} for word, token in zip(words, tokens)]
    return words


def phrase_groups(words, protected_phrases=()):
    """Partition aligned words; prefer punctuation and avoid one-word tails.

    A small dynamic program keeps actual word times. A hard pause or sentence
    boundary cannot be crossed just to make two lines look more balanced.
    """
    words = sorted(words, key=lambda w: (w["start"], w["end"]))
    unique, seen = [], set()
    for word in words:
        key = (round(word["start"], 3), round(word["end"], 3), word["text"])
        if key not in seen:
            unique.append(word)
            seen.add(key)
    words = unique
    n = len(words)
    protected_breaks = set()
    normal = lambda value: re.sub(r"[^\w]", "", value.casefold())
    tokens = [normal(w['text']) for w in words]
    for phrase in protected_phrases:
        parts = [normal(w) for w in phrase.split()]
        for i in range(n-len(parts)+1) if parts else ():
            if tokens[i:i+len(parts)] == parts:
                protected_breaks.update(range(i+1,i+len(parts)))
    costs, nexts = [float("inf")] * (n + 1), [n] * n
    costs[n] = 0
    for i in range(n - 1, -1, -1):
        for j in range(i + 1, min(n, i + CAPTION_MAX_WORDS) + 1):
            group = words[i:j]
            text = " ".join(w["text"] for w in group)
            if j > i + 1 and (len(text) > CAPTION_MAX_CHARACTERS or group[-1]["end"] - group[0]["start"] > CAPTION_MAX_SECONDS):
                break
            count = j - i
            boundary = j == n or _ENDING.search(group[-1]["text"])
            pause = words[j]["start"] - words[j-1]["end"] if j < n else 0
            # Prefer 4–6 words; sentence endings and real pauses take precedence.
            cost = 3 + (max(0, 4-count) ** 2) * 1.5 + max(0, count-6)
            if boundary or pause >= .38:
                cost *= .3
            if j < n and group[-1]["text"].lower().strip(",") in {"a", "an", "the", "to", "of", "for", "with", "in", "and"}:
                cost += 5
            if j < n and (_quantity_break(group[-1]['text'], words[j]['text']) or j in protected_breaks):
                cost += 100
            if cost + costs[j] < costs[i]:
                costs[i], nexts[i] = cost + costs[j], j
            if boundary or pause >= .38:
                break
    result, i = [], 0
    while i < n:
        j = nexts[i]
        result.append(words[i:j])
        i = j
    return result


def sentence_case_events(events, corrections=None):
    """Capitalise real sentence starts and 'I', never title-case every card.

    Existing mixed-case names/acronyms and explicit user replacement spellings
    are retained. Missing punctuation/names are not guessed locally.
    """
    def capitalise(match):
        word = match[0]
        return word[0].upper()+word[1:] if word[0].isalpha() and word.islower() else word

    result, beginning, previous_end = [], True, None
    protected = [str(c.get("replacement_text") or "") for c in corrections or []]
    for event in events:
        text = event["text"]
        if previous_end is not None and event["start"] - previous_end >= 1.2:
            beginning = True
        text = re.sub(r"\bi(?=\b|['\u2019](?:m|d|ll|ve))", "I", text)
        if beginning and not any(p and text.startswith(p) for p in protected):
            text = re.sub(r"[^\W_][\w'’]*", capitalise, text, count=1)
        text = re.sub(r'([.!?][\"\u201d\u2019\')\]]*\s+)([^\W_][\w\u2019\']*)',
                      lambda m: m[1]+re.sub(r".+",capitalise,m[2],count=1), text)
        result.append({**event, "text": text})
        beginning = bool(_ENDING.search(text))
        previous_end = event["end"]
    return result


def single_caption_lane(events):
    """Coalesce genuinely overlapping generated cues without dropping words.

    No approximate word timings are invented. Conflicting legacy cues keep
    their combined visible window; the editor can split it with user timing.
    """
    result = []
    for event in sorted(events, key=lambda e: (e["start"], e["end"])):
        event = dict(event)
        if result and event["start"] < result[-1]["end"] - .001:
            old = result[-1]
            left, right = old["text"].split(), event["text"].split()
            common = 0
            for length in range(1, min(len(left), len(right)) + 1):
                if [w.casefold() for w in left[-length:]] == [w.casefold() for w in right[:length]]:
                    common = length
            old["text"] = " ".join(left + right[common:])
            old["end"] = max(old["end"], event["end"])
        else:
            result.append(event)
    return result


@lru_cache(maxsize=64)
def measured_font(family, size, bold=True):
    from PIL import ImageFont
    stem = {"DejaVu Sans Mono": "DejaVuSansMono", "DejaVu Serif": "DejaVuSerif"}.get(family, "DejaVuSans")
    name = stem + ("-Bold" if bold else "") + ".ttf"
    for root in ("/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/dejavu"):
        path = Path(root) / name
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.truetype(name, size)


def text_width(text, family, size, bold=True):
    try:
        return measured_font(family, size, bold).getlength(text)
    except (ImportError, OSError):
        # API-only reconstruction may not include worker fonts/Pillow. The
        # worker image includes both; conservative fallback is deterministic.
        return sum(.35 if c in "il.,'! " else .95 if c in "MW@" else .65 for c in text) * size


def balanced_lines(text, family, size, max_width, *, bold=True):
    """At most two lines, using measured glyph widths, respecting manual breaks."""
    explicit = text.splitlines()
    if len(explicit) > 1:
        rows = explicit
    elif text_width(text, family, size, bold) <= max_width:
        rows = [text]
    else:
        words = text.split()
        candidates = []
        for i in range(1, len(words)):
            a, b = " ".join(words[:i]), " ".join(words[i:])
            wa, wb = text_width(a, family, size, bold), text_width(b, family, size, bold)
            # Penalise short hanging words, but never compromise the safe width.
            score = abs(wa-wb) + (size*2 if min(i, len(words)-i) == 1 and len(words) > 4 else 0)
            if _quantity_break(words[i-1], words[i]):
                score += size*20
            candidates.append((max(0, max(wa, wb)-max_width)*100 + score, [a, b]))
        if not candidates and len(text)>1:
            # A long single token (e.g. a URL) may wrap between glyphs. Never
            # discard/truncate it or interpret its contents as ASS commands.
            for i in range(1,len(text)):
                a,b=text[:i],text[i:]
                wa,wb=text_width(a,family,size,bold),text_width(b,family,size,bold)
                candidates.append((max(0,max(wa,wb)-max_width)*100+abs(wa-wb),[a,b]))
        rows = min(candidates, key=lambda c: c[0])[1] if candidates else [text]
    return rows, max((text_width(r, family, size, bold) for r in rows), default=0) <= max_width and len(rows) <= 2


def caption_lines(text, family, size, max_width, *, bold=True, minimum_scale=.72):
    for fitted in range(size, max(9, round(size*minimum_scale))-1, -1):
        rows, fits = balanced_lines(text, family, fitted, max_width, bold=bold)
        if fits:
            return "\n".join(rows), fitted
    raise ValueError("caption is too long for two readable lines; split it in Edit subtitles")
