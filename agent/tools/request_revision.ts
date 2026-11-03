import { defineTool } from "eve/tools";
import { z } from "zod";

import { mediaApi } from "../lib/media-api";

const captionCorrection = z
  .object({
    original_text: z.string().min(1).max(300),
    replacement_text: z.string().min(1).max(300),
  })
  .strict();

export default defineTool({
  description:
    'Request a new, versioned preview. Exact single requests such as Make "recorded words" louder by 3 dB or Shorten the pause after "recorded words" to 0.5 seconds use frozen source-grounded local operations. Add in clip 2 for repeated quotes. Ambiguity/unsafe pauses are rejected before queueing; never guess which occurrence or promise silence from a transcript gap. Other notes use the existing editor. Use the subtitle editor for on-screen wording.',
  inputSchema: z
    .object({
      jobId: z.string().uuid(),
      note: z.string().max(1200).default(""),
      baseVersion: z.number().int().positive().optional(),
      captionCorrections: z.array(captionCorrection).max(50).default([]),
    })
    .strict()
    .refine((value) => value.note.trim().length > 0 || value.captionCorrections.length > 0, {
      message: "Provide feedback or a caption correction.",
    }),
  async execute({ jobId, note, baseVersion, captionCorrections }) {
    const version = baseVersion ?? (await mediaApi(`/api/v1/jobs/${encodeURIComponent(jobId)}/finishing-tools`)).version;
    return mediaApi(`/api/v1/jobs/${encodeURIComponent(jobId)}/revisions`, {
      method: "POST",
      body: JSON.stringify({
        note,
        base_version: version,
        caption_corrections: captionCorrections,
      }),
    });
  },
});
