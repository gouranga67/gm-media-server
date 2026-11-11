# Phase 32E — Comment Drop

Implemented in source on 2026-11-11. Container verification, deployment and owner playback acceptance remain pending.

## Purpose

Comment Drop formalises the existing caption-aware comment card as a named Effects Engine capability. It deliberately reuses the proven callout renderer rather than creating a second card layout and animation implementation.

## Implemented result

Native effect registry version 4 adds **Comment Drop** with:

- a 1–4 second duration and 2.2 second default;
- subtle fade, standard slide-up or strong pop entrance through the shared strength control;
- upper, centre or lower requested placement; and
- 1–48 characters of plain, source-backed comment text.

The registry effect is converted to the established `comment` callout at render time. The renderer measures and wraps the text, draws the existing brand-accented card, and checks active dialogue-caption bands. If the requested band is occupied, it selects another safe band; dialogue captions retain priority. Audio and picture timing are unchanged.

GM Studio exposes the typed controls from registry version 4. Selection and typing remain local form state until explicit Apply. The editing agent receives the same duration and text bounds plus a rule against fabricated audience feedback, attribution or claims. Treatment review and manifests preserve the original named effect and its bounded parameters.

## Verification added

- Model tests reject missing, unsafe, overlong and misplaced comment parameters.
- Registry tests cover the text type and 48-character maximum.
- ASS tests prove the effect produces the existing three-layer comment card, keeps dialogue captions at the higher layer and uses the selected entrance.
- Browser coverage confirms registry discovery, guidance, exact payload and no request before submit.
- The synthetic preview now includes a Comment Drop frame alongside the newer cursor and typography effects.
- The deployed-registry verifier expects version 4 and all five native effects without starting work.

The complete eight-gate source suite passes, including Python compilation, 114 browser interactions, agent-tool TypeScript, production web build, Compose validation, release auditing and patch-integrity checks. Worker-container execution remains part of deployment acceptance.

## Acceptance required

1. Run `test_visual_beats.py` inside the deployed worker.
2. Deploy and run `python3 scripts/verify-phase32.py`.
3. Apply Comment Drop over footage with lower dialogue captions and confirm the card selects a safe band.
4. Check subtle, standard and strong entrances on phone and desktop.
5. Confirm spoken audio and subtitle timing remain unchanged.
6. Review an AI-selected example for truthful text and restraint.

## Next slice

Add **Voice Note** as the next bounded social overlay, then reassess Post Wall and Sketch Words. Shot-aware Rack Focus, Dolly Zoom and Paper Tear remain a later pack with separate footage-quality gates.
