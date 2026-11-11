# Phase 32B — Effects Engine foundation

Implemented, container-verified, deployed and owner-tested on 2026-11-11.

## Purpose

New transitions and animations must be reusable capabilities rather than isolated renderer patches. This checkpoint makes the two existing native picture effects the first entries in one versioned contract that the validator, renderer, agent and GM Studio interface can share.

It does not add a third effect or claim exact reproduction of an external reference video. It establishes the path for adding and testing those effects one at a time.

## Implemented result

Registry version 1 contains:

| Effect | Category | Duration | Parameters | Segmentation |
|---|---|---:|---|---|
| Impact Frame | Accent | 0.1–0.25 seconds | Strength | Not required |
| Clone Row | Layout | 0.1–2.5 seconds | Strength; upper/centre/lower position | Not required |

Each definition also states its default duration, renderer version, summary, dialogue-preservation guarantee and caption layering. The read-only `/api/v1/effects/registry` endpoint lists this contract without starting a render, model request or database write.

The finishing-tools response embeds the same registry. GM Studio builds the effect selector and supported parameter controls from that response instead of duplicating effect labels and duration limits in the browser. Changing an effect, strength or position performs no work; the existing explicit form submission queues one local preview.

Strength now has three bounded levels: subtle, standard and strong. Clone Row additionally supports upper, centre and lower placement. Impact Frame has a fixed full-frame position. Unsupported names, durations, values and Impact Frame positions are rejected before rendering.

Default `standard` and `center` values are omitted when saved. This keeps the canonical documents and plan hashes of earlier effects unchanged while new non-default choices remain explicit. The finished manifest records the registry version and chosen non-default parameters, and the treatment review describes strength and position.

The editor receives the same registered names and timing limits. Effects remain optional, preserve recorded dialogue, render below captions and cannot introduce arbitrary FFmpeg expressions, JavaScript, URLs or generated replacement footage.

The synthetic preview helper now exercises a strong Impact Frame and a subtle upper Clone Row and records the registry version in its report.

## Source verification completed

- Python source and test compilation passed.
- Web TypeScript checking passed.
- The production web build passed.
- All 111 existing browser interaction tests passed, including the expanded native-effect test.
- `git diff --check` passed.

The complete eight-gate source suite passed, including Compose validation, public-release audit and agent-tool TypeScript checking.

The browser test confirms that selection and parameter changes cause no request, while explicit submission sends exactly one bounded finishing document. New Python registry and real FFmpeg assertions are present, but the host Python environment does not contain the container dependencies. They must run in the normal container suite before this checkpoint is deployed.

## Container and deployment acceptance

Before accepting Phase 32B:

1. Run the native-effect unit and real FFmpeg tests in the worker image.
2. Run the synthetic preview helper and inspect its Impact Frame and Clone Row samples.
3. Deploy the committed build and run `python3 scripts/verify-phase32.py` to confirm the registry endpoint reports version 1 without starting work.
4. Apply each effect from GM Studio with default settings, then a non-default strength and Clone Row position.
5. Confirm captions stay above the picture treatment and recorded speech remains continuous.
6. Confirm the saved treatment review and render manifest identify the effect and registry version.
7. Watch the previews on phone and desktop before marking the phase accepted.

## Next slice

Phase 32C begins with **Live Cursor** as the first new registry entry. It reuses the same timing, parameter, explicit-submit, manifest and render-test contracts. [The source checkpoint is implemented here](phase-32-live-cursor.md). Letter Dive, Comment Drop, Voice Note, Post Wall and Sketch Words follow one at a time after playback acceptance.
