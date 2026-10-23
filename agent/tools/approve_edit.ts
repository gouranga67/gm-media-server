import { defineTool } from "eve/tools";
import { z } from "zod";

import { mediaApi } from "../lib/media-api";

export default defineTool({
  description:
    "Approve one ready preview version and start the local full-resolution final export. Approval is idempotent for the same version.",
  inputSchema: z
    .object({
      jobId: z.string().uuid(),
      version: z.number().int().positive(),
      note: z.string().max(1000).default(""),
    })
    .strict(),
  async execute({ jobId, version, note }) {
    return mediaApi(`/api/v1/jobs/${encodeURIComponent(jobId)}/approval`, {
      method: "POST",
      body: JSON.stringify({ version, note }),
    });
  },
});
