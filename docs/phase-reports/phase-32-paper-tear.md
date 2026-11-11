# Phase 32J — Paper Tear

Implemented in source on 2026-11-11. Container verification, deployment and real-footage quality acceptance remain pending.

## Purpose and contract

Paper Tear is the first native effect that belongs to a real cut rather than an arbitrary time window. It freezes the final outgoing frame, divides it into deterministic horizontal paper strips and pulls those strips left or right at staggered speeds. The already assembled incoming clip is revealed underneath. No replacement image, generated footage, segmentation or model request is used.

The effect stores the exact clip boundary as the number of completed clips. Boundary 1 means the cut between clips 1 and 2. Its start must equal that boundary's cumulative reel time, its 0.4–1 second window must finish inside the incoming clip, and the incoming clip must use an ordinary cut rather than another transition. A later trim, reorder or source change clears Paper Tear so it cannot silently migrate to unrelated footage.

## Implemented result

Native effect registry version 9 adds **Paper Tear** with:

- a 0.4–1 second duration and 0.7 second default;
- subtle, standard and strong strip counts and edge weights;
- left and right pull directions;
- exact boundary validation against the saved clip sequence;
- no overlap with an existing dissolve or dip transition; and
- unchanged recorded dialogue, music and caption timing.

GM Studio lists only eligible ordinary-cut boundaries with at least 0.4 seconds in the incoming clip. Choosing a boundary sets the read-only start time and safe default end time. The owner may change duration, strength and direction; selection does no work until Create preview is pressed.

The editing agent may use Paper Tear only for a motivated scene or idea change. Its guidance defines the boundary index precisely and prohibits decorative use at every cut. Treatment review records the selected boundary, pull direction, real incoming clip and unchanged audio contract.

## Verification added

- The complete eight-gate source suite passes, including Python compilation, 119 browser interactions, agent-tool TypeScript, the production web build, Compose validation, release auditing and patch-integrity checks.
- Model tests require both boundary and direction and reject those parameters on other effects.
- Plan validation rejects missing boundaries, shifted start times, windows extending beyond the incoming clip and competing transitions.
- Timeline-retiming coverage proves that exact-boundary tears are cleared after cut changes.
- Filter-graph coverage checks the outgoing-frame freeze, bounded strip count, paper edge and timed movement expression.
- A real FFmpeg test uses distinct outgoing and incoming colours to prove both are visible during the tear, only the incoming clip remains afterward, and audio stays continuous.
- Browser coverage confirms eligible boundary labels, derived timing, direction payload and no request before explicit submission.
- The synthetic effects preview now includes Paper Tear at a real two-clip boundary.
- The deployed-registry verifier expects version 9 and all ten native effects without starting work.

Worker-container execution and real playback remain deployment acceptance checks because the development host does not provide the worker's Python dependencies or FFmpeg binary.

## Acceptance required

1. Run `test_visual_beats.py` inside the deployed worker.
2. Deploy and run `python3 scripts/verify-phase32.py`.
3. Apply Paper Tear to an ordinary cut between two visually different clips.
4. Compare subtle, standard and strong in both pull directions.
5. Confirm the outgoing frame covers the start of the cut, its uneven paper edge moves cleanly, and the real incoming clip remains after the transition.
6. Confirm dialogue, music and dialogue captions remain synchronized across the boundary.
7. Reject uses where the frozen outgoing frame or strip movement obscures an important face, product or on-screen text.

## Next slice

Prototype **Dolly Zoom** as a bounded crop-and-scale illusion, with explicit camera-motion limitations and real-shot eligibility checks.
