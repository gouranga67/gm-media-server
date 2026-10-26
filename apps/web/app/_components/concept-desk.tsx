"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { ArrowRightIcon, CheckIcon, LoaderCircleIcon, PlusIcon, SparklesIcon } from "lucide-react";
import { LibraryUpload } from "@/app/_components/library-upload";
import {
  generateLibraryConcepts, getConceptLibraryStatus, getConceptSession, getConceptSessions,
  getLibraryCollections, getMusicTracks, libraryAssetPreviewUrl, libraryAssetThumbnailUrl, renderLibraryConcepts,
  type ConceptJob, type ConceptLibraryStatus, type ConceptSession, type EffectLevel,
  type LibraryCollection, type MusicMode, type ReelConcept, type TargetPlatform,
} from "@/lib/media-api";

const control = "min-h-11 w-full rounded-md border border-[#D7D9D3] bg-white px-3 text-sm text-[#20211F] disabled:opacity-50";
const primary = "inline-flex min-h-11 items-center justify-center gap-2 rounded-md bg-[#173F5F] px-4 text-sm font-bold text-white disabled:opacity-50";
const message = (error: unknown) => error instanceof Error ? error.message : "This request could not be completed.";
function sourceTime(time: number) { return `${Math.floor(time / 60)}:${String(Math.floor(time % 60)).padStart(2, "0")}`; }
const blooperLabels: Readonly<Record<string, string>> = {
  self_correction: "self-correction", word_stumble: "word stumble", lost_line: "lost line",
  transcribed_laughter: "laughter in transcript", retake_direction: "retake direction",
  repeated_start: "repeated start", possible_alternate_take: "possible alternate take",
  nearby_setup_or_recovery: "nearby setup or recovery",
};

function ConceptCard({ concept, selected, disabled, job, onSelect }: {
  readonly concept: ReelConcept; readonly selected: boolean; readonly disabled: boolean;
  readonly job?: ConceptJob; readonly onSelect: () => void;
}) {
  return <article className={`overflow-hidden rounded-md border bg-white ${selected ? "border-[#173F5F] ring-1 ring-[#173F5F]" : "border-[#D7D9D3]"}`}>
    <div className="border-b border-[#E7E8E4] p-4">
      <label className="flex min-h-11 cursor-pointer items-start gap-3"><input aria-label={`Choose ${concept.title}`} checked={selected} className="mt-1 size-5 shrink-0 accent-[#173F5F]" disabled={disabled || Boolean(job)} onChange={onSelect} type="checkbox" /><span><span className="block text-lg font-bold text-[#173F5F]">{concept.title}</span><span className="mt-1 block text-xs text-[#666862]">{concept.estimated_seconds}s of recorded speech · {concept.asset_ids.length} source files</span></span></label>
      <p className="mt-3 text-sm leading-6 text-[#666862]">{concept.angle}</p>
      {job ? <Link className={`${primary} mt-3`} href={`/jobs/${job.job_id}`}><CheckIcon aria-hidden="true" className="size-4" />Open edit<ArrowRightIcon aria-hidden="true" className="size-4" /></Link> : null}
    </div>
    <div className="space-y-4 p-4">
      <p className="font-mono text-[10px] font-bold tracking-wide text-[#666862] uppercase">Recorded script · your existing words</p>
      <ol className="space-y-4">{concept.script.map((beat) => <li key={beat.evidence_id}><p className="font-mono text-[10px] font-bold text-[#173F5F] uppercase">{beat.role}</p>{beat.blooper_signals?.length ? <p className="mt-1 text-xs text-[#8A5928]">{beat.blooper_candidate ? "Possible outtake" : "Context"} · {beat.blooper_signals.map((signal) => blooperLabels[signal] ?? signal.replaceAll("_", " ")).join(", ")}</p> : null}<blockquote className="mt-1 text-sm leading-6 text-[#20211F]">“{beat.text}”</blockquote><a className="mt-1 inline-block max-w-full truncate text-xs text-[#666862] underline underline-offset-2" href={`${libraryAssetPreviewUrl(beat.asset_id)}#t=${beat.start},${beat.end}`} rel="noreferrer" target="_blank">{beat.display_name} · {sourceTime(beat.start)}–{sourceTime(beat.end)}</a></li>)}</ol>
      {concept.visuals.length ? <section className="border-t border-[#E7E8E4] pt-4"><p className="font-mono text-[10px] font-bold text-[#666862] uppercase">Supporting pictures</p><ul className="mt-3 space-y-3">{concept.visuals.map((visual) => <li className="flex items-start gap-3" key={visual.asset_id}><a aria-label={`Preview ${visual.display_name}`} className="shrink-0" href={libraryAssetPreviewUrl(visual.asset_id)} rel="noreferrer" target="_blank"><img alt="" className="size-14 rounded-sm bg-[#E4EBEF] object-cover" loading="lazy" src={libraryAssetThumbnailUrl(visual.asset_id)} /></a><div className="min-w-0"><p className="truncate text-xs font-bold text-[#173F5F]">{visual.display_name}</p><p className="mt-1 text-xs leading-5 text-[#666862]">{visual.reason}</p></div></li>)}</ul></section> : <p className="border-t border-[#E7E8E4] pt-3 text-xs text-[#666862]">Speech-led concept. No additional pictures were confidently selected.</p>}
    </div>
  </article>;
}

