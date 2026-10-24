import { defineTool } from "eve/tools";
import { always } from "eve/tools/approval";
import { z } from "zod";

import { mediaApi } from "../lib/media-api";

export default defineTool({
  description:
    "Attach one or more existing, analyzed GM Studio library originals to a draft editing job after the user has explicitly chosen them. This creates references and never copies or modifies media bytes.",
  inputSchema: z.object({
    jobId: z.string().uuid(),
    assetIds: z.array(z.string().uuid()).min(1).max(50),
  }).strict(),
  approval: {
    request: always(),
    prompt: ({ input }) => `Attach ${input.assetIds.length} existing library ${input.assetIds.length === 1 ? "item" : "items"} to job ${input.jobId.slice(0, 8)}?`,
  },
  label: {
    start: ({ assetIds }) => `Attach ${assetIds.length} library ${assetIds.length === 1 ? "item" : "items"}`,
  },
  async execute({ jobId, assetIds }) {
    return mediaApi(`/api/v1/jobs/${encodeURIComponent(jobId)}/assets`, {
      method: "POST",
      body: JSON.stringify({ asset_ids: Array.from(new Set(assetIds)) }),
    });
  },
});
