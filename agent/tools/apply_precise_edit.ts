import { defineTool } from "eve/tools";
import { z } from "zod";
import { mediaApi } from "../lib/media-api";
const change = z
  .object({
    clip_index: z.number().int().min(0).max(47),
    clip_id: z.string().length(16),
    action: z.enum(["keep", "remove", "move_up", "move_down"]).default("keep"),
    source_in: z.number().nonnegative().optional(),
    source_out: z.number().positive().optional(),
    split_at: z.number().positive().optional(),
    transition: z.enum(["cut", "dip_to_black", "cross_dissolve"]).optional(),
    replacement_asset_id: z.string().uuid().optional(),
    max_pause_seconds: z.number().min(0.3).max(2).optional(),
    visual_preset: z
      .enum([
        "standard",
        "punch_in",
        "strong_punch_in",
        "slow_push_in",
        "slow_pull_out",
        "rhythmic_punch",
      ])
      .optional(),
    source_audio_gain_db: z.number().min(-12).max(12).optional(),
  })
  .strict();
export default defineTool({
  description:
    "Create one local preview with exact trims, splits, take replacement, pause limits or framing. Inspect the review for clip handles and the current base version first. Source times refer to the original recording. Use only attached media. This preserves prior versions and uses zero additional editor-model tokens.",
  inputSchema: z
    .object({
      jobId: z.string().uuid(),
      baseVersion: z.number().int().positive(),
      changes: z.array(change).min(1).max(48),
    })
    .strict(),
  async execute({ jobId, baseVersion, changes }) {
    return mediaApi(`/api/v1/jobs/${encodeURIComponent(jobId)}/revisions`, {
      method: "POST",
      body: JSON.stringify({
        note: "",
        base_version: baseVersion,
        clip_adjustments: changes,
      }),
    });
  },
});
