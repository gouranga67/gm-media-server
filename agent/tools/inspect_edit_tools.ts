import { defineTool } from "eve/tools";
import { z } from "zod";
import { mediaApi } from "../lib/media-api";
export default defineTool({
  description:
    "Inspect the latest ready version, stable clip handles, allowed attached picture sources and local finishing settings before proposing a precise edit. No hosted editing request.",
  inputSchema: z.object({ jobId: z.string().uuid() }).strict(),
  async execute({ jobId }) {
    return mediaApi(
      `/api/v1/jobs/${encodeURIComponent(jobId)}/finishing-tools`,
    );
  },
});
