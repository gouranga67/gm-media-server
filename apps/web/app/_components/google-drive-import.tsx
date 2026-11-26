"use client";

import { useEffect, useRef, useState } from "react";
import { CheckIcon, CloudDownloadIcon, ExternalLinkIcon, LoaderCircleIcon, XIcon } from "lucide-react";

import {
  createGoogleDriveImports,
  getGoogleDriveImports,
  getGoogleDrivePickerToken,
  getGoogleDriveStatus,
  type GoogleDriveImportItem,
  type MediaRole,
} from "@/lib/media-api";

type SelectedFile = { readonly id: string; readonly name: string };
type PickerView = { setMimeTypes(value: string): PickerView };
type PickerBuilder = {
  addView(view: PickerView): PickerBuilder;
  enableFeature(feature: unknown): PickerBuilder;
  setOAuthToken(token: string): PickerBuilder;
  setDeveloperKey(key: string): PickerBuilder;
  setAppId(id: string): PickerBuilder;
  setCallback(callback: (data: unknown) => void): PickerBuilder;
  build(): { setVisible(value: boolean): void };
};
type PickerApi = {
  DocsView: new () => PickerView;
  PickerBuilder: new () => PickerBuilder;
  Feature: { MULTISELECT_ENABLED: unknown };
};
type GoogleWindow = Window & {
  gapi?: { load(name: string, options: { callback(): void; onerror(): void }): void };
  google?: { picker?: PickerApi };
};

let pickerLoader: Promise<PickerApi> | undefined;

function loadPicker(): Promise<PickerApi> {
  const current = window as GoogleWindow;
  if (current.google?.picker) return Promise.resolve(current.google.picker);
  if (pickerLoader) return pickerLoader;
  pickerLoader = new Promise((resolve, reject) => {
    function loadApi() {
      const gapi = (window as GoogleWindow).gapi;
      if (!gapi) { reject(new Error("Google Drive picker did not load.")); return; }
      gapi.load("picker", {
        callback() {
          const picker = (window as GoogleWindow).google?.picker;
          if (picker) resolve(picker); else reject(new Error("Google Drive picker is unavailable."));
        },
        onerror() { reject(new Error("Google Drive picker could not be opened.")); },
      });
    }
    const existing = document.querySelector<HTMLScriptElement>('script[data-google-picker="true"]');
    if (existing) { existing.addEventListener("load", loadApi, { once: true }); return; }
    const script = document.createElement("script");
    script.src = "https://apis.google.com/js/api.js";
    script.async = true;
    script.dataset.googlePicker = "true";
    script.addEventListener("load", loadApi, { once: true });
    script.addEventListener("error", () => reject(new Error("Google Drive picker could not be loaded.")), { once: true });
    document.head.appendChild(script);
  });
  return pickerLoader;
}

function readableError(error: unknown): string {
  return error instanceof Error ? error.message : "Google Drive import is unavailable. Try again.";
}

function pickedFiles(value: unknown): SelectedFile[] {
  if (!value || typeof value !== "object") return [];
  const response = value as { action?: unknown; docs?: unknown };
  if (response.action !== "picked" || !Array.isArray(response.docs)) return [];
  return response.docs.flatMap((item) => {
    if (!item || typeof item !== "object") return [];
    const doc = item as { id?: unknown; name?: unknown };
    return typeof doc.id === "string" ? [{ id: doc.id, name: typeof doc.name === "string" ? doc.name : "Drive file" }] : [];
  });
}

function statusLabel(item: GoogleDriveImportItem): string {
  if (item.status === "downloading" && item.byte_size) {
    return `Downloading ${Math.min(100, Math.round(100 * (item.downloaded_bytes ?? 0) / item.byte_size))}%`;
  }
  return item.status === "ready" ? "Ready in your library"
    : item.status === "processing" ? "Downloaded · analysing on the server"
      : item.status === "failed" ? "Needs attention" : "Queued for server download";
}

