import { defineTool } from "eve/tools";
import { z } from "zod";

import { mediaApi } from "../lib/media-api";

const talkingHeadClip = z
  .object({
    asset_id: z.string().uuid(),
    source_in: z.number().nonnegative(),
    source_out: z.number().positive(),
    crop: z.literal("center_fill"),
    transition: z.enum(["cut", "dip_to_black"]),
    visual_preset: z.enum([
      "standard",
      "punch_in",
      "strong_punch_in",
      "slow_push_in",
      "slow_pull_out",
    ]),
  })
  .strict();

const talkingHeadPlan = z
  .object({
    schema_version: z.literal("1.1"),
    recipe: z.literal("talking_head"),
    clips: z.array(talkingHeadClip).min(1).max(24),
    caption_style: z.literal("clean_blue_v1"),
    audio_preset: z.literal("spoken_voice_v1"),
    end_card: z.literal("none"),
    editorial_summary: z.string().min(1).max(600),
    post_copy: z.string().max(2200),
    music_track_id: z.string().uuid().nullable(),
    music_mix: z.enum(["none", "subtle", "present"]),
  })
  .strict();

const montageClip = z
  .object({
    asset_id: z.string().uuid(),
    media_kind: z.enum(["video", "image"]),
    source_in: z.number().nonnegative(),
    source_out: z.number().nonnegative(),
    duration: z.number().min(0.5).max(8),
    crop: z.literal("center_fill"),
    transition: z.enum(["cut", "dip_to_black"]),
    visual_preset: z.enum(["standard", "punch_in", "slow_push_in", "slow_pull_out"]),
    include_source_audio: z.boolean(),
  })
  .strict();

const montagePlan = z
  .object({
    schema_version: z.literal("1.0"),
    recipe: z.literal("montage"),
    clips: z.array(montageClip).min(2).max(48),
    audio_preset: z.literal("montage_mix_v1"),
    end_card: z.literal("none"),
    editorial_summary: z.string().min(1).max(600),
    post_copy: z.string().max(2200),
    music_track_id: z.string().uuid().nullable(),
    music_mix: z.enum(["none", "subtle", "present"]),
  })
  .strict();

const plan = z.discriminatedUnion("recipe", [talkingHeadPlan, montagePlan]);

export default defineTool({
  description:
    "Submit an exact source-only talking-head or montage plan after inspecting the job. Music may reference only a rights-approved track returned by inspect_job. The server independently validates duration, assets, ranges, motion, transitions, music, and copy permissions.",
  inputSchema: z.object({ jobId: z.string().uuid(), plan }).strict(),
  async execute({ jobId, plan: document }) {
    return mediaApi(`/api/v1/jobs/${encodeURIComponent(jobId)}/edit-plans`, {
      method: "POST",
      body: JSON.stringify(document),
    });
  },
});
