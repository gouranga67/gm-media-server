export type PrivacyMode = "hybrid" | "text_only" | "local_only";
export type EditStyle = "clean" | "energetic" | "calm";
export type MusicMode = "none" | "subtle" | "present";
export type TargetDuration = 15 | 20 | 30 | 45 | 60;
export type Recipe = "talking_head" | "montage";
export type ReasoningEffort = "low" | "medium" | "high";
export type OutputAspect = "vertical" | "landscape" | "square";
export type TargetPlatform = "all_social" | "facebook" | "instagram" | "linkedin" | "tiktok" | "youtube";
export type PublishingPreset = "custom" | "instagram_reel" | "tiktok" | "youtube_short" | "linkedin_landscape" | "facebook_square";

export type Project = {
  readonly id: string;
  readonly name: string;
  readonly brief: string;
  readonly privacy_mode: PrivacyMode;
  readonly ai_copy_allowed: boolean;
  readonly created_at: string;
  readonly updated_at: string;
};

export type MediaJob = {
  readonly id: string;
  readonly project_id: string;
  readonly recipe: Recipe;
  readonly status: string;
  readonly revision: number;
  readonly target_duration_seconds: TargetDuration | null;
  readonly edit_style: EditStyle | null;
  readonly music_mode: MusicMode | null;
  readonly target_platform: TargetPlatform | null;
  readonly must_include: string;
  readonly audience: string;
  readonly story_goal: string;
  readonly desired_feeling: string;
  readonly ending_instruction: string;
  readonly editor_model: string | null;
  readonly reasoning_effort: ReasoningEffort;
  readonly output_aspect: OutputAspect;
  readonly creative_profile_id: string | null;
  readonly brand_kit_id: string | null;
  readonly publishing_preset: PublishingPreset;
  readonly cover_time_seconds: number;
  readonly created_at: string;
  readonly updated_at: string;
};

export type Asset = {
  readonly id: string;
  readonly project_id: string;
  readonly source_name: string;
  readonly storage_key: string;
  readonly mime_type: string | null;
  readonly byte_size: number | null;
  readonly status: string;
  readonly tus_upload_id: string | null;
  readonly sha256: string | null;
  readonly created_at: string;
  readonly updated_at: string;
};

export type LibraryAsset = {
  readonly id: string;
  readonly project_id: string;
  readonly project_name: string;
  readonly source_name: string;
  readonly mime_type: string;
  readonly byte_size: number;
  readonly sha256: string;
  readonly duration_seconds: number | null;
  readonly thumbnail_available: boolean;
  readonly created_at: string;
};

export type DuplicateAssetCopy = {
  readonly id: string;
  readonly project_id: string;
  readonly project_name: string;
  readonly source_name: string;
  readonly mime_type: string;
  readonly byte_size: number;
  readonly job_references: number;
  readonly thumbnail_available: boolean;
  readonly storage_optimized: boolean;
  readonly created_at: string;
};

export type DuplicateGroup = {
  readonly sha256: string;
  readonly media_kind: "video" | "image" | "audio";
  readonly mime_type: string;
  readonly byte_size: number;
  readonly copy_count: number;
  readonly reclaimable_bytes: number;
  readonly canonical_asset_id: string;
  readonly canonical_reason: string;
  readonly reviewed: boolean;
  readonly reviewed_at: string | null;
  readonly cleanup_ready: boolean;
  readonly optimized_copies: number;
  readonly copies: readonly DuplicateAssetCopy[];
};

export type DuplicateAudit = {
  readonly summary: {
    readonly originals_scanned: number;
    readonly duplicate_groups: number;
    readonly unreviewed_groups: number;
    readonly redundant_copies: number;
    readonly optimized_copies: number;
    readonly reclaimable_bytes: number;
  };
  readonly groups: readonly DuplicateGroup[];
};