export function GoogleDriveImport({ batchName, collectionId, namePrefix, mediaRole, onReady }: {
  readonly batchName: string;
  readonly collectionId: string;
  readonly namePrefix: string;
  readonly mediaRole: MediaRole;
  readonly onReady: () => Promise<void>;
}) {
  const [connection, setConnection] = useState<{ enabled: boolean; connected: boolean }>();
  const [selected, setSelected] = useState<readonly SelectedFile[]>([]);
  const [imports, setImports] = useState<readonly GoogleDriveImportItem[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const readySent = useRef(new Set<string>());

  useEffect(() => {
    let cancelled = false;
    void getGoogleDriveStatus().then((status) => { if (!cancelled) setConnection(status); })
      .catch((failure) => { if (!cancelled) setError(readableError(failure)); });
    return () => { cancelled = true; };
  }, []);

  const activeIds = imports.filter((item) => item.status !== "ready" && item.status !== "failed").map((item) => item.id).join(",");
  useEffect(() => {
    if (!activeIds) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const states = await getGoogleDriveImports(activeIds.split(","));
        if (cancelled) return;
        const byId = new Map(states.map((item) => [item.id, item]));
        setImports((current) => current.map((item) => byId.get(item.id) ?? item));
        const newlyReady = states.filter((item) => item.status === "ready" && !readySent.current.has(item.id));
        if (newlyReady.length) {
          for (const item of newlyReady) readySent.current.add(item.id);
          await onReady();
        }
      } catch (failure) {
        if (!cancelled) setError(`Import status is temporarily unavailable: ${readableError(failure)}`);
      }
      if (!cancelled) timer = setTimeout(() => void poll(), 5_000);
    }
    timer = setTimeout(() => void poll(), 0);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [activeIds, onReady]);

  async function chooseFromDrive() {
    setBusy(true); setError(undefined);
    try {
      const [picker, config] = await Promise.all([loadPicker(), getGoogleDrivePickerToken()]);
      const view = new picker.DocsView().setMimeTypes("video/mp4,video/quicktime,video/webm,image/jpeg,image/png,image/heic,image/heif,audio/mpeg,audio/mp4,audio/wav,audio/aac");
      new picker.PickerBuilder().addView(view).enableFeature(picker.Feature.MULTISELECT_ENABLED)
        .setOAuthToken(config.access_token).setDeveloperKey(config.developer_key).setAppId(config.app_id)
        .setCallback((data) => {
          const files = pickedFiles(data);
          if (files.length) setSelected(files.slice(0, 200));
        }).build().setVisible(true);
    } catch (failure) { setError(readableError(failure)); }
    finally { setBusy(false); }
  }

  async function startImport() {
    if (!selected.length || !batchName.trim()) return;
    setBusy(true); setError(undefined);
    try {
      const result = await createGoogleDriveImports({ fileIds: selected.map((item) => item.id), batchName: batchName.trim(),
        collectionId: collectionId || undefined, namePrefix: namePrefix.trim() || undefined, mediaRole });
      setImports(result.items.map((item) => ({ ...item, status: item.status ?? "queued" })));
      setSelected([]);
      if (result.already_imported) setError(`${result.already_imported} selected ${result.already_imported === 1 ? "file was" : "files were"} already in your library; no duplicate download was started.`);
    } catch (failure) { setError(readableError(failure)); }
    finally { setBusy(false); }
  }

  if (!connection) return <p className="flex items-center gap-2 text-sm text-[#4E5960]" role="status"><LoaderCircleIcon className="size-4 animate-spin" />Checking Google Drive…</p>;
  if (!connection.enabled) return <div className="rounded-lg border border-[#D7D9D3] bg-white p-4"><p className="font-bold text-[#173F5F]">Google Drive needs one-time server setup</p><p className="mt-1 text-sm leading-6 text-[#666862]">Run the provided Google Drive configuration helper, redeploy, then return here.</p></div>;
  if (!connection.connected) return <div className="rounded-lg border border-[#D7D9D3] bg-white p-4"><p className="font-bold text-[#173F5F]">Connect your Google Drive</p><p className="mt-1 text-sm leading-6 text-[#666862]">GM Studio will only receive files that you explicitly select.</p><a className="mt-3 inline-flex min-h-11 items-center gap-2 rounded-md bg-[#173F5F] px-4 text-sm font-bold text-white" href="/api/media/google-drive/connect">Connect Google Drive <ExternalLinkIcon className="size-4" /></a></div>;

  return <div className="space-y-4">
    <div className="flex flex-wrap items-center gap-3">
      <button className="inline-flex min-h-11 items-center gap-2 rounded-md border border-[#173F5F] bg-white px-4 text-sm font-bold text-[#173F5F] disabled:opacity-60" disabled={busy} onClick={() => void chooseFromDrive()} type="button"><CloudDownloadIcon className="size-4" />Choose from Google Drive</button>
      {selected.length ? <button className="inline-flex min-h-11 items-center gap-2 rounded-md bg-[#173F5F] px-4 text-sm font-bold text-white disabled:opacity-60" disabled={busy || !batchName.trim()} onClick={() => void startImport()} type="button">{busy ? <LoaderCircleIcon className="size-4 animate-spin" /> : <CloudDownloadIcon className="size-4" />}Import {selected.length} {selected.length === 1 ? "file" : "files"}</button> : null}
      <span className="text-xs text-[#666862]">Connected · selected files download directly to this server</span>
    </div>
    {selected.length ? <div className="rounded-lg border border-[#C8D7DF] bg-white p-3"><div className="flex items-center justify-between gap-3"><p className="text-sm font-bold text-[#173F5F]">{selected.length} selected from Drive</p><button aria-label="Clear Drive selection" className="flex size-11 items-center justify-center text-[#666862]" onClick={() => setSelected([])} type="button"><XIcon className="size-4" /></button></div><p className="mt-1 line-clamp-2 text-xs text-[#666862]">{selected.map((item) => item.name).join(" · ")}</p></div> : null}
    {error ? <p className="rounded-md border border-[#D8B4AA] bg-[#FFF7F4] p-3 text-sm text-[#8A3528]" role="status">{error}</p> : null}
    {imports.length ? <ul aria-label="Google Drive imports" className="space-y-2">{imports.map((item) => <li className="rounded-md border border-[#D7D9D3] bg-white p-3" key={item.id}><div className="flex items-center justify-between gap-3"><div className="min-w-0"><p className="truncate text-sm font-bold text-[#173F5F]">{item.remote_name}</p><p className="mt-1 text-xs text-[#666862]" aria-live="polite">{statusLabel(item)}</p></div>{item.status === "ready" ? <CheckIcon className="size-5 shrink-0 text-[#307455]" /> : item.status === "failed" ? <XIcon className="size-5 shrink-0 text-[#A23B2A]" /> : <LoaderCircleIcon className="size-5 shrink-0 animate-spin text-[#173F5F]" />}</div>{item.status === "downloading" && item.byte_size ? <progress className="mt-2 h-1.5 w-full accent-[#173F5F]" max={item.byte_size} value={item.downloaded_bytes ?? 0} /> : null}{item.error ? <p className="mt-2 text-xs text-[#A23B2A]">{item.error}</p> : null}</li>)}</ul> : null}
    <p className="text-xs leading-5 text-[#4E5960]">You may close this page after starting the import. Downloading and analysis continue on the server, and the files appear in the Library Inbox.</p>
  </div>;
}
