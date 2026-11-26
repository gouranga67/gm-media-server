"use client";

import { folderLabel } from "@/lib/library-folder-tree";

import { useEffect, useRef, useState } from "react";
import type { Upload } from "tus-js-client";
import { CheckIcon, LoaderCircleIcon, PauseIcon, PlayIcon, UploadCloudIcon, XIcon } from "lucide-react";

import { createProject, getLibraryIntakeStatus, mediaTypeForFile, registerAsset, type MediaRole, type LibraryCollection, type LibraryIntakePreferences } from "@/lib/media-api";
import { startResumableUpload } from "@/lib/resumable-upload";
import { GoogleDriveImport } from "@/app/_components/google-drive-import";

type Phase = "queued" | "waiting" | "preparing" | "uploading" | "paused" | "indexing" | "ready" | "error";
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

export function LibraryUpload({ onReady, folders = [], destination = "" }: {
  readonly onReady: () => Promise<void>; readonly folders?: readonly LibraryCollection[]; readonly destination?: string;
}) {
  const [entries, setEntries] = useState<readonly Entry[]>([]);
  const [source, setSource] = useState<"device" | "drive">("device");
  const [batchName, setBatchName] = useState("Library uploads");
  const [namePrefix, setNamePrefix] = useState("");
  const [mediaRole, setMediaRole] = useState<MediaRole>("auto");
  const [folderId, setFolderId] = useState(destination);
  const preferences = useRef(new Map<string, LibraryIntakePreferences>());
  const [starting, setStarting] = useState(false);
  const [hasProject, setHasProject] = useState(false);
  useEffect(() => { if (destination && !hasProject && !entries.length) setFolderId(destination); }, [destination, hasProject, entries.length]);
  const [error, setError] = useState<string>();
  const projectId = useRef<string | undefined>(undefined);
  const projectRequestId = useRef<string | undefined>(undefined);
  const handles = useRef(new Map<string, Upload>());
  const activeTransfers = useRef(new Set<string>());
  const waitingTransfers = useRef(new Map<string, { entry: Entry; projectId: string }>());
  const mounted = useRef(true);
  const busy = useRef(false);
  const readyCallback = useRef(onReady);
  useEffect(() => { readyCallback.current = onReady; }, [onReady]);
  useEffect(() => {
    mounted.current = true;
    const activeHandles = handles.current;
    return () => {
      mounted.current = false;
      waitingTransfers.current.clear();
      for (const upload of activeHandles.values()) void upload.abort().catch(() => undefined);
    };
  }, []);

  const update = (id: string, changes: Partial<Entry>) => {
    if (mounted.current) setEntries((current) => current.map((entry) => entry.id === id ? { ...entry, ...changes } : entry));
  };

  const indexingIds = entries.filter((entry) => entry.phase === "indexing" && entry.assetId).map((entry) => entry.assetId!).join(",");
  useEffect(() => {
    if (!indexingIds) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    const ids = indexingIds.split(",");
    async function poll() {
      try {
        const statuses = [];
        // Sequential groups keep requests and response size bounded even for 200 files.
        for (let index = 0; index < ids.length && !cancelled; index += 100) statuses.push(...await getLibraryIntakeStatus(ids.slice(index, index + 100)));
        if (cancelled) return;
        setError((current) => current?.startsWith("Originals uploaded. Status is temporarily unavailable:") ? undefined : current);
        const states = new Map(statuses.map((item) => [item.id, item]));
        setEntries((current) => current.map((entry) => {
          const state = states.get(entry.assetId ?? "");
          if (entry.phase !== "indexing" || !state) return entry;
          if (state.intake_status === "ready") return { ...entry, phase: "ready", progress: 100, error: undefined };
          if (state.intake_status === "failed") return { ...entry, phase: "error", error: `Original saved; analysis needs attention: ${state.error || "check server status"}` };
          return entry;
        }));
        if (statuses.some((item) => item.intake_status === "ready")) void readyCallback.current().catch(() => undefined);
      } catch (error) {
        if (!cancelled) setError(`Originals uploaded. Status is temporarily unavailable: ${message(error)}. You can also reopen the Inbox.`);
      }
      if (!cancelled) timer = setTimeout(() => void poll(), 10_000);
    }
    timer = setTimeout(() => void poll(), 0);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [indexingIds]);

  function pumpTransfers() {
    while (mounted.current && activeTransfers.current.size < 2 && waitingTransfers.current.size) {
      const next = waitingTransfers.current.entries().next().value;
      if (!next) return;
      const [id, task] = next;
      waitingTransfers.current.delete(id);
      activeTransfers.current.add(id);
      const existing = handles.current.get(id);
      if (existing) {
        update(id, { phase: "uploading", error: undefined });
        existing.start();
      } else void transfer(task.entry, task.projectId);
    }
  }
  function releaseTransfer(id: string) {
    activeTransfers.current.delete(id);
    pumpTransfers();
  }
  function enqueue(entry: Entry, activeProjectId: string) {
    if (activeTransfers.current.has(entry.id) || waitingTransfers.current.has(entry.id)) return;
    update(entry.id, { phase: "waiting", error: undefined });
    waitingTransfers.current.set(entry.id, { entry, projectId: activeProjectId });
    pumpTransfers();
  }

  async function transfer(entry: Entry, activeProjectId: string) {
    update(entry.id, { phase: "preparing", error: undefined });
    try {
      // A project groups this upload batch; job_id=null creates no editing job.
      const asset = await registerAsset(activeProjectId, null, entry.file, entry.id, preferences.current.get(entry.id));
      if (!mounted.current) { releaseTransfer(entry.id); return; }
      update(entry.id, { assetId: asset.id });
      const upload = await startResumableUpload(entry.file, asset, {
        onProgress(bytes, total) {
          update(entry.id, { progress: total ? Math.min(100, Math.round(bytes * 100 / total)) : 0 });
        },
        onRetry() { update(entry.id, { error: "Connection interrupted; retrying upload…" }); },
        onError(uploadError) { update(entry.id, { phase: "error", error: uploadError.message }); releaseTransfer(entry.id); },
        onSuccess() {
          update(entry.id, { uploaded: true, progress: 100, phase: "indexing", error: undefined });
          releaseTransfer(entry.id);
        },
      });
      handles.current.set(entry.id, upload);
      if (mounted.current) setEntries((current) => current.map((item) => item.id === entry.id && item.phase === "preparing"
        ? { ...item, phase: "uploading" } : item));
      if (!mounted.current) await upload.abort();
    } catch (uploadError) {
      update(entry.id, { phase: "error", error: message(uploadError) });
      releaseTransfer(entry.id);
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
        if (entries.length + added.length >= 200) throw new Error("Choose up to 200 files per intake batch.");
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
          display_name: namePrefix.trim() ? `${namePrefix.trim()} ${String(entries.indexOf(entry) + 1).padStart(3, "0")}` : undefined,
          media_role: mediaTypeForFile(entry.file).startsWith("video/") ? mediaRole : "auto",
          collection_id: folderId || undefined,
        });
      }
      for (const entry of queued) enqueue(entry, activeProjectId);
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
      releaseTransfer(entry.id);
    } catch (uploadError) { update(entry.id, { error: message(uploadError) }); }
  }

  function retry(entry: Entry) {
    if (entry.uploaded && entry.assetId) { update(entry.id, { phase: "indexing", error: undefined }); return; }
    if (projectId.current) enqueue(entry, projectId.current);
  }

  const queuedCount = entries.filter((entry) => entry.phase === "queued").length;
  const busyCount = entries.filter((entry) => ["waiting", "preparing", "uploading", "paused"].includes(entry.phase)).length;
  const actionClass = "inline-flex min-h-11 items-center justify-center gap-2 rounded-md border border-[#D7D9D3] bg-white px-3 text-xs font-bold text-[#173F5F] disabled:opacity-60";
  return (
    <section aria-labelledby="library-upload-heading" className="mt-6 space-y-4 rounded-md border border-[#BFD2DE] bg-[#EFF6FA] p-4 sm:p-5">
      <div>
        <h2 className="flex items-center gap-2 text-lg font-bold text-[#173F5F]" id="library-upload-heading"><UploadCloudIcon aria-hidden="true" className="size-5" />Add media to your library</h2>
        <p className="mt-1 text-sm leading-6 text-[#4E5960]">Choose files from this device or let the server fetch selected recordings directly from Google Drive.</p>
      </div>
      <div aria-label="Media source" className="inline-flex w-full rounded-lg border border-[#BFD2DE] bg-white p-1 sm:w-auto" role="tablist">
        <button aria-selected={source === "device"} className={`min-h-11 flex-1 rounded-md px-4 text-sm font-bold sm:flex-none ${source === "device" ? "bg-[#173F5F] text-white" : "text-[#4E5960]"}`} onClick={() => setSource("device")} role="tab" type="button">From this device</button>
        <button aria-selected={source === "drive"} className={`min-h-11 flex-1 rounded-md px-4 text-sm font-bold sm:flex-none ${source === "drive" ? "bg-[#173F5F] text-white" : "text-[#4E5960]"}`} onClick={() => setSource("drive")} role="tab" type="button">Google Drive</button>
      </div>
      <label className="block text-xs font-bold text-[#173F5F]">Import group name
        <input className="mt-2 h-11 w-full rounded-md border border-[#D7D9D3] bg-white px-3 text-sm text-[#20211F] disabled:opacity-60" disabled={starting || hasProject} maxLength={160} onChange={(event) => setBatchName(event.currentTarget.value)} value={batchName} />
      </label>
      <div className="grid gap-3 sm:grid-cols-3">
        <label className="text-xs font-bold text-[#666862]">Destination folder<select aria-label="Upload destination folder" className="mt-1 min-h-11 w-full rounded-md border border-[#D7D9D3] bg-white px-3 text-sm text-[#20211F]" disabled={starting} onChange={(event) => setFolderId(event.currentTarget.value)} value={folderId}><option value="">Not in folders</option>{folders.map((folder) => <option key={folder.id} value={folder.id}>{folderLabel(folders, folder.id)}</option>)}</select></label>
        <label className="text-xs font-bold text-[#666862]">Name these files <span className="font-normal">(optional)</span><input aria-label="Upload file name prefix" className="mt-1 min-h-11 w-full rounded-md border border-[#D7D9D3] px-3 text-sm text-[#20211F]" disabled={starting || hasProject} maxLength={230} onChange={(event) => setNamePrefix(event.currentTarget.value)} placeholder="e.g. Cream close-up → Cream close-up 001" value={namePrefix} /></label>
        <label className="text-xs font-bold text-[#666862]">Footage role<select aria-label="Upload footage role" className="mt-1 min-h-11 w-full rounded-md border border-[#D7D9D3] bg-white px-3 text-sm text-[#20211F]" disabled={starting || hasProject} onChange={(event) => setMediaRole(event.currentTarget.value as MediaRole)} value={mediaRole}><option value="auto">Unsorted video</option><option value="talking">Talking footage</option><option value="broll">B-roll</option></select></label>
      </div>
      {source === "device" ? <>
        <div className="flex flex-wrap gap-3">
          <label className={`${actionClass} cursor-pointer focus-within:ring-2 focus-within:ring-[#173F5F]`}>
            <UploadCloudIcon aria-hidden="true" className="size-4" />Choose files
            <input accept="video/*,image/*,audio/*,.heic,.heif" aria-label="Choose files for the media library" className="sr-only" disabled={starting} multiple onChange={(event) => { choose(Array.from(event.currentTarget.files ?? [])); event.currentTarget.value = ""; }} type="file" />
          </label>
          <button className="inline-flex min-h-11 items-center justify-center gap-2 rounded-md bg-[#173F5F] px-4 text-sm font-bold text-white disabled:opacity-60" disabled={starting || !queuedCount || !batchName.trim()} onClick={() => void uploadSelected()} type="button">
            {starting ? <LoaderCircleIcon aria-hidden="true" className="size-4 animate-spin motion-reduce:animate-none" /> : <UploadCloudIcon aria-hidden="true" className="size-4" />}
            {starting ? "Starting uploads…" : queuedCount ? `Upload ${queuedCount} ${queuedCount === 1 ? "file" : "files"} to library` : "Upload to library"}
          </button>
        </div>
        <p className="text-xs leading-5 text-[#666862]">Two uploads run at a time. Keep this page open until device transfers finish. New imports appear in the Inbox for review.</p>
        {error ? <p className="text-sm text-[#A23B2A]" role="alert">{error}</p> : null}
        {entries.length ? <ul aria-label="Library uploads" className="space-y-2">{entries.map((entry) => (
        <li className="rounded-md border border-[#D7D9D3] bg-white p-3" key={entry.id}>
          <div className="flex items-center justify-between gap-3">
            <div className="min-w-0"><p className="truncate text-sm font-bold text-[#173F5F]">{entry.file.name}</p><p aria-live="polite" className="mt-1 text-xs text-[#666862]">{entry.phase === "queued" ? "Selected · ready to upload" : entry.phase === "waiting" ? "Waiting for an upload slot…" : entry.phase === "preparing" ? "Preparing upload…" : entry.phase === "ready" ? "Ready in your library" : entry.phase === "indexing" ? "Uploaded · analysing on the server" : entry.phase === "paused" ? "Paused" : entry.phase === "error" ? "Needs attention" : `Uploading ${entry.progress}%`}</p></div>
            {entry.phase === "queued" ? <button aria-label={`Remove ${entry.file.name}`} className={actionClass} onClick={() => setEntries((current) => current.filter((item) => item.id !== entry.id))} type="button"><XIcon aria-hidden="true" className="size-4" /></button>
              : entry.phase === "uploading" ? <button aria-label={`Pause ${entry.file.name}`} className={actionClass} onClick={() => void pause(entry)} type="button"><PauseIcon aria-hidden="true" className="size-4" /></button>
                : entry.phase === "paused" || entry.phase === "error" ? <button aria-label={`${entry.uploaded ? "Check status of" : "Resume"} ${entry.file.name}`} className={actionClass} onClick={() => retry(entry)} type="button"><PlayIcon aria-hidden="true" className="size-4" />{entry.uploaded ? "Check status" : "Resume"}</button>
                  : entry.phase === "ready" ? <CheckIcon aria-label={`${entry.file.name} is ready`} className="size-5 shrink-0 text-[#307455]" /> : <LoaderCircleIcon aria-label={entry.phase === "preparing" ? "Preparing upload" : "Analysing"} className="size-5 shrink-0 animate-spin text-[#173F5F] motion-reduce:animate-none" />}
          </div>
          {entry.phase === "uploading" ? <progress aria-label={`${entry.file.name} upload progress`} className="mt-2 h-1.5 w-full accent-[#173F5F]" max={100} value={entry.progress} /> : null}
          {entry.error ? <p className="mt-2 text-xs text-[#A23B2A]" role="alert">{entry.error}</p> : null}
        </li>
        ))}</ul> : null}
        <p className="text-xs leading-5 text-[#4E5960]">{busyCount ? "Transfer in progress. " : ""}Once uploaded, analysis continues on the server even after you leave.</p>
      </> : <GoogleDriveImport batchName={batchName} collectionId={folderId} mediaRole={mediaRole} namePrefix={namePrefix} onReady={onReady} />}
    </section>
  );
}