export type CatalogSearchResult = {
  readonly segment_id: number;
  readonly asset_id: string;
  readonly project_id: string;
  readonly project_name: string;
  readonly source_name: string;
  readonly mime_type: string;
  readonly byte_size: number;
  readonly sha256: string;
  readonly duration_seconds: number | null;
  readonly thumbnail_available: boolean;
  readonly segment_kind: "asset" | "transcript" | "scene" | "image" | "visual";
  readonly start_seconds: number;
  readonly end_seconds: number;
  readonly text: string;
  readonly facts: Record<string, unknown>;
  readonly source_model: string;
  readonly rank: number;
  readonly evidence_kinds: readonly ("metadata" | "spoken_words" | "visual")[];
  readonly visual_frame_id: number | null;
  readonly visual_frame_seconds: number | null;
  readonly created_at: string;
};

export type CatalogSearch = {
  readonly query: string;
  readonly total: number;
  readonly results: readonly CatalogSearchResult[];
};

export type VisualIndexStatus = {
  readonly assets_total: number;
  readonly assets_ready: number;
  readonly assets_aliased: number;
  readonly assets_pending: number;
  readonly assets_failed: number;
  readonly frames_total: number;
  readonly model_id: string;
  readonly model_revision: string;
  readonly index_version: string;
  readonly local_only: boolean;
};

export type ManagedLibraryAsset = {
  readonly id: string;
  readonly project_id: string;
  readonly project_name: string;
  readonly source_name: string;
  readonly display_name: string;
  readonly notes: string;
  readonly favorite: boolean;
  readonly tags: readonly string[];
  readonly library_status: "active" | "archived";
  readonly mime_type: string;
  readonly byte_size: number;
  readonly sha256: string;
  readonly duration_seconds: number | null;
  readonly thumbnail_available: boolean;
  readonly job_references: number;
  readonly collection_count: number;
  readonly visual_status: string | null;
  readonly created_at: string;
  readonly updated_at: string;
};

export type LibraryEvidenceSegment = {
  readonly id: number;
  readonly segment_kind: "transcript" | "scene" | "image";
  readonly start_seconds: number;
  readonly end_seconds: number;
  readonly text: string;
  readonly source_model: string;
};

export type LibraryVisualFrame = {
  readonly id: number;
  readonly start_seconds: number;
  readonly end_seconds: number;
  readonly frame_seconds: number;
};

export type LibraryCollection = {
  readonly id: string;
  readonly name: string;
  readonly description: string;
  readonly asset_count: number;
  readonly created_at: string;
  readonly updated_at: string;
};

export type LibraryAssetDetail = {
  readonly asset: ManagedLibraryAsset;
  readonly evidence: readonly LibraryEvidenceSegment[];
  readonly visual_frames: readonly LibraryVisualFrame[];
  readonly collections: readonly LibraryCollection[];
};

export type MusicTrack = {
  readonly id: string;
  readonly title: string;
  readonly artist: string;
  readonly duration_seconds: number;
  readonly mood: string;
  readonly energy: "low" | "medium" | "high";
  readonly bpm: number | null;
  readonly beat_grid_seconds: readonly number[];
  readonly license_name: string;
  readonly license_source_url: string;
  readonly allowed_platforms: readonly TargetPlatform[];
  readonly attribution: string;
  readonly created_at: string;
};

export type EditRun = {
  readonly id: string;
  readonly job_id: string;
  readonly version: number;
  readonly status: "pending" | "planning" | "rendering" | "ready" | "failed";
  readonly attempts: number;
  readonly provider: string | null;
  readonly model: string | null;
  readonly reasoning_effort: ReasoningEffort | null;
  readonly based_on_run_id: string | null;
  readonly revision_note: string | null;
  readonly caption_corrections: readonly CaptionCorrection[];
  readonly approved_at: string | null;
  readonly preview_available: boolean;
  readonly manifest: Record<string, unknown>;
  readonly error: string | null;
  readonly started_at: string | null;
  readonly completed_at: string | null;
  readonly created_at: string;
  readonly updated_at: string;
};

export type CaptionCorrection = {
  readonly original_text: string;
  readonly replacement_text: string;
};

export type FinalExport = {
  readonly id: string;
  readonly job_id: string;
  readonly edit_run_id: string;
  readonly version: number;
  readonly status: "pending" | "rendering" | "ready" | "failed";
  readonly attempts: number;
  readonly files_available: boolean;
  readonly post_copy_available: boolean;
  readonly manifest: Record<string, unknown>;
  readonly error: string | null;
  readonly started_at: string | null;
  readonly completed_at: string | null;
  readonly created_at: string;
  readonly updated_at: string;
};

