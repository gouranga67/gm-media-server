"use client";

import { useEffect, useRef, useState } from "react";
import { CaptionsIcon, LoaderCircleIcon, Undo2Icon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { applySubtitles, getSubtitles, saveSubtitles, type SubtitleCue, type SubtitleDraft } from "@/lib/media-api";
import { mergeSubtitles, replaceSubtitles, splitSubtitle } from "@/lib/subtitle-editing";

const stamp = (seconds: number) => `${Math.floor(seconds / 60).toString().padStart(2, "0")}:${(seconds % 60).toFixed(1).padStart(4, "0")}`;
const equal = (left: readonly SubtitleCue[], right: readonly SubtitleCue[]) => JSON.stringify(left) === JSON.stringify(right);
const message = (error: unknown) => error instanceof Error ? error.message : "The subtitle request failed.";

export function SubtitleEditor({ jobId, runId, version, videoUrl, onApplied, onOpen }: {
  readonly jobId: string; readonly runId: string; readonly version: number; readonly videoUrl: string;
  readonly onApplied: () => void; readonly onOpen?: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<SubtitleDraft>();
  const [cues, setCues] = useState<readonly SubtitleCue[]>([]);
  const [history, setHistory] = useState<readonly (readonly SubtitleCue[])[]>([]);
  const [busy, setBusy] = useState<"loading" | "saving" | "applying">();
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [search, setSearch] = useState("");
  const [replacement, setReplacement] = useState("");
  const [clock, setClock] = useState(-1);
  const video = useRef<HTMLVideoElement>(null);
  const fields = useRef(new Map<string, HTMLTextAreaElement>());
  const dirty = draft !== undefined && !equal(cues, draft.cues);
  const changed = draft !== undefined && !equal(cues, draft.baseline);
  const active = cues.findIndex((cue) => cue.start <= clock && cue.end > clock);

  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  async function load() {
    setBusy("loading"); setError("");
    try {
      const result = await getSubtitles(jobId, runId);
      setDraft(result); setCues(result.cues); setHistory([]);
      setNotice(result.saved ? "Your saved draft is ready to continue." : "");
    } catch (failure) { setError(message(failure)); }
    finally { setBusy(undefined); }
  }
  function change(next: readonly SubtitleCue[]) {
    if (equal(next, cues)) return;
    setHistory((previous) => [...previous.slice(-39), cues]); setCues(next); setError(""); setNotice("");
  }
  function edit(id: string, updates: Partial<SubtitleCue>) {
    change(cues.map((cue) => cue.id === id ? { ...cue, ...updates } : cue));
  }
  function safely(operation: () => void) {
    try { operation(); } catch (failure) { setError(message(failure)); }
  }
  async function save() {
    if (!draft) return undefined;
    const result = await saveSubtitles(jobId, runId, draft, cues);
    setDraft(result); setCues(result.cues); setNotice("Draft saved on the server. The video has not changed.");
    return result;
  }
  async function persist(apply: boolean) {
    setBusy(apply ? "applying" : "saving"); setError("");
    try {
      const current = dirty || !draft?.saved ? await save() : draft;
      if (apply && current) {
        await applySubtitles(jobId, runId, current);
        setOpen(false); onApplied();
      }
    } catch (failure) { setError(message(failure)); }
    finally { setBusy(undefined); }
  }
  function close(next: boolean) {
    if (busy || (!next && dirty && !window.confirm("Close without saving these subtitle changes?"))) return;
    if (!next) video.current?.pause();
    setOpen(next);
  }
  function listen(cue: SubtitleCue) {
    if (!video.current) return;
    video.current.currentTime = cue.start;
    setClock(cue.start);
    void video.current.play().catch(() => setNotice("Press Play in the video to listen."));
  }
  function replace(all: boolean) {
    safely(() => {
      const next = replaceSubtitles(cues, search, replacement, all, all ? 0 : Math.max(active, 0));
      if (equal(next, cues)) { setNotice("No matching text from this point. Try another phrase or Replace all."); return; }
      change(next); setNotice(all ? "Replaced matching text throughout the captions." : "Replaced the next matching phrase.");
    });
  }
  return <>
    <Button className="h-12 w-full" type="button" variant="outline" onClick={() => {
      onOpen?.(); setOpen(true); if (!draft) void load();
    }}><CaptionsIcon aria-hidden="true" />Edit subtitles</Button>
    <Dialog open={open} onOpenChange={close}>
      <DialogContent showCloseButton={false} className="flex max-h-[95dvh] w-[calc(100%-1rem)] max-w-5xl flex-col overflow-hidden bg-[#F7F7F5] p-4 text-[#20211F] [color-scheme:light] sm:max-w-5xl sm:p-6">
        <DialogHeader className="shrink-0 pr-20 text-left">
          <DialogTitle className="text-xl text-[#173F5F]">Edit subtitles</DialogTitle>
          <DialogDescription className="text-[#666862]">Version {version} · Correct the words, keep your cut.</DialogDescription>
        </DialogHeader>
        <Button className="absolute top-4 right-4" disabled={busy !== undefined} type="button" variant="outline" onClick={() => close(false)}>Close</Button>
        <div className="grid min-h-0 flex-1 gap-4 overflow-y-auto md:grid-cols-[minmax(200px,300px)_1fr] md:overflow-hidden">
          <aside className="min-w-0">
            <video ref={video} className="mx-auto max-h-[18dvh] w-full rounded-md bg-black object-contain md:max-h-[65dvh]" controls playsInline preload="metadata" src={videoUrl} onTimeUpdate={(event) => setClock(event.currentTarget.currentTime)}>
              Your browser cannot play this preview.
            </video>
            <p className="mt-2 text-xs leading-relaxed text-[#666862]">The video shows saved subtitles until you apply your draft.</p>
          </aside>
          <div className="flex min-h-0 min-w-0 flex-col rounded-md border border-[#D7D9D3] bg-white md:overflow-hidden">
            <div className="shrink-0 border-b border-[#D7D9D3] p-3">
              <p className="text-sm font-bold">Click a timestamp to listen. Edit any line below.</p>
              <details className="mt-2">
                <summary className="min-h-10 cursor-pointer content-center text-xs font-bold text-[#173F5F]">Find, replace &amp; move all</summary>
              <div className="mt-2 grid grid-cols-2 gap-2">
                <label className="text-xs">Find<Input aria-label="Find subtitle text" value={search} onChange={(e) => setSearch(e.target.value)} disabled={busy !== undefined} /></label>
                <label className="text-xs">Replace with<Input aria-label="Replacement subtitle text" value={replacement} onChange={(e) => setReplacement(e.target.value)} disabled={busy !== undefined} /></label>
              </div>
              <div className="mt-2 flex flex-wrap gap-2">
                <Button size="sm" type="button" variant="outline" disabled={busy !== undefined || !draft} onClick={() => replace(false)}>Replace next</Button>
                <Button size="sm" type="button" variant="outline" disabled={busy !== undefined || !draft} onClick={() => replace(true)}>Replace all</Button>
                <label className="ml-auto flex items-center gap-2 text-xs">Move all
                  <select aria-label="Position all subtitles" className="min-h-10 rounded border bg-white px-2" value="" disabled={busy !== undefined || !draft} onChange={(event) => change(cues.map((cue) => ({ ...cue, position: event.target.value as SubtitleCue["position"] })))}>
                    <option value="" disabled>Choose position</option><option value="lower_safe">Lower safe area</option><option value="middle">Middle</option><option value="upper">Upper</option>
                  </select>
                </label>
              </div>
              </details>
            </div>
            <div className="min-h-0 space-y-3 p-3 md:overflow-y-auto" aria-label="Timed subtitle transcript">
              {busy === "loading" ? <p role="status" className="p-4">Loading subtitles…</p> : null}
              {draft && !cues.length ? <p className="p-4 text-sm">This version has no spoken captions to edit.</p> : null}
              {cues.map((cue, index) => <div key={cue.id} className={`rounded-md border p-3 ${active === index ? "border-[#173F5F] bg-[#EFF6FA]" : "border-[#D7D9D3]"} ${cue.hidden ? "opacity-60" : ""}`} aria-current={active === index ? "true" : undefined}>
                <div className="flex items-center justify-between gap-2">
                  <button className="min-h-10 text-left font-mono text-xs text-[#173F5F] underline underline-offset-4" type="button" onClick={() => listen(cue)}>{stamp(cue.start)}–{stamp(cue.end)} · Listen</button>
                  <label className="flex min-h-10 items-center gap-2 text-xs"><input type="checkbox" checked={cue.hidden} disabled={busy !== undefined} onChange={(event) => edit(cue.id, { hidden: event.target.checked })} />Hide caption</label>
                </div>
                <Textarea aria-label={`Subtitle ${index + 1}`} ref={(element) => { if (element) fields.current.set(cue.id, element); else fields.current.delete(cue.id); }} className="mt-1 min-h-20 bg-white" value={cue.text} maxLength={600} disabled={busy !== undefined} onChange={(event) => edit(cue.id, { text: event.target.value })} />
                {cue.text.length > 90 && !cue.hidden ? <p className="mt-1 text-xs text-[#A23B2A]">This is a long caption. Split it to improve readability.</p> : null}
                <div className="mt-2 flex flex-wrap items-center gap-2">
                  <Button size="sm" type="button" variant="outline" disabled={busy !== undefined || cue.hidden} onClick={() => safely(() => {
                    const parts = splitSubtitle(cue, fields.current.get(cue.id)?.selectionStart ?? 0);
                    change([...cues.slice(0, index), ...parts, ...cues.slice(index + 1)]);
                    setNotice("Caption split. Its new timing is estimated within the original interval; listen to check it.");
                  })}>Split at cursor</Button>
                  <Button size="sm" type="button" variant="outline" disabled={busy !== undefined || index === cues.length - 1} onClick={() => safely(() => change([
                    ...cues.slice(0, index), mergeSubtitles(cue, cues[index + 1]), ...cues.slice(index + 2),
                  ]))}>Merge next</Button>
                  <select aria-label={`Position subtitle ${index + 1}`} className="min-h-10 rounded border bg-white px-2 text-xs" disabled={busy !== undefined} value={cue.position ?? ""} onChange={(event) => edit(cue.id, { position: (event.target.value || null) as SubtitleCue["position"] })}>
                    <option value="">Default ({draft?.position.replaceAll("_", " ")})</option><option value="lower_safe">Lower safe area</option><option value="middle">Middle</option><option value="upper">Upper</option>
                  </select>
                </div>
              </div>)}
            </div>
          </div>
        </div>
        <div className="shrink-0 border-t border-[#D7D9D3] pt-3">
          {error ? <p className="mb-2 text-sm text-[#A23B2A]" role="alert">{error}</p> : null}
          {notice ? <p className="mb-2 text-xs text-[#173F5F]" role="status">{notice}</p> : null}
          <div className="flex flex-wrap items-center gap-2">
            <Button size="sm" type="button" variant="outline" disabled={busy !== undefined || !history.length} onClick={() => { const previous = history.at(-1); if (previous) { setCues(previous); setHistory(history.slice(0, -1)); setError(""); setNotice(""); } }}><Undo2Icon aria-hidden="true" />Undo</Button>
            <Button size="sm" type="button" variant="outline" disabled={busy !== undefined || !draft || !changed} title={`Restore subtitles from version ${version}`} onClick={() => draft && change(draft.baseline)}>Reset draft</Button>
            <button className="min-h-10 text-xs text-[#173F5F] underline" type="button" disabled={busy !== undefined} onClick={() => { if (!dirty || window.confirm("Replace unsaved changes with the server draft?")) void load(); }}>Reload draft</button>
            <span className="ml-auto text-xs text-[#666862]">{dirty ? "Unsaved changes" : draft?.saved ? "Draft saved" : "No changes"} · No AI editing calls</span>
          </div>
          <div className="mt-3 grid grid-cols-2 gap-3">
            <Button className="min-h-12" type="button" variant="outline" disabled={busy !== undefined || !draft || !dirty} onClick={() => void persist(false)}>{busy === "saving" ? <LoaderCircleIcon aria-hidden="true" className="animate-spin" /> : null}Save draft</Button>
            <Button className="min-h-12 bg-[#173F5F] text-white" type="button" disabled={busy !== undefined || !draft || !changed} onClick={() => void persist(true)}>{busy === "applying" ? <LoaderCircleIcon aria-hidden="true" className="animate-spin" /> : null}Apply subtitles</Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  </>;
}
