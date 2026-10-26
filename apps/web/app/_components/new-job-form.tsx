"use client";

import { Component, type DragEvent, type ErrorInfo, type FormEvent, type ReactNode } from "react";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import type { Upload } from "tus-js-client";
import {
  ArrowRightIcon,
  AudioLinesIcon,
  CheckIcon,
  CircleAlertIcon,
  FolderIcon,
  ImageIcon,
  LoaderCircleIcon,
  PauseIcon,
  PlayIcon,
  RefreshCwIcon,
  SearchIcon,
  Trash2Icon,
  UploadCloudIcon,
  VideoIcon,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  attachServerAssets,
  createProject,
  createMediaJob,
  getCreativeProfiles,
  getCreativeAssets,
  getBrandKits,
  getEditorModels,
  getAsset,
  getMusicTracks,
  getServerLibraryAssets,
  getSystemInformation,
  getVisualIndexStatus,
  libraryAssetThumbnailUrl,
  mediaTypeForFile,
  registerAsset,
  requestPreview,
  searchCatalog,
  visualIndexFrameUrl,
  type Asset,
  type CatalogSearchResult,
  type CreativeProfile,
  type CreativeAsset,
  type BrandKit,
  type PublishingPreset,
  type EditStyle,
  type EffectLevel,
  type EditorModel,
  type MusicMode,
  type MusicTrack,
  type LibraryAsset,
  type PrivacyMode,
  type OutputAspect,
  type ReasoningEffort,
  type Recipe,
  type TargetDuration,
  type TargetPlatform,
  type VisualIndexStatus,
} from "@/lib/media-api";
import { startResumableUpload } from "@/lib/resumable-upload";
import { cn } from "@/lib/utils";

const MAX_FILE_BYTES = 20 * 1024 * 1024 * 1024;
const READY_POLL_ATTEMPTS = 45;
const READY_POLL_INTERVAL_MS = 1_000;

type ServerStatus = "checking" | "online" | "offline";
type LibraryKind = "all" | "video" | "image" | "audio";
type UploadPhase =
  | "queued"
  | "registering"
  | "uploading"
  | "paused"
  | "processing"
  | "ready"
  | "error";

type UploadEntry = {
  readonly localId: string;
  readonly assetRequestId: string;
  readonly file: File;
  readonly mediaType: string;
  readonly assetId?: string;
  readonly phase: UploadPhase;
  readonly uploadedBytes: number;
  readonly totalBytes: number;
  readonly uploadComplete: boolean;
  readonly uploadBytesPerSecond?: number;
  readonly uploadEtaSeconds?: number;
  readonly retryAttempt?: number;
  readonly error?: string;
};

const PRIVACY_OPTIONS: ReadonlyArray<{
  readonly value: PrivacyMode;
  readonly label: string;
  readonly description: string;
}> = [
  {
    value: "hybrid",
    label: "Hybrid",
    description: "A hosted editor may see transcript text and selected low-resolution frames. Originals stay here.",
  },
  {
    value: "text_only",
    label: "Text only",
    description: "A hosted editor may see transcript and metadata, but no images or original files.",
  },
  {
    value: "local_only",
    label: "Local only",
    description: "No media-derived material leaves this server; editing uses local fixed recipes.",
  },
];

const EDIT_STYLE_OPTIONS: ReadonlyArray<{
  readonly value: EditStyle;
  readonly label: string;
  readonly description: string;
}> = [
  {
    value: "clean",
    label: "Clean",
    description: "Stable framing, restrained punch-ins and simple cuts.",
  },
  {
    value: "energetic",
    label: "Energetic",
    description: "Faster pacing, emphasis punch-ins and occasional dip transitions.",
  },
  {
    value: "calm",
    label: "Calm",
    description: "Longer thoughts with subtle push-ins and pull-outs.",
  },
  {
    value: "high_impact",
    label: "High impact",
    description: "Picture or sound accents around every 2–3 seconds, with punch-ins and relevant B-roll over continuous speech.",
  },
];

const MUSIC_OPTIONS: ReadonlyArray<{
  readonly value: MusicMode;
  readonly label: string;
  readonly description: string;
}> = [
  { value: "none", label: "No music", description: "Voice only." },
  {
    value: "subtle",
    label: "Subtle",
    description: "Use a rights-approved local track quietly under speech when available.",
  },
  {
    value: "present",
    label: "Present",
    description: "Use a more noticeable approved track with automatic speech ducking.",
  },
];

const PLATFORM_OPTIONS: ReadonlyArray<{
  readonly value: TargetPlatform;
  readonly label: string;
}> = [
  { value: "all_social", label: "All social platforms" },
  { value: "instagram", label: "Instagram / Reels" },
  { value: "tiktok", label: "TikTok" },
  { value: "youtube", label: "YouTube Shorts" },
  { value: "facebook", label: "Facebook" },
  { value: "linkedin", label: "LinkedIn" },
];

function toErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Something went wrong";
}

function viewportSnapshot() {
  if (typeof window === "undefined") return undefined;
  const shell = document.querySelector<HTMLElement>("[data-gm-job-shell]")?.getBoundingClientRect();
  const body = document.body.getBoundingClientRect();
  const visual = window.visualViewport;
  return {
    innerWidth: window.innerWidth,
    innerHeight: window.innerHeight,
    clientWidth: document.documentElement.clientWidth,
    clientHeight: document.documentElement.clientHeight,
    bodyWidth: body.width,
    bodyHeight: body.height,
    bodyTop: body.top,
    shellWidth: shell?.width ?? null,
    shellHeight: shell?.height ?? null,
    shellTop: shell?.top ?? null,
    shellBottom: shell?.bottom ?? null,
    visualWidth: visual?.width ?? null,
    visualHeight: visual?.height ?? null,
    visualOffsetTop: visual?.offsetTop ?? null,
    visualOffsetLeft: visual?.offsetLeft ?? null,
    scrollY: window.scrollY,
    scrollHeight: document.documentElement.scrollHeight,
  };
}

function resetRootScroll() {
  if (typeof window === "undefined") return;
  window.scrollTo({ top: 0, left: 0, behavior: "auto" });
  document.documentElement.scrollTop = 0;
  document.body.scrollTop = 0;
}

function settleRootScroll() {
  resetRootScroll();
  window.requestAnimationFrame(resetRootScroll);
  window.setTimeout(resetRootScroll, 100);
}

function reportClientDiagnostic(event: string, details: Record<string, unknown> = {}) {
  if (typeof window === "undefined") return;
  const payload = {
    event,
    href: window.location.pathname,
    userAgent: window.navigator.userAgent,
    visibility: document.visibilityState,
    viewport: viewportSnapshot(),
    ...details,
  };
  void fetch("/api/client-diagnostics", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload),
    keepalive: true,
  }).catch(() => undefined);
}

class NewJobErrorBoundary extends Component<
  { readonly children: ReactNode },
  { readonly error?: string }
> {
  state: { readonly error?: string } = {};

  static getDerivedStateFromError(error: unknown) {
    return { error: toErrorMessage(error) };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    reportClientDiagnostic("react-render-error", {
      message: error.message,
      stack: `${error.stack ?? ""}\n${info.componentStack ?? ""}`,
    });
  }

  render() {
    if (this.state.error === undefined) return this.props.children;
    return (
      <main className="flex min-h-screen items-center justify-center bg-[#F7F7F5] p-6 text-[#20211F] [color-scheme:light]">
        <div className="w-full max-w-md rounded-md border border-[#D7D9D3] bg-white p-5">
          <p className="font-mono text-xs font-bold tracking-wide text-[#C54B35] uppercase">Phone display error</p>
          <h1 className="mt-2 text-xl font-bold text-[#173F5F]">GM Studio could not draw this screen</h1>
          <p className="mt-3 text-sm leading-relaxed text-[#666862]">{this.state.error}</p>
          <Button className="mt-5 h-11 w-full bg-[#173F5F] text-white hover:bg-[#12344F]" onClick={() => window.location.reload()} type="button">
            Reload GM Studio
          </Button>
        </div>
      </main>
    );
  }
}

function delay(milliseconds: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const unitIndex = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const value = bytes / 1024 ** unitIndex;
  const digits = value >= 10 || unitIndex === 0 ? 0 : 1;
  return `${value.toFixed(digits)} ${units[unitIndex]}`;
}

function fileIdentity(file: File): string {
  return [file.name, file.size, file.lastModified].join(":");
}

function formatDuration(seconds: number | null): string | undefined {
  if (seconds === null || !Number.isFinite(seconds) || seconds <= 0) return undefined;
  const rounded = Math.round(seconds);
  const minutes = Math.floor(rounded / 60);
  const remainder = rounded % 60;
  return minutes > 0 ? `${minutes}:${remainder.toString().padStart(2, "0")}` : `${remainder}s`;
}

function formatLibraryDate(value: string): string {
  return new Intl.DateTimeFormat(undefined, { day: "numeric", month: "short", year: "numeric" }).format(
    new Date(value),
  );
}

function formatCatalogTime(seconds: number): string {
  const rounded = Math.max(0, Math.floor(seconds));
  const minutes = Math.floor(rounded / 60);
  return `${minutes}:${(rounded % 60).toString().padStart(2, "0")}`;
}

function catalogResultAsAsset(result: CatalogSearchResult): LibraryAsset {
  return {
    id: result.asset_id,
    project_id: result.project_id,
    project_name: result.project_name,
    source_name: result.source_name,
    mime_type: result.mime_type,
    byte_size: result.byte_size,
    sha256: result.sha256,
    duration_seconds: result.duration_seconds,
    thumbnail_available: result.thumbnail_available,
    created_at: result.created_at,
  };
}

function phaseLabel(entry: UploadEntry): string {
  const percent =
    entry.totalBytes === 0 ? 0 : Math.min(100, Math.round((entry.uploadedBytes / entry.totalBytes) * 100));

  switch (entry.phase) {
    case "queued":
      return "Queued";
    case "registering":
      return "Preparing";
    case "uploading":
      if (entry.retryAttempt) return `Retrying connection (${entry.retryAttempt}) · ${percent}%`;
      if (entry.uploadBytesPerSecond && entry.uploadEtaSeconds !== undefined) {
        const remaining = entry.uploadEtaSeconds < 60
          ? `${Math.max(1, Math.ceil(entry.uploadEtaSeconds))}s`
          : `${Math.ceil(entry.uploadEtaSeconds / 60)}m`;
        return `Uploading ${percent}% · ${formatBytes(entry.uploadBytesPerSecond)}/s · about ${remaining} left`;
      }
      return `Uploading ${percent}% · measuring speed`;
    case "paused":
      return `Paused at ${percent}%`;
    case "processing":
      return "Verifying on server";
    case "ready":
      return "Ready";
    case "error":
      return "Needs attention";
  }
}