export type CreativeProfile = {
  readonly id: string;
  readonly name: string;
  readonly description: string;
  readonly recipe: Recipe;
  readonly target_duration_seconds: TargetDuration;
  readonly edit_style: EditStyle;
  readonly music_mode: MusicMode;
  readonly target_platform: TargetPlatform;
  readonly output_aspect: OutputAspect;
  readonly reasoning_effort: ReasoningEffort;
  readonly source_job_id: string | null;
  readonly brand_kit_id: string | null;
  readonly publishing_preset: PublishingPreset;
  readonly created_at: string;
  readonly updated_at: string;
};

export type BrandKit = {
  readonly id: string;
  readonly name: string;
  readonly primary_color: string;
  readonly accent_color: string;
  readonly caption_style: "clean" | "bold" | "minimal";
  readonly font_family: "sans" | "serif" | "mono";
  readonly created_at: string;
  readonly updated_at: string;
};

export type EditorialClip = {
  readonly clip_index: number;
  readonly asset_id: string;
  readonly source_name: string;
  readonly media_kind: "video" | "image";
  readonly source_in: number;
  readonly source_out: number;
  readonly duration: number;
  readonly transition: string;
  readonly visual_preset: "standard" | "punch_in" | "strong_punch_in" | "slow_push_in" | "slow_pull_out";
  readonly include_source_audio: boolean;
  readonly source_audio_gain_db: number;
  readonly transcript_excerpt: string;
  readonly story_role: "hook" | "context" | "development" | "payoff" | "reaction" | "ending";
  readonly editorial_intent: string;
};

export type DeliveryVariant = {
  readonly id: string;
  readonly job_id: string;
  readonly edit_run_id: string;
  readonly version: number;
  readonly output_aspect: OutputAspect;
  readonly target_duration_seconds: TargetDuration;
  readonly status: "pending" | "rendering" | "ready" | "failed";
  readonly attempts: number;
  readonly files_available: boolean;
  readonly post_copy_available: boolean;
  readonly manifest: Record<string, unknown>;
  readonly error: string | null;
  readonly started_at: string | null;
  readonly completed_at: string | null;
  readonly created_at: string;
  readonly updated_at: string;
};

export type JobEvent = {
  readonly id: number;
  readonly event_type: string;
  readonly payload: Record<string, unknown>;
  readonly created_at: string;
};

export type JobReview = {
  readonly job: MediaJob;
  readonly versions: readonly EditRun[];
  readonly latest_run: EditRun | null;
  readonly final_export: FinalExport | null;
  readonly delivery_variants: readonly DeliveryVariant[];
  readonly editorial_timeline: readonly EditorialClip[];
  readonly story_assessment: {
    readonly version: string;
    readonly coverage: Readonly<Record<"hook" | "context" | "development" | "payoff" | "ending", boolean>>;
    readonly gaps: readonly string[];
    readonly clean_spoken_edit_points: number;
    readonly duplicate_idea_groups: readonly (readonly { readonly text: string }[])[];
    readonly recommendations: readonly string[];
    readonly source_moments_considered: number;
    readonly hosted_model_calls: number;
  };
  readonly brand_kit: BrandKit | null;
  readonly events: readonly JobEvent[];
  readonly usage: JobUsage;
};

export type EditorModel = {
  readonly slug: string;
  readonly display_name: string;
  readonly provider: string;
  readonly available: boolean;
  readonly refreshed_at: string;
};

export type AiUsageEvent = {
  readonly id: string;
  readonly job_id: string;
  readonly edit_run_id: string;
  readonly provider: string;
  readonly model: string;
  readonly reasoning_effort: ReasoningEffort | null;
  readonly request_kind: string;
  readonly input_tokens: number;
  readonly cached_input_tokens: number;
  readonly output_tokens: number;
  readonly reasoning_tokens: number;
  readonly total_tokens: number;
  readonly latency_ms: number;
  readonly created_at: string;
};

export type JobUsage = {
  readonly requests: number;
  readonly input_tokens: number;
  readonly cached_input_tokens: number;
  readonly output_tokens: number;
  readonly reasoning_tokens: number;
  readonly total_tokens: number;
  readonly latency_ms: number;
  readonly events: readonly AiUsageEvent[];
};

