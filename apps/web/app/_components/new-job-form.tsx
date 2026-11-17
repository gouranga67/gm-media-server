"use client";

import { libraryRoleLabel } from "@/lib/library-organization";
import { Component, type DragEvent, type ErrorInfo, type FormEvent, type ReactNode } from "react";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { DurationFields } from "./duration-fields";
import { StudioNav } from "./studio-nav";
import { useJobLibrary } from "./use-job-library";
import { writeMediaBasket } from "@/lib/media-basket";
import { folderLabel } from "@/lib/library-folder-tree";
import { useRouter } from "next/navigation";
import type { Upload } from "tus-js-client";
import {
  ArrowRightIcon,
  AudioLinesIcon,
  BookOpenIcon,
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
  getSystemInformation,
  getVisualIndexStatus,
  interpretBrief,
  libraryAssetThumbnailUrl,
  mediaTypeForFile,
  registerAsset,
  requestPreview,
  setJobComposition,
  visualIndexFrameUrl,
  type Asset,
  type CatalogSearchResult,
  type CreativeProfile,
  type CreativeAsset,
  type BrandKit,
  type BriefInterpretation,
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
  type AssemblyMode,
  type PacingMode,
  type TargetDuration,
  type DurationMode,
  type TargetPlatform,
  type JobCompositionMode,
  type VisualIndexStatus,
} from "@/lib/media-api";
import { startResumableUpload } from "@/lib/resumable-upload";
import { cn } from "@/lib/utils";

const MAX_FILE_BYTES = 20 * 1024 * 1024 * 1024;
const READY_POLL_ATTEMPTS = 45;
const READY_POLL_INTERVAL_MS = 1_000;

type ServerStatus = "checking" | "online" | "offline";
type CreateStep = 1 | 2 | 3;
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
    description: "A hosted editor may see transcript, recognized image text and library metadata, but no images or original files.",
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

function suggestedProjectName(brief: string, sourceName?: string): string {
  const lines = brief.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  const firstUsefulLine = lines.find((line) => !/^(?:voiceover\s+|spoken\s+|recorded\s+)?script\s*:?$/i.test(line));
  const fromBrief = (firstUsefulLine ?? "")
    .replace(/^\s*(?:[-*•]|\d+[.)]|(?:scene|shot|beat)\s*#?\d+\s*[:.)-])\s*/i, "")
    .replace(/^\s*(?:make|create|turn|edit)\s+(?:(?:a|an|the|this|these|my|our)\s+)?/i, "")
    .replace(/\s+/g, " ")
    .trim();
  if (fromBrief) {
    const shortened = fromBrief.split(" ").slice(0, 8).join(" ").replace(/[.,:;!?-]+$/, "");
    return `${shortened.charAt(0).toUpperCase()}${shortened.slice(1)}`.slice(0, 80);
  }
  const fromSource = String(sourceName || "").replace(/\.[^.]+$/, "").replace(/[_-]+/g, " ").trim();
  if (fromSource && !/^(?:vid|img|dsc|pxl)[ -]?\d+$/i.test(fromSource)) {
    return `${fromSource.charAt(0).toUpperCase()}${fromSource.slice(1)} edit`.slice(0, 80);
  }
  return "New media edit";
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
          <p className="font-mono text-xs font-bold tracking-wide text-[#A23B2A] uppercase">Phone display error</p>
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
      return "Uploaded · final checks continue on server";
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
        "relative flex min-h-28 items-start gap-3 rounded-md bg-white p-3 sm:block",
        selected ? "border-2 border-[#173F5F]" : "border border-[#D7D9D3]",
        disabled ? "cursor-not-allowed opacity-60" : "cursor-pointer",
      )}
    >
      <span className="flex h-20 w-24 shrink-0 items-center justify-center overflow-hidden rounded-sm bg-[#E9EDF0] text-[#173F5F] sm:aspect-video sm:h-auto sm:w-full">
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
      <span className="min-w-0 flex-1 pr-8 sm:mt-3 sm:block">
        <span className="block truncate font-mono text-xs font-bold text-[#20211F]">{asset.display_name || asset.source_name}</span>
        <span className="block truncate text-xs text-[#666862]">{libraryRoleLabel(asset)}{asset.display_name && asset.display_name !== asset.source_name ? ` · ${asset.source_name}` : ""}</span>
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
        className="absolute top-4 right-4 size-5 shrink-0 accent-[#173F5F]"
        disabled={disabled}
        onChange={() => onChange(asset)}
        type="checkbox"
      />
    </label>
  );
}

