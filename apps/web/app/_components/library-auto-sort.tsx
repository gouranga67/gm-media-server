"use client";

import { useEffect, useRef, useState } from "react";
import { LoaderCircleIcon, SparklesIcon, XIcon } from "lucide-react";
import { applyLibraryOrganization, getOrganizationSession, getOrganizationSessions, libraryAssetThumbnailUrl,
  suggestLibraryOrganization, type MediaCategory, type MediaRole, type OrganizationSession, type OrganizationSuggestion } from "@/lib/media-api";
import { mediaCategories } from "@/lib/library-organization";

const control = "min-h-11 rounded-md border border-[#D7D9D3] bg-white px-3 text-sm text-[#173F5F] disabled:opacity-50";
const errorText = (error: unknown) => error instanceof Error ? error.message : "Auto-sort could not complete.";

export function LibraryAutoSort({ assetIds, onClose, onApplied }: {
  readonly assetIds: readonly string[]; readonly onClose: () => void; readonly onApplied: () => Promise<void>;
}) {
  const [history, setHistory] = useState<readonly OrganizationSession[]>([]);
  const [session, setSession] = useState<OrganizationSession>();
  const [activeId, setActiveId] = useState<string>();
  const [suggestions, setSuggestions] = useState<readonly OrganizationSuggestion[]>([]);
  const [chosen, setChosen] = useState<ReadonlySet<string>>(new Set());
  const [renameExisting, setRenameExisting] = useState(false);
  const [privacy, setPrivacy] = useState<"hybrid" | "text_only">("hybrid");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const [notice, setNotice] = useState<string>();
  const nonce = useRef<{ key: string; id: string } | undefined>(undefined);
  const waiting = session?.status === "pending" || session?.status === "generating" || Boolean(activeId && !session);
  useEffect(() => {
    let cancelled = false;
    void getOrganizationSessions().then((items) => { if (!cancelled) setHistory(items); }).catch((error: unknown) => { if (!cancelled) setError(errorText(error)); });
    return () => { cancelled = true; };
  }, []);
  useEffect(() => {
    if (!activeId) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    setSession(undefined); setChosen(new Set()); setSuggestions([]);
    async function poll() {
      try {
        const result = await getOrganizationSession(activeId!);
        if (cancelled) return;
        setSession(result); setError(undefined);
        setHistory((items) => [result, ...items.filter((item) => item.id !== result.id)]);
        if (result.status === "ready") {
          setSuggestions(result.suggestions);
          setChosen(new Set(result.suggestions.filter((item) => item.confidence === "supported" && !result.applied_asset_ids.includes(item.asset_id)).map((item) => item.asset_id)));
        }
        if (result.status === "pending" || result.status === "generating") timer = setTimeout(() => void poll(), 2000);
      } catch (error) { if (!cancelled) { setError(errorText(error)); timer = setTimeout(() => void poll(), 5000); } }
    }
    void poll();
    return () => { cancelled = true; clearTimeout(timer); };
  }, [activeId]);
  async function suggest() {
    if (busy || waiting || !assetIds.length || assetIds.length > 24) return;
    setBusy(true); setError(undefined); setNotice(undefined);
    const input = { asset_ids: assetIds, rename_existing: renameExisting, privacy_mode: privacy };
    const key = JSON.stringify(input);
    if (nonce.current?.key !== key) nonce.current = { key, id: crypto.randomUUID() };
    try {
      const result = await suggestLibraryOrganization({ ...input, id: nonce.current.id });
      nonce.current = undefined; setSession(result); setActiveId(result.id);
    } catch (error) { setError(errorText(error)); }
    finally { setBusy(false); }
  }
  async function apply() {
    if (!session || busy || !chosen.size) return;
    setBusy(true); setError(undefined); setNotice(undefined);
    try {
      const result = await applyLibraryOrganization(session.id, suggestions.filter((item) => chosen.has(item.asset_id)));
      setSession((current) => current ? { ...current, applied_asset_ids: result.applied_asset_ids } : current);
      setChosen(new Set());
      await onApplied();
      setNotice(`${result.updated} files organized. Original files and existing edits are preserved.`);
    } catch (error) { setError(errorText(error)); }
    finally { setBusy(false); }
  }
  function edit(id: string, changes: Partial<OrganizationSuggestion>) {
    setSuggestions((items) => items.map((item) => item.asset_id === id ? { ...item, ...changes } : item));
  }
  return <section aria-label="Auto-sort library" className="my-4 space-y-4 rounded-md border border-[#AFC7D5] bg-[#EFF6FA] p-4">
    <div className="flex items-start justify-between gap-3"><div><h2 className="font-bold text-[#173F5F]">Auto-sort names &amp; categories</h2><p className="mt-1 max-w-3xl text-xs leading-5 text-[#666862]">Uses stored transcripts and small preview images to suggest what each file is about. One AI request for up to 24 files. Review and edit suggestions before applying; originals stay unchanged.</p></div><button aria-label="Close auto-sort" className={control} disabled={busy} onClick={onClose} type="button"><XIcon aria-hidden="true" className="size-4" /></button></div>
    <div className="flex flex-wrap items-end gap-3"><p className="text-sm font-bold text-[#173F5F]">{assetIds.length} files in this batch</p><label className="flex min-h-11 items-center gap-2 text-xs text-[#173F5F]"><input checked={renameExisting} disabled={busy || waiting} onChange={(event) => setRenameExisting(event.currentTarget.checked)} type="checkbox" />Also suggest replacing existing custom names</label><label className="text-xs text-[#173F5F]">Analysis shared<select aria-label="Auto-sort privacy" className={`${control} ml-2`} disabled={busy || waiting} onChange={(event) => setPrivacy(event.currentTarget.value as typeof privacy)} value={privacy}><option value="hybrid">Transcript + small previews</option><option value="text_only">Transcript and metadata only</option></select></label><button className={`${control} inline-flex items-center gap-2 font-bold`} disabled={busy || waiting || !assetIds.length || assetIds.length > 24} onClick={() => void suggest()} type="button">{busy || waiting ? <LoaderCircleIcon aria-hidden="true" className="size-4 animate-spin" /> : <SparklesIcon aria-hidden="true" className="size-4" />}Suggest names &amp; categories</button></div>
    {assetIds.length > 24 ? <p className="text-sm text-[#A23B2A]">Select up to 24 files for one batch.</p> : null}
    {history.length ? <label className="block text-xs text-[#173F5F]">Saved auto-sort sessions<select aria-label="Saved auto-sort session" className={`${control} ml-2 max-w-full`} disabled={busy || waiting} onChange={(event) => { setActiveId(event.currentTarget.value || undefined); setNotice(undefined); setSession(undefined); setSuggestions([]); setChosen(new Set()); }} value={activeId ?? ""}><option value="">Choose saved suggestions</option>{history.map((item) => <option key={item.id} value={item.id}>{new Date(item.created_at).toLocaleString()} · {item.asset_ids.length} files · {item.status}</option>)}</select></label> : null}
    {error ? <p className="text-sm text-[#A23B2A]" role="alert">{error}</p> : null}
    {notice ? <p className="text-sm text-[#215B43]" role="status">{notice}</p> : null}
    {waiting ? <p className="text-sm text-[#173F5F]" role="status">{session?.status === "pending" ? "Queued behind current studio work." : "Reading analysis and preparing suggestions…"} You can close this panel and reopen the saved session later.</p> : null}
    {session?.status === "failed" ? <p className="text-sm text-[#A23B2A]" role="alert">{session.error} No files were renamed.</p> : null}
    {session?.status === "ready" ? <>
      <p className="text-xs leading-5 text-[#666862]">{session.total_tokens.toLocaleString()} measured tokens. Uncertain suggestions are unchecked. Existing names and manual labels are kept by default.</p>
      <div className="max-h-[36rem] space-y-3 overflow-y-auto pr-1">{suggestions.map((item) => {
        const applied = session.applied_asset_ids.includes(item.asset_id);
        return <article className="rounded-md border border-[#D7D9D3] bg-white p-3" key={item.asset_id}><div className="flex items-start gap-3"><input aria-label={`Apply suggestion for ${item.previous_name ?? item.asset_id}`} checked={chosen.has(item.asset_id)} className="mt-3 size-4 accent-[#173F5F]" disabled={busy || applied} onChange={(event) => { const checked = event.currentTarget.checked; setChosen((current) => { const next = new Set(current); if (checked) next.add(item.asset_id); else next.delete(item.asset_id); return next; }); }} type="checkbox" /><img alt="" className="size-14 shrink-0 rounded object-contain" loading="lazy" src={libraryAssetThumbnailUrl(item.asset_id)} /><div className="min-w-0 flex-1"><p className="truncate text-xs text-[#666862]">{item.previous_name} {applied ? "· Applied" : item.confidence === "uncertain" ? "· Needs review" : ""}</p><div className="mt-2 flex flex-wrap gap-2"><input aria-label={`Suggested name for ${item.previous_name ?? item.asset_id}`} className={`${control} min-w-40 flex-1`} disabled={busy || applied} maxLength={255} onChange={(event) => edit(item.asset_id, { display_name: event.currentTarget.value })} value={item.display_name} /><select aria-label={`Category for ${item.previous_name ?? item.asset_id}`} className={control} disabled={busy || applied} onChange={(event) => edit(item.asset_id, { media_category: event.currentTarget.value as MediaCategory })} value={item.media_category}>{mediaCategories.map((category) => <option key={category.id} value={category.id}>{category.label}</option>)}</select>{item.mime_type?.startsWith("video/") ? <select aria-label={`Footage label for ${item.previous_name ?? item.asset_id}`} className={control} disabled={busy || applied} onChange={(event) => edit(item.asset_id, { media_role: event.currentTarget.value as MediaRole })} value={item.media_role}><option value="auto">Unsorted video</option><option value="talking">Talking footage</option><option value="broll">B-roll</option></select> : null}</div><p className="mt-2 text-xs leading-5 text-[#666862]">{item.reason}</p></div></div></article>;
      })}</div><button className="min-h-11 rounded-md bg-[#173F5F] px-4 text-sm font-bold text-white disabled:opacity-50" disabled={busy || !chosen.size || suggestions.some((item) => chosen.has(item.asset_id) && !item.display_name.trim())} onClick={() => void apply()} type="button">Apply {chosen.size} selected suggestions</button>
    </> : null}
  </section>;
}
