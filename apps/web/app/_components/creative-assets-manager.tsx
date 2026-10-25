"use client";

import { type FormEvent, type ReactNode, useEffect, useState } from "react";
import { ArchiveIcon, ExternalLinkIcon, LoaderCircleIcon, Music2Icon, RotateCcwIcon, SparklesIcon, UploadIcon } from "lucide-react";

import {
  creativeAssetMediaUrl, getAllMusicTracks, getCreativeAssets, importCreativeAsset,
  musicTrackMediaUrl, setCreativeAssetActive, setMusicTrackActive,
  type CreativeAsset, type MusicTrack,
} from "@/lib/media-api";
import { StudioNav } from "./studio-nav";

const field = "mt-2 min-h-11 w-full rounded-md border border-[#C7CBD0] bg-white px-3 text-sm font-normal text-[#20211F]";

function message(error: unknown) { return error instanceof Error ? error.message : "The creative library could not be updated"; }
function bytes(value: number) { return value < 1_000_000 ? `${Math.round(value / 1000)} KB` : `${(value / 1_000_000).toFixed(1)} MB`; }

export function CreativeAssetsManager() {
  const [music, setMusic] = useState<readonly MusicTrack[]>();
  const [effects, setEffects] = useState<readonly CreativeAsset[]>();
  const [error, setError] = useState<string>();
  const [notice, setNotice] = useState<string>();
  const [saving, setSaving] = useState(false);

  const load = async () => {
    const [tracks, activeEffects, archivedEffects] = await Promise.all([
      getAllMusicTracks(), getCreativeAssets(true), getCreativeAssets(false),
    ]);
    setMusic(tracks); setEffects([...activeEffects, ...archivedEffects]);
  };
  useEffect(() => { void load().catch((reason: unknown) => setError(message(reason))); }, []);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); setSaving(true); setError(undefined); setNotice(undefined);
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const file = form.get("file");
    if (!(file instanceof File) || file.size === 0) { setError("Choose a downloaded media file first."); setSaving(false); return; }
    try {
      await importCreativeAsset(file, {
        kind: String(form.get("kind")), title: String(form.get("title")), creator: String(form.get("creator")),
        tags: String(form.get("tags")), purpose: String(form.get("purpose")), mood: String(form.get("mood")),
        energy: String(form.get("energy")), license_name: String(form.get("license_name")),
        license_source_url: String(form.get("license_source_url")), license_proof: String(form.get("license_proof")),
        attribution: String(form.get("attribution")), allowed_platforms: String(form.get("allowed_platforms")),
        commercial_use_confirmed: form.get("commercial_use_confirmed") === "on",
      });
      formElement.reset(); setNotice("Imported with its rights record. It is ready for future edits."); await load();
    } catch (reason) { setError(message(reason)); } finally { setSaving(false); }
  };

  return <main className="min-h-dvh bg-[#F7F7F5] px-4 py-[max(1.25rem,env(safe-area-inset-top))] text-[#20211F] sm:px-6">
    <div className="mx-auto max-w-6xl">
      <header className="border-b border-[#D7D9D3] pb-5"><StudioNav current="/creative" /><p className="mt-8 font-mono text-[10px] font-bold tracking-widest text-[#174D73] uppercase">Phase 16 · rights-aware library</p><h1 className="mt-2 text-3xl font-black text-[#173F5F]">Music &amp; creative effects</h1><p className="mt-3 max-w-3xl text-sm leading-6 text-[#666862]">Import music, sounds, stickers, GIFs, and meme images you are allowed to use commercially. GM Studio records the source and licence, then gives the editor only compatible assets.</p></header>
      {error ? <p className="mt-5 rounded-md bg-[#FFF0EC] p-4 text-sm text-[#A23B2A]">{error}</p> : null}{notice ? <p className="mt-5 rounded-md bg-[#E4F1E9] p-4 text-sm text-[#307455]">{notice}</p> : null}
      <div className="grid gap-6 py-6 lg:grid-cols-[0.9fr_1.4fr]">
        <form className="h-fit rounded-md border border-[#D7D9D3] bg-white p-5" onSubmit={submit}>
          <div className="flex items-center gap-2"><UploadIcon className="size-4 text-[#174D73]" /><h2 className="font-bold text-[#173F5F]">Import a licensed asset</h2></div>
          <p className="mt-2 text-xs leading-5 text-[#666862]">For Pixabay, download from the official track page and paste that page URL below. Keep the original filename.</p>
          <label className="mt-5 block text-xs font-bold text-[#53646F]">TYPE<select className={field} name="kind" defaultValue="music"><option value="music">Music track</option><option value="sound_effect">Sound effect</option><option value="meme_sound">Meme sound</option><option value="sticker">Sticker / emoji image</option><option value="gif">Animated GIF</option><option value="meme_image">Meme image</option></select></label>
          <label className="mt-4 block text-xs font-bold text-[#53646F]">FILE<input accept="audio/*,image/png,image/jpeg,image/webp,image/gif" className={`${field} py-2`} name="file" required type="file" /></label>
          <div className="mt-4 grid grid-cols-2 gap-3"><label className="text-xs font-bold text-[#53646F]">TITLE<input className={field} name="title" required /></label><label className="text-xs font-bold text-[#53646F]">CREATOR<input className={field} name="creator" /></label></div>
          <div className="mt-4 grid grid-cols-2 gap-3"><label className="text-xs font-bold text-[#53646F]">PURPOSE<select className={field} name="purpose" defaultValue="emphasis"><option value="hook">Hook</option><option value="transition">Transition</option><option value="emphasis">Emphasis</option><option value="reveal">Reveal</option><option value="reaction">Reaction</option><option value="payoff">Payoff</option></select></label><label className="text-xs font-bold text-[#53646F]">ENERGY<select className={field} name="energy" defaultValue="medium"><option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option></select></label></div>
          <label className="mt-4 block text-xs font-bold text-[#53646F]">MOOD / TAGS<div className="mt-2 grid grid-cols-2 gap-3"><input className={`${field} mt-0`} defaultValue="uplifting" name="mood" /><input className={`${field} mt-0`} name="tags" placeholder="funny, pop, reveal" /></div></label>
          <label className="mt-4 block text-xs font-bold text-[#53646F]">LICENCE<input className={field} defaultValue="Pixabay Content License" name="license_name" required /></label>
          <label className="mt-4 block text-xs font-bold text-[#53646F]">SOURCE / TRACK PAGE URL<input className={field} name="license_source_url" placeholder="https://pixabay.com/music/..." required type="url" /></label>
          <label className="mt-4 block text-xs font-bold text-[#53646F]">PROOF NOTE<input className={field} name="license_proof" placeholder="Downloaded 25 Oct 2026 while signed in" /></label>
          <label className="mt-4 block text-xs font-bold text-[#53646F]">ATTRIBUTION<input className={field} name="attribution" placeholder="Optional credit text" /></label>
          <label className="mt-4 block text-xs font-bold text-[#53646F]">ALLOWED PLATFORMS<input className={field} defaultValue="all_social" name="allowed_platforms" /><span className="mt-1 block font-normal">Comma separated: all_social, instagram, tiktok, youtube, facebook, linkedin.</span></label>
          <label className="mt-5 flex items-start gap-3 rounded-md bg-[#EFF6FA] p-3 text-xs leading-5 text-[#36546A]"><input className="mt-1 accent-[#173F5F]" name="commercial_use_confirmed" required type="checkbox" />I reviewed the source licence and confirm this file may be used commercially on the selected platforms.</label>
          <button className="mt-5 flex min-h-12 w-full items-center justify-center gap-2 rounded-md bg-[#173F5F] text-sm font-bold text-white disabled:opacity-50" disabled={saving}>{saving ? <LoaderCircleIcon className="size-4 animate-spin" /> : <UploadIcon className="size-4" />}{saving ? "Validating and importing…" : "Import to library"}</button>
        </form>
        <section className="space-y-6">
          <LibrarySection title="Music" icon={<Music2Icon className="size-4" />} empty="No music has been imported yet.">{music?.map((track) => <article className={`rounded-md border p-4 ${track.active ? "border-[#D7D9D3] bg-white" : "border-dashed border-[#C7CBD0] bg-[#F1F2EF] opacity-70"}`} key={track.id}><div className="flex flex-wrap items-start justify-between gap-3"><div><p className="font-bold text-[#173F5F]">{track.title}</p><p className="mt-1 text-xs text-[#666862]">{track.artist || "Unknown creator"} · {track.mood} · {track.energy} energy · {Math.round(track.duration_seconds)}s</p><a className="mt-2 inline-flex items-center gap-1 text-xs font-bold text-[#174D73] underline" href={track.license_source_url} rel="noreferrer" target="_blank">Licence source <ExternalLinkIcon className="size-3" /></a></div><button className="rounded-md border border-[#D7D9D3] p-2 text-[#53646F]" onClick={() => void setMusicTrackActive(track.id, !track.active).then(load)} type="button">{track.active ? <ArchiveIcon className="size-4" /> : <RotateCcwIcon className="size-4" />}</button></div><audio className="mt-3 w-full" controls preload="none" src={musicTrackMediaUrl(track.id)} /></article>)}</LibrarySection>
          <LibrarySection title="Effects" icon={<SparklesIcon className="size-4" />} empty="No creative effects have been imported yet.">{effects?.map((asset) => <article className={`rounded-md border p-4 ${asset.active ? "border-[#D7D9D3] bg-white" : "border-dashed border-[#C7CBD0] bg-[#F1F2EF] opacity-70"}`} key={asset.id}><div className="flex items-start justify-between gap-3"><div><p className="font-bold text-[#173F5F]">{asset.title}</p><p className="mt-1 text-xs text-[#666862]">{asset.kind.replaceAll("_", " ")} · {asset.purpose} · {bytes(asset.byte_size)}{asset.duration_seconds ? ` · ${asset.duration_seconds.toFixed(1)}s` : ""}</p><p className="mt-1 text-[11px] text-[#666862]">{asset.tags.join(" · ") || "No tags"}</p></div><button className="rounded-md border border-[#D7D9D3] p-2 text-[#53646F]" onClick={() => void setCreativeAssetActive(asset.id, !asset.active).then(load)} type="button">{asset.active ? <ArchiveIcon className="size-4" /> : <RotateCcwIcon className="size-4" />}</button></div>{asset.kind.includes("sound") ? <audio className="mt-3 w-full" controls preload="none" src={creativeAssetMediaUrl(asset.id)} /> : <img alt="" className="mt-3 max-h-48 rounded-md object-contain" loading="lazy" src={creativeAssetMediaUrl(asset.id)} />}<a className="mt-3 inline-flex items-center gap-1 text-xs font-bold text-[#174D73] underline" href={asset.license_source_url} rel="noreferrer" target="_blank">Licence source <ExternalLinkIcon className="size-3" /></a></article>)}</LibrarySection>
        </section>
      </div>
    </div>
  </main>;
}

function LibrarySection({ title, icon, empty, children }: { readonly title: string; readonly icon: ReactNode; readonly empty: string; readonly children: ReactNode }) {
  const items = Array.isArray(children) ? children : [children];
  return <section><h2 className="flex items-center gap-2 font-mono text-xs font-bold tracking-wide text-[#173F5F] uppercase">{icon}{title}</h2><div className="mt-3 grid gap-3">{items.some(Boolean) ? children : <p className="rounded-md border border-dashed border-[#C7CBD0] bg-white p-6 text-sm text-[#666862]">{empty}</p>}</div></section>;
}
