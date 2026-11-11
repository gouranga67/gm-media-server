# Phase 32D — Letter Dive

Implemented in source on 2026-11-11. Container render verification, deployment and owner playback acceptance remain pending.

## Purpose

Letter Dive is the second new animation added through the Effects Engine. It proves that the registry can describe bounded text as well as enum, number and boolean parameters while keeping the result local, deterministic and reviewable.

## Implemented result

Native effect registry version 3 adds **Letter Dive**. It accepts:

- 0.6–2.5 seconds of final-reel time;
- subtle, standard or strong entrance motion;
- upper, centre or lower placement; and
- 1–18 characters of plain, source-backed text.

The text rejects subtitle commands, control characters and unbounded copy. The editing agent is instructed to use only a genuine word or short phrase supported by the footage; it must not invent a quote, claim or slogan.

The renderer measures the chosen text locally, centres the complete word or phrase and gives each non-space character a staggered vertical entrance. Native ASS text events render below dialogue captions. The picture and recorded audio clocks are unchanged. Talking-head and montage output use the same treatment events.

GM Studio discovers the effect and all controls from registry version 3. Selecting or typing performs no work. Explicit Apply queues one local preview containing only the bounded effect document. The treatment review and render manifest record the displayed text, position, strength and registry version.

## Verification added

- Model validation covers missing, unsafe and misplaced text parameters.
- Registry checks cover text type and length bounds.
- ASS assertions cover staggered per-letter timing and caption layering.
- The real FFmpeg test adds Letter Dive to the same talking-head and montage render used for cursor, clone, impact, subtitle and continuous-audio verification.
- Browser coverage verifies the registry-driven control, source-backed guidance and exact explicit-submit payload.
- The synthetic preview now includes Letter Dive alongside Live Cursor, Clone Row and Impact Frame.

The complete eight-gate source suite passes, including Python compilation, 113 browser interactions, agent-tool TypeScript, the production web build, Compose validation, release auditing and patch-integrity checks. Container FFmpeg execution remains part of deployment acceptance because the host Python environment does not contain the worker dependencies.

## Acceptance required

1. Run `test_visual_beats.py` in the deployed worker image.
2. Run the synthetic preview and inspect the Letter Dive frame and complete movement.
3. Deploy and run `python3 scripts/verify-phase32.py`; it must report registry version 3 and four native effects.
4. Apply short words at all three positions in GM Studio and review phone and desktop playback.
5. Confirm captions remain readable and speech stays continuous.
6. Review an AI-selected example for truthfulness and restraint.

## Next slice

Add **Comment Drop** as the next low-risk social overlay. [Its source checkpoint is implemented here](phase-32-comment-drop.md), formalising the existing comment-card capability as a named registry effect rather than duplicating its renderer. Voice Note follows. Shot-aware Rack Focus, Dolly Zoom and Paper Tear remain a later pack with separate footage-quality gates.