export type UsageDashboard = {
  readonly days: number;
  readonly requests: number;
  readonly jobs: number;
  readonly input_tokens: number;
  readonly cached_input_tokens: number;
  readonly output_tokens: number;
  readonly reasoning_tokens: number;
  readonly total_tokens: number;
  readonly by_model: readonly { readonly model: string; readonly requests: number; readonly total_tokens: number }[];
  readonly job_history: readonly UsageJobSummary[];
};

export type UsageJobSummary = {
  readonly id: string;
  readonly project_name: string;
  readonly recipe: Recipe;
  readonly status: string;
  readonly created_at: string;
  readonly model: string | null;
  readonly requests: number;
  readonly total_tokens: number;
  readonly history_kind: "editing" | "verification";
};

export type ApplianceHealth = {
  readonly generated_at: string | null;
  readonly status: "healthy" | "attention" | "pending";
  readonly alerts: readonly string[];
  readonly disk?: { readonly total_bytes: number; readonly available_bytes: number; readonly used_percent: number };
  readonly gpu?: { readonly temperature_celsius: number | null };
  readonly services?: { readonly running: number; readonly expected: number };
  readonly queues?: Readonly<Record<string, number>>;
  readonly smart?: { readonly state: "passed" | "attention" | "unavailable" };
  readonly backup?: {
    readonly state: "ready" | "running" | "failed" | "stale" | "missing";
    readonly message: string;
    readonly started_at?: string | null;
    readonly completed_at?: string | null;
    readonly age_hours: number | null;
  };
  readonly offsite_backup?: {
    readonly state: "ready" | "running" | "failed" | "stale" | "missing" | "not_configured";
    readonly message: string;
    readonly configured: boolean;
    readonly started_at?: string | null;
    readonly completed_at?: string | null;
    readonly age_hours: number | null;
  };
  readonly reboot_recovery?: {
    readonly status: "passed" | "failed" | "running" | "not_run";
    readonly message: string;
    readonly completed_at?: string | null;
    readonly boot_id_changed?: boolean;
    readonly attempts?: number;
  };
};

export type StudioMember = {
  readonly login: string;
  readonly display_name: string;
  readonly role: "owner" | "editor" | "viewer";
  readonly active: boolean;
  readonly created_at: string;
  readonly updated_at: string;
};

export type AiBudget = {
  readonly allowed: boolean;
  readonly today_tokens: number;
  readonly month_tokens: number;
  readonly daily_limit: number;
  readonly monthly_limit: number;
};

export type StudioSettings = {
  readonly studio_name: string;
  readonly onboarding_completed: boolean;
  readonly daily_ai_token_limit: number;
  readonly monthly_ai_token_limit: number;
  readonly max_active_jobs: number;
  readonly preview_retention_days: number;
  readonly delivery_retention_days: number;
  readonly updated_at: string;
  readonly budget: AiBudget;
};

export type StudioOverview = {
  readonly settings: Omit<StudioSettings, "budget">;
  readonly counts: {
    readonly projects: number;
    readonly jobs: number;
    readonly assets: number;
    readonly deliveries: number;
    readonly brand_kits: number;
    readonly music_tracks: number;
    readonly editor_models: number;
    readonly members: number;
    readonly active_jobs: number;
  };
  readonly budget: AiBudget;
  readonly storage: {
    readonly original_logical_bytes: number;
    readonly original_physical_estimate_bytes: number;
    readonly preview_estimate_bytes: number;
    readonly delivery_estimate_bytes: number;
  };
  readonly retention: { readonly preview_records: number; readonly delivery_records: number; readonly originals_eligible: 0 };
  readonly readiness: Readonly<Record<"private_access" | "editor_connected" | "backup_monitoring" | "brand_ready" | "library_ready" | "first_delivery", boolean>>;
};

export type ManagedJob = {
  readonly id: string;
  readonly project_name: string;
  readonly brief: string;
  readonly recipe: Recipe;
  readonly status: string;
  readonly revision: number;
  readonly output_aspect: OutputAspect;
  readonly target_duration_seconds: number;
  readonly requests: number;
  readonly total_tokens: number;
  readonly delivered: boolean;
  readonly archived_at: string | null;
  readonly created_at: string;
  readonly updated_at: string;
};

