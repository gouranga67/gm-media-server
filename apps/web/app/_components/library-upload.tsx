"use client";

import { useEffect, useRef, useState } from "react";
import type { Upload } from "tus-js-client";
import { CheckIcon, LoaderCircleIcon, PauseIcon, PlayIcon, UploadCloudIcon, XIcon } from "lucide-react";

import { createProject, getAsset, getAssetAnalysis, mediaTypeForFile, registerAsset, updateLibraryBatch, type MediaRole } from "@/lib/media-api";
import { startResumableUpload } from "@/lib/resumable-upload";

type Phase = "queued" | "preparing" | "uploading" | "paused" | "indexing" | "ready" | "error";
type Entry = {
  readonly id: string;
  readonly file: File;
  readonly phase: Phase;
  readonly progress: number;
  readonly assetId?: string;
  readonly uploaded?: boolean;
  readonly error?: string;
};

function message(error: unknown): string {
  return error instanceof Error ? error.message : "Upload unavailable. Try again.";
}

export function LibraryUpload({ onReady }: { readonly onReady: () => Promise<void> }) {
  const [entries, setEntries] = useState<readonly Entry[]>([]);
  const [batchName, setBatchName] = useState("Library uploads");
  const [namePrefix, setNamePrefix] = useState("");
  const [mediaRole, setMediaRole] = useState<MediaRole>("auto");
  const preferences = useRef(new Map<string, { name?: string; role: MediaRole }>());
  const [starting, setStarting] = useState(false);
  const [hasProject, setHasProject] = useState(false);
  const [error, setError] = useState<string>();
  const projectId = useRef<string | undefined>(undefined);
  const projectRequestId = useRef<string | undefined>(undefined);
  const handles = useRef(new Map<string, Upload>());
  const mounted = useRef(true);
  const busy = useRef(false);
  const readyCallback = useRef(onReady);
  useEffect(() => { readyCallback.current = onReady; }, [onReady]);
  useEffect(() => {
    mounted.current = true;
    const activeHandles = handles.current;
    return () => {
      mounted.current = false;
      for (const upload of activeHandles.values()) void upload.abort().catch(() => undefined);
    };
  }, []);

  const update = (id: string, changes: Partial<Entry>) => {
    if (mounted.current) setEntries((current) => current.map((entry) => entry.id === id ? { ...entry, ...changes } : entry));
  };

  async function checkReady(entry: Entry, assetId: string) {
    update(entry.id, { phase: "indexing", error: undefined });
    let failures = 0;
    for (let attempt = 0; attempt < 300 && mounted.current; attempt += 1) {
      try {
        const asset = await getAsset(assetId);
        if (!mounted.current) return;
        if (["failed", "quarantined", "error"].includes(asset.status)) {
          update(entry.id, { phase: "error", error: "Server verification needs attention. The file remains on this device." });
          return;
        }
        if (asset.status === "ready") {
          const analysis = await getAssetAnalysis(assetId);
          if (!mounted.current) return;
          if (analysis.status === "ready") {
            const preference = preferences.current.get(entry.id);
            if (preference?.name) await updateLibraryBatch([assetId], "rename", { namePrefix: preference.name });
            if (preference?.role && preference.role !== "auto" && mediaTypeForFile(entry.file).startsWith("video/")) {
              await updateLibraryBatch([assetId], "role", { mediaRole: preference.role });
            }
            update(entry.id, { phase: "ready", progress: 100, error: undefined });
            if (mounted.current) void readyCallback.current().catch(() => undefined);
            return;
          }
          if (analysis.status === "failed") {
            update(entry.id, { phase: "error", error: `Original saved; analysis needs attention: ${analysis.error ?? "local analysis failed"}` });
            return;
          }
        }
        failures = 0;
      } catch (requestError) {
        // tus completion can precede creation of the ingest row.
        if (message(requestError) !== "asset analysis has not been queued" && ++failures >= 3) {
          update(entry.id, { phase: "error", error: `Upload finished; check server status again: ${message(requestError)}` });
          return;
        }
      }
      await new Promise((resolve) => window.setTimeout(resolve, 2_000));
    }
    update(entry.id, { phase: "error", error: "Original uploaded; analysis is still running. Check status again shortly." });
  }

  async function transfer(entry: Entry, activeProjectId: string) {
    update(entry.id, { phase: "preparing", error: undefined });
    try {
      // A project groups this upload batch; job_id=null creates no editing job.
      const asset = await registerAsset(activeProjectId, null, entry.file, entry.id);
      update(entry.id, { assetId: asset.id });
      const upload = await startResumableUpload(entry.file, asset, {
        onProgress(bytes, total) {
          update(entry.id, { progress: total ? Math.min(100, Math.round(bytes * 100 / total)) : 0 });
        },
        onRetry() { update(entry.id, { error: "Connection interrupted; retrying upload…" }); },
        onError(uploadError) { update(entry.id, { phase: "error", error: uploadError.message }); },
        onSuccess() {
          update(entry.id, { uploaded: true, progress: 100, phase: "indexing", error: undefined });
          void checkReady(entry, asset.id);
        },
      });
      handles.current.set(entry.id, upload);
      if (mounted.current) setEntries((current) => current.map((item) => item.id === entry.id && item.phase === "preparing"
        ? { ...item, phase: "uploading" } : item));
      if (!mounted.current) await upload.abort();
    } catch (uploadError) {
      update(entry.id, { phase: "error", error: message(uploadError) });
    }
  }

  function choose(files: readonly File[]) {
    const identities = new Set(entries.map((entry) => `${entry.file.name}:${entry.file.size}:${entry.file.lastModified}`));
    const added: Entry[] = [];
    const rejected: string[] = [];
    for (const file of files) {
      try {
        mediaTypeForFile(file);
        if (!file.size) throw new Error(`${file.name} is empty.`);
        if (file.size > 20 * 1024 ** 3) throw new Error(`${file.name} exceeds 20 GB.`);
        if (file.name.length > 255) throw new Error(`${file.name} has a filename longer than 255 characters.`);
        const identity = `${file.name}:${file.size}:${file.lastModified}`;
        if (identities.has(identity)) continue;
        identities.add(identity);
        added.push({ id: crypto.randomUUID(), file, phase: "queued", progress: 0 });
      } catch (fileError) { rejected.push(message(fileError)); }
    }
    setError(rejected.length ? rejected.join(" ") : undefined);
    setEntries((current) => [...current, ...added]);
  }

  async function uploadSelected() {
    if (busy.current || !batchName.trim()) return;
    const queued = entries.filter((entry) => entry.phase === "queued");
    if (!queued.length) return;
    busy.current = true;
    setStarting(true);
    setError(undefined);
    try {
      if (!projectId.current) {
        projectRequestId.current ??= crypto.randomUUID();
        const project = await createProject({ id: projectRequestId.current, name: batchName.trim(), brief: "",
          privacyMode: "local_only", aiCopyAllowed: false });
        projectId.current = project.id;
        if (mounted.current) setHasProject(true);
      }
      const activeProjectId = projectId.current;
      for (const entry of queued) {
        if (!preferences.current.has(entry.id)) preferences.current.set(entry.id, {
          name: namePrefix.trim() ? `${namePrefix.trim()} ${String(entries.indexOf(entry) + 1).padStart(3, "0")}` : undefined,
          role: mediaRole,
        });
      }
      await Promise.all(queued.map((entry) => transfer(entry, activeProjectId)));
    } catch (requestError) {
      if (mounted.current) setError(message(requestError));
    } finally {
      busy.current = false;
      if (mounted.current) setStarting(false);
    }
  }

  async function pause(entry: Entry) {
    try {
      await handles.current.get(entry.id)?.abort();
      update(entry.id, { phase: "paused", error: undefined });
    } catch (uploadError) { update(entry.id, { error: message(uploadError) }); }
  }

  function retry(entry: Entry) {
    if (entry.uploaded && entry.assetId) { void checkReady(entry, entry.assetId); return; }
    const handle = handles.current.get(entry.id);
    if (handle) {
      update(entry.id, { phase: "uploading", error: undefined });
      handle.start();
    } else if (projectId.current) void transfer(entry, projectId.current);
  }

  const queuedCount = entries.filter((entry) => entry.phase === "queued").length;
  const busyCount = entries.filter((entry) => ["preparing", "uploading", "paused", "indexing"].includes(entry.phase)).length;
  const actionClass = "inline-flex min-h-11 items-center justify-center gap-2 rounded-md border border-[#D7D9D3] bg-white px-3 text-xs font-bold text-[#173F5F] disabled:opacity-60";
  return (
    <section aria-labelledby="library-upload-heading" className="mt-6 space-y-4 rounded-md border border-[#BFD2DE] bg-[#EFF6FA] p-4 sm:p-5">
      <div>
        <h2 className="flex items-center gap-2 text-lg font-bold text-[#173F5F]" id="library-upload-heading"><UploadCloudIcon aria-hidden="true" className="size-5" />Upload to library</h2>
        <p className="mt-1 text-sm leading-6 text-[#4E5960]">Save footage, product close-ups, photos, or audio for future edits. Uploading here creates no editing job.</p>
      </div>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
        <label className="flex-1 text-xs font-bold text-[#173F5F]">Upload group name
          <input className="mt-2 h-11 w-full rounded-md border border-[#D7D9D3] bg-white px-3 text-sm text-[#20211F] disabled:opacity-60" disabled={starting || hasProject} maxLength={160} onChange={(event) => setBatchName(event.currentTarget.value)} value={batchName} />
        </label>
        <label className={`${actionClass} cursor-pointer focus-within:ring-2 focus-within:ring-[#173F5F]`}>
          <UploadCloudIcon aria-hidden="true" className="size-4" />Choose files
          <input accept="video/*,image/*,audio/*,.heic,.heif" aria-label="Choose files for the media library" className="sr-only" disabled={starting} multiple onChange={(event) => { choose(Array.from(event.currentTarget.files ?? [])); event.currentTarget.value = ""; }} type="file" />
        </label>
        <button className="inline-flex min-h-11 items-center justify-center gap-2 rounded-md bg-[#173F5F] px-4 text-sm font-bold text-white disabled:opacity-60" disabled={starting || !queuedCount || !batchName.trim()} onClick={() => void uploadSelected()} type="button">
          {starting ? <LoaderCircleIcon aria-hidden="true" className="size-4 animate-spin motion-reduce:animate-none" /> : <UploadCloudIcon aria-hidden="true" className="size-4" />}
          {starting ? "Starting uploads…" : queuedCount ? `Upload ${queuedCount} ${queuedCount === 1 ? "file" : "files"} to library` : "Upload to library"}
        </button>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="text-xs font-bold text-[#666862]">Name these files <span className="font-normal">(optional)</span><input aria-label="Upload file name prefix" className="mt-1 min-h-11 w-full rounded-md border border-[#D7D9D3] px-3 text-sm text-[#20211F]" disabled={starting || hasProject} maxLength={230} onChange={(event) => setNamePrefix(event.currentTarget.value)} placeholder="e.g. Cream close-up → Cream close-up 001" value={namePrefix} /></label>
        <label className="text-xs font-bold text-[#666862]">Footage role<select aria-label="Upload footage role" className="mt-1 min-h-11 w-full rounded-md border border-[#D7D9D3] bg-white px-3 text-sm text-[#20211F]" disabled={starting || hasProject} onChange={(event) => setMediaRole(event.currentTarget.value as MediaRole)} value={mediaRole}><option value="auto">Unsorted video</option><option value="talking">Talking footage</option><option value="broll">B-roll</option></select></label>
      </div>
      <p className="text-xs text-[#666862]">Names are numbered in upload order. Footage roles apply to videos; photos and audio keep their own views.</p>
      {error ? <p className="text-sm text-[#A23B2A]" role="alert">{error}</p> : null}
      {entries.length ? <ul aria-label="Library uploads" className="space-y-2">{entries.map((entry) => (
        <li className="rounded-md border border-[#D7D9D3] bg-white p-3" key={entry.id}>
          <div className="flex items-center justify-between gap-3">
            <div className="min-w-0"><p className="truncate text-sm font-bold text-[#173F5F]">{entry.file.name}</p><p aria-live="polite" className="mt-1 text-xs text-[#666862]">{entry.phase === "queued" ? "Selected · ready to upload" : entry.phase === "preparing" ? "Preparing upload…" : entry.phase === "ready" ? "Ready in your library" : entry.phase === "indexing" ? "Uploaded · analysing on the server" : entry.phase === "paused" ? "Paused" : entry.phase === "error" ? "Needs attention" : `Uploading ${entry.progress}%`}</p></div>
            {entry.phase === "queued" ? <button aria-label={`Remove ${entry.file.name}`} className={actionClass} onClick={() => setEntries((current) => current.filter((item) => item.id !== entry.id))} type="button"><XIcon aria-hidden="true" className="size-4" /></button>
              : entry.phase === "uploading" ? <button aria-label={`Pause ${entry.file.name}`} className={actionClass} onClick={() => void pause(entry)} type="button"><PauseIcon aria-hidden="true" className="size-4" /></button>
                : entry.phase === "paused" || entry.phase === "error" ? <button aria-label={`${entry.uploaded ? "Check status of" : "Resume"} ${entry.file.name}`} className={actionClass} onClick={() => retry(entry)} type="button"><PlayIcon aria-hidden="true" className="size-4" />{entry.uploaded ? "Check status" : "Resume"}</button>
                  : entry.phase === "ready" ? <CheckIcon aria-label={`${entry.file.name} is ready`} className="size-5 shrink-0 text-[#307455]" /> : <LoaderCircleIcon aria-label={entry.phase === "preparing" ? "Preparing upload" : "Analysing"} className="size-5 shrink-0 animate-spin text-[#173F5F] motion-reduce:animate-none" />}
          </div>
          {entry.phase === "uploading" ? <progress aria-label={`${entry.file.name} upload progress`} className="mt-2 h-1.5 w-full accent-[#173F5F]" max={100} value={entry.progress} /> : null}
          {entry.error ? <p className="mt-2 text-xs text-[#A23B2A]" role="alert">{entry.error}</p> : null}
        </li>
      ))}</ul> : null}
      <p className="text-xs leading-5 text-[#4E5960]">{busyCount ? "Keep this page open while files upload and are analysed. " : ""}Once ready, select these files alongside your existing footage in New job.</p>
    </section>
  );
}
