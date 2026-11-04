import { defineTool } from "eve/tools";
import { z } from "zod";
import { mediaApi } from "../lib/media-api";
import { finishingToolsSchema as tools } from "../lib/finishing-schema";
export default defineTool({
  description:
    "Apply a complete local finishing configuration to the latest inspected ready version. Merge retained settings from inspect_edit_tools; omitted arrays must be explicitly empty. Set voice_cleanup=auto for a bounded measured voice cleanup/balance pass, or off to disable it; do not invent measurement profiles. On explicit user request, smart_framing=face inspects up to eight selected 1.5–12 second video shots for sparse single-face crop following; uncertain/group shots and manual camera anchors are preserved. stabilize_clips selects at most four inspected 1–8 second normal-speed main shots for native translation-shake reduction and a 6% edge crop, only on explicit request. Inspect stabilization_candidates first; no face follow/manual camera anchors on these shots. Timeline changes clear these indexes. Review pans, moving subjects and edges. shot_match=true permits only tiny measured SDR exposure adjustments; safe_overlays=true fits image cards around resolved caption bands. These are optional and use cached bounded CPU measurements, never invented profiles. Supports plain-text animated callouts/list counters, fixed arrows/circles, temporary music-only pauses with smooth return, bounded camera keyframes, phrase voice gain, caption windows, colour, licensed music excerpts, silent PiP/review cards and real green/blue-screen keying. Retiming and freeze apply only to silent picture layers; never alter spoken dialogue to fit a duration. Independent recorded audio joins support J/L cuts only at speech-free neighbouring boundaries; captions follow those audio ranges. product_tracks follows at most two explicitly user-marked first-frame source rectangles on inspected 1–8 second normal-speed main shots. Use the web marking control; never guess coordinates or automatically select a product. No face follow, stabilization or manual camera anchors on these shots. Profiles are measured locally, cannot be invented, and are cleared on timeline changes. Rotation, scale changes, occlusion or ambiguous matches preserve existing framing; review playback. No AI segmentation, automatic product recognition, arbitrary filter code or new external assets.",
  inputSchema: z
    .object({
      jobId: z.string().uuid(),
      baseVersion: z.number().int().positive(),
      settings: tools,
    })
    .strict(),
  async execute({ jobId, baseVersion, settings }) {
    return mediaApi(`/api/v1/jobs/${encodeURIComponent(jobId)}/revisions`, {
      method: "POST",
      body: JSON.stringify({
        note: "",
        base_version: baseVersion,
        finishing_settings: settings,
      }),
    });
  },
});
