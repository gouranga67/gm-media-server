import { defineTool } from "eve/tools";
import { z } from "zod";

import { mediaApi } from "../lib/media-api";

const clip = z
  .object({
    asset_id: z.string().uuid(),
    source_in: z.number().nonnegative(),
    source_out: z.number().positive(),
    crop: z.literal("center_fill"),
    transition: z.literal("cut"),
  })
  .strict();

const plan = z
  .object({
    schema_version: z.literal("1.0"),
    recipe: z.literal("talking_head"),
    clips: z.array(clip).min(1).max(24),
    caption_style: z.literal("clean_blue_v1"),
    audio_preset: z.literal("spoken_voice_v1"),
    end_card: z.literal("none"),
    editorial_summary: z.string().min(1).max(600),
  })
  .strict();

export default defineTool({
  description:
    "Submit exact source-only cuts for a job after inspecting it. The server independently rejects invented assets, invalid ranges, overlap, unsupported effects, and previews over 60 seconds.",
  inputSchema: z.object({ jobId: z.string().uuid(), plan }).strict(),
  async execute({ jobId, plan: document }) {
    return mediaApi(`/api/v1/jobs/${encodeURIComponent(jobId)}/edit-plans`, {
      method: "POST",
      body: JSON.stringify(document),
    });
  },
});
