"""Small lexical context links over selected cached evidence, not new analysis."""

import json
import re
from collections import defaultdict

from app.source_evidence import product_mentions

VERSION = 1
_REFERENCE = re.compile(r"^(?:because|which|it|this|that|they|these|those|their|but|and)\b", re.I)


def context_links(evidence, products=(), character_budget=3000):
    """Cite only IDs actually shared in this inventory, with bounded overhead.

    Products are explicit ASR mentions, not visual identity or inferred claims.
    Matching openings identify takes to compare, never equivalent assertions.
    """
    groups, prefixes, mentions = defaultdict(list), defaultdict(list), {}
    for item in evidence:
        groups[str(item["asset_id"])].append(item)
        names = tuple(p["name"] for p in product_mentions(item["text"], list(products)))
        mentions[item["evidence_id"]] = names
        tokens = re.findall(r"[^\W_]+", item["text"].casefold())
        if len(tokens) >= 7:
            prefixes[(tuple(tokens[:6]), names)].append(item)
    candidates = []
    # Round-robin passage order keeps a single recording from consuming every
    # contextual hint. No extra transcript text is duplicated into the prompt.
    queues = []
    for items in groups.values():
        queue = []
        ordered = sorted(items, key=lambda p: (p["start"], p["end"]))
        for index, item in enumerate(ordered):
            entry = {"evidence_id": item["evidence_id"]}
            if mentions[item["evidence_id"]]:
                entry["spoken_product_mentions"] = list(mentions[item["evidence_id"]])[:3]
            if item.get("needs_context") or _REFERENCE.search(item["text"].strip()):
                previous = ordered[index - 1] if index else None
                if previous and 0 <= item["start"] - previous["end"] <= .65:
                    entry["inspect_previous_evidence_id"] = previous["evidence_id"]
                else:
                    entry["preceding_context_unavailable"] = True
            critical = re.findall(r"\b(?:not|never|without|unless|only|if|cannot|can't|isn't|doesn't|don't|\d+(?:\.\d+)?)\b", item["text"].casefold().replace("’", "'"))
            if critical:
                entry["keep_qualifiers_and_numbers"] = list(dict.fromkeys(critical))[:8]
            if len(entry) > 1:
                queue.append(entry)
        queues.append(queue)
    while any(queues) and len(candidates) < 16:
        for queue in queues:
            if queue and len(candidates) < 16:
                candidates.append(queue.pop(0))
    alternatives = []
    for group in prefixes.values():
        if len(group) > 1:
            alternatives.append({"evidence_ids": [p["evidence_id"] for p in group[:4]],
                                 "basis": "same_recorded_opening_and_explicit_product_mentions"})
            if len(alternatives) == 6:
                break
    result = {"version": VERSION, "passages": candidates, "compare_takes": alternatives,
              "note": "Lexical evidence only. Inspect links and compare complete claims; matching openings are not equivalent takes. Product mentions do not verify pictured identity.",
              "hosted_retrieval_calls": 0}
    while len(json.dumps(result, ensure_ascii=False)) > max(0, character_budget):
        if result["compare_takes"]:
            result["compare_takes"].pop()
        elif result["passages"]:
            result["passages"].pop()
        else:
            return None
    return result if candidates or alternatives else None