function FileTypeIcon({ mediaType }: { readonly mediaType: string }) {
  if (mediaType.startsWith("image/")) return <ImageIcon aria-hidden="true" className="size-4" />;
  if (mediaType.startsWith("audio/")) return <AudioLinesIcon aria-hidden="true" className="size-4" />;
  return <VideoIcon aria-hidden="true" className="size-4" />;
}

function SectionHeading({ number, children }: { readonly number: string; readonly children: string }) {
  return (
    <div className="flex items-center gap-3">
      <span className="flex size-6 items-center justify-center rounded-sm border border-[#173F5F] font-mono text-xs font-bold text-[#173F5F]">
        {number}
      </span>
      <h2 className="font-mono text-xs font-bold tracking-wider text-[#666862] uppercase">{children}</h2>
    </div>
  );
}

function RecipeCard({
  name,
  detail,
  selected = false,
  disabled = false,
  value,
  onChange,
}: {
  readonly name: string;
  readonly detail: string;
  readonly selected?: boolean;
  readonly disabled?: boolean;
  readonly value: Recipe;
  readonly onChange: (value: Recipe) => void;
}) {
  return (
    <label
      className={cn(
        "flex min-h-16 w-full items-center justify-between rounded-md bg-white p-4 text-left",
        selected ? "border-2 border-[#173F5F]" : "border border-[#D7D9D3]",
        disabled && "cursor-not-allowed bg-[#F7F7F5] opacity-55",
      )}
    >
      <span>
        <span className={cn("block font-bold", selected ? "text-[#173F5F]" : "text-[#666862]")}>{name}</span>
        <span className="mt-1 block font-mono text-xs text-[#666862]">{detail}</span>
      </span>
      <span className="flex items-center gap-2">
        {disabled ? (
          <span className="font-mono text-[10px] font-bold tracking-wide text-[#666862] uppercase">Later</span>
        ) : null}
        <input
          aria-label={name}
          checked={selected}
          className="size-5 accent-[#173F5F]"
          disabled={disabled}
          name="recipe"
          onChange={() => onChange(value)}
          type="radio"
          value={value}
        />
      </span>
    </label>
  );
}

function PrivacyCard({
  description,
  disabled,
  label,
  selected,
  value,
  onChange,
}: {
  readonly description: string;
  readonly disabled: boolean;
  readonly label: string;
  readonly selected: boolean;
  readonly value: PrivacyMode;
  readonly onChange: (value: PrivacyMode) => void;
}) {
  return (
    <label
      className={cn(
        "block min-h-20 rounded-md bg-white p-3",
        selected ? "border-2 border-[#173F5F]" : "border border-[#D7D9D3]",
        disabled ? "cursor-not-allowed opacity-60" : "cursor-pointer",
      )}
    >
      <span className="flex items-center gap-2">
        <input
          checked={selected}
          className="size-5 accent-[#173F5F]"
          disabled={disabled}
          name="privacy"
          onChange={() => onChange(value)}
          type="radio"
          value={value}
        />
        <span className="text-sm font-bold text-[#173F5F]">{label}</span>
      </span>
      <span className="mt-1 block pl-7 text-xs leading-relaxed text-[#666862]">{description}</span>
    </label>
  );
}

function CreativeOptionCard({
  description,
  disabled,
  label,
  name,
  selected,
  value,
  onChange,
}: {
  readonly description: string;
  readonly disabled: boolean;
  readonly label: string;
  readonly name: string;
  readonly selected: boolean;
  readonly value: string;
  readonly onChange: () => void;
}) {
  return (
    <label
      className={cn(
        "block rounded-md bg-white p-3",
        selected ? "border-2 border-[#173F5F]" : "border border-[#D7D9D3]",
        disabled ? "cursor-not-allowed opacity-60" : "cursor-pointer",
      )}
    >
      <span className="flex items-center gap-2">
        <input
          checked={selected}
          className="size-5 accent-[#173F5F]"
          disabled={disabled}
          name={name}
          onChange={onChange}
          type="radio"
          value={value}
        />
        <span className="text-sm font-bold text-[#173F5F]">{label}</span>
      </span>
      <span className="mt-1 block pl-7 text-xs leading-relaxed text-[#666862]">{description}</span>
    </label>
  );
}

function UploadAction({
  entry,
  onPause,
  onRemove,
  onResume,
  onRetry,
}: {
  readonly entry: UploadEntry;
  readonly onPause: (entry: UploadEntry) => void;
  readonly onRemove: (entry: UploadEntry) => void;
  readonly onResume: (entry: UploadEntry) => void;
  readonly onRetry: (entry: UploadEntry) => void;
}) {
  const commonClass =
    "size-11 border-[#D7D9D3] bg-white text-[#20211F] hover:bg-[#F7F7F5] dark:bg-white dark:text-[#20211F]";

  if (entry.phase === "uploading") {
    return (
      <Button aria-label={`Pause ${entry.file.name}`} className={commonClass} onClick={() => onPause(entry)} size="icon" type="button" variant="outline">
        <PauseIcon aria-hidden="true" />
      </Button>
    );
  }
  if (entry.phase === "paused") {
    return (
      <Button aria-label={`Resume ${entry.file.name}`} className={commonClass} onClick={() => onResume(entry)} size="icon" type="button" variant="outline">
        <PlayIcon aria-hidden="true" />
      </Button>
    );
  }
  if (entry.phase === "error") {
    return (
      <Button aria-label={`Retry ${entry.file.name}`} className={commonClass} onClick={() => onRetry(entry)} size="icon" type="button" variant="outline">
        <RefreshCwIcon aria-hidden="true" />
      </Button>
    );
  }
  if (entry.phase === "queued") {
    return (
      <Button aria-label={`Remove ${entry.file.name}`} className={commonClass} onClick={() => onRemove(entry)} size="icon" type="button" variant="outline">
        <Trash2Icon aria-hidden="true" />
      </Button>
    );
  }
  if (entry.phase === "ready") {
    return (
      <span aria-label={`${entry.file.name} is ready`} className="flex size-11 items-center justify-center text-[#173F5F]">
        <CheckIcon aria-hidden="true" className="size-5" />
      </span>
    );
  }
  return (
    <span aria-label={`${entry.file.name} is being processed`} className="flex size-11 items-center justify-center text-[#173F5F]">
      <LoaderCircleIcon aria-hidden="true" className="size-5 animate-spin motion-reduce:animate-none" />
    </span>
  );
}

function UploadRow({
  entry,
  onPause,
  onRemove,
  onResume,
  onRetry,
}: {
  readonly entry: UploadEntry;
  readonly onPause: (entry: UploadEntry) => void;
  readonly onRemove: (entry: UploadEntry) => void;
  readonly onResume: (entry: UploadEntry) => void;
  readonly onRetry: (entry: UploadEntry) => void;
}) {
  const percent =
    entry.totalBytes === 0 ? 0 : Math.min(100, Math.round((entry.uploadedBytes / entry.totalBytes) * 100));
  const showProgress = entry.phase !== "queued" && entry.phase !== "registering" && entry.phase !== "ready";

  return (
    <li className="space-y-2 rounded-sm border border-[#D7D9D3] bg-white p-3 dark:bg-white">
      <div className="flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2 text-[#666862]">
          <FileTypeIcon mediaType={entry.mediaType} />
          <div className="min-w-0">
            <p className="truncate font-mono text-xs font-bold text-[#20211F]">{entry.file.name}</p>
            <p className="mt-0.5 font-mono text-[10px] text-[#666862]">
              {formatBytes(entry.file.size)} · {phaseLabel(entry)}
            </p>
          </div>
        </div>
        <UploadAction entry={entry} onPause={onPause} onRemove={onRemove} onResume={onResume} onRetry={onRetry} />
      </div>
      {showProgress ? (
        <div
          aria-label={`${entry.file.name} upload progress`}
          aria-valuemax={100}
          aria-valuemin={0}
          aria-valuenow={percent}
          className="h-1.5 overflow-hidden rounded-full bg-[#E9EDF0]"
          role="progressbar"
        >
          <div className="h-full bg-[#173F5F] transition-[width] motion-reduce:transition-none" style={{ width: `${percent}%` }} />
        </div>
      ) : null}
      {entry.error ? (
        <p className="flex items-start gap-1.5 text-xs leading-relaxed text-[#A23B2A]" role="alert">
          <CircleAlertIcon aria-hidden="true" className="mt-0.5 size-3.5 shrink-0" />
          {entry.error}
        </p>
      ) : null}
    </li>
  );
}

