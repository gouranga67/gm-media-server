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
    "Request a new, versioned preview from a ready job. Feedback may change source selections; caption corrections replace only text that already exists in the transcript.",
  inputSchema: z
    .object({
      jobId: z.string().uuid(),
      note: z.string().max(1200).default(""),
      captionCorrections: z.array(captionCorrection).max(50).default([]),
    })
    .strict()
    .refine((value) => value.note.trim().length > 0 || value.captionCorrections.length > 0, {
      message: "Provide feedback or a caption correction.",
    }),
  async execute({ jobId, note, captionCorrections }) {
    return mediaApi(`/api/v1/jobs/${encodeURIComponent(jobId)}/revisions`, {
      method: "POST",
      body: JSON.stringify({
        note,
        caption_corrections: captionCorrections,
      }),
    });
  },
});
