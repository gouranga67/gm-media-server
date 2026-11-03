"use client";

import { useEffect, useState } from "react";
import { InboxIcon, RotateCwIcon } from "lucide-react";
import { getLibraryIntake, reviewLibraryIntake, updateLibraryFolderMembers, libraryAssetThumbnailUrl,
  type LibraryCollection, type LibraryIntakeItem } from "@/lib/media-api";

const control = "min-h-11 rounded-md border border-[#D7D9D3] bg-white px-3 text-sm text-[#173F5F] disabled:opacity-50";

export function LibraryInbox({ folders, revision, onOpenAsset, onAutoSort, onChanged }: {
  readonly folders: readonly LibraryCollection[]; readonly revision: number;
  readonly onOpenAsset: (id: string) => void; readonly onAutoSort: (ids: readonly string[]) => void;
  readonly onChanged: () => Promise<void>;
}) {
  const [items, setItems] = useState<readonly LibraryIntakeItem[]>([]);
  const [total, setTotal] = useState(0);
  const [query, setQuery] = useState("");
  const [offset, setOffset] = useState(0);
  const [checked, setChecked] = useState<ReadonlySet<string>>(new Set());
  const [folder, setFolder] = useState("");
  const [refresh, setRefresh] = useState(0);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const [notice, setNotice] = useState<string>();
  const [dismiss, setDismiss] = useState<string>();

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    setLoading(true); setChecked(new Set());
    async function load() {
      try {
        const result = await getLibraryIntake(query.trim(), offset);
        if (cancelled) return;
        if (offset && !result.items.length) { setOffset(0); return; }
        setItems(result.items); setTotal(result.total); setLoading(false); setError(undefined);
        // One bounded request while this view is open. No per-file polling.
        if (result.items.some((item) => ["uploading", "processing"].includes(item.intake_status))) timer = setTimeout(() => void load(), 10_000);
      } catch (error) { if (!cancelled) { setLoading(false); setError(error instanceof Error ? error.message : "Inbox unavailable"); } }
    }
    timer = setTimeout(() => void load(), query ? 220 : 0);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [query, offset, refresh, revision]);

  const ready = items.filter((item) => item.intake_status === "ready");
  const selected = ready.filter((item) => checked.has(item.id)).map((item) => item.id);
  async function action(kind: "review" | "folder" | "dismiss", ids = selected) {
    if (busy || !ids.length) return;
    setBusy(true); setError(undefined); setNotice(undefined);
    try {
      if (kind === "folder") await updateLibraryFolderMembers(folder, ids, "add");
      else await reviewLibraryIntake(ids, kind);
      setChecked(new Set()); setDismiss(undefined);
      setNotice(kind === "folder" ? "Added to folder. Review the names and labels, then mark reviewed." : kind === "dismiss" ? "Removed from the Inbox. Any uploaded original remains in the library." : "Reviewed. These files are still available in All media and their folders.");
      setRefresh((value) => value + 1); await onChanged();
    } catch (error) { setError(error instanceof Error ? error.message : "The change could not be saved"); }
    finally { setBusy(false); }
  }
  return <section aria-label="Import Inbox" className="space-y-4">
    <div className="rounded-md border border-[#BFD2DE] bg-[#EFF6FA] p-4 text-sm leading-6 text-[#173F5F]">
      <p className="font-bold">Review new imports, then mark them reviewed</p>
      <p>Check names, footage roles and folders. Auto-sort can suggest names and labels from stored analysis; you choose what to apply. This does not start an edit.</p>
    </div>
    <div className="flex flex-wrap gap-2"><input aria-label="Search imports" className={`${control} min-w-0 flex-1`} maxLength={160} placeholder="Search import names or upload groups" value={query} disabled={busy} onChange={(event) => { setQuery(event.currentTarget.value); setOffset(0); setDismiss(undefined); }} /><button aria-label="Refresh Inbox" className={`${control} min-w-11`} disabled={busy} onClick={() => setRefresh((value) => value + 1)} type="button"><RotateCwIcon aria-hidden="true" className="size-4" /></button></div>
    {error ? <p role="alert" className="text-sm text-[#A23B2A]">{error}</p> : null}
    {notice ? <p role="status" className="text-sm text-[#215B43]">{notice}</p> : null}
    {selected.length ? <div aria-label="Selected imports" className="flex flex-wrap items-center gap-2 rounded-md border border-[#BFD2DE] bg-[#EFF6FA] p-3"><strong className="text-sm">{selected.length} selected</strong><select aria-label="File imports in folder" className={`${control} max-w-full`} value={folder} disabled={busy} onChange={(event) => setFolder(event.currentTarget.value)}><option value="">Choose folder…</option>{folders.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select><button className={control} disabled={busy || !folder} onClick={() => void action("folder")} type="button">Add imports to folder</button><button className={control} disabled={busy || selected.length > 24} onClick={() => onAutoSort(selected)} type="button">Suggest names & labels</button><button className={`${control} font-bold`} disabled={busy} onClick={() => void action("review")} type="button">Mark reviewed</button></div> : null}
    {loading ? <p role="status">Loading imports…</p> : <div className="divide-y divide-[#D7D9D3] rounded-md border border-[#D7D9D3] bg-white">
      <div className="flex min-h-14 items-center justify-between gap-2 px-3 text-xs text-[#666862]"><label className="flex min-h-11 items-center gap-2"><input aria-label="Select ready imports on this page" className="size-4 accent-[#173F5F]" type="checkbox" disabled={busy || !ready.length} checked={Boolean(ready.length) && ready.every((item) => checked.has(item.id))} onChange={() => setChecked(ready.every((item) => checked.has(item.id)) ? new Set() : new Set(ready.map((item) => item.id)))} />{total} new imports</label><span>60 per page</span></div>
      {items.map((item) => <article key={item.id} className="flex flex-wrap items-center gap-3 p-3 sm:flex-nowrap">
        <label className="flex size-11 shrink-0 items-center justify-center"><input aria-label={`Review ${item.display_name}`} type="checkbox" className="size-4 accent-[#173F5F]" disabled={busy || item.intake_status !== "ready"} checked={checked.has(item.id)} onChange={() => setChecked((current) => { const next = new Set(current); if (next.has(item.id)) next.delete(item.id); else next.add(item.id); return next; })} /></label>
        {item.thumbnail_available ? <img alt="" className="size-14 shrink-0 rounded object-cover" src={libraryAssetThumbnailUrl(item.id)} /> : <InboxIcon aria-hidden="true" className="size-10 shrink-0 text-[#666862]" />}
        <div className="min-w-0 flex-1"><p className="break-words font-bold text-[#173F5F]">{item.display_name}</p><p className="mt-1 break-words text-xs text-[#666862]">{item.source_name} · {item.project_name}</p><p className="mt-1 text-xs text-[#666862]">{item.folders.map((folder) => folder.name).join(" · ") || "Not in folders"} · {item.mime_type.startsWith("video/") ? item.media_role === "broll" ? "B-roll" : item.media_role === "talking" ? "Talking footage" : "Unsorted video" : item.mime_type.startsWith("image/") ? "Photo" : "Audio"}</p>
        <p className={`mt-2 text-xs ${item.intake_status === "failed" ? "text-[#A23B2A]" : "text-[#215B43]"}`}>{item.intake_status === "ready" ? "Ready to review" : item.intake_status === "uploading" ? "Waiting for upload to finish · keep the uploading tab open" : item.intake_status === "failed" ? `Needs attention: ${item.error || "Check the original and local analysis"}` : "Uploaded · analysing on the server"}</p></div>
        <div className="flex flex-wrap gap-2">{item.intake_status === "ready" ? <button className={control} disabled={busy} onClick={() => onOpenAsset(item.id)} type="button">Review details</button> : null}<button className={control} disabled={busy} onClick={() => setDismiss(item.id)} type="button">Dismiss from Inbox</button></div>
      </article>)}
      {!items.length ? <p className="p-8 text-sm text-[#666862]">{query ? "No imports match this search." : "Your Inbox is clear. Add media to import footage without creating a job."}</p> : null}
    </div>}
    {dismiss ? <div className="rounded-md border border-[#BFD2DE] bg-white p-4"><p className="text-sm leading-6">Remove this entry from the Inbox? This does not stop an upload or delete a file.</p><div className="mt-3 flex gap-2"><button className={control} disabled={busy} onClick={() => void action("dismiss", [dismiss])} type="button">Confirm dismiss</button><button className={control} disabled={busy} onClick={() => setDismiss(undefined)} type="button">Cancel</button></div></div> : null}
    {total > 60 ? <nav aria-label="Inbox pages" className="flex items-center gap-3"><button className={control} disabled={busy || !offset} onClick={() => { setOffset(Math.max(0, offset - 60)); setDismiss(undefined); }} type="button">Previous imports</button><span className="text-xs">{offset + 1}–{Math.min(total, offset + 60)} of {total}</span><button className={control} disabled={busy || offset + 60 >= total} onClick={() => { setOffset(offset + 60); setDismiss(undefined); }} type="button">Next imports</button></nav> : null}
  </section>;
}
