export type PrivacyMode = "hybrid" | "text_only" | "local_only";
export type EditStyle = "clean" | "energetic" | "calm";
export type MusicMode = "none" | "subtle" | "present";
export type TargetDuration = 20 | 30 | 45 | 60;
export type TargetPlatform = "all_social" | "facebook" | "instagram" | "linkedin" | "tiktok" | "youtube";

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
  readonly recipe: "talking_head";
  readonly status: string;
  readonly revision: number;
  readonly target_duration_seconds: TargetDuration | null;
  readonly edit_style: EditStyle | null;
  readonly music_mode: MusicMode | null;
  readonly target_platform: TargetPlatform | null;
  readonly must_include: string;
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

export type MusicTrack = {
  readonly id: string;
  readonly title: string;
  readonly artist: string;
  readonly duration_seconds: number;
  readonly mood: string;
  readonly energy: "low" | "medium" | "high";
  readonly bpm: number | null;
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
  readonly events: readonly JobEvent[];
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

export function createTalkingHeadJob(
  projectId: string,
  input: {
    readonly id?: string;
    readonly targetDurationSeconds: TargetDuration;
    readonly editStyle: EditStyle;
    readonly musicMode: MusicMode;
    readonly targetPlatform: TargetPlatform;
    readonly mustInclude: string;
  },
) {
  return apiRequest<MediaJob>(`projects/${projectId}/jobs`, {
    method: "POST",
    body: JSON.stringify({
      id: input.id,
      recipe: "talking_head",
      target_duration_seconds: input.targetDurationSeconds,
      edit_style: input.editStyle,
      music_mode: input.musicMode,
      target_platform: input.targetPlatform,
      must_include: input.mustInclude,
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

export function getMusicTracks() {
  return apiRequest<readonly MusicTrack[]>("music-tracks", { cache: "no-store" });
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
  },
) {
  return apiRequest<EditRun>(`jobs/${jobId}/revisions`, {
    method: "POST",
    body: JSON.stringify({
      note: input.note,
      caption_corrections: input.captionCorrections,
    }),
  });
}

export function approveEdit(jobId: string, version: number) {
  return apiRequest<FinalExport>(`jobs/${jobId}/approval`, {
    method: "POST",
    body: JSON.stringify({ version, note: "Approved from the GM Studio phone review." }),
  });
}

export function getSystemInformation() {
  return apiRequest<{ readonly service: string; readonly version: string }>("system", {
    cache: "no-store",
  });
}
