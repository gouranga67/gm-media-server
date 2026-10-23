import { defineTool } from "eve/tools";
import { z } from "zod";

import { mediaApi } from "../lib/media-api";

export default defineTool({
  description:
    "Idempotently request the server's bounded editor and local renderer to make a phone-downloadable preview for an inspected job.",
  inputSchema: z.object({ jobId: z.string().uuid() }).strict(),
  async execute({ jobId }) {
    return mediaApi(`/api/v1/jobs/${encodeURIComponent(jobId)}/preview`, {
      method: "POST",
      body: "{}",
    });
  },
});
