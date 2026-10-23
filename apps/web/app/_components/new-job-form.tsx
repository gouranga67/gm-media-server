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
  ImageIcon,
  LoaderCircleIcon,
  PauseIcon,
  PlayIcon,
  RefreshCwIcon,
  Trash2Icon,
  UploadCloudIcon,
  VideoIcon,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  createProject,
  createMediaJob,
  getEditorModels,
  getAsset,
  getMusicTracks,
  getSystemInformation,
  mediaTypeForFile,
  registerAsset,
  requestPreview,
  type Asset,
  type EditStyle,
  type EditorModel,
  type MusicMode,
  type MusicTrack,
  type PrivacyMode,
  type OutputAspect,
  type ReasoningEffort,
  type Recipe,
  type TargetDuration,
  type TargetPlatform,
} from "@/lib/media-api";
import { startResumableUpload } from "@/lib/resumable-upload";
import { cn } from "@/lib/utils";

const MAX_FILE_BYTES = 20 * 1024 * 1024 * 1024;
const READY_POLL_ATTEMPTS = 45;
const READY_POLL_INTERVAL_MS = 1_000;

type ServerStatus = "checking" | "online" | "offline";
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

function phaseLabel(entry: UploadEntry): string {
  const percent =
    entry.totalBytes === 0 ? 0 : Math.min(100, Math.round((entry.uploadedBytes / entry.totalBytes) * 100));

  switch (entry.phase) {
    case "queued":
      return "Queued";
    case "registering":
      return "Preparing";
    case "uploading":
      return `Uploading ${percent}%`;
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
  const [targetPlatform, setTargetPlatform] = useState<TargetPlatform>("all_social");
  const [mustInclude, setMustInclude] = useState("");
  const [editorModels, setEditorModels] = useState<readonly EditorModel[]>([]);
  const [editorModel, setEditorModel] = useState<string | null>(null);
  const [reasoningEffort, setReasoningEffort] = useState<ReasoningEffort>("medium");
  const [outputAspect, setOutputAspect] = useState<OutputAspect>("vertical");
  const [musicTracks, setMusicTracks] = useState<readonly MusicTrack[]>([]);
  const [entries, setEntries] = useState<UploadEntry[]>([]);
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
    void Promise.all([getSystemInformation(), getMusicTracks(), getEditorModels()])
      .then(([, tracks, models]) => {
        if (!cancelled) {
          setMusicTracks(tracks);
          setEditorModels(models);
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

  const totalBytes = entries.reduce((total, entry) => total + entry.file.size, 0);
  const allReady = entries.length > 0 && entries.every((entry) => entry.phase === "ready");
  const formLocked = projectId !== undefined;
  const compatibleMusicCount = musicTracks.filter(
    (track) =>
      track.allowed_platforms.includes("all_social")
      || track.allowed_platforms.includes(targetPlatform),
  ).length;
  const durationOptions: readonly TargetDuration[] = recipe === "montage" ? [15, 30, 45, 60] : [20, 30, 45, 60];

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
      onProgress(uploadedBytes, totalUploadBytes) {
        const percent = totalUploadBytes === 0 ? 0 : Math.floor((uploadedBytes / totalUploadBytes) * 100);
        if (lastProgressRef.current.get(entry.localId) === percent) return;
        lastProgressRef.current.set(entry.localId, percent);
        updateEntry(entry.localId, {
          phase: "uploading",
          uploadedBytes,
          totalBytes: totalUploadBytes,
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
    if (entries.length === 0) {
      setFormError("Add at least one source media file.");
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
          targetPlatform,
          mustInclude: mustInclude.trim(),
          editorModel,
          reasoningEffort,
          outputAspect,
        });
        activeJobId = job.id;
        setJobId(job.id);
      }

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
          <div className="flex items-center gap-3">
            <p className="text-sm font-bold tracking-tight text-[#173F5F]">GM Studio</p>
            <Link className="font-mono text-[10px] font-bold text-[#173F5F] underline underline-offset-4" href="/usage">
              AI usage
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
            Agents plan the edit. Visuals and speech come only from your uploads; optional music comes from your approved local library.
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
            </fieldset>
            <fieldset className="space-y-3" disabled={formLocked}>
              <legend className="text-xs font-bold text-[#173F5F]">OUTPUT SHAPE</legend>
              <div className="grid grid-cols-2 gap-2">
                {([
                  { value: "vertical", label: "Vertical 9:16" },
                  { value: "landscape", label: "Landscape 16:9" },
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
                    onChange={() => setEditStyle(option.value)}
                    selected={editStyle === option.value}
                    value={option.value}
                  />
                ))}
              </div>
            </fieldset>
            <fieldset className="space-y-3" disabled={formLocked}>
              <legend className="text-xs font-bold text-[#173F5F]">BACKING MUSIC</legend>
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
                    onChange={() => setMusicMode(option.value)}
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
                onChange={setPrivacyMode}
                selected={privacyMode === option.value}
                value={option.value}
              />
            ))}
          </div>
          <label className={cn("flex min-h-14 items-start justify-between gap-4 pt-4", formLocked ? "cursor-not-allowed opacity-60" : "cursor-pointer")}>
            <span className="space-y-1">
              <span className="block text-sm font-bold text-[#173F5F]">Allow AI-written caption copy</span>
              <span className="block text-xs leading-relaxed text-[#666862]">
                This affects text only. Visuals and speech remain grounded in your uploads.
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

        <section className="space-y-4 pb-8">
          <SectionHeading number="04">Source media</SectionHeading>
          <label
            className={cn(
              "flex min-h-36 w-full cursor-pointer flex-col items-center justify-center rounded-md border-2 border-dashed border-[#C7CBD0] bg-white p-6 text-center transition-colors hover:border-[#173F5F] focus-within:border-[#173F5F] focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-[#173F5F] dark:bg-white",
              isSubmitting && "pointer-events-none cursor-wait opacity-60",
            )}
            onDragOver={(event) => event.preventDefault()}
            onDrop={handleDrop}
          >
            <UploadCloudIcon aria-hidden="true" className="mb-2 size-6 text-[#173F5F]" />
            <span className="text-sm font-bold text-[#173F5F]">Add source media</span>
            <span className="mt-1 font-mono text-[10px] tracking-tight text-[#666862] uppercase">
              Video, photo, audio · Up to 20 GB per file
            </span>
            <input
              accept="video/*,image/*,audio/*,.heic,.heif"
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
            <ul aria-label="Selected source media" className="space-y-2">
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
            <p className="text-center font-mono text-[10px] text-[#666862]">No source files selected yet.</p>
          )}
          <p className="text-center font-mono text-[10px] leading-relaxed text-[#666862]">
            Interrupted uploads continue when this phone reconnects. Keep the file on your phone until it shows Ready.
          </p>
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
              {entries.length === 0
                ? "No files"
                : `${entries.length} ${entries.length === 1 ? "file" : "files"} · ${formatBytes(totalBytes)}`}
            </span>
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
              Create job &amp; upload
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
