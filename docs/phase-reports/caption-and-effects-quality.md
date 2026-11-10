# Caption and effects quality sprint

Implemented in source. Deployment and real-footage playback acceptance remain separate.

## Caption and headline finishing

- Phrase-aware groups span neighbouring ASR segments and retain actual aligned word times. Groups are bounded to seven words, 44 characters and 2.6 seconds where a single token permits. Sentence endings and pauses take priority; number/unit pairs and explicit correction phrases should stay together.
- Segment punctuation/case is recovered only when its tokens agree with the aligned words. Sentence starts and “I” are capitalised locally. Existing names/acronyms and explicit replacement spelling are preserved; unknown names and missing semantic punctuation are not guessed.
- The worker measures installed DejaVu fonts and balances at most two lines. Default subtitles use white text and a dark outline; selected brand typography/accent remains available. Per-cue lower-safe positions now share the global platform margins.
- Manual line breaks survive draft save/apply and ASS reconstruction. More than two explicit lines is rejected with guidance to split the cue. Oversized text must be split rather than silently truncated.
- New visible subtitle drafts cannot overlap, even in different bands. Hidden cues do not block visible speech. Generated/legacy overlaps are coalesced into a single lane, retaining words and the combined interval rather than fabricating word timings. This recovery still needs human review.
- Headlines remain separate from subtitles. Labels/headlines get a backing panel, accent stripe and stronger typography. A source-backed leading figure such as "$40 million" gets a large accent line and smaller supporting line. Thought/comment cards remain sentence case. Decorative text does not enter the editable dialogue layer. If all caption bands are occupied, the callout is omitted.

The historical `GMBlue` ASS identifier and `clean_blue_v1` plan enum remain for compatibility. Metadata identifies `phrase_cards_v2` / `headline_cards_v2`. Existing export files are not rewritten. An explicit exact re-render uses current presentation while keeping the saved cut; saved subtitle edits retain their text and case.

## First native effects pack

| Tool | Bounds | Behaviour |
| --- | --- | --- |
| Headline / comment / thought / counter | 0.1–8 seconds; 64 plain-text characters | Native text/panel graphics; no invented claims or attempt counts |
| Impact frame | 0.1–0.25 seconds | One accent border; no full-screen flash or strobe |
| Clone row | 0.1–2.5 seconds | Three live copies of the whole recorded shot; one unchanged audio track |

Clone row is a full-shot triptych, **not** person segmentation. Decoder work is limited to the selected window. It does not hold the last frame after the cue; captions remain above the picture treatment.

`visual_beats` is a strict bounded part of `finishing`. Empty arrays are omitted from saved-plan serialisation. It shares the requested effect budget, is disabled for Effects Off, appears in the treatment timeline, respects effect locks and is cleared by Remove effects. Retiming follows surviving content. No minimum effect count is imposed.

In **Finishing tools · local preview**, select **Impact frame / clone row**, set the reel range and explicitly create the preview. Selecting an option never renders. Headline/comment styles extend the existing callout tool. These local operations do not request a new story or another model call.

## Preparation speech

Ordinary-story cleanup also supports promotional speech. A standalone opening “well” is removable only when it is a short separate clip from the same recording, followed by at least 650 ms of word gap, plus an independent introduction or a saved preparation marker. Meaningful continuations such as “well, that depends”, explicit preserved openings, natural-audio preservation and blooper intent are retained. Ambiguous words inside a larger passage are not automatically deleted.

This does not promise perfect filler detection. Wider false-start/repeated-take comparison belongs to the existing planner and source evidence. Saved-cut re-renders do not run new story cleanup.

## Compute and verification

This pack uses existing FFmpeg/ASS/Pillow capabilities. It adds no hosted critic, transcription pass, browser-render service or GPU dependency. The planner gets a small typed option in its existing request. Remotion remains a candidate for later effects that cannot be expressed cleanly here; it is not installed in this sprint.

`scripts/preview-creative-quality.py --output-dir /tmp/creative-quality` produces a synthetic seven-second demonstration, contact frames and a timing report without database access or AI calls. It is a typography/effects fixture, not real-footage story acceptance or a universal performance claim. One local CPU sample rendered in approximately 1.5 seconds at 540×960; target-server performance needs observation.

Tests cover word preservation, punctuation agreement, number grouping, delivery aspects, manual line breaks, overlap handling, distinct text layers, effect bounds/budget/locks/removal, and changing picture content plus continuous sound through both render engines. The server-compatible FFmpeg 4.4 family and a newer runtime are checked. GPU encoding is unavailable in this isolated runtime, so render checks use libx264 fallback.

Verification: the complete backend/local-render suite ran 800 tests on both FFmpeg 4.4.2 and 8.0.1: 799 passed and one optional rclone-dependent test was skipped in each run. All 111 browser interaction tests, TypeScript checking, production web build and public-release audit passed. A final sentence-case edge check also preserves mixed-case names such as eBay/iPhone and numeric starts such as "$40 million". This is automated technical evidence; deployment and human playback are still pending.

## Deployment and playback checklist

1. Run `sudo ./scripts/install-service.sh` from the repository on the server.
2. Use **Re-render exact edit** on the revenue-headline example. Confirm the stronger headline and readable subtitles, without a new story request or increased model usage.
3. Check fresh speech captions for natural phrase groups, complete words and number/unit pairs. A short sentence can legitimately have one word; the system should avoid accidental orphan cards.
4. Save a two-line subtitle correction, reopen it, apply it and verify line breaks/spelling. An overlapping visible cue should produce an actionable save error.
5. Add an impact frame and a two-second clone row locally. Check cue windows, continuing picture movement and uninterrupted sound. Then test Remove effects.
6. Compare a marked preparation opening with meaningful “well” dialogue and a blooper; preserve the latter two.

Further animation presets, genuine person cutouts and wider real-footage acceptance remain later work. Readability, source fidelity and continuous audio take priority.
