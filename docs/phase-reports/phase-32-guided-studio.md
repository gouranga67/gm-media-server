# Phase 32A — Guided Studio home

Implemented in source on 2026-11-11. Deployment and phone/owner acceptance remain pending.

## Purpose

GM Studio has accumulated capable editing, library, review, learning, publishing and system tools. The next product step is to make the correct starting point obvious without hiding the operational evidence that already makes the server trustworthy.

The selected direction is the action-led Home design: lead with what the owner wants to accomplish, then explain the workflow in a compact visual sequence. This is the first Guided Studio slice, not a separate application or a replacement for the existing navigation.

## Implemented result

The Home screen now starts with six plain-language tasks, each linked to an existing GM Studio route:

1. **Make a new edit** — `/jobs/new`
2. **Organise my media** — `/library`
3. **Find an idea or blooper** — `/concepts`
4. **Continue an edit** — `/jobs`
5. **Export or publish** — `/publishing`
6. **Check system health** — `/system`

A compact guide directly below the launcher shows the end-to-end journey:

**Add media → Plan edit → Build → Review → Approve → Export**

The change deliberately preserves the existing live overview and managed-job data, conditional onboarding prompt, recent jobs, AI budget summary and operations link. It changes the information hierarchy without adding an API, database migration, model call or new background work.

The task cards and workflow steps use semantic headings, labelled regions, visible focus behaviour and touch-sized controls. The implementation reuses the existing GM Studio visual language and icon set.

## Verification completed

- Web production build passed.
- Web TypeScript check passed when run after the build.
- The existing web interaction regression suite passed all 111 tests.
- `git diff --check` passed.

These checks establish source integrity and regression coverage. They do not substitute for visual inspection or owner acceptance on the deployed phone and desktop interfaces.

## Deployment acceptance

After deployment:

- inspect the Home layout on a phone and desktop;
- open all six task cards and confirm they lead to the intended existing tools;
- confirm live overview, onboarding, recent-job and budget states still render with real server data;
- confirm the workflow guide remains readable without horizontal overflow;
- check keyboard focus, screen-reader headings and touch targets;
- confirm no change to editing, rendering, publishing or AI usage behaviour.

## Next build slices

- **Phase 32B — Effects foundation:** establish the reusable effects registry, parameter contract, preview samples and render-test pattern around the existing Clone Row and Impact Frame effects. [Source checkpoint implemented](phase-32-effects-foundation.md); container and playback acceptance remain pending.
- **Phase 32C–G — Social animation pack:** add one effect at a time, beginning with low-risk overlays. [Live Cursor](phase-32-live-cursor.md), [Letter Dive](phase-32-letter-dive.md), [Comment Drop](phase-32-comment-drop.md), [Voice Note](phase-32-voice-note.md) and [Post Wall](phase-32-post-wall.md) now have bounded registry implementations.
- **Phase 32H — Camera and transition pack:** add and evaluate Rack Focus, Dolly Zoom, Paper Tear and other shot-aware transitions, with masking or segmentation kept behind explicit quality gates where required.

Each effect must remain selectable by name and bounded parameters, preserve original footage, produce a reviewable preview and pass a real-footage playback check before it is treated as accepted.

## Recovered effects backlog

This is the complete named set recovered from the earlier planning discussion. It records product intent rather than claiming exact reproduction of an unseen reference animation.

| Effect | Initial estimate | Current position |
|---|---|---|
| Live Cursor | Easy | Registry v2 deployed; playback acceptance pending |
| Clone Row | Medium | Native bounded first version already implemented; move behind the shared Phase 32B contract |
| Post Wall | Medium | Registry v6 source checkpoint implemented |
| Letter Dive | Easy | Registry v3 source checkpoint implemented |
| Comment Drop | Easy | Registry v4 source checkpoint implemented by reusing the comment-card renderer |
| Sketch Words | Medium | Phase 32C candidate |
| Rack Focus | Easy | Phase 32E candidate; test against real footage |
| Voice Note | Easy | Registry v5 source checkpoint implemented |
| Impact Frame | Easy | Native bounded first version already implemented; move behind the shared Phase 32B contract |
| Dolly Zoom | Medium | Phase 32E candidate; source framing and crop limits required |
| Paper Tear | Easy | Phase 32E transition candidate |

Effects that depend on convincing person cloning, isolation or background separation may require prepared footage, masks or segmentation. They must not silently replace the owner's footage with generated video, and learned cutout work remains behind the existing quality gate.
