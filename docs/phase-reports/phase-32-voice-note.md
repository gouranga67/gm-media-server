# Phase 32F — Voice Note

Implemented in source on 2026-11-11. Container verification, deployment and owner playback acceptance remain pending.

## Purpose

Voice Note presents a genuine recorded-speech moment as a familiar voice-message card. It is a picture treatment only: it does not synthesize, replace, mute, stretch or analyse the amplitude of the audio, and it does not claim that another person sent the recording.

## Implemented result

Native effect registry version 5 adds **Voice Note** with:

- a 1–5 second duration and 2.6 second default;
- subtle, standard and strong entrance/waveform density;
- upper, centre or lower requested placement;
- a native play icon, decorative animated waveform, moving progress marker and duration readout; and
- no segmentation, external asset, browser renderer or additional model request.

The ASS renderer derives the displayed duration from the bounded treatment window and layers the card beneath dialogue captions. It checks every active caption band and moves the card to a free band when the requested position is occupied. If every band is occupied, captions win and the decorative card is omitted. Overlapping callout cards are rejected before rendering.

GM Studio reads the controls from registry version 5. Choosing an effect changes only local form state; Apply creates the preview. Agent guidance restricts Voice Note to genuine recorded speech and explicitly forbids invented senders, speakers or message sources. Treatment review and manifests retain the selected position, strength and real-audio-window explanation.

## Verification added

- Model and registry tests cover duration, parameter bounds and the complete six-effect catalogue.
- ASS tests cover the panel, icon, waveform/progress layers, duration text and caption priority.
- Finishing validation rejects overlapping text callouts.
- Browser coverage confirms registry discovery, user guidance, exact typed payload and no request before Apply.
- The synthetic effects preview exercises Voice Note with continuous original audio.
- The deployed-registry verifier expects version 5 and all six native effects without starting a render or model request.

The complete eight-gate source suite passes, including Python compilation, 115 browser interactions, agent-tool TypeScript, the production web build, Compose validation, release auditing and patch-integrity checks. Worker-container execution and real playback remain deployment acceptance checks because the host Python environment does not contain the worker dependencies.

## Acceptance required

1. Run `test_visual_beats.py` inside the deployed worker.
2. Deploy and run `python3 scripts/verify-phase32.py`.
3. Apply Voice Note to a real spoken window and confirm the voice remains unchanged.
4. Request the lower position over lower dialogue captions and confirm the card moves to a safe band.
5. Compare subtle, standard and strong at phone and desktop widths.
6. Confirm the agent uses the effect only for genuine recorded speech and does not imply a sender.

## Next slice

Add **Post Wall** as a bounded source-backed card treatment. [Its source checkpoint is implemented here](phase-32-post-wall.md). Sketch Words remains the final social-pack candidate before the shot-aware Rack Focus, Dolly Zoom and Paper Tear quality gates.
