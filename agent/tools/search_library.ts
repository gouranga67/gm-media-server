import { defineTool } from "eve/tools";
import { z } from "zod";

import { mediaApi } from "../lib/media-api";

export default defineTool({
  description:
    "Search GM Studio's local source-derived catalogue for filenames, projects, spoken phrases, or subjects visible in video scenes and photos. Hybrid results include immutable asset IDs, exact source time ranges, evidence kinds, and local source-frame IDs; visual matches are similarity evidence, never generated descriptions.",
  inputSchema: z.object({
    query: z.string().trim().min(1).max(160),
    mediaKind: z.enum(["all", "video", "image", "audio"]).default("all"),
    projectId: z.string().uuid().optional(),
    limit: z.number().int().min(1).max(50).default(20),
  }).strict(),
  async execute({ query, mediaKind, projectId, limit }) {
    const parameters = new URLSearchParams({
      query,
      media_kind: mediaKind,
      limit: String(limit),
    });
    if (projectId !== undefined) parameters.set("project_id", projectId);
    return mediaApi(`/api/v1/catalog/search?${parameters.toString()}`);
  },
});