export type StudioAuditEvent = {
  readonly id: number;
  readonly actor_login: string;
  readonly action: string;
  readonly target_type: string;
  readonly target_id: string;
  readonly details: Readonly<Record<string, unknown>>;
  readonly created_at: string;
};

async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/media/${path}`, {
    ...init,
    headers: {
      "content-type": "application/json",
      ...init?.headers,
    },
  });

  if (!response.ok) {
    const detail = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(detail?.detail ?? `Request failed with status ${response.status}`);
  }

  if (response.status === 204) return undefined as T;

  return (await response.json()) as T;
}

export function createProject(input: {
  readonly id?: string;
  readonly name: string;
  readonly brief: string;
  readonly privacyMode: PrivacyMode;
  readonly aiCopyAllowed: boolean;
}) {
  return apiRequest<Project>("projects", {
    method: "POST",
    body: JSON.stringify({
      id: input.id,
      name: input.name,
      brief: input.brief,
      privacy_mode: input.privacyMode,
      ai_copy_allowed: input.aiCopyAllowed,
    }),
  });
}

export function createMediaJob(
  projectId: string,
  input: {
    readonly id?: string;
    readonly recipe: Recipe;
    readonly targetDurationSeconds: TargetDuration;
    readonly editStyle: EditStyle;
    readonly musicMode: MusicMode;
    readonly targetPlatform: TargetPlatform;
    readonly mustInclude: string;
    readonly audience?: string;
    readonly storyGoal?: string;
    readonly desiredFeeling?: string;
    readonly endingInstruction?: string;
    readonly editorModel: string | null;
    readonly reasoningEffort: ReasoningEffort;
    readonly outputAspect: OutputAspect;
    readonly creativeProfileId?: string | null;
    readonly brandKitId?: string | null;
    readonly publishingPreset?: PublishingPreset;
  },
) {
  return apiRequest<MediaJob>(`projects/${projectId}/jobs`, {
    method: "POST",
    body: JSON.stringify({
      id: input.id,
      recipe: input.recipe,
      target_duration_seconds: input.targetDurationSeconds,
      edit_style: input.editStyle,
      music_mode: input.musicMode,
      target_platform: input.targetPlatform,
      must_include: input.mustInclude,
      audience: input.audience ?? "",
      story_goal: input.storyGoal ?? "",
      desired_feeling: input.desiredFeeling ?? "",
      ending_instruction: input.endingInstruction ?? "",
      editor_model: input.editorModel,
      reasoning_effort: input.reasoningEffort,
      output_aspect: input.outputAspect,
      creative_profile_id: input.creativeProfileId ?? null,
      brand_kit_id: input.brandKitId ?? null,
      publishing_preset: input.publishingPreset ?? "custom",
    }),
  });
}

const MEDIA_TYPES_BY_EXTENSION: Readonly<Record<string, string>> = {
  aac: "audio/aac",
  heic: "image/heic",
  heif: "image/heif",
  jpeg: "image/jpeg",
  jpg: "image/jpeg",
  m4a: "audio/mp4",
  mov: "video/quicktime",
  mp3: "audio/mpeg",
  mp4: "video/mp4",
  png: "image/png",
  wav: "audio/wav",
  webm: "video/webm",
};

export function mediaTypeForFile(file: File): string {
  const declared = file.type.trim().toLowerCase();
  if (declared.startsWith("video/") || declared.startsWith("image/") || declared.startsWith("audio/")) {
    return declared;
  }

  const extension = file.name.split(".").at(-1)?.toLowerCase() ?? "";
  const inferred = MEDIA_TYPES_BY_EXTENSION[extension];
  if (inferred === undefined) {
    throw new Error(`${file.name} does not have a supported video, photo, or audio type`);
  }
  return inferred;
}

export function registerAsset(projectId: string, jobId: string, file: File, id?: string) {
  const mimeType = mediaTypeForFile(file);

  return apiRequest<Asset>(`projects/${projectId}/assets`, {
    method: "POST",
    body: JSON.stringify({
      id,
      job_id: jobId,
      source_name: file.name,
      mime_type: mimeType,
      byte_size: file.size,
    }),
  });
}

export function getAsset(assetId: string) {
  return apiRequest<Asset>(`assets/${assetId}`, { cache: "no-store" });
}

export function getServerLibraryAssets() {
  return apiRequest<readonly LibraryAsset[]>("assets/library?limit=500", { cache: "no-store" });
}

export function attachServerAssets(jobId: string, assetIds: readonly string[]) {
  return apiRequest<{ readonly job_id: string; readonly asset_ids: readonly string[]; readonly attached_count: number }>(
    `jobs/${jobId}/assets`,
    {
      method: "POST",
      body: JSON.stringify({ asset_ids: assetIds }),
    },
  );
}

export function libraryAssetThumbnailUrl(assetId: string) {
  return `/api/media/assets/${encodeURIComponent(assetId)}/thumbnail`;
}

export function getDuplicateAudit(input: {
  readonly query?: string;
  readonly reviewState?: "all" | "unreviewed" | "reviewed";
  readonly sort?: "most_storage" | "most_copies" | "newest";
} = {}) {
  const parameters = new URLSearchParams({
    query: input.query ?? "",
    review_state: input.reviewState ?? "all",
    sort: input.sort ?? "most_storage",
    limit: "250",
  });
  return apiRequest<DuplicateAudit>(`assets/duplicates?${parameters.toString()}`, { cache: "no-store" });
}

export function reviewDuplicateGroup(sha256: string, canonicalAssetId: string) {
  return apiRequest<{
    readonly sha256: string;
    readonly canonical_asset_id: string;
    readonly asset_count: number;
    readonly reviewed_at: string;
  }>(`assets/duplicates/${encodeURIComponent(sha256)}/review`, {
    method: "POST",
    body: JSON.stringify({ canonical_asset_id: canonicalAssetId }),
  });
}

export function cleanupDuplicateGroup(sha256: string, canonicalAssetId: string) {
  return apiRequest<{
    readonly sha256: string;
    readonly canonical_asset_id: string;
    readonly optimized_asset_ids: readonly string[];
    readonly optimized_copies: number;
    readonly bytes_reclaimed: number;
    readonly already_optimized: number;
  }>(`assets/duplicates/${encodeURIComponent(sha256)}/cleanup`, {
    method: "POST",
    body: JSON.stringify({
      canonical_asset_id: canonicalAssetId,
      confirmation: "share_verified_storage",
    }),
  });
}

export function searchCatalog(input: {
  readonly query: string;
  readonly mediaKind?: "all" | "video" | "image" | "audio";
  readonly projectId?: string;
  readonly limit?: number;
}) {
  const parameters = new URLSearchParams({
    query: input.query,
    media_kind: input.mediaKind ?? "all",
    limit: String(input.limit ?? 100),
  });
  if (input.projectId !== undefined && input.projectId !== "all") {
    parameters.set("project_id", input.projectId);
  }
  return apiRequest<CatalogSearch>(`catalog/search?${parameters.toString()}`, { cache: "no-store" });
}

export function getVisualIndexStatus() {
  return apiRequest<VisualIndexStatus>("catalog/visual/status", { cache: "no-store" });
}

export function visualIndexFrameUrl(frameId: number) {
  return `/api/media/catalog/visual/frames/${encodeURIComponent(String(frameId))}`;
}

export function getManagedLibraryAssets(input: {
  readonly query?: string;
  readonly state?: "active" | "archived" | "all";
  readonly mediaKind?: "all" | "video" | "image" | "audio";
  readonly favorite?: boolean;
  readonly tag?: string;
} = {}) {
  const parameters = new URLSearchParams({
    query: input.query ?? "",
    state: input.state ?? "active",
    media_kind: input.mediaKind ?? "all",
    limit: "500",
  });
  if (input.favorite !== undefined) parameters.set("favorite", String(input.favorite));
  if (input.tag) parameters.set("tag", input.tag);
  return apiRequest<readonly ManagedLibraryAsset[]>(`library/assets?${parameters.toString()}`, { cache: "no-store" });
}

export function getLibraryAssetDetail(assetId: string) {
  return apiRequest<LibraryAssetDetail>(`library/assets/${encodeURIComponent(assetId)}`, { cache: "no-store" });
}

export function updateLibraryAsset(assetId: string, input: {
  readonly displayName: string;
  readonly notes: string;
  readonly favorite: boolean;
  readonly tags: readonly string[];
}) {
  return apiRequest<ManagedLibraryAsset>(`library/assets/${encodeURIComponent(assetId)}`, {
    method: "PATCH",
    body: JSON.stringify({
      display_name: input.displayName,
      notes: input.notes,
      favorite: input.favorite,
      tags: input.tags,
    }),
  });
}

export function setLibraryAssetState(assetId: string, state: "active" | "archived") {
  return apiRequest<{ readonly asset_id: string; readonly library_status: "active" | "archived" }>(
    `library/assets/${encodeURIComponent(assetId)}/${state === "active" ? "restore" : "archive"}`,
    { method: "POST", body: "{}" },
  );
}

export function libraryAssetPreviewUrl(assetId: string) {
  return `/api/media/library/assets/${encodeURIComponent(assetId)}/preview`;
}

export function getLibraryCollections() {
  return apiRequest<readonly LibraryCollection[]>("library/collections", { cache: "no-store" });
}

export function createLibraryCollection(name: string, description = "") {
  return apiRequest<LibraryCollection>("library/collections", {
    method: "POST",
    body: JSON.stringify({ name, description }),
  });
}

export function setLibraryCollectionMembership(collectionId: string, assetId: string, selected: boolean) {
  return apiRequest<undefined>(
    `library/collections/${encodeURIComponent(collectionId)}/assets/${encodeURIComponent(assetId)}`,
    { method: selected ? "PUT" : "DELETE", body: selected ? "{}" : undefined },
  );
}

export function getMusicTracks() {
  return apiRequest<readonly MusicTrack[]>("music-tracks", { cache: "no-store" });
}

export function getEditorModels() {
  return apiRequest<readonly EditorModel[]>("editor/models", { cache: "no-store" });
}

export function getCreativeProfiles() {
  return apiRequest<readonly CreativeProfile[]>("creative-profiles", { cache: "no-store" });
}

export function createCreativeProfile(input: Omit<CreativeProfile, "id" | "created_at" | "updated_at">) {
  return apiRequest<CreativeProfile>("creative-profiles", { method: "POST", body: JSON.stringify(input) });
}

export function updateCreativeProfile(profileId: string, name: string, description = "") {
  return apiRequest<CreativeProfile>(`creative-profiles/${profileId}`, {
    method: "PUT",
    body: JSON.stringify({ name, description }),
  });
}

export function deleteCreativeProfile(profileId: string) {
  return apiRequest<void>(`creative-profiles/${profileId}`, { method: "DELETE" });
}

export function getBrandKits() {
  return apiRequest<readonly BrandKit[]>("brand-kits", { cache: "no-store" });
}

export function saveBrandKit(input: Omit<BrandKit, "id" | "created_at" | "updated_at">, id?: string) {
  return apiRequest<BrandKit>(id ? `brand-kits/${id}` : "brand-kits", {
    method: id ? "PUT" : "POST",
    body: JSON.stringify(input),
  });
}

export function deleteBrandKit(id: string) {
  return apiRequest<void>(`brand-kits/${id}`, { method: "DELETE" });
}

export function saveCreativeProfileFromJob(jobId: string, name: string, description = "") {
  return apiRequest<CreativeProfile>(`jobs/${jobId}/creative-profile`, {
    method: "POST",
    body: JSON.stringify({ name, description }),
  });
}

export function requestDeliveryVariant(
  jobId: string,
  input: { readonly outputAspect: OutputAspect; readonly targetDurationSeconds: TargetDuration },
) {
  return apiRequest<DeliveryVariant>(`jobs/${jobId}/variants`, {
    method: "POST",
    body: JSON.stringify({
      output_aspect: input.outputAspect,
      target_duration_seconds: input.targetDurationSeconds,
    }),
  });
}

export function getUsageDashboard(days = 0) {
  return apiRequest<UsageDashboard>(`usage?days=${days}`, { cache: "no-store" });
}

export function requestPreview(jobId: string) {
  return apiRequest<EditRun>(`jobs/${jobId}/preview`, {
    method: "POST",
    body: "{}",
  });
}

export function getPreview(jobId: string) {
  return apiRequest<EditRun>(`jobs/${jobId}/preview`, { cache: "no-store" });
}

export function getJobReview(jobId: string) {
  return apiRequest<JobReview>(`jobs/${jobId}/review`, { cache: "no-store" });
}

export function requestRevision(
  jobId: string,
  input: {
    readonly note: string;
    readonly captionCorrections: readonly CaptionCorrection[];
    readonly clipAdjustments?: readonly {
      readonly clip_index: number;
      readonly action: "keep" | "remove" | "move_up" | "move_down";
      readonly visual_preset?: EditorialClip["visual_preset"];
      readonly source_audio_gain_db?: number;
    }[];
    readonly lockedElements?: readonly string[];
  },
) {
  return apiRequest<EditRun>(`jobs/${jobId}/revisions`, {
    method: "POST",
    body: JSON.stringify({
      note: input.note,
      caption_corrections: input.captionCorrections,
      clip_adjustments: input.clipAdjustments ?? [],
      locked_elements: input.lockedElements ?? [],
    }),
  });
}

export function approveEdit(jobId: string, version: number) {
  return apiRequest<FinalExport>(`jobs/${jobId}/approval`, {
    method: "POST",
    body: JSON.stringify({ version, note: "Approved from the GM Studio phone review." }),
  });
}

export function updateCoverFrame(jobId: string, timeSeconds: number) {
  return apiRequest<MediaJob>(`jobs/${jobId}/cover-frame`, {
    method: "PUT",
    body: JSON.stringify({ time_seconds: timeSeconds }),
  });
}

export function getSystemInformation() {
  return apiRequest<{ readonly service: string; readonly version: string }>("system", {
    cache: "no-store",
  });
}

export function getApplianceHealth() {
  return apiRequest<ApplianceHealth>("system/health", { cache: "no-store" });
}

export function getStudioOverview() {
  return apiRequest<StudioOverview>("studio/overview", { cache: "no-store" });
}

export function getStudioSettings() {
  return apiRequest<StudioSettings>("studio/settings", { cache: "no-store" });
}

export function saveStudioSettings(input: Omit<StudioSettings, "updated_at" | "budget">) {
  return apiRequest<StudioSettings>("studio/settings", { method: "PUT", body: JSON.stringify(input) });
}

export function getCurrentMember() {
  return apiRequest<StudioMember>("members/me", { cache: "no-store" });
}

export function getStudioMembers() {
  return apiRequest<readonly StudioMember[]>("members", { cache: "no-store" });
}

export function createStudioMember(input: { readonly login: string; readonly display_name: string; readonly role: "editor" | "viewer" }) {
  return apiRequest<StudioMember>("members", { method: "POST", body: JSON.stringify(input) });
}

export function updateStudioMember(login: string, input: { readonly display_name: string; readonly role: "editor" | "viewer"; readonly active: boolean }) {
  return apiRequest<StudioMember>(`members/${encodeURIComponent(login)}`, { method: "PUT", body: JSON.stringify(input) });
}

export function deleteStudioMember(login: string) {
  return apiRequest<void>(`members/${encodeURIComponent(login)}`, { method: "DELETE" });
}

export function getManagedJobs(state: "active" | "archived" | "all" = "active", query = "") {
  const parameters = new URLSearchParams({ state, query });
  return apiRequest<readonly ManagedJob[]>(`jobs/manage?${parameters.toString()}`, { cache: "no-store" });
}

export function setJobArchived(jobId: string, archived: boolean) {
  return apiRequest<{ readonly id: string; readonly archived_at: string | null }>(`jobs/${jobId}/${archived ? "archive" : "restore"}`, { method: "POST", body: "{}" });
}

export function applyRetention() {
  return apiRequest<{ readonly id: string; readonly preview_files_removed: number; readonly delivery_files_removed: number; readonly bytes_reclaimed: number; readonly originals_removed: 0 }>("studio/retention/apply", { method: "POST", body: JSON.stringify({ confirmation: "remove_reproducible_derived_files" }) });
}

export function getStudioAudit() {
  return apiRequest<readonly StudioAuditEvent[]>("studio/audit?limit=100", { cache: "no-store" });
}
