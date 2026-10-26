"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { StudioNav } from "./studio-nav";
import { CopyIcon, LoaderCircleIcon, PencilIcon, PlusIcon, Trash2Icon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  deleteBrandKit,
  deleteCreativeProfile,
  createCreativeProfile,
  getBrandKits,
  getCreativeProfiles,
  saveBrandKit,
  updateCreativeProfile,
  type BrandKit,
  type CreativeProfile,
} from "@/lib/media-api";

export function BrandProfileManager() {
  const [kits, setKits] = useState<readonly BrandKit[]>([]);
  const [profiles, setProfiles] = useState<readonly CreativeProfile[]>([]);
  const [name, setName] = useState("");
  const [primaryColor, setPrimaryColor] = useState("#173F5F");
  const [accentColor, setAccentColor] = useState("#4BA3D3");
  const [captionStyle, setCaptionStyle] = useState<BrandKit["caption_style"]>("bold");
  const [fontFamily, setFontFamily] = useState<BrandKit["font_family"]>("sans");
  const [editingId, setEditingId] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();

  const refresh = async () => {
    const [nextKits, nextProfiles] = await Promise.all([getBrandKits(), getCreativeProfiles()]);
    setKits(nextKits); setProfiles(nextProfiles);
  };

  useEffect(() => { void refresh().catch((value) => setError(value instanceof Error ? value.message : "Could not load settings")); }, []);

  const reset = () => { setName(""); setPrimaryColor("#173F5F"); setAccentColor("#4BA3D3"); setCaptionStyle("bold"); setFontFamily("sans"); setEditingId(undefined); };
  const submit = async () => {
    if (!name.trim()) { setError("Give this brand kit a name."); return; }
    setBusy(true); setError(undefined);
    try {
      await saveBrandKit({ name: name.trim(), primary_color: primaryColor, accent_color: accentColor, caption_style: captionStyle, font_family: fontFamily }, editingId);
      reset(); await refresh();
    } catch (value) { setError(value instanceof Error ? value.message : "Could not save brand kit"); }
    finally { setBusy(false); }
  };

  return (
    <main className="min-h-dvh bg-[#F7F7F5] px-4 py-8 text-[#20211F]">
      <div className="mx-auto max-w-4xl">
        <header className="flex items-start justify-between gap-4 border-b border-[#D7D9D3] pb-5">
          <div><StudioNav current="/settings" /><h1 className="mt-3 text-3xl font-bold text-[#173F5F]">Brand &amp; presets</h1><p className="mt-2 text-sm text-[#666862]">Reusable visual identity and editing recipes for every channel.</p></div>
          <Button asChild><Link href="/jobs/new">New edit</Link></Button>
        </header>
        <div className="mt-8 grid gap-6 lg:grid-cols-2">
          <section className="rounded-md border border-[#D7D9D3] bg-white p-5">
            <p className="font-mono text-xs font-bold text-[#173F5F] uppercase">Brand kit</p>
            <h2 className="mt-2 text-xl font-bold text-[#173F5F]">Caption identity</h2>
            <div className="mt-5 space-y-3">
              <Input aria-label="Brand kit name" maxLength={80} onChange={(event) => setName(event.target.value)} placeholder="Brand kit name" value={name} />
              <div className="grid grid-cols-2 gap-3">
                <label className="text-xs font-bold text-[#666862]">Primary <input className="mt-2 h-11 w-full" onChange={(event) => setPrimaryColor(event.target.value)} type="color" value={primaryColor} /></label>
                <label className="text-xs font-bold text-[#666862]">Caption accent <input className="mt-2 h-11 w-full" onChange={(event) => setAccentColor(event.target.value)} type="color" value={accentColor} /></label>
                <select aria-label="Caption style" className="h-11 rounded-md border px-3 text-sm" onChange={(event) => setCaptionStyle(event.target.value as BrandKit["caption_style"])} value={captionStyle}><option value="bold">Bold captions</option><option value="clean">Clean captions</option><option value="minimal">Minimal captions</option></select>
                <select aria-label="Caption font family" className="h-11 rounded-md border px-3 text-sm" onChange={(event) => setFontFamily(event.target.value as BrandKit["font_family"])} value={fontFamily}><option value="sans">Sans</option><option value="serif">Serif</option><option value="mono">Mono</option></select>
              </div>
              <div className="rounded-md px-4 py-5 text-center text-xl" style={{ backgroundColor: primaryColor, color: "white", fontFamily: fontFamily === "mono" ? "monospace" : fontFamily === "serif" ? "serif" : "sans-serif", fontWeight: captionStyle === "minimal" ? 400 : 800, WebkitTextStroke: `1px ${accentColor}` }}>Your captions look like this</div>
              <Button className="w-full" disabled={busy} onClick={() => void submit()}>{busy ? <LoaderCircleIcon className="animate-spin" /> : editingId ? <PencilIcon /> : <PlusIcon />}{editingId ? "Update brand kit" : "Save brand kit"}</Button>
            </div>
            <div className="mt-5 space-y-2 border-t pt-4">
              {kits.map((kit) => <div className="flex items-center justify-between rounded-md border p-3" key={kit.id}><div><p className="text-sm font-bold">{kit.name}</p><p className="mt-1 text-xs text-[#666862]">{kit.caption_style} · {kit.font_family}</p></div><div className="flex gap-1"><Button aria-label={`Edit ${kit.name}`} onClick={() => { setEditingId(kit.id); setName(kit.name); setPrimaryColor(kit.primary_color); setAccentColor(kit.accent_color); setCaptionStyle(kit.caption_style); setFontFamily(kit.font_family); }} size="icon" variant="outline"><PencilIcon /></Button><Button aria-label={`Delete ${kit.name}`} onClick={() => void deleteBrandKit(kit.id).then(refresh)} size="icon" variant="outline"><Trash2Icon /></Button></div></div>)}
            </div>
          </section>
          <section className="rounded-md border border-[#D7D9D3] bg-white p-5">
            <p className="font-mono text-xs font-bold text-[#173F5F] uppercase">Creative profiles</p>
            <h2 className="mt-2 text-xl font-bold text-[#173F5F]">Saved edit recipes</h2>
            <p className="mt-2 text-sm text-[#666862]">Rename or retire profiles saved from finished edits. Their pacing, format, music and brand choices remain bundled.</p>
            <div className="mt-5 space-y-3">
              {profiles.length === 0 ? <p className="rounded-md bg-[#F7F7F5] p-4 text-sm text-[#666862]">Save a profile from a finished delivery and it will appear here.</p> : profiles.map((profile) => <article className="rounded-md border p-4" key={profile.id}><div className="flex items-start justify-between gap-3"><div><p className="font-bold text-[#173F5F]">{profile.name}</p><p className="mt-1 text-xs text-[#666862]">{profile.recipe.replaceAll("_", " ")} · {profile.output_aspect} · {profile.target_duration_seconds}s · {profile.publishing_preset.replaceAll("_", " ")}</p></div><div className="flex gap-1"><Button aria-label="Duplicate profile" onClick={() => void createCreativeProfile({ name: `${profile.name} copy`, description: profile.description, recipe: profile.recipe, target_duration_seconds: profile.target_duration_seconds, edit_style: profile.edit_style, music_mode: profile.music_mode, target_platform: profile.target_platform, output_aspect: profile.output_aspect, reasoning_effort: profile.reasoning_effort, source_job_id: profile.source_job_id, brand_kit_id: profile.brand_kit_id, publishing_preset: profile.publishing_preset }).then(refresh)} size="icon" variant="outline"><CopyIcon /></Button><Button aria-label="Rename profile" onClick={() => { const renamed = window.prompt("Profile name", profile.name); if (renamed) void updateCreativeProfile(profile.id, renamed, profile.description).then(refresh); }} size="icon" variant="outline"><PencilIcon /></Button><Button aria-label="Delete profile" onClick={() => void deleteCreativeProfile(profile.id).then(refresh)} size="icon" variant="outline"><Trash2Icon /></Button></div></div></article>)}
            </div>
          </section>
        </div>
        {error ? <p className="mt-5 text-sm text-[#A23B2A]" role="alert">{error}</p> : null}
      </div>
    </main>
  );
}