export function ConceptDesk() {
  const [focus, setFocus] = useState("");
  const [audience, setAudience] = useState("");
  const [privacy, setPrivacy] = useState<"hybrid" | "text_only">("hybrid");
  const [reelKind, setReelKind] = useState<"story" | "bloopers">("story");
  const [collectionId, setCollectionId] = useState("");
  const [collections, setCollections] = useState<readonly LibraryCollection[]>([]);
  const [coverage, setCoverage] = useState<ConceptLibraryStatus>();
  const [history, setHistory] = useState<readonly ConceptSession[]>([]);
  const [activeId, setActiveId] = useState<string>();
  const [session, setSession] = useState<ConceptSession>();
  const [chosen, setChosen] = useState<ReadonlySet<string>>(new Set());
  const [effectLevel, setEffectLevel] = useState<EffectLevel>("social");
  const [musicMode, setMusicMode] = useState<MusicMode>("none");
  const [platform, setPlatform] = useState<TargetPlatform>("all_social");
  const [hasMusic, setHasMusic] = useState(false);
  const [busy, setBusy] = useState(false);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [error, setError] = useState<string>();
  const [historyError, setHistoryError] = useState<string>();
  const submission = useRef<{ key: string; id: string } | undefined>(undefined);
  const loadingSession = Boolean(activeId && !session);
  const generating = session?.status === "pending" || session?.status === "generating";

  async function refreshLibrary() {
    const [status, groups] = await Promise.all([getConceptLibraryStatus(), getLibraryCollections()]);
    setCoverage(status); setCollections(groups);
  }
  useEffect(() => {
    let cancelled = false;
    void Promise.all([getConceptLibraryStatus(), getLibraryCollections().catch(() => []), getConceptSessions(), getMusicTracks().catch(() => [])]).then(([status, groups, sessions, tracks]) => {
      if (cancelled) return;
      setCoverage(status); setCollections(groups); setHistory(sessions); setHasMusic(tracks.some((track) => track.active));
      const fromUrl = new URL(window.location.href).searchParams.get("session");
      setActiveId(fromUrl && /^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$/i.test(fromUrl) ? fromUrl : sessions[0]?.id);
    }).catch((requestError: unknown) => { if (!cancelled) setError(message(requestError)); });
    return () => { cancelled = true; };
  }, []);
  // Analysis can finish after an upload is ingested; keep readiness truthful.
  useEffect(() => {
    if (!coverage?.still_processing) return;
    let cancelled = false;
    const timer = window.setInterval(() => { void getConceptLibraryStatus().then((status) => { if (!cancelled) setCoverage(status); }).catch(() => undefined); }, 5000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [coverage?.still_processing]);
  useEffect(() => {
    if (!activeId) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    setSession(undefined); setChosen(new Set()); setHistoryError(undefined);
    window.history.replaceState(null, "", `/concepts?session=${encodeURIComponent(activeId)}`);
    async function poll() {
      try {
        const result = await getConceptSession(activeId!);
        if (cancelled) return;
        if (!result?.id || !Array.isArray(result.concepts)) throw new Error("Saved concept options could not be read. Retrying…");
        setSession(result); setHistoryError(undefined);
        setHistory((current) => [result, ...current.filter((item) => item.id !== result.id)]);
        if (result.status === "pending" || result.status === "generating") timer = setTimeout(() => void poll(), 2000);
      } catch (requestError) {
        if (!cancelled) { setHistoryError(message(requestError)); if (message(requestError).includes("concept session not found")) setActiveId(undefined); else timer = setTimeout(() => void poll(), 5000); }
      }
    }
    void poll();
    return () => { cancelled = true; clearTimeout(timer); };
  }, [activeId]);

  async function generate() {
    if (busy || generating || loadingSession) return;
    setBusy(true); setError(undefined);
    const settings = { focus: focus.trim(), audience: audience.trim(), collection_id: collectionId || null, privacy_mode: privacy, reel_kind: reelKind };
    const key = JSON.stringify(settings);
    if (submission.current?.key !== key) submission.current = { key, id: crypto.randomUUID() };
    try {
      const result = await generateLibraryConcepts({ ...settings, id: submission.current.id });
      submission.current = undefined;
      setHistory((current) => [result, ...current.filter((item) => item.id !== result.id)]);
      setSession(result); setActiveId(result.id); setChosen(new Set());
    } catch (requestError) { setError(message(requestError)); }
    finally { setBusy(false); }
  }
  async function createPreviews() {
    if (busy || !session || chosen.size === 0) return;
    setBusy(true); setError(undefined);
    try {
      const result = await renderLibraryConcepts(session.id, { concept_ids: Array.from(chosen), effect_level: effectLevel, music_mode: musicMode, target_platform: platform });
      setSession((current) => current ? { ...current, jobs: [...current.jobs.filter((job) => !result.jobs.some((created) => created.concept_id === job.concept_id)), ...result.jobs] } : current);
      setChosen(new Set());
    } catch (requestError) { setError(message(requestError)); }
    finally { setBusy(false); }
  }
  function toggle(id: string) { setChosen((current) => { const next = new Set(current); if (next.has(id)) next.delete(id); else if (next.size < 2) next.add(id); return next; }); }

  return <main className="min-h-dvh bg-[#F7F7F5] px-4 py-6 text-[#20211F] [color-scheme:light] sm:px-6">
    <div className="mx-auto max-w-[1320px]">
      <header className="border-b border-[#D7D9D3] pb-5"><nav aria-label="Studio" className="flex flex-wrap items-center gap-5 text-sm font-bold text-[#173F5F]"><Link href="/jobs/new">GM Studio</Link><Link href="/library">Library</Link><Link href="/jobs">Jobs</Link><Link href="/usage">AI usage</Link></nav><div className="mt-7 flex flex-wrap items-end justify-between gap-4"><div><p className="font-mono text-[10px] font-bold tracking-widest text-[#666862] uppercase">Create from your library</p><h1 className="mt-2 text-3xl font-bold text-[#173F5F]">Find your next reel</h1><p className="mt-2 max-w-2xl text-sm leading-6 text-[#666862]">Your recorded words, a fresh story. Explore up to three concepts, choose one or two, and let the editor make the previews.</p></div><button aria-controls="concept-import" aria-expanded={uploadOpen} className="inline-flex min-h-11 items-center gap-2 rounded-md border border-[#D7D9D3] bg-white px-4 text-sm font-bold text-[#173F5F]" onClick={() => setUploadOpen((current) => !current)} type="button"><PlusIcon aria-hidden="true" className="size-4" />Add more footage</button></div></header>
      <div hidden={!uploadOpen} id="concept-import"><LibraryUpload onReady={refreshLibrary} /></div>
      <p aria-live="polite" className="my-4 text-xs leading-6 text-[#666862]">{coverage ? `${coverage.catalogued_sources} unique sources catalogued · ${coverage.spoken_sources} with recorded speech · ${coverage.visually_indexed_sources} visually indexed${coverage.still_processing ? ` · ${coverage.still_processing} files still processing` : ""}${coverage.analysis_failed ? ` · ${coverage.analysis_failed} files need attention` : ""}` : "Checking library analysis…"}</p>
      <form aria-label="Find reel concepts" className="grid gap-4 rounded-md border border-[#D7D9D3] bg-white p-4 lg:grid-cols-[1.5fr_1fr]" onSubmit={(event) => { event.preventDefault(); void generate(); }}>
        <div className="space-y-2 lg:col-span-2"><label className="block max-w-sm text-xs font-bold text-[#173F5F]">Reel type<select aria-label="Reel type" className={`${control} mt-2`} disabled={busy || generating || loadingSession} onChange={(event) => setReelKind(event.currentTarget.value as typeof reelKind)} value={reelKind}><option value="story">Story reel</option><option value="bloopers">Bloopers &amp; outtakes</option></select></label>{reelKind === "bloopers" ? <p className="max-w-3xl rounded-md bg-[#FFF7EB] p-3 text-xs leading-5 text-[#8A5928]">Find possible mistakes, restarts and laughter in stored transcripts, with nearby setup and recovery. Clues are not confirmed errors; review the source links before choosing. Purely visual gags and untranscribed laughter may be missed. No model request is queued when the local scan finds no candidates.</p> : null}</div>
        <div className="space-y-3"><label className="block text-xs font-bold text-[#173F5F]">Direction <span className="font-normal text-[#666862]">· optional</span><textarea className={`${control} mt-2 min-h-24 resize-y py-3`} disabled={busy || generating} maxLength={1200} onChange={(event) => setFocus(event.currentTarget.value)} placeholder="Surprise me with a new reel concept from our footage—or focus on a product, problem or theme." value={focus} /></label><label className="block text-xs font-bold text-[#173F5F]">Audience <span className="font-normal text-[#666862]">· optional</span><input className={`${control} mt-2`} disabled={busy || generating} maxLength={600} onChange={(event) => setAudience(event.currentTarget.value)} placeholder="Who should this connect with?" value={audience} /></label></div>
        <div className="space-y-3"><label className="block text-xs font-bold text-[#173F5F]">Footage scope<select aria-label="Concept footage scope" className={`${control} mt-2`} disabled={busy || generating} onChange={(event) => setCollectionId(event.currentTarget.value)} value={collectionId}><option value="">All active library media</option>{collections.map((collection) => <option key={collection.id} value={collection.id}>{collection.name}</option>)}</select></label><label className="block text-xs font-bold text-[#173F5F]">Analysis shared for this request<select aria-label="Concept privacy" className={`${control} mt-2`} disabled={busy || generating} onChange={(event) => setPrivacy(event.currentTarget.value as typeof privacy)} value={privacy}><option value="hybrid">Transcript + small preview frames</option><option value="text_only">Transcript and metadata only</option></select></label><p className="text-xs leading-5 text-[#666862]">Original files stay on your server. Reuses stored analysis; one bounded concept request when you press Generate. Creating selected edits makes their normal editing requests. No new speech is generated.</p>{coverage?.still_processing ? <p className="rounded-md bg-[#EFF6FA] p-2 text-xs leading-5 text-[#173F5F]">More files are still processing. Wait to include them, or generate ideas from the ready footage now.</p> : null}<button className={`${primary} w-full`} disabled={busy || generating || loadingSession || !coverage || coverage.spoken_sources === 0} type="submit">{busy || generating ? <LoaderCircleIcon aria-hidden="true" className="size-4 animate-spin" /> : <SparklesIcon aria-hidden="true" className="size-4" />}{generating ? "Finding supported moments…" : reelKind === "bloopers" ? "Find blooper reel ideas" : "Generate reel ideas"}</button></div>
      </form>
      {error ? <p className="my-4 rounded-md border border-[#D8B4AA] bg-[#FFF7F4] p-3 text-sm text-[#A23B2A]" role="alert">{error}</p> : null}
      <section aria-label="Saved concept sessions" className="mt-6 flex flex-wrap items-center justify-between gap-3"><h2 className="text-lg font-bold text-[#173F5F]">Concept options</h2>{history.length ? <label className="text-xs font-bold text-[#666862]">Saved sessions<select aria-label="Saved concept session" className={`${control} mt-1 max-w-80`} disabled={busy || generating} onChange={(event) => { setActiveId(event.currentTarget.value); setError(undefined); }} value={activeId ?? ""}>{history.map((item) => <option key={item.id} value={item.id}>{new Date(item.created_at).toLocaleString()} · {item.focus.slice(0,45) || (item.reel_kind === "bloopers" ? "Blooper ideas" : "Library ideas")} · {item.status}</option>)}</select></label> : null}</section>
      {historyError ? <p className="mt-3 text-sm text-[#A23B2A]" role="alert">{historyError} · Reconnecting to saved results…</p> : null}
      {session ? <p className="mt-3 text-xs leading-6 text-[#666862]">Considered {session.coverage.sources_considered} of {session.coverage.unique_sources_available} unique ready sources and {session.coverage.speech_passages} speech passages. {session.reel_kind === "bloopers" ? `${session.coverage.possible_blooper_passages ?? 0} possible outtake passages. ` : ""}{session.total_tokens ? `${session.total_tokens.toLocaleString()} measured concept tokens.` : ""} {session.coverage.sources_considered < session.coverage.unique_sources_available ? "Use a collection or direction to explore another part of a large library." : ""}</p> : null}
      {session?.status === "failed" ? <p className="mt-4 rounded-md border border-[#D8B4AA] bg-[#FFF7F4] p-4 text-sm text-[#A23B2A]" role="alert">{session.error} No edits were created. Generate again only when you want another concept request.</p> : null}
      {generating || (activeId && !session) ? <div className="my-6 flex min-h-48 items-center justify-center gap-3 rounded-md border border-[#D7D9D3] bg-white text-sm text-[#173F5F]" role="status"><LoaderCircleIcon aria-hidden="true" className="size-5 animate-spin" />{session?.status === "pending" ? "Queued behind current studio work. You can leave and return to these saved results." : loadingSession ? "Loading saved concept options…" : "Finding stories supported by your existing footage…"}</div> : null}
      {session?.status === "ready" ? <>
        {session.concepts.length === 0 ? <p className="mt-4 rounded-md border border-[#D7D9D3] bg-white p-4 text-sm text-[#666862]">No worthwhile blooper reel was supported by these candidates. Nothing was created. Try another collection or review the footage yourself.</p> : null}
        <div className="mt-4 grid items-start gap-4 lg:grid-cols-3">{session.concepts.map((concept) => <ConceptCard concept={concept} disabled={busy || (!chosen.has(concept.id) && chosen.size >= 2)} job={session.jobs.find((job) => job.concept_id === concept.id)} key={concept.id} onSelect={() => toggle(concept.id)} selected={chosen.has(concept.id)} />)}</div>
        <section aria-label="Create selected edits" className="sticky bottom-2 mt-5 space-y-3 rounded-md border border-[#AFC7D5] bg-[#EFF6FA] p-4"><div className="flex flex-wrap items-end gap-3"><p className="min-w-40 flex-1 text-sm font-bold text-[#173F5F]">{chosen.size} of 2 selected <span className="mt-1 block text-xs font-normal text-[#666862]">High impact · vertical · {session.reel_kind === "bloopers" ? "recorded bloopers" : "existing recorded speech"}</span></p><label className="text-xs font-bold text-[#173F5F]">Effects<select aria-label="Concept edit effects" className={`${control} mt-1`} disabled={busy} onChange={(event) => setEffectLevel(event.currentTarget.value as EffectLevel)} value={effectLevel}><option value="off">Off</option><option value="subtle">Subtle</option><option value="social">Social</option><option value="meme_heavy">Meme-heavy</option></select></label><label className="text-xs font-bold text-[#173F5F]">Music<select aria-label="Concept edit music" className={`${control} mt-1`} disabled={busy} onChange={(event) => setMusicMode(event.currentTarget.value as MusicMode)} value={musicMode}><option value="none">None</option><option disabled={!hasMusic} value="subtle">Subtle</option><option disabled={!hasMusic} value="present">Present</option></select></label><label className="text-xs font-bold text-[#173F5F]">Platform<select aria-label="Concept edit platform" className={`${control} mt-1`} disabled={busy} onChange={(event) => setPlatform(event.currentTarget.value as TargetPlatform)} value={platform}><option value="all_social">All social</option><option value="instagram">Instagram</option><option value="tiktok">TikTok</option><option value="youtube">YouTube</option><option value="facebook">Facebook</option><option value="linkedin">LinkedIn</option></select></label><button className={primary} disabled={busy || chosen.size === 0} onClick={() => void createPreviews()} type="button">{busy ? <LoaderCircleIcon aria-hidden="true" className="size-4 animate-spin" /> : <ArrowRightIcon aria-hidden="true" className="size-4" />}Create {chosen.size || "selected"} {chosen.size === 1 ? "preview" : "previews"}</button></div><p className="text-xs leading-5 text-[#666862]">Only selected concepts become jobs. You review the finished previews before approving an export.</p></section>
      </> : !activeId ? <div className="mt-4 rounded-md border border-dashed border-[#C7CBD0] p-8 text-center text-sm leading-6 text-[#666862]">Add footage to the library, wait for its speech analysis, then generate ideas. Nothing renders until you choose a concept.</div> : null}
    </div>
  </main>;
}
