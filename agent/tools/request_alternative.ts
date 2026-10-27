import { defineTool } from "eve/tools";
import { z } from "zod";
import { mediaApi } from "../lib/media-api";

export default defineTool({
  description:
    "Only when the user explicitly requests another creative option: make a different cut of a ready version or explore a different recorded story. Reuses source analysis and preserves earlier versions. Consumes an editing request; never loop automatically for novelty. Reuse requestId after a lost response.",
  inputSchema: z
    .object({
      jobId: z.string().uuid(),
      requestId: z.string().uuid(),
      baseVersion: z.number().int().positive(),
      kind: z.enum(["different_cut", "different_story"]),
      direction: z.string().max(600).default(""),
    })
    .strict(),
  async execute({ jobId, requestId, baseVersion, kind, direction }) {
    return mediaApi(`/api/v1/jobs/${encodeURIComponent(jobId)}/alternatives`, {
      method: "POST",
      body: JSON.stringify({
        request_id: requestId,
        base_version: baseVersion,
        kind,
        direction,
      }),
    });
  },
});
