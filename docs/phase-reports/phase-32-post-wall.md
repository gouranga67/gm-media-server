# Phase 32G — Post Wall

Implemented in source on 2026-11-11. Container verification, deployment and owner playback acceptance remain pending.

## Purpose

Post Wall builds two or three short ideas into a staggered graphic wall. The cards must be supported by the footage or brief. They deliberately contain no username, profile picture, engagement count or platform branding, so the treatment cannot silently manufacture social proof or claim that a real third party published the text.

## Implemented result

Native effect registry version 6 adds **Post Wall** with:

- a 1.2–5 second duration and 3 second default;
- subtle, standard and strong entrance timing;
- two or three plain-text cards, each limited to 42 characters;
- staggered brand-accented native ASS panels; and
- no segmentation, external assets, generated footage or additional model request.

The renderer wraps and measures each phrase, staggers the card entrances and keeps every graphic below layer-zero dialogue captions. A lower caption band compacts the wall upward; an upper caption band moves it down. A middle caption band splits the layout around it. If dialogue occupies more than one band, the decorative wall yields entirely. Overlapping callouts are rejected before rendering.

GM Studio reads the list bounds from registry version 6 and exposes two required card fields plus one optional field. Selection and typing remain local until Apply. Agent guidance requires source-backed wording and prohibits fabricated posts, accounts, attribution, likes, shares, comments or audience reactions. Treatment review and manifests preserve the exact card list and strength.

## Verification added

- Model tests reject missing, single, unsafe, overlong and misplaced card lists.
- Registry tests cover the `text_list` type, two-to-three item range and 42-character item limit.
- ASS tests cover staggered panel timing, all three phrases and dialogue-caption priority.
- Finishing validation rejects overlapping callout cards.
- Browser coverage confirms all three fields, exact typed payload and no request before Apply.
- The synthetic effects preview exercises Post Wall with continuous original audio.
- The deployed-registry verifier expects version 6 and all seven native effects without starting work.

The complete eight-gate source suite passes, including Python compilation, 116 browser interactions, agent-tool TypeScript, the production web build, Compose validation, release auditing and patch-integrity checks. Worker-container execution and real playback remain deployment acceptance checks because the host Python environment does not contain the worker dependencies.

## Acceptance required

1. Run `test_visual_beats.py` inside the deployed worker.
2. Deploy and run `python3 scripts/verify-phase32.py`.
3. Apply two-card and three-card walls to real footage.
4. Test against lower, middle and upper dialogue captions and confirm captions always win.
5. Compare subtle, standard and strong at phone and desktop widths.
6. Confirm an AI-selected example uses supported wording and invents no social metadata.

## Next slice

Add **Sketch Words** as the remaining low-risk social/typography candidate. [Its source checkpoint is implemented here](phase-32-sketch-words.md). Then begin the shot-aware camera and transition pack with separate footage-quality gates.