function NewJobFormContent() {
  const router = useRouter();
  const [createStep, setCreateStep] = useState<CreateStep>(1);
  const [mediaSourceTab, setMediaSourceTab] = useState<"upload" | "library">("upload");
  const [name, setName] = useState("");
  const [brief, setBrief] = useState("");
  const [briefInterpretation, setBriefInterpretation] = useState<BriefInterpretation>();
  const [privacyMode, setPrivacyMode] = useState<PrivacyMode>("hybrid");
  const [aiCopyAllowed, setAiCopyAllowed] = useState(false);
  const [assemblyMode, setAssemblyMode] = useState<AssemblyMode>("auto");
  const [pacingMode, setPacingMode] = useState<PacingMode>("auto");
  const [reelIntent, setReelIntent] = useState<"auto" | "story" | "promotion" | "bloopers">("auto");
  const [targetDuration, setTargetDuration] = useState<TargetDuration>(45);
  const [durationMode, setDurationMode] = useState<DurationMode>("follow_story");
  const [maxDuration, setMaxDuration] = useState(90);
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
  const [compositionMode, setCompositionMode] = useState<JobCompositionMode>("auto");
  const [foregroundAssetId, setForegroundAssetId] = useState<string | null>(null);
  const [backgroundAssetId, setBackgroundAssetId] = useState<string | null>(null);
  const [presentationCustomized, setPresentationCustomized] = useState(false);
  const [musicTracks, setMusicTracks] = useState<readonly MusicTrack[]>([]);
  const [creativeAssets, setCreativeAssets] = useState<readonly CreativeAsset[]>([]);
  const [entries, setEntries] = useState<UploadEntry[]>([]);
  const library = useJobLibrary();
  const { query: libraryQuery, kind: libraryKind, purpose: libraryPurpose, projectId: libraryProjectId } = library.filters;
  const selectedLibraryAssetIds = library.selectedIds;
  const selectedLibraryAssets = library.selectedAssets;
  const selectedLibraryById = new Map(selectedLibraryAssets.map(asset => [asset.id, asset]));
  const libraryLoading = library.loading;
  const libraryError = library.error;
  const catalogMatches = library.matches;
  const catalogSearching = library.searching;
  const catalogSearchError = library.searchError;
  const normalizedLibraryQuery = libraryQuery.trim().toLocaleLowerCase();
  const filteredLibraryAssets = library.items;
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

  const applyPublishingPreset = (preset: PublishingPreset, customized: boolean) => {
    if (customized) setPresentationCustomized(true);
    setPublishingPreset(preset);
    if (preset === "instagram_reel") { setTargetPlatform("instagram"); setOutputAspect("vertical"); setTargetDuration(30); }
    if (preset === "tiktok") { setTargetPlatform("tiktok"); setOutputAspect("vertical"); setTargetDuration(30); }
    if (preset === "youtube_short") { setTargetPlatform("youtube"); setOutputAspect("vertical"); setTargetDuration(45); }
    if (preset === "linkedin_landscape") { setTargetPlatform("linkedin"); setOutputAspect("landscape"); setTargetDuration(30); }
    if (preset === "facebook_square") { setTargetPlatform("facebook"); setOutputAspect("square"); setTargetDuration(30); }
  };

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
    return () => {
      cancelled = true;
      mountedRef.current = false;
    };
  }, []);

  useEffect(() => {
    const text = brief.trim();
    if (!text) {
      setBriefInterpretation(undefined);
      return;
    }
    let cancelled = false;
    const timer = window.setTimeout(() => {
      void interpretBrief(text)
        .then((interpretation) => {
          if (!cancelled) setBriefInterpretation(interpretation);
        })
        .catch(() => {
          if (!cancelled) setBriefInterpretation(undefined);
        });
    }, 450);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [brief]);

  useEffect(() => {
    const suggestion = briefInterpretation?.suggested_publishing_preset;
    if (!presentationCustomized && suggestion && suggestion !== "custom" && suggestion !== publishingPreset) {
      applyPublishingPreset(suggestion, false);
    }
  }, [briefInterpretation, presentationCustomized, publishingPreset]);

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

  const totalItems = entries.length + selectedLibraryAssets.length;
  const compositionSources = [
    ...selectedLibraryAssets.map((asset) => ({
      id: asset.id,
      label: asset.display_name || asset.source_name,
      mediaType: asset.mime_type,
      origin: "Server library",
    })),
    ...entries.map((entry) => ({
      id: entry.assetRequestId,
      label: entry.file.name,
      mediaType: entry.mediaType,
      origin: "This device",
    })),
  ];
  const foregroundCandidates = compositionSources.filter((source) => source.mediaType.startsWith("video/"));
  const backgroundCandidates = compositionSources.filter(
    (source) => source.mediaType.startsWith("video/") || source.mediaType.startsWith("image/"),
  );
  const compositionReady = compositionMode !== "green_screen"
    || (
      foregroundAssetId !== null
      && backgroundAssetId !== null
      && foregroundAssetId !== backgroundAssetId
      && foregroundCandidates.some((source) => source.id === foregroundAssetId)
      && backgroundCandidates.some((source) => source.id === backgroundAssetId)
    );
  const totalBytes = entries.reduce((total, entry) => total + entry.file.size, 0)
    + selectedLibraryAssets.reduce((total, asset) => total + asset.byte_size, 0);
  const transferredEntries = entries.filter((entry) => entry.uploadComplete && entry.phase !== "error").length;
  const transferredItems = selectedLibraryAssets.length + transferredEntries;
  const uploadsTransferred = totalItems > 0 && transferredEntries === entries.length;
  const deviceTransferBytes = entries.reduce((total, entry) => total + entry.totalBytes, 0);
  const deviceTransferredBytes = entries.reduce((total, entry) => total + Math.min(entry.uploadedBytes, entry.totalBytes), 0);
  const transferPercent = entries.length === 0
    ? 100
    : Math.min(100, Math.round((deviceTransferredBytes / Math.max(1, deviceTransferBytes)) * 100));
  const automaticProjectName = suggestedProjectName(
    brief,
    selectedLibraryAssets[0]?.display_name || selectedLibraryAssets[0]?.source_name || entries[0]?.file.name,
  );
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
  const chooseCompositionMode = (mode: JobCompositionMode) => {
    setCompositionMode(mode);
    setFormError(undefined);
    if (mode !== "green_screen") {
      setForegroundAssetId(null);
      setBackgroundAssetId(null);
      return;
    }
    setAssemblyMode("talking_head");
    const foreground = foregroundCandidates.find((source) => source.id === foregroundAssetId)
      ?? foregroundCandidates[0];
    const background = backgroundCandidates.find(
      (source) => source.id === backgroundAssetId && source.id !== foreground?.id,
    ) ?? backgroundCandidates.find((source) => source.id !== foreground?.id);
    setForegroundAssetId(foreground?.id ?? null);
    setBackgroundAssetId(background?.id ?? null);
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
    library.toggle(asset);
    setFormError(undefined);
  };

  const handleDrop = (event: DragEvent<HTMLLabelElement>) => {
    event.preventDefault();
    queueFiles(Array.from(event.dataTransfer.files));
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (jobId === undefined && createStep !== 3) {
      if (totalItems === 0) {
        setFormError("Choose at least one source file before continuing.");
        return;
      }
      if (!compositionReady) {
        setFormError("Choose different foreground and background sources for green screen.");
        return;
      }
      goToStep(createStep === 1 ? 2 : 3);
      return;
    }
    const cleanName = name.trim() || automaticProjectName;
    const cleanBrief = brief.trim();
    if (totalItems === 0) {
      setFormError("Select server media or add at least one new file.");
      return;
    }
    if (!compositionReady) {
      setFormError("Choose different foreground and background sources for green screen.");
      return;
    }

    if (!library.selectionReady) { setFormError("Review the selected server media before creating this job (maximum 100 originals)."); return; }
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
          recipe: assemblyMode === "auto" ? "talking_head" : assemblyMode,
          assemblyMode,
          pacingMode,
          reelIntent,
          targetDurationSeconds: targetDuration,
          durationMode,
          maxDurationSeconds: maxDuration,
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
    if (jobId === undefined || !uploadsTransferred) return;
    setIsSubmitting(true);
    setFormError(undefined);
    try {
      await setJobComposition(jobId, {
        mode: compositionMode,
        foreground_asset_id: compositionMode === "green_screen" ? foregroundAssetId : null,
        background_asset_id: compositionMode === "green_screen" ? backgroundAssetId : null,
        chroma_key_color: "#00FF00",
        chroma_similarity: 0.12,
        chroma_blend: 0.08,
        spill_suppression: 0.15,
      });
      await requestPreview(jobId);
      writeMediaBasket([]);
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
  const presentationPresetLabel: Record<PublishingPreset, string> = {
    custom: "Recommended defaults",
    instagram_reel: "Instagram Reel",
    tiktok: "TikTok",
    youtube_short: "YouTube Short",
    linkedin_landscape: "LinkedIn",
    facebook_square: "Facebook",
  };
  const presentationShapeLabel: Record<OutputAspect, string> = {
    vertical: "Vertical 9:16",
    landscape: "Landscape 16:9",
    square: "Square 1:1",
  };
  const presentationDurationLabel = durationMode === "follow_story"
    ? `Follow the story · up to ${maxDuration}s`
    : durationMode === "aim"
      ? `Aim for ${targetDuration}s`
      : `Exactly ${targetDuration}s`;
  const presentationStyleLabel = pacingMode === "auto"
    ? "AI follows your brief"
    : editStyle.replaceAll("_", " ");
  const privacySummary = PRIVACY_OPTIONS.find((option) => option.value === privacyMode)?.label ?? "Hybrid";
  const assemblySummary = assemblyMode === "auto" ? "Automatic assembly" : assemblyMode.replaceAll("_", " ");
  const selectedMediaNames = [
    ...selectedLibraryAssets.map((asset) => asset.display_name || asset.source_name),
    ...entries.map((entry) => entry.file.name),
  ];
  const stepHeading = createStep === 1
    ? ["Choose your media", "Upload from this device or choose footage already stored in your library."]
    : createStep === 2
      ? ["Tell GM Studio what to make", "Write the outcome in plain language. Scripts, numbered points and scene order are followed when supplied."]
      : ["Check your job", "Review the essentials below. Optional settings stay available without getting in the way."];
  const goToStep = (step: CreateStep) => {
    setCreateStep(step);
    setFormError(undefined);
    window.requestAnimationFrame(() => document.querySelector<HTMLElement>("[data-create-main]")?.scrollTo({ top: 0, behavior: "smooth" }));
  };

  return (
    <form
      aria-busy={isSubmitting}
      className="flex h-dvh min-h-0 w-full flex-col overflow-hidden overscroll-none bg-[#F7F7F5] text-[#20211F] [color-scheme:light]"
      data-gm-job-shell
      onSubmit={handleSubmit}
    >
      <header className="z-40 shrink-0 border-b border-[#D7D9D3] bg-[#F7F7F5] px-4 pt-[max(1rem,env(safe-area-inset-top))] pb-3">
        <div className="mx-auto w-full max-w-7xl">
          <div className="mb-1 flex items-center justify-between gap-3">
            <StudioNav current="/jobs/new" />
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
        </div>
      </header>

      <main className="mx-auto min-h-0 w-full max-w-7xl flex-1 touch-pan-y space-y-6 overflow-y-auto overscroll-contain px-4 py-5 sm:py-7" data-create-main>
        <section className="space-y-3">
          <nav aria-label="Create an edit steps" className="grid grid-cols-3 overflow-hidden rounded-lg border border-[#C7CBD0] bg-white shadow-sm">
            {([
              [1, "Choose media"],
              [2, "Give direction"],
              [3, "Review & create"],
            ] as const).map(([step, label]) => (
              <button
                aria-current={createStep === step ? "step" : undefined}
                className={cn(
                  "relative min-h-16 border-r border-[#D7D9D3] px-2 py-2 text-center text-xs font-bold last:border-r-0 sm:px-4",
                  createStep === step ? "bg-[#173F5F] text-white" : "text-[#53646F] hover:bg-[#EFF6FA]",
                )}
                disabled={step === 3 && totalItems === 0}
                key={step}
                onClick={() => goToStep(step)}
                type="button"
              >
                <span className={cn("block font-mono text-[9px]", createStep === step ? "text-[#C9DDE8]" : "text-[#7A7D77]")}>0{step}</span>
                {label}
                {step === 1 && totalItems > 0 ? <span className="absolute top-2 right-2 size-2 rounded-full bg-[#3A8F63]" aria-label="Media selected" /> : null}
              </button>
            ))}
          </nav>
          <div className="pt-2">
            <p className="font-mono text-[10px] font-bold tracking-wider text-[#174D73] uppercase">Step {createStep} of 3</p>
            <h1 className="mt-1 text-2xl font-bold tracking-tight text-[#173F5F] sm:text-3xl">{stepHeading[0]}</h1>
            <p className="mt-2 max-w-3xl text-sm leading-relaxed text-[#666862]">{stepHeading[1]}</p>
          </div>
          {createStep === 1 ? <div className="flex flex-col gap-2 rounded-md border border-[#BFD2DE] bg-[#EFF6FA] px-4 py-3 text-xs leading-relaxed text-[#53646F] sm:flex-row sm:items-center sm:justify-between">
            <p className="flex items-start gap-2"><BookOpenIcon aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-[#174D73]" /><span><strong className="text-[#173F5F]">First edit?</strong> Start with only the footage that might belong in this reel.</span></p>
            <Link className="min-h-9 shrink-0 content-center font-bold text-[#173F5F] underline underline-offset-4" href="/guide#first-edit">Read the 60-second guide</Link>
          </div> : null}
        </section>

        {jobId !== undefined ? <section aria-label="Upload handoff" className="rounded-xl border border-[#BFD2DE] bg-white p-4 shadow-sm sm:p-5">
          <div className="flex flex-wrap items-start justify-between gap-3"><div><p className="font-mono text-[10px] font-bold tracking-widest text-[#174D73] uppercase">Job created</p><h2 className="mt-1 text-lg font-bold text-[#173F5F]">{uploadsTransferred ? "Uploads complete" : "Sending media to the server"}</h2><p className="mt-1 text-sm leading-6 text-[#666862]">{uploadsTransferred ? "Continue now. Final checks and source analysis will finish inside the queued edit." : `Keep this page open while ${entries.length - transferredEntries} ${entries.length - transferredEntries === 1 ? "file finishes" : "files finish"} uploading.`}</p></div><span className={cn("rounded-full px-3 py-1 text-xs font-bold", uploadsTransferred ? "bg-[#E4F1E9] text-[#215B43]" : "bg-[#EFF6FA] text-[#173F5F]")}>{transferredItems} of {totalItems} transferred</span></div>
          <div aria-label="Overall upload progress" aria-valuemax={100} aria-valuemin={0} aria-valuenow={transferPercent} className="mt-4 h-2 overflow-hidden rounded-full bg-[#E9EDF0]" role="progressbar"><div className="h-full bg-[#173F5F] transition-[width] motion-reduce:transition-none" style={{ width: `${transferPercent}%` }} /></div>
          {entries.length ? <ul aria-label="Active job uploads" className="mt-4 space-y-2">{entries.map((entry) => <UploadRow entry={entry} key={entry.localId} onPause={(selected) => void pauseUpload(selected)} onRemove={removeUpload} onResume={resumeUpload} onRetry={retryUpload} />)}</ul> : null}
        </section> : null}
        <section className={cn("space-y-4 pb-4", createStep !== 1 && "hidden")} id="server-library">
          <div className="rounded-lg border border-[#D7D9D3] bg-white p-4 shadow-sm sm:p-5">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
              <div><h2 className="text-lg font-bold text-[#173F5F]">Add source media</h2><p className="mt-1 text-xs leading-5 text-[#666862]">You can combine files from this device with originals already on the server.</p></div>
              <p aria-live="polite" className="font-mono text-xs font-bold text-[#173F5F]">{selectedLibraryAssets.length} server + {entries.length} new</p>
            </div>
            <div aria-label="Choose a media source" className="mt-4 grid grid-cols-2 rounded-md bg-[#F1F2EF] p-1" role="tablist">
              <button aria-controls="device-media-panel" aria-selected={mediaSourceTab === "upload"} className={cn("min-h-11 rounded px-3 text-sm font-bold", mediaSourceTab === "upload" ? "bg-white text-[#173F5F] shadow-sm" : "text-[#666862]")} onClick={() => setMediaSourceTab("upload")} role="tab" type="button">From this device {entries.length ? `(${entries.length})` : ""}</button>
              <button aria-controls="library-media-panel" aria-selected={mediaSourceTab === "library"} className={cn("min-h-11 rounded px-3 text-sm font-bold", mediaSourceTab === "library" ? "bg-white text-[#173F5F] shadow-sm" : "text-[#666862]")} onClick={() => setMediaSourceTab("library")} role="tab" type="button">Server library {selectedLibraryAssets.length ? `(${selectedLibraryAssets.length})` : ""}</button>
            </div>
          </div>

            <div aria-label="Upload new source media" className={cn("space-y-4 rounded-lg border border-[#D7D9D3] bg-white p-4 shadow-sm sm:p-5", mediaSourceTab !== "upload" && "hidden")} id="device-media-panel" role="tabpanel">
              <h3 className="text-sm font-bold text-[#173F5F]">Upload from this device</h3>
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
            <div aria-label="Choose existing server media" className={cn("space-y-4 rounded-lg border border-[#D7D9D3] bg-white p-4 shadow-sm sm:p-5", mediaSourceTab !== "library" && "hidden")} id="library-media-panel" role="tabpanel">
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
                  maxLength={160}
                  onChange={(event) => library.changeFilters({ query: event.currentTarget.value })}
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
                    onClick={() => library.changeFilters({ kind: option.value })}
                    type="button"
                  >
                    {option.label}
                  </button>
                ))}
              </div>
              <details className="rounded-md border border-[#D7D9D3] bg-white p-3">
                <summary className="min-h-11 cursor-pointer content-center text-sm font-bold text-[#173F5F]">More filters · role, project &amp; folder</summary>
                <div className="mt-3 grid gap-4 border-t border-[#E5E6E1] pt-4 md:grid-cols-3">
                  <label className="block space-y-2 text-xs font-bold text-[#173F5F]" htmlFor="library-purpose">FOOTAGE ROLE
                    <select className="h-11 w-full rounded-md border border-[#D7D9D3] bg-white px-3 text-sm text-[#20211F]" id="library-purpose" onChange={(event) => library.changeFilters({ purpose: event.currentTarget.value })} value={libraryPurpose}>
                      <option value="all">All roles</option><option value="talking">Talking footage</option><option value="broll">B-roll</option><option value="auto">Unsorted video</option>
                    </select>
                  </label>
                  <label className="block space-y-2 text-xs font-bold text-[#173F5F]" htmlFor="library-project">
                    PROJECT
                    <select
                      className="h-11 w-full rounded-md border border-[#D7D9D3] bg-white px-3 text-sm text-[#20211F] shadow-none focus:border-[#173F5F] focus:outline-none focus:ring-2 focus:ring-[#173F5F]/20"
                      id="library-project"
                      onChange={(event) => library.changeFilters({ projectId: event.currentTarget.value })}
                      value={libraryProjectId}
                    >
                      <option value="all">All projects</option>
                      {library.projects.map(({id, name: projectName}) => (
                        <option key={id} value={id}>{projectName}</option>
                      ))}
                    </select>
                  </label>
                  <label className="block space-y-2 text-xs font-bold text-[#173F5F]" htmlFor="library-folder">FOLDER
                    <select className="min-h-11 w-full min-w-0 rounded-md border border-[#D7D9D3] bg-white px-3 text-sm" id="library-folder" value={library.filters.folderId} onChange={event => library.changeFilters({ folderId: event.currentTarget.value })}>
                      <option value="">All folders</option><option value="unfiled">Not in folders</option>
                      {library.folders.map(folder => <option key={folder.id} value={folder.id}>{folderLabel(library.folders, folder.id)}</option>)}
                    </select>
                    <span className="block text-xs font-normal text-[#666862]">Choose a folder to see files stored directly inside it.</span>
                  </label>
                  {library.optionsError ? <p role="alert" className="text-xs text-[#A23B2A] md:col-span-3">Folder/project choices could not be loaded. Refresh server media to retry.</p> : null}
                </div>
              </details>
              <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-[#53646F]">
                <span aria-live="polite">{libraryLoading ? "Loading server media…" : libraryError ? "Server media unavailable" : `${library.total ? library.filters.offset + 1 : 0}–${Math.min(library.filters.offset + filteredLibraryAssets.length, library.total)} of ${library.total} matching originals`}</span>
                <button className="min-h-11 rounded border border-[#D7D9D3] px-3 font-bold text-[#173F5F]" onClick={library.refresh} type="button">Refresh server media</button>
              </div>
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
                <div className="grid max-h-[42rem] gap-3 overflow-y-auto overscroll-contain pr-1 sm:grid-cols-2 xl:grid-cols-3" aria-label="Server media library">
                  {filteredLibraryAssets.map((asset) => (
                    <LibraryAssetRow
                      asset={asset}
                      disabled={formLocked || isSubmitting || (!selectedLibraryAssetIds.has(asset.id) && selectedLibraryAssetIds.size >= 100)}
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
                  <p className="mt-1 text-xs text-[#666862]">Try another folder or filter, or refresh server media after uploads finish.</p>
                </div>
              )}
              <div aria-label="Server media pages" className="flex flex-wrap gap-2">
                <button className="min-h-11 rounded border border-[#D7D9D3] px-3 text-sm disabled:opacity-50" disabled={libraryLoading || library.filters.offset === 0} onClick={() => library.changeFilters({ offset: Math.max(0, library.filters.offset - 60) })} type="button">Previous media page</button>
                <button className="min-h-11 rounded border border-[#D7D9D3] px-3 text-sm disabled:opacity-50" disabled={libraryLoading || Boolean(libraryError) || library.filters.offset + 60 >= library.total} onClick={() => library.changeFilters({ offset: library.filters.offset + 60 })} type="button">Next media page</button>
              </div>
              {!library.selectionReady && selectedLibraryAssetIds.size > 0 ? <p role="status" className="text-xs text-[#A23B2A]">{selectedLibraryAssetIds.size > 100 ? "Choose at most 100 server originals." : library.selectionError || library.unavailableIds.length ? "Review your selected server media below, then refresh or remove unavailable items." : "Loading selected originals before this job can be created…"}</p> : null}
              {selectedLibraryAssetIds.size ? <details className="rounded border border-[#BFD2DE] bg-[#EFF6FA] p-3" aria-label="Selected server media">
                <summary className="min-h-11 cursor-pointer content-center text-sm font-bold text-[#173F5F]">{selectedLibraryAssetIds.size} selected server originals · kept across pages and filters</summary>
                <p className="my-2 text-xs text-[#53646F]">Up to 100 originals per job. Device uploads are listed separately above.</p>
                {library.selectionError ? <p role="alert" className="my-2 text-xs text-[#A23B2A]">Selection details could not be loaded. Refresh server media to retry.</p> : null}
                {library.unavailableIds.length ? <p role="alert" className="my-2 text-xs text-[#A23B2A]">{library.unavailableIds.length} selected originals are unavailable or still processing. Remove them or restore them in Library, then refresh.</p> : null}
                {selectedLibraryAssetIds.size > 100 ? <p role="alert" className="my-2 text-xs text-[#A23B2A]">Choose at most 100 server originals before creating this job.</p> : null}
                <ul className="max-h-64 space-y-1 overflow-y-auto">{[...selectedLibraryAssetIds].map(id => <li key={id} className="flex min-w-0 items-center justify-between gap-2 text-xs"><span className="min-w-0 break-words">{selectedLibraryById.get(id)?.display_name || selectedLibraryById.get(id)?.source_name || (library.unavailableIds.includes(id) ? `Unavailable original ${id.slice(0, 8)}` : `Loading original ${id.slice(0, 8)}…`)}</span><button className="min-h-11 shrink-0 px-2 font-bold text-[#173F5F]" disabled={formLocked || isSubmitting} onClick={() => library.remove(id)} type="button" aria-label={`Remove selected original ${id}`}>Remove</button></li>)}</ul>
                <button className="mt-2 min-h-11 rounded border border-[#BFD2DE] bg-white px-3 text-xs font-bold text-[#173F5F] disabled:opacity-50" disabled={formLocked || isSubmitting} onClick={library.clear} type="button">Clear server selection</button>
              </details> : null}
              <p className="text-center font-mono text-[10px] leading-relaxed text-[#666862]">
                Selecting an item attaches the existing original. It does not copy or re-upload the file.
              </p>
            </div>
          <section className="rounded-lg border border-[#D7D9D3] bg-white p-4 shadow-sm sm:p-5" aria-labelledby="composition-heading">
            <div>
              <p className="font-mono text-[10px] font-bold tracking-wider text-[#174D73] uppercase">Composition</p>
              <h2 className="mt-1 text-lg font-bold text-[#173F5F]" id="composition-heading">How should these pictures work together?</h2>
              <p className="mt-1 text-xs leading-5 text-[#666862]">Most jobs can stay automatic. Choose green screen when one video contains the presenter and another item is the intended background.</p>
            </div>
            <div className="mt-4 grid gap-3 sm:grid-cols-3">
              {([
                ["auto", "Automatic", "GM Studio chooses a normal source-led edit."],
                ["standard", "Standard edit", "Use cuts, framing and supporting pictures without keying."],
                ["green_screen", "Green screen", "Place a keyed presenter over one chosen background."],
              ] as const).map(([value, label, description]) => (
                <label className={cn("min-h-28 rounded-md p-4", compositionMode === value ? "border-2 border-[#173F5F] bg-[#EFF6FA]" : "border border-[#D7D9D3] bg-white", formLocked ? "cursor-not-allowed opacity-60" : "cursor-pointer")} key={value}>
                  <span className="flex items-center gap-2">
                    <input checked={compositionMode === value} className="size-5 accent-[#173F5F]" disabled={formLocked} name="composition-mode" onChange={() => chooseCompositionMode(value)} type="radio" value={value} />
                    <span className="text-sm font-bold text-[#173F5F]">{label}</span>
                  </span>
                  <span className="mt-2 block text-xs leading-5 text-[#666862]">{description}</span>
                </label>
              ))}
            </div>
            {compositionMode === "green_screen" ? (
              <div className="mt-4 rounded-md border border-[#BFD2DE] bg-[#EFF6FA] p-4">
                <div className="grid gap-4 sm:grid-cols-2">
                  <label className="space-y-2 text-xs font-bold text-[#173F5F]">
                    FOREGROUND · PRESENTER
                    <select className="h-12 w-full rounded-md border border-[#BFD2DE] bg-white px-3 text-sm font-normal text-[#20211F]" disabled={formLocked} onChange={(event) => {
                      const next = event.currentTarget.value || null;
                      setForegroundAssetId(next);
                      if (next === backgroundAssetId) setBackgroundAssetId(backgroundCandidates.find((source) => source.id !== next)?.id ?? null);
                    }} value={foregroundAssetId ?? ""}>
                      <option value="">Choose presenter video</option>
                      {foregroundCandidates.map((source) => <option key={source.id} value={source.id}>{source.label} · {source.origin}</option>)}
                    </select>
                    <span className="block font-normal leading-5 text-[#53646F]">This video supplies the keyed picture and the recorded speech.</span>
                  </label>
                  <label className="space-y-2 text-xs font-bold text-[#173F5F]">
                    BACKGROUND
                    <select className="h-12 w-full rounded-md border border-[#BFD2DE] bg-white px-3 text-sm font-normal text-[#20211F]" disabled={formLocked} onChange={(event) => setBackgroundAssetId(event.currentTarget.value || null)} value={backgroundAssetId ?? ""}>
                      <option value="">Choose background</option>
                      {backgroundCandidates.filter((source) => source.id !== foregroundAssetId).map((source) => <option key={source.id} value={source.id}>{source.label} · {source.origin}</option>)}
                    </select>
                    <span className="block font-normal leading-5 text-[#53646F]">A photo or video fills the complete frame behind the presenter.</span>
                  </label>
                </div>
                {!compositionReady ? <p className="mt-3 flex items-start gap-1.5 text-xs text-[#A23B2A]" role="status"><CircleAlertIcon aria-hidden="true" className="mt-0.5 size-3.5 shrink-0" />Add at least one presenter video and a different image or video background.</p> : <p className="mt-3 flex items-center gap-1.5 text-xs font-bold text-[#215B43]"><CheckIcon aria-hidden="true" className="size-3.5" />Green-screen sources assigned</p>}
              </div>
            ) : null}
          </section>
          {jobId ? (
            <p className="text-center font-mono text-[10px] text-[#666862]" aria-live="polite">
              Job {jobId.slice(0, 8)} created
            </p>
          ) : null}
        </section>
        <div className={cn("space-y-5", createStep !== 2 && "hidden")}>
        <section className="scroll-mt-4 space-y-4 rounded-lg border border-[#D7D9D3] bg-white p-4 shadow-sm sm:p-6" id="edit-direction">
          <div><h2 className="text-lg font-bold text-[#173F5F]">Describe the result</h2><p className="mt-1 text-xs leading-5 text-[#666862]">A short plain-language instruction is enough. Add exact wording or an ordered list only when it must be followed.</p></div>
          <div className="space-y-5">
            <div className="space-y-2">
              <label className="flex justify-between text-xs font-bold text-[#173F5F]" htmlFor="project-name">
                <span>PROJECT NAME</span>
                <span className="text-[10px] text-[#666862]">OPTIONAL</span>
              </label>
              <Input
                className="h-12 rounded-sm border-[#D7D9D3] bg-white text-[#20211F] shadow-none focus-visible:border-[#173F5F] focus-visible:ring-[#173F5F]/20 dark:bg-white dark:text-[#20211F]"
                disabled={formLocked}
                id="project-name"
                maxLength={160}
                onChange={(event) => {
                  setName(event.currentTarget.value);
                  setFormError(undefined);
                }}
                placeholder={automaticProjectName}
                value={name}
              />
              {!name.trim() ? <p className="text-xs text-[#666862]">GM Studio will save this as <span className="font-bold text-[#173F5F]">{automaticProjectName}</span>. Type a name only if you want something different.</p> : null}
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
                placeholder="e.g. Make a warm product story. Keep my explanation and show the cream close-ups. No sales ending."
                value={brief}
              />
              {briefInterpretation ? (
                <div className="rounded-md border border-[#BFE3FF] bg-[#EFF6FA] p-4" aria-live="polite">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="font-mono text-[10px] font-bold tracking-wider text-[#174D73] uppercase">Instructions detected</p>
                    <div className="flex flex-wrap gap-1.5">
                      {briefInterpretation.wording_fidelity === "verbatim" ? <Badge variant="outline">Wording locked</Badge> : null}
                      {briefInterpretation.sequence_locked ? <Badge variant="outline">Order locked</Badge> : null}
                    </div>
                  </div>
                  <p className="mt-2 text-sm font-bold text-[#173F5F]">{briefInterpretation.interpretation}</p>
                  <p className="mt-1 text-xs leading-relaxed text-[#53646F]">
                    AI may decide {briefInterpretation.ai_may_decide.map((item) => item.replaceAll("_", " ")).join(", ")}. Explicit requirements in your brief still take priority.
                  </p>
                  {briefInterpretation.suggested_publishing_preset !== "custom" ? (
                    <p className="mt-2 text-xs font-bold text-[#174D73]">
                      {presentationCustomized
                        ? `Your brief suggests ${presentationPresetLabel[briefInterpretation.suggested_publishing_preset]}; your manually adjusted presentation settings were kept.`
                        : `${presentationPresetLabel[briefInterpretation.suggested_publishing_preset]} setup applied from your brief. You can change it under Optional presentation.`}
                    </p>
                  ) : null}
                </div>
              ) : null}
            </div>
            <fieldset className="space-y-2" disabled={formLocked}>
              <legend className="text-xs font-bold text-[#173F5F]">OPTIONAL BRIEF STARTERS</legend>
              <div className="flex flex-wrap gap-2">
                {([
                  ["Product story", "Make a product story from the recorded explanation and relevant supporting pictures."],
                  ["Recorded bloopers", "Make a bloopers reel. Keep the real mistake, enough setup to understand it and its genuine reaction. Trim empty waiting."],
                  ["Feel-good montage", "Make a gentle, feel-good visual montage from these scenes and pictures."],
                  ["Surprise me", "Find a coherent story in these sources and make a reel from the strongest recorded moments."],
                ] as const).map(([label, text]) => <Button className="min-h-11 whitespace-normal" key={label} type="button" variant="outline" onClick={() => setBrief((current) => current.includes(text) ? current : `${current.trim()}${current.trim() ? "\n\n" : ""}${text}`)}>{label}</Button>)}
              </div>
              <p className="text-xs text-[#666862]">Adds editable text to your brief. Nothing starts until you submit.</p>
            </fieldset>
            <details className="rounded-md border border-[#D7D9D3] bg-white p-3"><summary className="min-h-11 cursor-pointer content-center text-sm font-bold text-[#173F5F]">Optional story direction</summary>
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
            </details>
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
          </div>
        </section>
        <details className="group rounded-lg border border-[#D7D9D3] bg-white p-4 shadow-sm">
          <summary className="min-h-11 cursor-pointer text-[#173F5F] marker:text-[#173F5F]">
            <span className="ml-2 inline-flex max-w-[calc(100%-2rem)] flex-col align-middle">
              <span className="text-sm font-bold">Optional presentation</span>
              <span className="mt-1 text-xs font-normal leading-relaxed text-[#666862]">
                {presentationPresetLabel[publishingPreset]} · {presentationShapeLabel[outputAspect]} · {presentationDurationLabel} · {presentationStyleLabel}
              </span>
              <span className="mt-1 text-[11px] font-bold text-[#174D73] group-open:hidden">Open only if you want to change the recommended setup</span>
            </span>
          </summary>
          <div className="mt-5 space-y-5 border-t border-[#E5E6E1] pt-5">
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
                    setPresentationCustomized(true);
                    const profile = creativeProfiles.find((item) => item.id === event.currentTarget.value);
                    setCreativeProfileId(profile?.id ?? null);
                    if (profile) {
                      setTargetDuration(profile.target_duration_seconds);
                      setEditStyle(profile.edit_style);
                      setPacingMode("auto");
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
                  Applies saved presentation defaults: pacing, music, platform, shape and reasoning. Your brief still guides automatic pacing; the profile does not change assembly or purpose.
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
                    applyPublishingPreset(preset, true);
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
                Presets set the platform, shape and preferred duration. Your duration mode and maximum below take precedence. Brand kits apply your caption colours, weight and typeface.
              </p>
            </div>
            <DurationFields disabled={formLocked}
              settings={{ duration_mode: durationMode, target_duration_seconds: targetDuration, max_duration_seconds: maxDuration }}
              onChange={(value) => { setPresentationCustomized(true); setDurationMode(value.duration_mode); setTargetDuration(value.target_duration_seconds); setMaxDuration(value.max_duration_seconds); }} />
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
                      onChange={() => { setPresentationCustomized(true); setOutputAspect(option.value); }}
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
                <CreativeOptionCard description={`Use explicit pacing in your brief; otherwise use ${editStyle.replaceAll("_", " ")} presentation defaults.`} disabled={formLocked} label="Follow my brief" name="edit-style" onChange={() => { setPresentationCustomized(true); setPacingMode("auto"); }} selected={pacingMode === "auto"} value="auto" />
                {EDIT_STYLE_OPTIONS.map((option) => (
                  <CreativeOptionCard
                    description={option.description}
                    disabled={formLocked}
                    key={option.value}
                    label={option.label}
                    name="edit-style"
                    onChange={() => {
                      setPresentationCustomized(true);
                      setEditStyle(option.value);
                      setPacingMode("manual");
                      if (option.value === "high_impact" && effectLevel === "off" && compatibleEffectCount > 0 && privacyMode !== "local_only") setEffectLevel("social");
                    }}
                    selected={pacingMode === "manual" && editStyle === option.value}
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
                    setPresentationCustomized(true);
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
            <details className="rounded-md border border-[#D7D9D3] bg-white p-3"><summary className="min-h-11 cursor-pointer content-center text-sm font-bold text-[#173F5F]">Advanced model settings</summary>
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
            </details>
          </div>
        </details>
        <details className="group rounded-lg border border-[#D7D9D3] bg-white p-4 shadow-sm">
          <summary className="min-h-11 cursor-pointer text-[#173F5F] marker:text-[#173F5F]">
            <span className="ml-2 inline-flex max-w-[calc(100%-2rem)] flex-col align-middle">
              <span className="text-sm font-bold">Advanced editor controls</span>
              <span className="mt-1 text-xs font-normal leading-relaxed text-[#666862]">{assemblySummary} · {privacySummary} privacy · {reasoningEffort} model effort</span>
              <span className="mt-1 text-[11px] font-bold text-[#174D73] group-open:hidden">Most users can leave these unchanged</span>
            </span>
          </summary>
          <div className="mt-5 space-y-5 border-t border-[#E5E6E1] pt-5">
          <fieldset className="space-y-4" disabled={formLocked}>
            <label className="block text-xs font-bold text-[#173F5F]" htmlFor="assembly-mode">ASSEMBLY
              <select id="assembly-mode" className="mt-2 h-12 w-full rounded-md border border-[#D7D9D3] bg-white px-3 text-sm" value={assemblyMode} onChange={(event) => setAssemblyMode(event.currentTarget.value as AssemblyMode)}>
                <option value="auto">Automatic from brief and analysed media</option><option value="talking_head">Speech with supporting pictures</option><option value="montage">Visual montage</option>
              </select>
            </label>
            <p className="text-xs text-[#666862]">Automatic keeps recorded dialogue when it is central, or uses a visual sequence. Source analysis and interpretation continue automatically after the edit is queued.</p>
          <div className="space-y-2">
            <label className="text-xs font-bold text-[#173F5F]" htmlFor="reel-intent">REEL PURPOSE</label>
            <select
              className="h-12 w-full rounded-md border border-[#D7D9D3] bg-white px-3 text-sm"
              id="reel-intent"
              value={reelIntent}
              onChange={(event) => setReelIntent(event.currentTarget.value as typeof reelIntent)}
            >
              <option value="auto">Follow my brief</option>
              <option value="story">Story / explanation</option>
              <option value="promotion">Product / promotion</option>
              <option value="bloopers">Bloopers / outtakes</option>
            </select>
            <p className="text-xs leading-relaxed text-[#666862]">
              {reelIntent === "bloopers"
                ? "Keep the recorded setup, stumble and real reaction. No sales payoff or call to action is required."
                : "Purpose guides the story; pacing, effects and publishing presets control presentation. Saved creative profiles do not change this choice."}
            </p>
          </div>
          </fieldset>
        <fieldset className="space-y-4" disabled={formLocked}>
          <legend className="sr-only">Privacy</legend>
          <SectionHeading number="04">Privacy</SectionHeading>
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
        </details>
        </div>

        <section className={cn("space-y-4", createStep !== 3 && "hidden")} aria-label="Review job before creating">
          <div className="grid gap-4 lg:grid-cols-2">
            <article className="rounded-lg border border-[#D7D9D3] bg-white p-5 shadow-sm">
              <div className="flex items-start justify-between gap-4">
                <div><p className="font-mono text-[10px] font-bold tracking-wide text-[#174D73] uppercase">Media</p><h2 className="mt-1 text-lg font-bold text-[#173F5F]">{totalItems} selected {totalItems === 1 ? "item" : "items"}</h2></div>
                <button className="min-h-10 text-xs font-bold text-[#173F5F] underline underline-offset-4" onClick={() => goToStep(1)} type="button">Change</button>
              </div>
              {selectedMediaNames.length ? <ul className="mt-4 space-y-2 text-sm text-[#53646F]">{selectedMediaNames.slice(0, 5).map((item, index) => <li className="truncate" key={`${item}-${index}`}>• {item}</li>)}</ul> : <p className="mt-4 text-sm text-[#A23B2A]">No media selected.</p>}
              {selectedMediaNames.length > 5 ? <p className="mt-2 text-xs text-[#666862]">+ {selectedMediaNames.length - 5} more</p> : null}
            </article>

            <article className="rounded-lg border border-[#D7D9D3] bg-white p-5 shadow-sm">
              <div className="flex items-start justify-between gap-4">
                <div><p className="font-mono text-[10px] font-bold tracking-wide text-[#174D73] uppercase">Direction</p><h2 className="mt-1 text-lg font-bold text-[#173F5F]">{name.trim() || automaticProjectName}</h2></div>
                <button className="min-h-10 text-xs font-bold text-[#173F5F] underline underline-offset-4" onClick={() => goToStep(2)} type="button">Change</button>
              </div>
              <p className="mt-4 line-clamp-5 whitespace-pre-line text-sm leading-6 text-[#53646F]">{brief.trim() || "No brief supplied. GM Studio will find a coherent story from the selected media."}</p>
              {briefInterpretation ? <div className="mt-4 rounded-md bg-[#EFF6FA] p-3"><p className="text-xs font-bold text-[#173F5F]">{briefInterpretation.interpretation}</p>{briefInterpretation.sequence_locked ? <p className="mt-1 text-xs text-[#53646F]">Requested order will be protected.</p> : null}</div> : null}
              <p className="mt-3 text-xs text-[#53646F]"><span className="font-bold text-[#173F5F]">Composition:</span> {compositionMode === "green_screen" ? "Green screen with assigned presenter and background" : compositionMode === "standard" ? "Standard edit" : "Automatic"}</p>
            </article>
          </div>

          <article className="rounded-lg border border-[#BFD2DE] bg-[#EFF6FA] p-5">
            <div className="flex items-start justify-between gap-4"><div><p className="font-mono text-[10px] font-bold tracking-wide text-[#174D73] uppercase">Output</p><h2 className="mt-1 text-lg font-bold text-[#173F5F]">{presentationPresetLabel[publishingPreset]} · {presentationShapeLabel[outputAspect]}</h2></div><button className="min-h-10 text-xs font-bold text-[#173F5F] underline underline-offset-4" onClick={() => goToStep(2)} type="button">Change</button></div>
            <div className="mt-4 grid gap-3 text-sm text-[#53646F] sm:grid-cols-3">
              <p><span className="block text-[10px] font-bold tracking-wide uppercase">Duration</span>{presentationDurationLabel}</p>
              <p><span className="block text-[10px] font-bold tracking-wide uppercase">Editing</span>{presentationStyleLabel}</p>
              <p><span className="block text-[10px] font-bold tracking-wide uppercase">Processing</span>{assemblySummary} · {privacySummary}</p>
            </div>
          </article>

          <div className="rounded-md border border-[#D7D9D3] bg-white p-4 text-xs leading-5 text-[#666862]">
            <strong className="text-[#173F5F]">What happens next:</strong> GM Studio creates the job, uploads any new files, analyses the media, and shows its interpretation before editing starts. Nothing is published automatically.
          </div>
        </section>
      </main>

      <footer className="z-50 shrink-0 touch-none scroll-mt-4 border-t border-[#D7D9D3] bg-white px-4 pt-4 pb-[max(1rem,env(safe-area-inset-bottom))] dark:bg-white" id="create-action">
        <div className="mx-auto w-full max-w-7xl">
        {formError ? (
          <p className="mb-3 flex items-start gap-1.5 text-xs leading-relaxed text-[#A23B2A]" role="alert">
            <CircleAlertIcon aria-hidden="true" className="mt-0.5 size-3.5 shrink-0" />
            {formError}
          </p>
        ) : null}
        <div className="mb-3 flex items-end justify-between">
          <div>
            <span className="block font-mono text-[10px] font-bold text-[#666862] uppercase">{jobId ? "Job progress" : `Step ${createStep} of 3`}</span>
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
          {uploadsTransferred ? (
            <Badge className="rounded-sm border-[#BFE3FF] bg-[#E8F5FF] font-mono text-[10px] font-bold text-[#173F5F]" variant="outline">
              <CheckIcon aria-hidden="true" /> Uploaded
            </Badge>
          ) : null}
        </div>
        {jobId !== undefined ? (
          <Button
            className="h-14 w-full touch-manipulation rounded-md bg-[#173F5F] text-sm font-bold text-white hover:bg-[#12344F] focus-visible:ring-[#173F5F]/35 disabled:bg-[#8A9CAB]"
            disabled={isSubmitting || !uploadsTransferred}
            onClick={uploadsTransferred ? () => void startEditing() : undefined}
            type="button"
          >
            {isSubmitting ? <><LoaderCircleIcon aria-hidden="true" className="animate-spin motion-reduce:animate-none" /><span>Starting edit…</span></> : uploadsTransferred ? <><span>Continue to editing</span><ArrowRightIcon aria-hidden="true" /></> : <><LoaderCircleIcon aria-hidden="true" className="animate-spin motion-reduce:animate-none" /><span>Finish uploads to continue</span></>}
          </Button>
        ) : (
          <div className={cn("grid gap-2", createStep > 1 && "grid-cols-[auto_1fr]")}>
            {createStep > 1 ? <Button className="h-14 px-5" onClick={() => goToStep(createStep === 3 ? 2 : 1)} type="button" variant="outline">Back</Button> : null}
            <Button
              className="h-14 w-full touch-manipulation rounded-md bg-[#173F5F] text-sm font-bold text-white hover:bg-[#12344F] focus-visible:ring-[#173F5F]/35 disabled:bg-[#8A9CAB]"
              disabled={isSubmitting || !library.selectionReady || totalItems === 0 || !compositionReady}
              onClick={createStep < 3 ? () => goToStep((createStep + 1) as CreateStep) : undefined}
              type={createStep === 3 ? "submit" : "button"}
            >
              {isSubmitting ? <><LoaderCircleIcon aria-hidden="true" className="animate-spin motion-reduce:animate-none" />Creating job…</>
                : createStep === 1 ? <>Continue to direction<ArrowRightIcon aria-hidden="true" /></>
                  : createStep === 2 ? <>Review job<ArrowRightIcon aria-hidden="true" /></>
                    : <>{entries.length > 0 ? "Create job & upload" : "Create job"}<ArrowRightIcon aria-hidden="true" /></>}
            </Button>
          </div>
        )}
        </div>
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
