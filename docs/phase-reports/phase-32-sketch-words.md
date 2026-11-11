# Phase 32H — Sketch Words

Implemented in source on 2026-11-11. Container verification, deployment and owner playback acceptance remain pending.

## Purpose

Sketch Words gives one to three genuine words a hand-marked emphasis without replacing the footage. It is designed for a short phrase already supported by the recording, not for manufacturing a slogan, quote, fact or product claim.

## Implemented result

Native effect registry version 7 adds **Sketch Words** with:

- a 0.8–3 second duration and 1.6 second default;
- subtle, standard and strong travel, outline and stroke weight;
- upper, centre or lower requested placement;
- one to three plain source-backed words, limited to 24 characters total; and
- no segmentation, external font/asset, generated footage or additional model request.

The native ASS renderer measures the complete phrase, reduces its size to the safe frame width, and reveals each word separately. A slightly rotated accent outline, solid readable lettering and an expanding brand-colour underline create the sketch treatment. The requested band moves when dialogue captions occupy it; every sketch layer remains below the caption layer. Audio and picture timing are unchanged.

GM Studio reads the controls from registry version 7. Selection and typing stay local until Apply. Agent guidance permits only supported wording and explicitly prohibits turning an implication into a slogan, claim, fact or quote. Treatment review and manifests preserve the exact text, position and strength.

## Verification added

- Model tests reject missing, unsafe, overlong, four-word and misplaced sketch text.
- Registry tests cover the text type and 24-character maximum.
- ASS tests cover three staggered words, marker strokes and dialogue-caption priority.
- Finishing validation rejects overlapping text callouts.
- Browser coverage confirms guidance, exact typed payload and no request before Apply.
- The synthetic effects preview exercises Sketch Words with continuous original audio.
- The deployed-registry verifier expects version 7 and all eight native effects without starting work.

The complete eight-gate source suite passes, including Python compilation, 117 browser interactions, agent-tool TypeScript, the production web build, Compose validation, release auditing and patch-integrity checks. Worker-container execution and real playback remain deployment acceptance checks because the host Python environment does not contain the worker dependencies.

## Acceptance required

1. Run `test_visual_beats.py` inside the deployed worker.
2. Deploy and run `python3 scripts/verify-phase32.py`.
3. Apply one-, two- and three-word examples to real footage.
4. Test upper, centre and lower requests against active dialogue captions.
5. Compare subtle, standard and strong at phone and desktop widths.
6. Confirm AI-selected wording is genuinely supported and visually restrained.

## Next slice

Begin the shot-aware camera and transition pack with **Rack Focus**. [Its source checkpoint is implemented here](phase-32-rack-focus.md). Paper Tear and Dolly Zoom follow with their own real-footage quality gates and conservative agent eligibility.