function LibraryAssetRow({
  asset,
  disabled,
  match,
  selected,
  onChange,
}: {
  readonly asset: LibraryAsset;
  readonly disabled: boolean;
  readonly match?: CatalogSearchResult;
  readonly selected: boolean;
  readonly onChange: (asset: LibraryAsset) => void;
}) {
  const duration = formatDuration(asset.duration_seconds);
  const visualMatch = match?.evidence_kinds.includes("visual") ?? false;
  const spokenMatch = match?.evidence_kinds.includes("spoken_words") ?? false;
  const thumbnailUrl = match?.visual_frame_id !== null && match?.visual_frame_id !== undefined
    ? visualIndexFrameUrl(match.visual_frame_id)
    : libraryAssetThumbnailUrl(asset.id);
  return (
    <label
      className={cn(
        "flex min-h-20 items-center gap-3 rounded-md bg-white p-3",
        selected ? "border-2 border-[#173F5F]" : "border border-[#D7D9D3]",
        disabled ? "cursor-not-allowed opacity-60" : "cursor-pointer",
      )}
    >
      <span className="flex size-14 shrink-0 items-center justify-center overflow-hidden rounded-sm bg-[#E9EDF0] text-[#173F5F]">
        {asset.thumbnail_available ? (
          <img
            alt=""
            className="h-full w-full object-cover"
            loading="lazy"
            src={thumbnailUrl}
          />
        ) : (
          <FileTypeIcon mediaType={asset.mime_type} />
        )}
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate font-mono text-xs font-bold text-[#20211F]">{asset.source_name}</span>
        <span className="mt-1 block truncate font-mono text-[10px] text-[#666862]">
          {[formatBytes(asset.byte_size), duration, asset.project_name].filter(Boolean).join(" · ")}
        </span>
        <span className="mt-1 block font-mono text-[10px] text-[#666862]">{formatLibraryDate(asset.created_at)}</span>
        {match !== undefined ? (
          <span className="mt-2 flex flex-wrap gap-1.5">
            {visualMatch ? (
              <span className="rounded-sm border border-[#BFD2DE] bg-[#EFF6FA] px-1.5 py-1 font-mono text-[9px] font-bold text-[#173F5F] uppercase">
                Visual match
              </span>
            ) : null}
            {spokenMatch ? (
              <span className="rounded-sm border border-[#BFD2DE] bg-[#EFF6FA] px-1.5 py-1 font-mono text-[9px] font-bold text-[#173F5F] uppercase">
                Spoken words
              </span>
            ) : null}
          </span>
        ) : null}
        {match?.segment_kind === "transcript" ? (
          <span className="mt-2 block rounded-sm border-l-2 border-[#173F5F] bg-[#EFF6FA] px-2 py-1.5 text-xs leading-relaxed text-[#314553]">
            “{match.text}”
            <span className="mt-1 block font-mono text-[9px] font-bold text-[#173F5F] uppercase">
              Spoken at {formatCatalogTime(match.start_seconds)}–{formatCatalogTime(match.end_seconds)} · source transcript
            </span>
          </span>
        ) : visualMatch && match !== undefined ? (
          <span className="mt-2 block font-mono text-[9px] font-bold text-[#173F5F] uppercase">
            Seen at {formatCatalogTime(match.start_seconds)}–{formatCatalogTime(match.end_seconds)} · source frame
          </span>
        ) : match !== undefined ? (
          <span className="mt-2 block font-mono text-[9px] font-bold text-[#173F5F] uppercase">
            Catalogue match · {match.segment_kind}
          </span>
        ) : null}
      </span>
      <input
        aria-label={`Use ${asset.source_name}`}
        checked={selected}
        className="size-5 shrink-0 accent-[#173F5F]"
        disabled={disabled}
        onChange={() => onChange(asset)}
        type="checkbox"
      />
    </label>
  );
}

function NewJobFormContent() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [brief, setBrief] = useState("");
  const [privacyMode, setPrivacyMode] = useState<PrivacyMode>("hybrid");
  const [aiCopyAllowed, setAiCopyAllowed] = useState(false);
  const [recipe, setRecipe] = useState<Recipe>("talking_head");
  const [targetDuration, setTargetDuration] = useState<TargetDuration>(45);
  const [editStyle, setEditStyle] = useState<EditStyle>("energetic");
  const [musicMode, setMusicMode] = useState<MusicMode>("none");
  const [selectedMusicTrackId, setSelectedMusicTrackId] = useState<string | null>(null);
  const [effectLevel, setEffectLevel] = useState<EffectLevel>("off");
  const [targetPlatform, setTargetPlatform] = useState<TargetPlatform>("all_social");
  const [mustInclude, setMustInclude] = useState("");
  const [audience, setAudience] = useState("");
  const [storyGoal, setStoryGoal] = useState("");
  const [desiredFeeling, setDesiredFeeling] = useState("");
  const [endingInstruction, setEndingInstruction] = useState("");
  const [editorModels, setEditorModels] = useState<readonly EditorModel[]>([]);
  const [editorModel, setEditorModel] = useState<string | null>(null);
  const [reasoningEffort, setReasoningEffort] = useState<ReasoningEffort>("medium");
  const [outputAspect, setOutputAspect] = useState<OutputAspect>("vertical");
  const [creativeProfiles, setCreativeProfiles] = useState<readonly CreativeProfile[]>([]);
  const [creativeProfileId, setCreativeProfileId] = useState<string | null>(null);
  const [brandKits, setBrandKits] = useState<readonly BrandKit[]>([]);
  const [brandKitId, setBrandKitId] = useState<string | null>(null);
  const [publishingPreset, setPublishingPreset] = useState<PublishingPreset>("custom");
  const [musicTracks, setMusicTracks] = useState<readonly MusicTrack[]>([]);
  const [creativeAssets, setCreativeAssets] = useState<readonly CreativeAsset[]>([]);
  const [entries, setEntries] = useState<UploadEntry[]>([]);
  const [libraryAssets, setLibraryAssets] = useState<readonly LibraryAsset[]>([]);
  const [selectedLibraryAssetIds, setSelectedLibraryAssetIds] = useState<ReadonlySet<string>>(new Set());
  const [libraryQuery, setLibraryQuery] = useState("");
  const [libraryKind, setLibraryKind] = useState<LibraryKind>("all");
  const [libraryProjectId, setLibraryProjectId] = useState("all");
  const [libraryLoading, setLibraryLoading] = useState(true);
  const [libraryError, setLibraryError] = useState<string>();
  const [catalogMatches, setCatalogMatches] = useState<ReadonlyMap<string, CatalogSearchResult>>(new Map());
  const [catalogSearching, setCatalogSearching] = useState(false);
  const [catalogSearchError, setCatalogSearchError] = useState<string>();
  const [visualIndexStatus, setVisualIndexStatus] = useState<VisualIndexStatus>();
  const [serverStatus, setServerStatus] = useState<ServerStatus>("checking");
  const [formError, setFormError] = useState<string>();
  const [fileError, setFileError] = useState<string>();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [projectId, setProjectId] = useState<string>();
  const [jobId, setJobId] = useState<string>();
  const uploadHandlesRef = useRef(new Map<string, Upload>());
  const lastProgressRef = useRef(new Map<string, number>());
  const projectRequestIdRef = useRef<string | undefined>(undefined);
  const jobRequestIdRef = useRef<string | undefined>(undefined);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    let cancelled = false;
    void Promise.all([getSystemInformation(), getMusicTracks(), getCreativeAssets(true), getEditorModels(), getCreativeProfiles(), getBrandKits()])
      .then(([, tracks, effects, models, profiles, kits]) => {
        if (!cancelled) {
          setMusicTracks(tracks);
          setCreativeAssets(effects);
          setEditorModels(models);
          setCreativeProfiles(profiles);
          setBrandKits(kits);
          setEditorModel((current) => current ?? models[0]?.slug ?? null);
          setServerStatus("online");
        }
      })
      .catch(() => {
        if (!cancelled) setServerStatus("offline");
      });
    void getServerLibraryAssets()
      .then((assets) => {
        if (!cancelled) {
          setLibraryAssets(assets);
          setLibraryLoading(false);
          setLibraryError(undefined);
        }
      })
      .catch((error) => {
        if (!cancelled) {
          setLibraryLoading(false);
          setLibraryError(toErrorMessage(error));
        }
      });
    return () => {
      cancelled = true;
      mountedRef.current = false;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;

    const refreshVisualIndexStatus = () => {
      void getVisualIndexStatus()
        .then((status) => {
          if (cancelled) return;
          setVisualIndexStatus(status);
          if (status.assets_pending > 0) {
            timer = window.setTimeout(refreshVisualIndexStatus, 5000);
          }
        })
        .catch(() => {
          if (!cancelled) timer = window.setTimeout(refreshVisualIndexStatus, 15000);
        });
    };

    refreshVisualIndexStatus();
    return () => {
      cancelled = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, []);

  useEffect(() => {
    const query = libraryQuery.trim();
    if (query.length < 2) {
      setCatalogMatches(new Map());
      setCatalogSearching(false);
      setCatalogSearchError(undefined);
      return;
    }
    let cancelled = false;
    setCatalogSearching(true);
    setCatalogSearchError(undefined);
    const timer = window.setTimeout(() => {
      void searchCatalog({
        query,
        mediaKind: libraryKind,
        projectId: libraryProjectId,
      }).then((search) => {
        if (cancelled) return;
        const matches = new Map<string, CatalogSearchResult>();
        for (const result of search.results) {
          if (!matches.has(result.asset_id)) matches.set(result.asset_id, result);
        }
        setCatalogMatches(matches);
        setLibraryAssets((current) => {
          const assets = new Map(current.map((asset) => [asset.id, asset]));
          for (const result of matches.values()) {
            if (!assets.has(result.asset_id)) assets.set(result.asset_id, catalogResultAsAsset(result));
          }
          return Array.from(assets.values());
        });
        setCatalogSearching(false);
      }).catch((error: unknown) => {
        if (cancelled) return;
        setCatalogMatches(new Map());
        setCatalogSearching(false);
        setCatalogSearchError(toErrorMessage(error));
      });
    }, 250);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [libraryKind, libraryProjectId, libraryQuery]);

  useEffect(() => {
    settleRootScroll();
    reportClientDiagnostic("job-screen-mounted");
    const reportVisibility = () => {
      if (document.visibilityState === "visible") settleRootScroll();
      reportClientDiagnostic(`visibility-${document.visibilityState}`);
    };
    const reportFocus = () => {
      settleRootScroll();
      reportClientDiagnostic("window-focus");
    };
    const reportPageShow = () => {
      settleRootScroll();
      reportClientDiagnostic("page-show");
    };
    const reportResize = () => {
      resetRootScroll();
      reportClientDiagnostic("viewport-resize");
    };
    const guardRootScroll = () => {
      if (window.scrollY !== 0) resetRootScroll();
    };
    const reportError = (event: ErrorEvent) => {
      reportClientDiagnostic("window-error", {
        message: event.message,
        stack: event.error instanceof Error ? event.error.stack : undefined,
      });
    };
    const reportRejection = (event: PromiseRejectionEvent) => {
      reportClientDiagnostic("unhandled-rejection", {
        message: toErrorMessage(event.reason),
        stack: event.reason instanceof Error ? event.reason.stack : undefined,
      });
    };

    document.addEventListener("visibilitychange", reportVisibility);
    window.addEventListener("focus", reportFocus);
    window.addEventListener("pageshow", reportPageShow);
    window.addEventListener("resize", reportResize);
    window.addEventListener("scroll", guardRootScroll, { passive: true });
    window.addEventListener("error", reportError);
    window.addEventListener("unhandledrejection", reportRejection);
    window.visualViewport?.addEventListener("resize", reportResize);
    return () => {
      document.removeEventListener("visibilitychange", reportVisibility);
      window.removeEventListener("focus", reportFocus);
      window.removeEventListener("pageshow", reportPageShow);
      window.removeEventListener("resize", reportResize);
      window.removeEventListener("scroll", guardRootScroll);
      window.removeEventListener("error", reportError);
      window.removeEventListener("unhandledrejection", reportRejection);
      window.visualViewport?.removeEventListener("resize", reportResize);
    };
  }, []);

  const selectedLibraryAssets = libraryAssets.filter((asset) => selectedLibraryAssetIds.has(asset.id));
  const totalItems = entries.length + selectedLibraryAssets.length;
  const totalBytes = entries.reduce((total, entry) => total + entry.file.size, 0)
    + selectedLibraryAssets.reduce((total, asset) => total + asset.byte_size, 0);
  const allReady = totalItems > 0 && entries.every((entry) => entry.phase === "ready");
  const formLocked = projectId !== undefined;
  const compatibleMusicCount = musicTracks.filter(
    (track) =>
      track.allowed_platforms.includes("all_social")
      || track.allowed_platforms.includes(targetPlatform),
  ).length;
  const compatibleEffectCount = creativeAssets.filter(
    (asset) => asset.allowed_platforms.includes("all_social")
      || asset.allowed_platforms.includes(targetPlatform),
  ).length;
  const durationOptions: readonly TargetDuration[] = recipe === "montage" ? [15, 30, 45, 60] : [20, 30, 45, 60];
  const libraryProjects = Array.from(
    new Map(libraryAssets.map((asset) => [asset.project_id, asset.project_name])).entries(),
  ).sort((left, right) => left[1].localeCompare(right[1]));
  const normalizedLibraryQuery = libraryQuery.trim().toLocaleLowerCase();
  const filteredLibraryAssets = libraryAssets
    .filter((asset) => {
      const matchesQuery = normalizedLibraryQuery.length === 0
        || asset.source_name.toLocaleLowerCase().includes(normalizedLibraryQuery)
        || asset.project_name.toLocaleLowerCase().includes(normalizedLibraryQuery)
        || catalogMatches.has(asset.id);
      const matchesKind = libraryKind === "all" || asset.mime_type.startsWith(`${libraryKind}/`);
      const matchesProject = libraryProjectId === "all" || asset.project_id === libraryProjectId;
      return matchesQuery && matchesKind && matchesProject;
    })
    .sort((left, right) => {
      const leftMatch = catalogMatches.get(left.id);
      const rightMatch = catalogMatches.get(right.id);
      if (leftMatch !== undefined && rightMatch !== undefined) {
        return rightMatch.rank - leftMatch.rank;
      }
      if (leftMatch !== undefined) return -1;
      if (rightMatch !== undefined) return 1;
      return new Date(right.created_at).getTime() - new Date(left.created_at).getTime();
    });

  const selectRecipe = (selected: Recipe) => {
    setRecipe(selected);
    setFormError(undefined);
    if (selected === "montage") {
      setTargetDuration(30);
    } else if (targetDuration === 15) {
      setTargetDuration(20);
    }
  };

  const updateEntry = (localId: string, changes: Partial<UploadEntry>) => {
    if (!mountedRef.current) return;
    setEntries((current) =>
      current.map((entry) => (entry.localId === localId ? { ...entry, ...changes } : entry)),
    );
  };

  const pollUntilReady = async (entry: UploadEntry, assetId: string) => {
    for (let attempt = 0; attempt < READY_POLL_ATTEMPTS; attempt += 1) {
      if (!mountedRef.current) return;
      try {
        const asset = await getAsset(assetId);
        if (asset.status === "ready") {
          updateEntry(entry.localId, {
            assetId,
            phase: "ready",
            uploadedBytes: entry.totalBytes,
            uploadComplete: true,
            error: undefined,
          });
          return;
        }
        if (asset.status === "failed") {
          updateEntry(entry.localId, {
            assetId,
            phase: "error",
            uploadComplete: true,
            error: "The server could not verify this file. Retry the status check or choose the file again.",
          });
          return;
        }
      } catch (error) {
        if (attempt === READY_POLL_ATTEMPTS - 1) {
          updateEntry(entry.localId, {
            assetId,
            phase: "error",
            uploadComplete: true,
            error: `The upload finished, but its server status is unavailable: ${toErrorMessage(error)}`,
          });
          return;
        }
      }
      await delay(READY_POLL_INTERVAL_MS);
    }

    updateEntry(entry.localId, {
      assetId,
      phase: "error",
      uploadComplete: true,
      error: "The upload finished, but server verification is taking longer than expected. Check again.",
    });
  };

  const startUpload = async (entry: UploadEntry, asset: Asset) => {
    updateEntry(entry.localId, {
      assetId: asset.id,
      phase: "uploading",
      error: undefined,
    });
    lastProgressRef.current.set(entry.localId, -1);

    const upload = await startResumableUpload(entry.file, asset, {
      onProgress(uploadedBytes, totalUploadBytes, bytesPerSecond, etaSeconds) {
        const percent = totalUploadBytes === 0 ? 0 : Math.floor((uploadedBytes / totalUploadBytes) * 100);
        if (lastProgressRef.current.get(entry.localId) === percent) return;
        lastProgressRef.current.set(entry.localId, percent);
        updateEntry(entry.localId, {
          phase: "uploading",
          uploadedBytes,
          totalBytes: totalUploadBytes,
          uploadBytesPerSecond: bytesPerSecond,
          uploadEtaSeconds: etaSeconds,
          retryAttempt: undefined,
          error: undefined,
        });
      },
      onRetry(attempt) {
        updateEntry(entry.localId, {
          phase: "uploading",
          retryAttempt: attempt,
          uploadBytesPerSecond: undefined,
          uploadEtaSeconds: undefined,
          error: undefined,
        });
      },
      onError(error) {
        updateEntry(entry.localId, {
          phase: "error",
          error: error.message,
        });
      },
      onSuccess() {
        updateEntry(entry.localId, {
          assetId: asset.id,
          phase: "processing",
          uploadedBytes: entry.totalBytes,
          uploadComplete: true,
          error: undefined,
        });
        void pollUntilReady(entry, asset.id);
      },
    });
    uploadHandlesRef.current.set(entry.localId, upload);
  };

  const registerAndStart = async (
    entry: UploadEntry,
    activeProjectId: string,
    activeJobId: string,
  ) => {
    updateEntry(entry.localId, { phase: "registering", error: undefined });
    try {
      const asset = await registerAsset(
        activeProjectId,
        activeJobId,
        entry.file,
        entry.assetRequestId,
      );
      await startUpload(entry, asset);
    } catch (error) {
      updateEntry(entry.localId, {
        phase: "error",
        error: toErrorMessage(error),
      });
    }
  };

  const queueFiles = (files: File[]) => {
    const existing = new Set(entries.map((entry) => fileIdentity(entry.file)));
    const added: UploadEntry[] = [];
    const rejected: string[] = [];

    for (const file of files) {
      try {
        if (file.size <= 0) throw new Error(`${file.name} is empty`);
        if (file.size > MAX_FILE_BYTES) throw new Error(`${file.name} is larger than 20 GB`);
        if (file.name.length > 255) throw new Error(`${file.name} has a name longer than 255 characters`);
        const mediaType = mediaTypeForFile(file);
        const identity = fileIdentity(file);
        if (existing.has(identity)) throw new Error(`${file.name} is already selected`);
        existing.add(identity);
        added.push({
          localId: crypto.randomUUID(),
          assetRequestId: crypto.randomUUID(),
          file,
          mediaType,
          phase: "queued",
          uploadedBytes: 0,
          totalBytes: file.size,
          uploadComplete: false,
        });
      } catch (error) {
        rejected.push(toErrorMessage(error));
      }
    }

    setFileError(rejected.length > 0 ? rejected.join(" ") : undefined);
    if (added.length === 0) return;
    setFormError(undefined);
    setEntries((current) => [...current, ...added]);

    if (projectId !== undefined && jobId !== undefined) {
      for (const entry of added) void registerAndStart(entry, projectId, jobId);
    }
  };

  const toggleLibraryAsset = (asset: LibraryAsset) => {
    if (formLocked) return;
    setSelectedLibraryAssetIds((current) => {
      const next = new Set(current);
      if (next.has(asset.id)) {
        next.delete(asset.id);
      } else {
        next.add(asset.id);
      }
      return next;
    });
    setFormError(undefined);
  };

  const handleDrop = (event: DragEvent<HTMLLabelElement>) => {
    event.preventDefault();
    queueFiles(Array.from(event.dataTransfer.files));
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const cleanName = name.trim();
    const cleanBrief = brief.trim();
    if (cleanName.length === 0) {
      setFormError("Enter a project name.");
      return;
    }
    if (totalItems === 0) {
      setFormError("Select server media or add at least one new file.");
      return;
    }
    if (recipe === "talking_head" && /\bmontage\b/i.test(cleanBrief)) {
      setFormError("Your brief asks for a montage. Select the Montage recipe, then submit again.");
      return;
    }

    setIsSubmitting(true);
    setFormError(undefined);
    try {
      let activeProjectId = projectId;
      if (activeProjectId === undefined) {
        projectRequestIdRef.current ??= crypto.randomUUID();
        const project = await createProject({
          id: projectRequestIdRef.current,
          name: cleanName,
          brief: cleanBrief,
          privacyMode,
          aiCopyAllowed,
        });
        activeProjectId = project.id;
        setProjectId(project.id);
        setServerStatus("online");
      }

      let activeJobId = jobId;
      if (activeJobId === undefined) {
        jobRequestIdRef.current ??= crypto.randomUUID();
        const job = await createMediaJob(activeProjectId, {
          id: jobRequestIdRef.current,
          recipe,
          targetDurationSeconds: targetDuration,
          editStyle,
          musicMode,
          selectedMusicTrackId,
          effectLevel,
          targetPlatform,
          mustInclude: mustInclude.trim(),
          audience: audience.trim(),
          storyGoal: storyGoal.trim(),
          desiredFeeling: desiredFeeling.trim(),
          endingInstruction: endingInstruction.trim(),
          editorModel,
          reasoningEffort,
          outputAspect,
          creativeProfileId,
          brandKitId,
          publishingPreset,
        });
        activeJobId = job.id;
      }

      if (selectedLibraryAssetIds.size > 0) {
        await attachServerAssets(activeJobId, Array.from(selectedLibraryAssetIds));
      }
      setJobId(activeJobId);

      const queuedEntries = entries.filter((entry) => entry.phase === "queued");
      await Promise.all(
        queuedEntries.map((entry) => registerAndStart(entry, activeProjectId, activeJobId)),
      );
    } catch (error) {
      setFormError(toErrorMessage(error));
    } finally {
      setIsSubmitting(false);
    }
  };

  const pauseUpload = async (entry: UploadEntry) => {
    const upload = uploadHandlesRef.current.get(entry.localId);
    if (upload === undefined) return;
    try {
      await upload.abort();
      updateEntry(entry.localId, { phase: "paused", error: undefined });
    } catch (error) {
      updateEntry(entry.localId, { phase: "error", error: toErrorMessage(error) });
    }
  };

  const resumeUpload = (entry: UploadEntry) => {
    const upload = uploadHandlesRef.current.get(entry.localId);
    if (upload === undefined) {
      if (projectId !== undefined && jobId !== undefined) {
        void registerAndStart(entry, projectId, jobId);
      }
      return;
    }
    updateEntry(entry.localId, { phase: "uploading", error: undefined });
    upload.start();
  };

  const retryUpload = (entry: UploadEntry) => {
    if (entry.uploadComplete && entry.assetId !== undefined) {
      updateEntry(entry.localId, { phase: "processing", error: undefined });
      void pollUntilReady(entry, entry.assetId);
      return;
    }
    resumeUpload(entry);
  };

  const removeUpload = (entry: UploadEntry) => {
    setEntries((current) => current.filter((candidate) => candidate.localId !== entry.localId));
    setFileError(undefined);
  };

  const startEditing = async () => {
    if (jobId === undefined || !allReady) return;
    setIsSubmitting(true);
    setFormError(undefined);
    try {
      await requestPreview(jobId);
      router.push(`/jobs/${jobId}`);
    } catch (error) {
      setFormError(toErrorMessage(error));
      setIsSubmitting(false);
    }
  };

  const statusCopy =
    serverStatus === "online"
      ? "Private · Online"
      : serverStatus === "offline"
        ? "Server unavailable"
        : "Checking server";

  return (
    <form
      aria-busy={isSubmitting}
      className="flex h-dvh min-h-0 w-full flex-col overflow-hidden overscroll-none bg-[#F7F7F5] text-[#20211F] [color-scheme:light]"
      data-gm-job-shell
      onSubmit={handleSubmit}
    >
      <header className="z-40 shrink-0 border-b border-[#D7D9D3] bg-[#F7F7F5] px-4 pt-[max(1rem,env(safe-area-inset-top))] pb-3">
        <div className="mb-1 flex items-center justify-between gap-3">
          <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1">
            <Link className="text-sm font-bold tracking-tight text-[#173F5F]" href="/">GM Studio</Link>
            <Link className="font-mono text-[10px] font-bold text-[#173F5F] underline underline-offset-4" href="/jobs">
              Jobs
            </Link>
            <Link className="font-mono text-[10px] font-bold text-[#173F5F] underline underline-offset-4" href="/prompts">
              Prompts
            </Link>
            <Link className="font-mono text-[10px] font-bold text-[#173F5F] underline underline-offset-4" href="/usage">
              AI usage
            </Link>
            <Link className="font-mono text-[10px] font-bold text-[#173F5F] underline underline-offset-4" href="/library">
              Library
            </Link>
            <Link className="hidden font-mono text-[10px] font-bold text-[#173F5F] underline underline-offset-4 sm:inline" href="/settings">
              Brand &amp; presets
            </Link>
            <Link className="hidden font-mono text-[10px] font-bold text-[#173F5F] underline underline-offset-4 md:inline" href="/system">
              System
            </Link>
            <Link className="hidden font-mono text-[10px] font-bold text-[#173F5F] underline underline-offset-4 sm:inline" href="/library/duplicates">
              Duplicate audit
            </Link>
          </div>
          <Badge className="rounded-sm border-[#D7D9D3] bg-white px-2 py-1 font-mono text-[10px] font-bold text-[#173F5F] uppercase dark:bg-white" variant="outline">
            <span
              aria-hidden="true"
              className={cn(
                "size-1.5 rounded-full",
                serverStatus === "online"
                  ? "bg-[#3A8F63]"
                  : serverStatus === "offline"
                    ? "bg-[#FF8C69]"
                    : "bg-[#F4D35E]",
              )}
            />
            {statusCopy}
          </Badge>
        </div>
        <p className="font-mono text-[10px] text-[#666862]">Source-led editing · originals stay on this server</p>
      </header>

      <main className="min-h-0 flex-1 touch-pan-y space-y-10 overflow-y-auto overscroll-contain px-4 py-8">
        <section className="space-y-3">
          <h1 className="text-2xl font-bold tracking-tight text-[#173F5F]">Start a new edit</h1>
          <p className="text-sm leading-relaxed text-[#666862]">
            Agents plan the edit. Visuals and speech come only from your selected media; optional music comes from your approved local library.
          </p>
        </section>

        <fieldset className="space-y-4" disabled={formLocked}>
          <legend className="sr-only">Recipe</legend>
          <SectionHeading number="01">Recipe</SectionHeading>
          <div className="space-y-2">
            <RecipeCard
              detail="20–60 sec · transcript-led"
              name="Talking-head Reel"
              onChange={selectRecipe}
              selected={recipe === "talking_head"}
              value="talking_head"
            />
            <RecipeCard
              detail="15–60 sec · video + photos"
              name="Montage"
              onChange={selectRecipe}
              selected={recipe === "montage"}
              value="montage"
            />
          </div>
        </fieldset>

        <section className="space-y-4">
          <SectionHeading number="02">Direction</SectionHeading>
          <div className="space-y-5">
            {creativeProfiles.length > 0 ? (
              <div className="space-y-2 rounded-md border border-[#BFE3FF] bg-[#F4FAFE] p-4">
                <label className="text-xs font-bold text-[#173F5F]" htmlFor="creative-profile">
                  CREATIVE PROFILE
                </label>
                <select
                  className="h-12 w-full rounded-md border border-[#D7D9D3] bg-white px-3 text-sm text-[#20211F] focus:border-[#173F5F] focus:outline-none focus:ring-2 focus:ring-[#173F5F]/20"
                  disabled={formLocked}
                  id="creative-profile"
                  onChange={(event) => {
                    const profile = creativeProfiles.find((item) => item.id === event.currentTarget.value);
                    setCreativeProfileId(profile?.id ?? null);
                    if (profile) {
                      setRecipe(profile.recipe);
                      setTargetDuration(profile.target_duration_seconds);
                      setEditStyle(profile.edit_style);
                      setMusicMode(profile.music_mode);
                      setSelectedMusicTrackId(null);
                      setTargetPlatform(profile.target_platform);
                      if (!creativeAssets.some((asset) => asset.allowed_platforms.includes("all_social") || asset.allowed_platforms.includes(profile.target_platform))) setEffectLevel("off");
                      else if (profile.edit_style === "high_impact" && effectLevel === "off" && privacyMode !== "local_only") setEffectLevel("social");
                      setOutputAspect(profile.output_aspect);
                      setReasoningEffort(profile.reasoning_effort);
                      setBrandKitId(profile.brand_kit_id);
                      setPublishingPreset(profile.publishing_preset);
                    }
                  }}
                  value={creativeProfileId ?? ""}
                >
                  <option value="">No saved profile</option>
                  {creativeProfiles.map((profile) => (
                    <option key={profile.id} value={profile.id}>{profile.name}</option>
                  ))}
                </select>
                <p className="text-xs leading-relaxed text-[#666862]">
                  Applies your saved recipe, pacing, music, platform, shape and reasoning settings. You can still adjust them below.
                </p>
              </div>
            ) : null}
            <div className="grid gap-4 rounded-md border border-[#D7D9D3] bg-white p-4 sm:grid-cols-2">
              <div className="space-y-2">
                <label className="text-xs font-bold text-[#173F5F]" htmlFor="publishing-preset">PUBLISHING PRESET</label>
                <select
                  className="h-12 w-full rounded-md border border-[#D7D9D3] bg-white px-3 text-sm"
                  disabled={formLocked}
                  id="publishing-preset"
                  onChange={(event) => {
                    const preset = event.currentTarget.value as PublishingPreset;
                    setPublishingPreset(preset);
                    if (preset === "instagram_reel") { setTargetPlatform("instagram"); setOutputAspect("vertical"); setTargetDuration(30); }
                    if (preset === "tiktok") { setTargetPlatform("tiktok"); setOutputAspect("vertical"); setTargetDuration(30); }
                    if (preset === "youtube_short") { setTargetPlatform("youtube"); setOutputAspect("vertical"); setTargetDuration(45); }
                    if (preset === "linkedin_landscape") { setTargetPlatform("linkedin"); setOutputAspect("landscape"); setTargetDuration(30); }
                    if (preset === "facebook_square") { setTargetPlatform("facebook"); setOutputAspect("square"); setTargetDuration(30); }
                  }}
                  value={publishingPreset}
                >
                  <option value="custom">Custom settings</option>
                  <option value="instagram_reel">Instagram Reel · 9:16 · 30s</option>
                  <option value="tiktok">TikTok · 9:16 · 30s</option>
                  <option value="youtube_short">YouTube Short · 9:16 · 45s</option>
                  <option value="linkedin_landscape">LinkedIn · 16:9 · 30s</option>
                  <option value="facebook_square">Facebook · 1:1 · 30s</option>
                </select>
              </div>
              <div className="space-y-2">
                <label className="text-xs font-bold text-[#173F5F]" htmlFor="brand-kit">BRAND KIT</label>
                <select
                  className="h-12 w-full rounded-md border border-[#D7D9D3] bg-white px-3 text-sm"
                  disabled={formLocked}
                  id="brand-kit"
                  onChange={(event) => setBrandKitId(event.currentTarget.value || null)}
                  value={brandKitId ?? ""}
                >
                  <option value="">GM Studio default</option>
                  {brandKits.map((kit) => <option key={kit.id} value={kit.id}>{kit.name}</option>)}
                </select>
              </div>
              <p className="text-xs leading-relaxed text-[#666862] sm:col-span-2">
                Presets set the platform, shape and duration. Brand kits apply your caption colours, weight and typeface.
              </p>
            </div>
            <div className="space-y-2">
              <label className="flex justify-between text-xs font-bold text-[#173F5F]" htmlFor="project-name">
                <span>PROJECT NAME</span>
                <span className="text-[10px] text-[#C54B35]">REQUIRED</span>
              </label>
              <Input
                aria-invalid={formError === "Enter a project name."}
                className="h-12 rounded-sm border-[#D7D9D3] bg-white text-[#20211F] shadow-none focus-visible:border-[#173F5F] focus-visible:ring-[#173F5F]/20 dark:bg-white dark:text-[#20211F]"
                disabled={formLocked}
                id="project-name"
                maxLength={160}
                onChange={(event) => {
                  setName(event.currentTarget.value);
                  setFormError(undefined);
                }}
                placeholder="e.g. Spring launch interview"
                required
                value={name}
              />
            </div>
            <div className="space-y-2">
              <label className="text-xs font-bold text-[#173F5F]" htmlFor="project-brief">
                BRIEF
              </label>
              <Textarea
                className="min-h-28 rounded-sm border-[#D7D9D3] bg-white text-[#20211F] shadow-none focus-visible:border-[#173F5F] focus-visible:ring-[#173F5F]/20 dark:bg-white dark:text-[#20211F]"
                disabled={formLocked}
                id="project-brief"
                maxLength={4000}
                onChange={(event) => {
                  setBrief(event.currentTarget.value);
                  setFormError(undefined);
                }}
                placeholder="Describe the audience, key message, tone and intended platform…"
                value={brief}
              />
            </div>
            <fieldset className="rounded-md border border-[#D7D9D3] bg-[#EFF6FA] p-4" disabled={formLocked}>
              <legend className="px-2 font-mono text-xs font-bold tracking-wide text-[#173F5F] uppercase">
                Story direction
              </legend>
              <p className="mb-4 text-xs leading-relaxed text-[#53646F]">
                Optional answers give the editor a clear hook, payoff and ending. They reuse local source analysis and do not add another model call.
              </p>
              <div className="grid gap-4 sm:grid-cols-2">
                <label className="text-xs font-bold text-[#173F5F]" htmlFor="story-audience">
                  WHO IS THIS FOR?
                  <Input className="mt-2 h-11 bg-white" id="story-audience" maxLength={600} onChange={(event) => setAudience(event.currentTarget.value)} placeholder="e.g. First-time home buyers" value={audience} />
                </label>
                <label className="text-xs font-bold text-[#173F5F]" htmlFor="story-feeling">
                  HOW SHOULD THEY FEEL?
                  <Input className="mt-2 h-11 bg-white" id="story-feeling" maxLength={600} onChange={(event) => setDesiredFeeling(event.currentTarget.value)} placeholder="e.g. Curious, then reassured" value={desiredFeeling} />
                </label>
                <label className="text-xs font-bold text-[#173F5F] sm:col-span-2" htmlFor="story-goal">
                  WHAT SHOULD THEY UNDERSTAND?
                  <Textarea className="mt-2 min-h-20 bg-white" id="story-goal" maxLength={1200} onChange={(event) => setStoryGoal(event.currentTarget.value)} placeholder="The one idea the edit should make clear." value={storyGoal} />
                </label>
                <label className="text-xs font-bold text-[#173F5F] sm:col-span-2" htmlFor="story-ending">
                  HOW SHOULD IT END?
                  <Input className="mt-2 h-11 bg-white" id="story-ending" maxLength={600} onChange={(event) => setEndingInstruction(event.currentTarget.value)} placeholder="e.g. End on the laugh, then show the call to action" value={endingInstruction} />
                </label>
              </div>
            </fieldset>
            <div className="space-y-2">
              <label className="text-xs font-bold text-[#173F5F]" htmlFor="must-include">
                MUST-INCLUDE POINTS
              </label>
              <Textarea
                className="min-h-20 rounded-sm border-[#D7D9D3] bg-white text-[#20211F] shadow-none focus-visible:border-[#173F5F] focus-visible:ring-[#173F5F]/20 dark:bg-white dark:text-[#20211F]"
                disabled={formLocked}
                id="must-include"
                maxLength={2000}
                onChange={(event) => setMustInclude(event.currentTarget.value)}
                placeholder="For example: include the price, launch date and final call to action."
                value={mustInclude}
              />
            </div>
            <fieldset className="space-y-3" disabled={formLocked}>
              <legend className="text-xs font-bold text-[#173F5F]">TARGET LENGTH</legend>
              <div className="grid grid-cols-4 gap-2">
                {durationOptions.map((duration) => (
                  <label
                    className={cn(
                      "flex min-h-12 cursor-pointer items-center justify-center rounded-md bg-white font-mono text-xs font-bold",
                      targetDuration === duration
                        ? "border-2 border-[#173F5F] text-[#173F5F]"
                        : "border border-[#D7D9D3] text-[#666862]",
                      formLocked && "cursor-not-allowed opacity-60",
                    )}
                    key={duration}
                  >
                    <input
                      checked={targetDuration === duration}
                      className="sr-only"
                      name="target-duration"
                      onChange={() => setTargetDuration(duration)}
                      type="radio"
                      value={duration}
                    />
                    {duration} sec
                  </label>
                ))}
              </div>
              <p className="text-xs leading-relaxed text-[#666862]">An approximate aim. The editor can finish sooner when the story is complete, without adding pauses to fill time.</p>
            </fieldset>
            <fieldset className="space-y-3" disabled={formLocked}>
              <legend className="text-xs font-bold text-[#173F5F]">OUTPUT SHAPE</legend>
              <div className="grid grid-cols-3 gap-2">
                {([
                  { value: "vertical", label: "Vertical 9:16" },
                  { value: "landscape", label: "Landscape 16:9" },
                  { value: "square", label: "Square 1:1" },
                ] as const).map((option) => (
                  <label
                    className={cn(
                      "flex min-h-12 cursor-pointer items-center justify-center rounded-md bg-white text-xs font-bold",
                      outputAspect === option.value
                        ? "border-2 border-[#173F5F] text-[#173F5F]"
                        : "border border-[#D7D9D3] text-[#666862]",
                    )}
                    key={option.value}
                  >
                    <input
                      checked={outputAspect === option.value}
                      className="sr-only"
                      name="output-aspect"
                      onChange={() => setOutputAspect(option.value)}
                      type="radio"
                      value={option.value}
                    />
                    {option.label}
                  </label>
                ))}
              </div>
            </fieldset>
            <fieldset className="space-y-3" disabled={formLocked}>
              <legend className="text-xs font-bold text-[#173F5F]">EDITING STYLE</legend>
              <div className="space-y-2">
                {EDIT_STYLE_OPTIONS.map((option) => (
                  <CreativeOptionCard
                    description={option.description}
                    disabled={formLocked}
                    key={option.value}
                    label={option.label}
                    name="edit-style"
                    onChange={() => {
                      setEditStyle(option.value);
                      if (option.value === "high_impact" && effectLevel === "off" && compatibleEffectCount > 0 && privacyMode !== "local_only") setEffectLevel("social");
                    }}
                    selected={editStyle === option.value}
                    value={option.value}
                  />
                ))}
              </div>
            </fieldset>
            <fieldset className="space-y-3" disabled={formLocked}>
              <legend className="text-xs font-bold text-[#173F5F]">BACKING MUSIC</legend>
              {editStyle === "high_impact" ? <p className="text-xs leading-relaxed text-[#53646F]">Include product close-ups or relevant scene footage among your selected media for B-roll. Your speech continues underneath. Sounds and stickers still follow your Creative effects setting below.</p> : null}
              <label className="block space-y-2 text-xs font-bold text-[#173F5F]" htmlFor="target-platform">
                TARGET PLATFORM
                <select
                  className="h-12 w-full rounded-md border border-[#D7D9D3] bg-white px-3 text-sm text-[#20211F] shadow-none focus:border-[#173F5F] focus:outline-none focus:ring-2 focus:ring-[#173F5F]/20 disabled:opacity-60"
                  disabled={formLocked}
                  id="target-platform"
                  onChange={(event) => {
                    const selected = event.currentTarget.value as TargetPlatform;
                    setTargetPlatform(selected);
                    const hasCompatibleTrack = musicTracks.some(
                      (track) =>
                        track.allowed_platforms.includes("all_social")
                        || track.allowed_platforms.includes(selected),
                    );
                    if (!hasCompatibleTrack) setMusicMode("none");
                    if (!hasCompatibleTrack || (selectedMusicTrackId && !musicTracks.some((track) => track.id === selectedMusicTrackId && (track.allowed_platforms.includes("all_social") || track.allowed_platforms.includes(selected))))) setSelectedMusicTrackId(null);
                    if (!creativeAssets.some((asset) => asset.allowed_platforms.includes("all_social") || asset.allowed_platforms.includes(selected))) setEffectLevel("off");
                  }}
                  value={targetPlatform}
                >
                  {PLATFORM_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>{option.label}</option>
                  ))}
                </select>
              </label>
              <div className="space-y-2">
                {MUSIC_OPTIONS.map((option) => (
                  <CreativeOptionCard
                    description={option.description}
                    disabled={formLocked || (option.value !== "none" && compatibleMusicCount === 0)}
                    key={option.value}
                    label={option.label}
                    name="music-mode"
                    onChange={() => { setMusicMode(option.value); if (option.value === "none") setSelectedMusicTrackId(null); }}
                    selected={musicMode === option.value}
                    value={option.value}
                  />
                ))}
              </div>
              <p className="text-xs leading-relaxed text-[#666862]">
                {compatibleMusicCount > 0
                  ? `${compatibleMusicCount} compatible rights-recorded ${compatibleMusicCount === 1 ? "track" : "tracks"} available.`
                  : "No compatible tracks are imported yet, so this job will remain voice-only."}
              </p>
              {musicMode !== "none" && compatibleMusicCount > 0 ? (
                <label className="block space-y-2 text-xs font-bold text-[#173F5F]">
                  TRACK
                  <select className="h-12 w-full rounded-md border border-[#D7D9D3] bg-white px-3 text-sm font-normal text-[#20211F]" onChange={(event) => setSelectedMusicTrackId(event.currentTarget.value || null)} value={selectedMusicTrackId ?? ""}>
                    <option value="">Auto-select for the story</option>
                    {musicTracks.filter((track) => track.allowed_platforms.includes("all_social") || track.allowed_platforms.includes(targetPlatform)).map((track) => <option key={track.id} value={track.id}>{track.title}{track.artist ? ` — ${track.artist}` : ""} · {track.mood}</option>)}
                  </select>
                </label>
              ) : null}
            </fieldset>
            <fieldset className="space-y-3" disabled={formLocked || privacyMode === "local_only"}>
              <legend className="text-xs font-bold text-[#173F5F]">CREATIVE EFFECTS</legend>
              <p className="text-xs leading-relaxed text-[#666862]">
                {privacyMode === "local_only"
                  ? "The fixed local recipe does not select creative effects. Choose a model-assisted privacy mode to have the editor select cues."
                  : "Adds reviewed sounds, stickers, GIFs, or meme assets at suitable story beats. Choose Social for a more noticeable test. Punch-ins and camera moves are controlled separately by the edit style."}
              </p>
              <div className="grid grid-cols-2 gap-2">
                {([
                  ["off", "Off", "Clean edit"], ["subtle", "Subtle", "Up to 2 cues"],
                  ["social", "Social", "Up to 4 cues"], ["meme_heavy", "Meme-heavy", "Up to 8 cues"],
                ] as const).map(([value, label, description]) => { const unavailable = value !== "off" && compatibleEffectCount === 0; return <label className={`rounded-md border p-3 focus-within:ring-2 focus-within:ring-[#173F5F]/40 ${unavailable ? "cursor-not-allowed opacity-45" : ""} ${effectLevel === value ? "border-[#173F5F] bg-[#EFF6FA]" : "border-[#D7D9D3] bg-white"}`} key={value}><input checked={effectLevel === value} className="sr-only" disabled={unavailable} name="effect-level" onChange={() => setEffectLevel(value)} type="radio" /><span className="block text-sm font-bold text-[#173F5F]">{label}</span><span className="mt-1 block text-[11px] text-[#666862]">{description}</span></label>; })}
              </div>
              <p className="text-xs text-[#666862]">
                {compatibleEffectCount > 0
                  ? `${compatibleEffectCount} compatible reviewed effects available. Off adds no sounds or overlays; other modes are maximum cue counts, not a guarantee of effects.`
                  : "No compatible effects are installed yet. Import the starter library before testing sounds and stickers."}
                {" "}<Link className="font-bold text-[#173F5F] underline underline-offset-4" href="/creative">View music &amp; effects library</Link>
              </p>
            </fieldset>
            <fieldset className="space-y-3" disabled={formLocked || privacyMode === "local_only"}>
              <legend className="text-xs font-bold text-[#173F5F]">EDITOR MODEL</legend>
              <label className="block space-y-2 text-xs font-bold text-[#173F5F]" htmlFor="editor-model">
                MODEL
                <select
                  className="h-12 w-full rounded-md border border-[#D7D9D3] bg-white px-3 text-sm text-[#20211F] shadow-none focus:border-[#173F5F] focus:outline-none focus:ring-2 focus:ring-[#173F5F]/20 disabled:opacity-60"
                  id="editor-model"
                  onChange={(event) => setEditorModel(event.currentTarget.value || null)}
                  value={editorModel ?? ""}
                >
                  {editorModels.length === 0 ? <option value="">Server default</option> : null}
                  {editorModels.map((model) => (
                    <option key={model.slug} value={model.slug}>{model.display_name}</option>
                  ))}
                </select>
              </label>
              <div className="grid grid-cols-3 gap-2">
                {([
                  { value: "low", label: "Economy" },
                  { value: "medium", label: "Balanced" },
                  { value: "high", label: "Best" },
                ] as const).map((option) => (
                  <label
                    className={cn(
                      "flex min-h-12 cursor-pointer items-center justify-center rounded-md bg-white text-xs font-bold",
                      reasoningEffort === option.value
                        ? "border-2 border-[#173F5F] text-[#173F5F]"
                        : "border border-[#D7D9D3] text-[#666862]",
                    )}
                    key={option.value}
                  >
                    <input
                      checked={reasoningEffort === option.value}
                      className="sr-only"
                      name="reasoning-effort"
                      onChange={() => setReasoningEffort(option.value)}
                      type="radio"
                      value={option.value}
                    />
                    {option.label}
                  </label>
                ))}
              </div>
              <p className="text-xs leading-relaxed text-[#666862]">
                Lower effort generally uses fewer reasoning tokens. The final screen records the actual usage.
              </p>
            </fieldset>
          </div>
        </section>

        <fieldset className="space-y-4" disabled={formLocked}>
          <legend className="sr-only">Privacy</legend>
          <SectionHeading number="03">Privacy</SectionHeading>
          <div className="space-y-2">
            {PRIVACY_OPTIONS.map((option) => (
              <PrivacyCard
                description={option.description}
                disabled={formLocked}
                key={option.value}
                label={option.label}
                onChange={(value) => {
                  setPrivacyMode(value);
                  if (value === "local_only") setEffectLevel("off");
                }}
                selected={privacyMode === option.value}
                value={option.value}
              />
            ))}
          </div>
          <label className={cn("flex min-h-14 items-start justify-between gap-4 pt-4", formLocked ? "cursor-not-allowed opacity-60" : "cursor-pointer")}>
            <span className="space-y-1">
              <span className="block text-sm font-bold text-[#173F5F]">Allow AI-written caption copy</span>
              <span className="block text-xs leading-relaxed text-[#666862]">
                This affects text only. Visuals and speech remain grounded in your selected media.
              </span>
            </span>
            <span className="flex size-11 shrink-0 items-center justify-end">
              <input
                checked={aiCopyAllowed}
                className="peer sr-only"
                disabled={formLocked}
                onChange={(event) => setAiCopyAllowed(event.currentTarget.checked)}
                role="switch"
                type="checkbox"
              />
              <span className="relative h-6 w-12 rounded-full bg-[#D7D9D3] transition-colors peer-checked:bg-[#173F5F] peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-[#173F5F] after:absolute after:top-1 after:left-1 after:size-4 after:rounded-full after:bg-white after:transition-transform peer-checked:after:translate-x-6 motion-reduce:transition-none motion-reduce:after:transition-none" />
            </span>
          </label>
        </fieldset>

        <section className="space-y-4 pb-8" id="server-library">
          <SectionHeading number="04">Source media</SectionHeading>
          <div className="rounded-md border border-[#BFD2DE] bg-[#EFF6FA] p-4 text-sm text-[#173F5F]">
            <p className="font-bold">Combine server footage and new uploads in one job</p>
            <p className="mt-1 text-xs leading-relaxed">Add files from this device and select existing footage below, then create your job. Both selections are included together.</p>
            <p aria-live="polite" className="mt-2 font-mono text-xs font-bold">{selectedLibraryAssets.length} from server + {entries.length} from this device</p>
          </div>

            <div aria-label="Upload new source media" className="space-y-4">
              <h3 className="text-sm font-bold text-[#173F5F]">Add from this device</h3>
              <label
                className={cn(
                  "flex min-h-36 w-full cursor-pointer flex-col items-center justify-center rounded-md border-2 border-dashed border-[#C7CBD0] bg-white p-6 text-center transition-colors hover:border-[#173F5F] focus-within:border-[#173F5F] focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-[#173F5F] dark:bg-white",
                  isSubmitting && "pointer-events-none cursor-wait opacity-60",
                )}
                onDragOver={(event) => event.preventDefault()}
                onDrop={handleDrop}
              >
                <UploadCloudIcon aria-hidden="true" className="mb-2 size-6 text-[#173F5F]" />
                <span className="text-sm font-bold text-[#173F5F]">Choose files or drop them here</span>
                <span className="mt-1 font-mono text-[10px] tracking-tight text-[#666862] uppercase">
                  Video, photo, audio · Up to 20 GB per file
                </span>
                <input
                  accept="video/*,image/*,audio/*,.heic,.heif"
                  aria-label="Add files from this device"
                  className="sr-only"
                  disabled={isSubmitting}
                  multiple
                  onClick={() => {
                    settleRootScroll();
                    reportClientDiagnostic("file-picker-open");
                  }}
                  onChange={(event) => {
                    settleRootScroll();
                    const files = Array.from(event.currentTarget.files ?? []);
                    reportClientDiagnostic("file-picker-change", {
                      fileCount: files.length,
                      fileTypes: files.map((file) => file.type || "unknown"),
                      fileSizes: files.map((file) => file.size),
                    });
                    try {
                      queueFiles(files);
                      reportClientDiagnostic("files-queued", { fileCount: files.length });
                    } catch (error) {
                      const message = toErrorMessage(error);
                      setFileError(message);
                      reportClientDiagnostic("file-selection-error", {
                        message,
                        stack: error instanceof Error ? error.stack : undefined,
                      });
                    } finally {
                      event.currentTarget.value = "";
                    }
                  }}
                  type="file"
                />
              </label>
              {fileError ? (
                <p className="flex items-start gap-1.5 text-xs leading-relaxed text-[#A23B2A]" role="alert">
                  <CircleAlertIcon aria-hidden="true" className="mt-0.5 size-3.5 shrink-0" />
                  {fileError}
                </p>
              ) : null}
              {entries.length > 0 ? (
                <ul aria-label="New source media" className="space-y-2">
                  {entries.map((entry) => (
                    <UploadRow
                      entry={entry}
                      key={entry.localId}
                      onPause={(selected) => void pauseUpload(selected)}
                      onRemove={removeUpload}
                      onResume={resumeUpload}
                      onRetry={retryUpload}
                    />
                  ))}
                </ul>
              ) : (
                <p className="text-center font-mono text-[10px] text-[#666862]">No new files selected.</p>
              )}
              <p className="text-center font-mono text-[10px] leading-relaxed text-[#666862]">
                Keep this page open while uploading. Interrupted uploads can resume when this device reconnects.
              </p>
            </div>
            <div aria-label="Choose existing server media" className="space-y-4 border-t border-[#D7D9D3] pt-5">
              <h3 className="text-sm font-bold text-[#173F5F]">Choose from the server library</h3>
              <div className="flex items-center justify-between gap-4">
                <p className="font-mono text-[10px] font-bold tracking-wide text-[#666862] uppercase">Analyzed originals</p>
                <Link className="text-xs font-bold text-[#173F5F] underline underline-offset-4" href="/library/duplicates">
                  Review exact duplicates
                </Link>
              </div>
              <label className="relative block" htmlFor="library-search">
                <span className="sr-only">Search server library</span>
                <SearchIcon aria-hidden="true" className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-[#666862]" />
                <Input
                  className="h-12 rounded-sm border-[#D7D9D3] bg-white pr-3 pl-10 text-[#20211F] shadow-none focus-visible:border-[#173F5F] focus-visible:ring-[#173F5F]/20 dark:bg-white dark:text-[#20211F]"
                  id="library-search"
                  onChange={(event) => setLibraryQuery(event.currentTarget.value)}
                  placeholder="Search speech or what appears in scenes"
                  type="search"
                  value={libraryQuery}
                />
              </label>
              {visualIndexStatus ? (
                <div className="rounded-sm border border-[#D7D9D3] bg-white p-3" aria-live="polite">
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-xs leading-relaxed text-[#4E5960]">
                      {visualIndexStatus.assets_pending > 0
                        ? `Visual indexing ${visualIndexStatus.assets_ready} canonical items; ${visualIndexStatus.assets_pending} remaining.`
                        : visualIndexStatus.assets_failed > 0
                          ? `${visualIndexStatus.assets_ready} canonical items searchable; ${visualIndexStatus.assets_failed} need attention.`
                          : `Visual search ready · ${visualIndexStatus.frames_total} source frames indexed.`}
                    </p>
                    <span className="shrink-0 font-mono text-[9px] font-bold text-[#173F5F] uppercase">Local</span>
                  </div>
                  {visualIndexStatus.assets_pending > 0 && visualIndexStatus.assets_total > 0 ? (
                    <div
                      aria-label="Visual indexing progress"
                      aria-valuemax={visualIndexStatus.assets_total - visualIndexStatus.assets_aliased}
                      aria-valuemin={0}
                      aria-valuenow={visualIndexStatus.assets_ready}
                      className="mt-2 h-1.5 overflow-hidden rounded-full bg-[#E9EDF0]"
                      role="progressbar"
                    >
                      <div
                        className="h-full bg-[#173F5F] transition-[width] motion-reduce:transition-none"
                        style={{
                          width: `${Math.min(100, Math.round((visualIndexStatus.assets_ready / Math.max(1, visualIndexStatus.assets_total - visualIndexStatus.assets_aliased)) * 100))}%`,
                        }}
                      />
                    </div>
                  ) : null}
                </div>
              ) : null}
              {normalizedLibraryQuery.length >= 2 ? (
                <div aria-live="polite" className="flex items-start justify-between gap-3 rounded-sm border border-[#BFD2DE] bg-[#EFF6FA] p-3">
                  <p className="text-xs leading-relaxed text-[#4E5960]">
                    {catalogSearching
                      ? "Searching speech and source frames…"
                      : catalogSearchError
                        ? "Indexed search is temporarily unavailable; filename and project search still work."
                        : catalogMatches.size > 0
                          ? `${catalogMatches.size} strongest source ${catalogMatches.size === 1 ? "match" : "matches"}, ordered by relevance. Results use exact words or visual frames with time ranges.`
                          : "No speech or visual evidence matched. Filename and project matches are still shown."}
                  </p>
                  <span className="shrink-0 font-mono text-[9px] font-bold text-[#173F5F] uppercase">
                    {catalogSearching ? "Searching" : "Local index"}
                  </span>
                </div>
              ) : null}
              <div className="flex gap-2 overflow-x-auto pb-1" aria-label="Library media filters">
                {([
                  { value: "all", label: "Recent" },
                  { value: "video", label: "Video" },
                  { value: "image", label: "Photos" },
                  { value: "audio", label: "Audio" },
                ] as const).map((option) => (
                  <button
                    aria-pressed={libraryKind === option.value}
                    className={cn(
                      "min-h-11 shrink-0 rounded-md bg-white px-4 text-xs font-bold",
                      libraryKind === option.value
                        ? "border-2 border-[#173F5F] text-[#173F5F]"
                        : "border border-[#D7D9D3] text-[#666862]",
                    )}
                    key={option.value}
                    onClick={() => setLibraryKind(option.value)}
                    type="button"
                  >
                    {option.label}
                  </button>
                ))}
              </div>
              <label className="block space-y-2 text-xs font-bold text-[#173F5F]" htmlFor="library-project">
                PROJECT
                <select
                  className="h-11 w-full rounded-md border border-[#D7D9D3] bg-white px-3 text-sm text-[#20211F] shadow-none focus:border-[#173F5F] focus:outline-none focus:ring-2 focus:ring-[#173F5F]/20"
                  id="library-project"
                  onChange={(event) => setLibraryProjectId(event.currentTarget.value)}
                  value={libraryProjectId}
                >
                  <option value="all">All projects</option>
                  {libraryProjects.map(([id, projectName]) => (
                    <option key={id} value={id}>{projectName}</option>
                  ))}
                </select>
              </label>
              {libraryError ? (
                <p className="flex items-start gap-1.5 text-xs leading-relaxed text-[#A23B2A]" role="alert">
                  <CircleAlertIcon aria-hidden="true" className="mt-0.5 size-3.5 shrink-0" />
                  {libraryError}
                </p>
              ) : libraryLoading ? (
                <p className="flex items-center justify-center gap-2 py-8 font-mono text-xs text-[#666862]">
                  <LoaderCircleIcon aria-hidden="true" className="size-4 animate-spin motion-reduce:animate-none" />
                  Loading server media…
                </p>
              ) : filteredLibraryAssets.length > 0 ? (
                <div className="max-h-96 space-y-2 overflow-y-auto overscroll-contain" aria-label="Server media library">
                  {filteredLibraryAssets.map((asset) => (
                    <LibraryAssetRow
                      asset={asset}
                      disabled={formLocked}
                      key={asset.id}
                      match={catalogMatches.get(asset.id)}
                      onChange={toggleLibraryAsset}
                      selected={selectedLibraryAssetIds.has(asset.id)}
                    />
                  ))}
                </div>
              ) : (
                <div className="rounded-md border border-[#D7D9D3] bg-white p-6 text-center">
                  <FolderIcon aria-hidden="true" className="mx-auto size-6 text-[#173F5F]" />
                  <p className="mt-2 text-sm font-bold text-[#173F5F]">No matching server media</p>
                  <p className="mt-1 text-xs text-[#666862]">Ready uploads will appear here automatically.</p>
                </div>
              )}
              <p className="text-center font-mono text-[10px] leading-relaxed text-[#666862]">
                Selecting an item attaches the existing original. It does not copy or re-upload the file.
              </p>
            </div>
          {jobId ? (
            <p className="text-center font-mono text-[10px] text-[#666862]" aria-live="polite">
              Job {jobId.slice(0, 8)} created
            </p>
          ) : null}
        </section>
      </main>

      <footer className="z-50 shrink-0 touch-none border-t border-[#D7D9D3] bg-white px-4 pt-4 pb-[max(1rem,env(safe-area-inset-bottom))] dark:bg-white">
        {formError ? (
          <p className="mb-3 flex items-start gap-1.5 text-xs leading-relaxed text-[#A23B2A]" role="alert">
            <CircleAlertIcon aria-hidden="true" className="mt-0.5 size-3.5 shrink-0" />
            {formError}
          </p>
        ) : null}
        <div className="mb-4 flex items-end justify-between">
          <div>
            <span className="block font-mono text-[10px] font-bold text-[#666862] uppercase">Total selected</span>
            <span className="text-sm font-bold text-[#173F5F]">
              {totalItems === 0
                ? "No media"
                : `${totalItems} ${totalItems === 1 ? "item" : "items"} · ${formatBytes(totalBytes)}`}
            </span>
            {totalItems > 0 ? (
              <span className="mt-0.5 block font-mono text-[10px] text-[#666862]">
                {selectedLibraryAssets.length} from server · {entries.length} new
              </span>
            ) : null}
          </div>
          {allReady ? (
            <Badge className="rounded-sm border-[#BFE3FF] bg-[#E8F5FF] font-mono text-[10px] font-bold text-[#173F5F]" variant="outline">
              <CheckIcon aria-hidden="true" /> Ready
            </Badge>
          ) : null}
        </div>
        <Button
          className="h-14 w-full touch-manipulation rounded-md bg-[#173F5F] text-sm font-bold text-white hover:bg-[#12344F] focus-visible:ring-[#173F5F]/35 disabled:bg-[#8A9CAB]"
          disabled={isSubmitting || (jobId !== undefined && !allReady)}
          onClick={jobId !== undefined && allReady ? () => void startEditing() : undefined}
          type={jobId !== undefined && allReady ? "button" : "submit"}
        >
          {isSubmitting ? (
            <>
              <LoaderCircleIcon aria-hidden="true" className="animate-spin motion-reduce:animate-none" />
              Creating job…
            </>
          ) : jobId !== undefined && allReady ? (
            <>
              Start editing
              <ArrowRightIcon aria-hidden="true" />
            </>
          ) : jobId !== undefined ? (
            <>
              <LoaderCircleIcon aria-hidden="true" className="animate-spin motion-reduce:animate-none" />
              Uploads underway
            </>
          ) : (
            <>
              {entries.length > 0 ? "Create job & upload" : "Create job"}
              <ArrowRightIcon aria-hidden="true" />
            </>
          )}
        </Button>
      </footer>
    </form>
  );
}

export function NewJobForm() {
  return (
    <NewJobErrorBoundary>
      <NewJobFormContent />
    </NewJobErrorBoundary>
  );
}
