import { defineTool } from "eve/tools";
import { z } from "zod";
import { mediaApi } from "../lib/media-api";
export default defineTool({
  description:
    "Inspect the latest ready version, stable clip handles, allowed attached picture sources and local finishing settings before proposing a precise edit. No hosted editing request.",
  inputSchema: z.object({ jobId: z.string().uuid() }).strict(),
  async execute({ jobId }) {
    const result = await mediaApi(
      `/api/v1/jobs/${encodeURIComponent(jobId)}/finishing-tools`,
    );
    // These are server measurements, not editable instructions. Auto recomputes
    // them locally when the retained configuration creates a new preview.
    if (result.settings) delete result.settings.voice_cleanup_profiles;
    if (result.settings) delete result.settings.visual_profiles;
    return result;
  },
});
