# Blooper purpose and preset correction

Blooper concepts already carried explicit outtake instructions, but their speech-editing path also supplied generic hook/development/payoff/ending rules, clean-take retrieval and shared recipe-level lessons. High-impact validation could additionally require a zoom or transition. Those conflicting directions could turn a recorded gag into a conventional product explanation.

The failed request shown during this review reported `server_is_overloaded`. That is a separate editor-service failure; this change cannot eliminate upstream capacity failures. It supplies a clearer busy-service message and adds no automatic model retry.

## Presets that remain useful

| Choice | Responsibility |
| --- | --- |
| Format: Speech-led or Montage | How the source picture and audio are assembled. Neither implies an advertisement. |
| Purpose: Follow my brief, Story/explanation, Product/promotion, Bloopers/outtakes | Which editorial outcome to preserve. An explicit selection takes precedence over product words or the project name. |
| Style and effects | Presentation and permitted accents. A high-impact style or meme-heavy effects never selects bloopers by itself. |
| Publishing preset | Delivery shape, captions and platform presentation; it does not require a sales ending. |

Selected concepts persist `bloopers` or `story` as the job purpose. Migration 032 recovers that explicit choice for existing concept jobs without altering their frozen plans, previews or exports. Other legacy jobs keep `auto` and use the existing brief-based inference. A saved creative profile does not overwrite the current purpose selection.

Bloopers receive setup → recorded stumble/restart → real reaction/recovery guidance. An unresolved question can be the ending. There is no sales-payoff, CTA, clean-take, mandatory transition or zoom quota. Source identity, source bounds, maximum duration, music/effect permissions and word synchronization checks remain enforced. Restarts are not automatically suppressed as duplicate ideas. None of this proves that a moment is funny or a genuine mistake; playback review remains necessary.

The review screen shows **Blooper review guidance**, rather than generic story-coverage checkboxes or hook auditions. The job list and usage history identify stored blooper purposes separately from the speech rendering format.

Historical recipe-level lessons do not apply to bloopers. Blooper notes are retained but are excluded from clean-take lesson proposals and preference aggregation; clean-take trials cannot target blooper jobs. Purpose-scoped blooper learning is future work, rather than silently borrowing ad preferences.

## Deployment and acceptance

```bash
sudo ./scripts/install-service.sh
sudo ./scripts/verify-live-suite.sh
```

After installation, retry the failed concept job once the editor service is available, or select a fresh blooper concept. Check that the actual setup, line loss and recorded reaction stay together, the ending is allowed to remain unresolved, and no ad conclusion was added. Confirm the review heading and guidance identify bloopers. For a manual job, choose **Bloopers / outtakes** under **Reel purpose**.

Source verification uses synthetic inputs and isolated SQL, with no hosted model requests or live job changes. Actual comic timing and story quality require the new real-footage preview.

Verified for this checkpoint: 319 backend tests including local FFmpeg renders; 24 interface interaction tests; all eight source-suite checks including TypeScript and the production web build; all 32 migrations plus actual job/learning/history SQL in isolation. Phone and desktop checks of the new-job and blooper-review screens found no JavaScript errors, horizontal overflow or automated WCAG 2 A/AA violations with synthetic fixtures.
