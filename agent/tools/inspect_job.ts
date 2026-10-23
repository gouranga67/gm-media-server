import { defineTool } from "eve/tools";
import { z } from "zod";

import { mediaApi } from "../lib/media-api";

export default defineTool({
  description:
    "Inspect a GM Studio job's trusted source inventory, transcript, timing, and analysis readiness before editing.",
  inputSchema: z.object({ jobId: z.string().uuid() }).strict(),
  async execute({ jobId }) {
    return mediaApi(`/api/v1/jobs/${encodeURIComponent(jobId)}/editor-context`);
  },
});
