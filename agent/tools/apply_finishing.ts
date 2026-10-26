import { defineTool } from "eve/tools";
import { z } from "zod";
import { mediaApi } from "../lib/media-api";
const time = {
  start: z.number().min(0).max(60),
  end: z.number().positive().max(60),
};
const point = z
  .object({
    time: z.number().min(0).max(60),
    zoom: z.number().min(1).max(1.35),
    x: z.number().min(0).max(1),
    y: z.number().min(0).max(1),
  })
  .strict();
const tools = z
  .object({
    audio_joins: z
      .array(
        z
          .object({
            clip_index: z.number().int().min(0).max(47),
            lead_seconds: z.number().min(0).max(1),
            tail_seconds: z.number().min(0).max(1),
          })
          .strict(),
      )
      .max(8)
      .optional(),
    motions: z
      .array(
        z
          .object({
            clip_index: z.number().int().min(0).max(47),
            points: z.array(point).min(1).max(6),
          })
          .strict(),
      )
      .max(24),
    audio_regions: z
      .array(
        z.object({ ...time, gain_db: z.number().min(-12).max(12) }).strict(),
      )
      .max(40),
    caption_regions: z
      .array(
        z
          .object({
            ...time,
            position: z.enum(["lower_safe", "middle", "upper", "hidden"]),
          })
          .strict(),
      )
      .max(40),
    colours: z
      .array(
        z
          .object({
            clip_index: z.number().int().min(0).max(47),
            contrast: z.number().min(0.8).max(1.2).optional(),
            saturation: z.number().min(0.5).max(1.5).optional(),
            brightness: z.number().min(-0.08).max(0.08).optional(),
            gamma: z.number().min(0.8).max(1.2).optional(),
          })
          .strict(),
      )
      .max(24),
    layers: z
      .array(
        z
          .object({
            ...time,
            asset_id: z.string().uuid(),
            media_kind: z.enum(["image", "video"]),
            source_in: z.number().min(0).max(86400),
            width: z.number().min(0.1).max(1),
            x: z.number().min(0).max(1),
            y: z.number().min(0).max(1),
            opacity: z.number().min(0.1).max(1).optional(),
            shape: z.enum(["rectangle", "circle"]),
            animation: z.enum(["none", "fade", "slide_up"]),
            chroma_color: z
              .string()
              .regex(/^#[0-9a-fA-F]{6}$/)
              .nullable(),
            playback_rate: z.number().min(0.25).max(4).optional(),
            freeze: z.boolean().optional(),
          })
          .strict(),
      )
      .max(4),
    music_start_seconds: z.number().min(0).max(86400),
    voice_denoise: z.boolean(),
  })
  .strict();
export default defineTool({
  description:
    "Apply a complete local finishing configuration to the latest inspected ready version. Merge retained settings from inspect_edit_tools; omitted arrays must be explicitly empty. Supports bounded camera keyframes, phrase voice gain, caption windows, colour, licensed music excerpts, silent PiP/review cards and real green/blue-screen keying. Retiming and freeze apply only to silent picture layers; never alter spoken dialogue to fit a duration. Independent recorded audio joins support J/L cuts only at speech-free neighbouring boundaries; captions follow those audio ranges. No AI segmentation, automatic tracking, arbitrary filter code or new external assets.",
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
