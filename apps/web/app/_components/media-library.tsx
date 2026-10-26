"use client";

import Link from "next/link";
import { LibraryUpload } from "@/app/_components/library-upload";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import {
  ArchiveIcon,
  AudioLinesIcon,
  CheckIcon,
  FilmIcon,
  FolderPlusIcon,
  HardDriveIcon,
  HeartIcon,
  ImageIcon,
  LibraryIcon,
  LoaderCircleIcon,
  LockKeyholeIcon,
  RotateCcwIcon,
  SearchIcon,
  SparklesIcon,
  TagIcon,
  VideoIcon,
  XIcon,
} from "lucide-react";

import {
  createLibraryCollection,
  getLibraryAssetDetail,
  getLibraryCollections,
  getManagedLibraryAssets,
  libraryAssetPreviewUrl,
  libraryAssetThumbnailUrl,
  searchCatalog,
  setLibraryAssetState,
  setLibraryCollectionMembership,
  updateLibraryAsset,
  visualIndexFrameUrl,
  type CatalogSearchResult,
  type LibraryAssetDetail,
  type LibraryCollection,
  type ManagedLibraryAsset,
} from "@/lib/media-api";

type MediaKind = "all" | "video" | "image" | "audio";
type LibraryState = "active" | "archived" | "all";

function formatBytes(value: number) {
  if (value < 1024) return `${value} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let amount = value / 1024;
  let unit = units[0];
  for (const candidate of units) {
    unit = candidate;
    if (amount < 1024 || candidate === units.at(-1)) break;
    amount /= 1024;
  }
  return `${new Intl.NumberFormat(undefined, { maximumFractionDigits: amount >= 10 ? 1 : 2 }).format(amount)} ${unit}`;
}

function formatDuration(value: number | null) {
  if (value === null) return "—";
  const rounded = Math.max(0, Math.round(value));
  const minutes = Math.floor(rounded / 60);
  const seconds = rounded % 60;
  return minutes ? `${minutes}:${String(seconds).padStart(2, "0")}` : `${seconds}s`;
}

function formatTime(value: number) {
  const rounded = Math.max(0, Math.round(value));
  return `${Math.floor(rounded / 60)}:${String(rounded % 60).padStart(2, "0")}`;
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat(undefined, { day: "numeric", month: "short", year: "numeric" }).format(new Date(value));
}

function mediaKind(asset: ManagedLibraryAsset): Exclude<MediaKind, "all"> {
  if (asset.mime_type.startsWith("image/")) return "image";
  if (asset.mime_type.startsWith("audio/")) return "audio";
  return "video";
}

function MediaIcon({ kind }: { readonly kind: Exclude<MediaKind, "all"> }) {
  if (kind === "image") return <ImageIcon aria-hidden="true" className="size-6" />;
  if (kind === "audio") return <AudioLinesIcon aria-hidden="true" className="size-6" />;
  return <VideoIcon aria-hidden="true" className="size-6" />;
}

function Metric({ icon, label, note, value, highlighted = false }: {
  readonly icon: ReactNode;
  readonly label: string;
  readonly note: string;
  readonly value: string;
  readonly highlighted?: boolean;
}) {
  return (
    <article className={`rounded-md border p-4 ${highlighted ? "border-[#AFC7D5] bg-[#EFF6FA]" : "border-[#D7D9D3] bg-white"}`}>
      <div className="flex items-center justify-between gap-3"><p className="font-mono text-[9px] font-bold tracking-wide text-[#666862] uppercase">{label}</p><span className="text-[#174D73]">{icon}</span></div>
      <p className="mt-3 text-2xl font-bold tracking-tight text-[#173F5F]">{value}</p>
      <p className="mt-1 text-xs text-[#666862]">{note}</p>
    </article>
  );
}

function AssetCard({ asset, evidence, selected, onSelect }: {
  readonly asset: ManagedLibraryAsset;
  readonly evidence?: CatalogSearchResult;
  readonly selected: boolean;
  readonly onSelect: () => void;
}) {
  const kind = mediaKind(asset);
  return (
    <button
      aria-pressed={selected}
      className={`grid w-full grid-cols-[5.5rem_minmax(0,1fr)] gap-3 rounded-md border bg-white p-3 text-left transition-colors sm:grid-cols-[7.5rem_minmax(0,1fr)_auto] ${selected ? "border-[#174D73] ring-1 ring-[#174D73]" : "border-[#D7D9D3] hover:border-[#AFC7D5] hover:bg-[#FAFAF8]"}`}
      onClick={onSelect}
      type="button"
    >
      <span className="flex h-20 items-center justify-center overflow-hidden rounded-sm bg-[#E4EBEF] text-[#174D73] sm:h-24">
        {asset.thumbnail_available ? <img alt="" className="h-full w-full object-cover" loading="lazy" src={libraryAssetThumbnailUrl(asset.id)} /> : <MediaIcon kind={kind} />}
      </span>
      <span className="min-w-0 py-0.5">
        <span className="flex flex-wrap items-center gap-2"><strong className="truncate text-sm text-[#173F5F] sm:text-base">{asset.display_name}</strong>{asset.favorite ? <HeartIcon aria-label="Favorite" className="size-3.5 fill-[#174D73] text-[#174D73]" /> : null}</span>
        <span className="mt-1 block truncate text-xs text-[#666862]">{asset.source_name} · {asset.project_name}</span>
        {evidence ? <span className="mt-2 line-clamp-2 block text-xs leading-5 text-[#20211F]"><span className="font-bold text-[#174D73]">{evidence.segment_kind === "visual" ? "Visual match" : evidence.segment_kind === "transcript" ? "Spoken match" : "Match"}:</span> {evidence.text || `seen at ${formatTime(evidence.start_seconds)}–${formatTime(evidence.end_seconds)}`}</span> : asset.notes ? <span className="mt-2 line-clamp-2 block text-xs leading-5 text-[#666862]">{asset.notes}</span> : null}
        <span className="mt-2 flex flex-wrap gap-1.5">{asset.tags.slice(0, 4).map((tag) => <span className="rounded-full bg-[#EFF6FA] px-2 py-1 font-mono text-[9px] font-bold text-[#174D73]" key={tag}>{tag}</span>)}</span>
      </span>
      <span className="col-span-2 flex items-end justify-between gap-4 border-t border-[#E7E8E4] pt-2 font-mono text-[9px] text-[#666862] sm:col-span-1 sm:flex-col sm:border-0 sm:pt-1 sm:text-right">
        <span className={`rounded-full px-2 py-1 font-bold ${asset.library_status === "active" ? "bg-[#E4F1E9] text-[#307455]" : "bg-[#F0F0EC] text-[#666862]"}`}>{asset.library_status.toUpperCase()}</span>
        <span>{formatDuration(asset.duration_seconds)} · {formatBytes(asset.byte_size)}</span>
      </span>
    </button>
  );
}

function AssetPreview({ detail }: { readonly detail: LibraryAssetDetail }) {
  const { asset } = detail;
  const source = libraryAssetPreviewUrl(asset.id);
  if (asset.mime_type.startsWith("image/")) return <img alt={asset.display_name} className="max-h-[28rem] w-full bg-[#E4EBEF] object-contain" src={source} />;
  if (asset.mime_type.startsWith("audio/")) return <div className="flex min-h-40 items-center bg-[#E4EBEF] p-5"><audio className="w-full" controls preload="metadata" src={source} /></div>;
  return <video className="aspect-video w-full bg-[#173F5F] object-contain" controls playsInline preload="metadata" src={source} />;
}

function AssetInspector({ assetId, allCollections, onClose, onChanged, onCollectionsChanged }: {
  readonly assetId: string;
  readonly allCollections: readonly LibraryCollection[];
  readonly onClose: () => void;
  readonly onChanged: () => Promise<void>;
  readonly onCollectionsChanged: () => Promise<void>;
}) {
  const [detail, setDetail] = useState<LibraryAssetDetail>();
  const [error, setError] = useState<string>();
  const [saving, setSaving] = useState(false);
  const [displayName, setDisplayName] = useState("");
  const [notes, setNotes] = useState("");
  const [tags, setTags] = useState("");
  const [favorite, setFavorite] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setDetail(undefined);
    setError(undefined);
    void getLibraryAssetDetail(assetId).then((result) => {
      if (cancelled) return;
      setDetail(result);
      setDisplayName(result.asset.display_name);
      setNotes(result.asset.notes);
      setTags(result.asset.tags.join(", "));
      setFavorite(result.asset.favorite);
    }).catch((requestError: unknown) => {
      if (!cancelled) setError(requestError instanceof Error ? requestError.message : "This original could not be loaded");
    });
    return () => { cancelled = true; };
  }, [assetId]);

  async function save() {
    if (!detail) return;
    setSaving(true);
    setError(undefined);
    try {
      await updateLibraryAsset(detail.asset.id, {
        displayName,
        notes,
        favorite,
        tags: tags.split(",").map((tag) => tag.trim()).filter(Boolean),
      });
      setDetail(await getLibraryAssetDetail(detail.asset.id));
      await onChanged();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Library details could not be saved");
    } finally {
      setSaving(false);
    }
  }

  async function changeState() {
    if (!detail) return;
    setSaving(true);
    setError(undefined);
    try {
      await setLibraryAssetState(detail.asset.id, detail.asset.library_status === "active" ? "archived" : "active");
      await onChanged();
      onClose();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "The library state could not be changed");
      setSaving(false);
    }
  }

  async function toggleCollection(collection: LibraryCollection, selected: boolean) {
    if (!detail) return;
    setSaving(true);
    setError(undefined);
    try {
      await setLibraryCollectionMembership(collection.id, detail.asset.id, selected);
      setDetail(await getLibraryAssetDetail(detail.asset.id));
      await onCollectionsChanged();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Collection membership could not be changed");
    } finally {
      setSaving(false);
    }
  }

  return (
    <aside aria-label="Selected original details" className="overflow-hidden rounded-md border border-[#AFC7D5] bg-white lg:sticky lg:top-4 lg:h-fit">
      <div className="flex items-start justify-between gap-4 border-b border-[#D7D9D3] p-4"><div><p className="font-mono text-[9px] font-bold tracking-widest text-[#174D73] uppercase">Selected original</p><h2 className="mt-1 text-lg font-bold text-[#173F5F]">{detail?.asset.display_name ?? "Loading original…"}</h2></div><button aria-label="Close details" className="rounded-md p-2 text-[#666862] hover:bg-[#F0F0EC]" onClick={onClose} type="button"><XIcon className="size-4" /></button></div>
      {!detail && !error ? <div className="flex min-h-80 items-center justify-center"><LoaderCircleIcon aria-label="Loading selected original" className="size-7 animate-spin text-[#173F5F]" /></div> : null}
      {error ? <p className="m-4 rounded-md border border-[#D8B4AA] bg-[#FFF7F4] p-3 text-sm text-[#A23B2A]" role="alert">{error}</p> : null}
      {detail ? <>
        <AssetPreview detail={detail} />
        <div className="space-y-5 p-4">
          <section><div className="flex items-center justify-between gap-3"><p className="font-mono text-[9px] font-bold tracking-wider text-[#666862] uppercase">Representative scenes</p><span className="font-mono text-[9px] text-[#666862]">LOCAL INDEX</span></div>{detail.visual_frames.length ? <div className="mt-2 grid grid-cols-4 gap-2">{detail.visual_frames.slice(0, 8).map((frame) => <figure key={frame.id}><img alt={`Frame at ${formatTime(frame.frame_seconds)}`} className="aspect-video w-full rounded-sm bg-[#E4EBEF] object-cover" loading="lazy" src={visualIndexFrameUrl(frame.id)} /><figcaption className="mt-1 font-mono text-[8px] text-[#666862]">{formatTime(frame.frame_seconds)}</figcaption></figure>)}</div> : <p className="mt-2 text-xs leading-5 text-[#666862]">No visual frames are indexed for this original yet.</p>}</section>
          <section><p className="font-mono text-[9px] font-bold tracking-wider text-[#666862] uppercase">Speech and scene evidence</p>{detail.evidence.length ? <div className="mt-2 max-h-56 space-y-2 overflow-y-auto overscroll-contain pr-1">{detail.evidence.slice(0, 30).map((segment) => <article className="rounded-md border border-[#E7E8E4] bg-[#FAFAF8] p-3" key={segment.id}><p className="text-xs leading-5 text-[#20211F]">{segment.text}</p><p className="mt-1 font-mono text-[8px] font-bold text-[#666862]">{segment.segment_kind.toUpperCase()} · {formatTime(segment.start_seconds)}–{formatTime(segment.end_seconds)}</p></article>)}</div> : <p className="mt-2 text-xs leading-5 text-[#666862]">No transcript or scene descriptions are available yet.</p>}</section>
          <section className="space-y-3"><p className="font-mono text-[9px] font-bold tracking-wider text-[#666862] uppercase">Library details</p><label className="block text-xs font-bold text-[#666862]">Display name<input className="mt-1 h-11 w-full rounded-md border border-[#D7D9D3] px-3 text-sm text-[#20211F] outline-none focus:border-[#173F5F]" maxLength={255} onChange={(event) => setDisplayName(event.currentTarget.value)} value={displayName} /></label><label className="block text-xs font-bold text-[#666862]">Notes<textarea className="mt-1 min-h-24 w-full resize-y rounded-md border border-[#D7D9D3] p-3 text-sm text-[#20211F] outline-none focus:border-[#173F5F]" maxLength={4000} onChange={(event) => setNotes(event.currentTarget.value)} value={notes} /></label><label className="block text-xs font-bold text-[#666862]">Tags <span className="font-normal">· comma separated</span><input className="mt-1 h-11 w-full rounded-md border border-[#D7D9D3] px-3 text-sm text-[#20211F] outline-none focus:border-[#173F5F]" onChange={(event) => setTags(event.currentTarget.value)} placeholder="aviation, travel, b-roll" value={tags} /></label><label className="flex min-h-11 items-center gap-3 rounded-md border border-[#D7D9D3] px-3 text-sm font-bold text-[#173F5F]"><input checked={favorite} className="size-4 accent-[#173F5F]" onChange={(event) => setFavorite(event.currentTarget.checked)} type="checkbox" /><HeartIcon className="size-4" />Favorite source</label></section>
          <section><p className="font-mono text-[9px] font-bold tracking-wider text-[#666862] uppercase">Collections</p>{allCollections.length ? <div className="mt-2 space-y-2">{allCollections.map((collection) => { const selected = detail.collections.some((item) => item.id === collection.id); return <label className="flex min-h-11 items-center justify-between gap-3 rounded-md border border-[#D7D9D3] bg-[#FAFAF8] px-3 text-sm" key={collection.id}><span className="font-medium">{collection.name}</span><input checked={selected} className="size-4 accent-[#173F5F]" disabled={saving} onChange={(event) => void toggleCollection(collection, event.currentTarget.checked)} type="checkbox" /></label>; })}</div> : <p className="mt-2 text-xs leading-5 text-[#666862]">Create a collection above to group reusable sources without copying them.</p>}</section>
          <div className="flex flex-col gap-2 sm:flex-row"><button className="inline-flex min-h-11 flex-1 items-center justify-center gap-2 rounded-md bg-[#173F5F] px-4 text-sm font-bold text-white disabled:opacity-60" disabled={saving || !displayName.trim()} onClick={() => void save()} type="button">{saving ? <LoaderCircleIcon className="size-4 animate-spin" /> : <CheckIcon className="size-4" />}Save details</button><button className="inline-flex min-h-11 items-center justify-center gap-2 rounded-md border border-[#D7D9D3] px-4 text-sm font-bold text-[#A23B2A] disabled:opacity-60" disabled={saving} onClick={() => void changeState()} type="button">{detail.asset.library_status === "active" ? <ArchiveIcon className="size-4" /> : <RotateCcwIcon className="size-4" />}{detail.asset.library_status === "active" ? "Archive" : "Restore"}</button></div>
          <aside className="rounded-md border border-dashed border-[#C7CBD0] bg-[#F7F7F5] p-3"><p className="flex items-center gap-2 text-xs font-bold text-[#666862]"><LockKeyholeIcon className="size-3.5" />Permanent cleanup locked</p><p className="mt-1 text-[11px] leading-5 text-[#777A75]">It unlocks only after the USB backup passes a verified restore drill. Archive is reversible and never deletes this original.</p></aside>
        </div>
      </> : null}
    </aside>
  );
}

export function MediaLibrary() {
  const [query, setQuery] = useState("");
  const [state, setState] = useState<LibraryState>("active");
  const [kind, setKind] = useState<MediaKind>("all");
  const [favoritesOnly, setFavoritesOnly] = useState(false);
  const [assets, setAssets] = useState<readonly ManagedLibraryAsset[]>([]);
  const [allAssets, setAllAssets] = useState<readonly ManagedLibraryAsset[]>([]);
  const [evidence, setEvidence] = useState<ReadonlyMap<string, CatalogSearchResult>>(new Map());
  const [selectedId, setSelectedId] = useState<string>();
  const [collections, setCollections] = useState<readonly LibraryCollection[]>([]);
  const [collectionName, setCollectionName] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>();

  async function refreshSummary() {
    const [libraryAssets, libraryCollections] = await Promise.all([getManagedLibraryAssets({ state: "all" }), getLibraryCollections()]);
    setAllAssets(libraryAssets);
    setCollections(libraryCollections);
  }

  useEffect(() => { void refreshSummary().catch((requestError: unknown) => setError(requestError instanceof Error ? requestError.message : "Library summary is unavailable")); }, []);

  useEffect(() => {
    let cancelled = false;
    const timer = window.setTimeout(() => {
      setLoading(true);
      setError(undefined);
      const normalized = query.trim();
      const filters = { state, mediaKind: kind, favorite: favoritesOnly ? true : undefined } as const;
      const request = normalized
        ? Promise.all([getManagedLibraryAssets(filters), getManagedLibraryAssets({ ...filters, query: normalized }), searchCatalog({ query: normalized, mediaKind: kind, limit: 100 })]).then(([candidates, metadataMatches, catalog]) => {
            const catalogEvidence = new Map<string, CatalogSearchResult>();
            for (const result of catalog.results) if (!catalogEvidence.has(result.asset_id)) catalogEvidence.set(result.asset_id, result);
            const metadataIds = new Set(metadataMatches.map((asset) => asset.id));
            const rank = new Map(catalog.results.map((result) => [result.asset_id, result.rank]));
            return {
              evidence: catalogEvidence,
              assets: candidates.filter((asset) => metadataIds.has(asset.id) || catalogEvidence.has(asset.id)).sort((left, right) => (rank.get(right.id) ?? 0) - (rank.get(left.id) ?? 0)),
            };
          })
        : getManagedLibraryAssets(filters).then((results) => ({ assets: results, evidence: new Map<string, CatalogSearchResult>() }));
      void request.then((result) => {
        if (cancelled) return;
        setAssets(result.assets);
        setEvidence(result.evidence);
        setLoading(false);
      }).catch((requestError: unknown) => {
        if (cancelled) return;
        setError(requestError instanceof Error ? requestError.message : "Library search is unavailable");
        setLoading(false);
      });
    }, 220);
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [favoritesOnly, kind, query, state]);

  const summary = useMemo(() => ({
    active: allAssets.filter((asset) => asset.library_status === "active").length,
    archived: allAssets.filter((asset) => asset.library_status === "archived").length,
    favorites: allAssets.filter((asset) => asset.favorite).length,
    bytes: allAssets.reduce((total, asset) => total + asset.byte_size, 0),
  }), [allAssets]);

  async function refreshVisible() {
    await refreshSummary();
    const refreshed = await getManagedLibraryAssets({ state, mediaKind: kind, favorite: favoritesOnly ? true : undefined });
    if (!query.trim()) setAssets(refreshed);
    else setAssets((current) => current.map((asset) => refreshed.find((candidate) => candidate.id === asset.id) ?? asset));
  }

  async function addCollection() {
    const normalized = collectionName.trim();
    if (!normalized) return;
    setError(undefined);
    try {
      await createLibraryCollection(normalized);
      setCollectionName("");
      await refreshSummary();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Collection could not be created");
    }
  }

  return (
    <main className="min-h-dvh bg-[#F7F7F5] px-4 pt-[max(1.25rem,env(safe-area-inset-top))] pb-[max(2rem,env(safe-area-inset-bottom))] text-[#20211F] [color-scheme:light] sm:px-6">
      <div className="mx-auto w-full max-w-[1480px]">
        <header className="border-b border-[#D7D9D3] pb-5">
          <div className="flex flex-wrap items-center justify-between gap-4"><div className="flex flex-wrap items-center gap-x-5 gap-y-2"><Link className="text-sm font-bold tracking-tight text-[#173F5F]" href="/jobs/new">GM Studio</Link><nav className="flex flex-wrap gap-4 text-xs font-bold text-[#666862]"><Link href="/jobs/new">New job</Link><Link href="/library/duplicates">Duplicate audit</Link><Link href="/usage">AI usage</Link><Link href="/system">System</Link></nav></div><span className="inline-flex items-center gap-1.5 rounded-full border border-[#D7D9D3] bg-white px-3 py-2 font-mono text-[10px] font-bold text-[#173F5F]"><span className="size-1.5 rounded-full bg-[#3A8F63]" />PRIVATE · ONLINE</span></div>
          <div className="mt-6 flex flex-col justify-between gap-5 lg:flex-row lg:items-end"><div className="max-w-3xl"><p className="font-mono text-[10px] font-bold tracking-widest text-[#174D73] uppercase">Content memory</p><h1 className="mt-2 text-3xl font-bold tracking-tight text-[#173F5F]">Media library</h1><p className="mt-3 max-w-2xl text-sm leading-6 text-[#666862]">Search spoken words and visual scenes, organize useful originals, and keep every source private on this server.</p></div><Link className="inline-flex min-h-11 items-center justify-center gap-2 rounded-md bg-[#173F5F] px-5 text-sm font-bold text-white" href="/jobs/new"><FilmIcon className="size-4" />Start a new job</Link></div>
        </header>

        <LibraryUpload onReady={refreshVisible} />

        <section aria-label="Library summary" className="mt-6 grid grid-cols-2 gap-3 lg:grid-cols-4"><Metric icon={<LibraryIcon className="size-4" />} label="Active originals" note="Ready for editing" value={summary.active.toLocaleString()} /><Metric icon={<ArchiveIcon className="size-4" />} label="Archived" note="Hidden, never deleted" value={summary.archived.toLocaleString()} /><Metric icon={<HeartIcon className="size-4" />} label="Favorites" note="Pinned source media" value={summary.favorites.toLocaleString()} /><Metric highlighted icon={<HardDriveIcon className="size-4" />} label="Library size" note="Originals on Lenovo" value={formatBytes(summary.bytes)} /></section>

        <section aria-label="Library search and filters" className="mt-4 rounded-md border border-[#D7D9D3] bg-white p-4">
          <div className="grid gap-3 lg:grid-cols-[minmax(320px,1fr)_auto_auto_auto]"><label className="relative"><span className="sr-only">Search the media library</span><SearchIcon className="pointer-events-none absolute top-1/2 left-4 size-4 -translate-y-1/2 text-[#666862]" /><input className="h-12 w-full rounded-md border border-[#D7D9D3] bg-[#F7F7F5] pr-10 pl-11 text-sm outline-none placeholder:text-[#777A75] focus:border-[#173F5F]" onChange={(event) => setQuery(event.currentTarget.value)} placeholder="Search speech, scenes, filenames, tags or notes" type="search" value={query} />{query ? <button aria-label="Clear search" className="absolute top-1/2 right-3 -translate-y-1/2 p-1 text-[#666862]" onClick={() => setQuery("")} type="button"><XIcon className="size-4" /></button> : null}</label><select aria-label="Media type" className="h-12 rounded-md border border-[#D7D9D3] bg-white px-4 text-sm font-bold" onChange={(event) => setKind(event.currentTarget.value as MediaKind)} value={kind}><option value="all">All media</option><option value="video">Video</option><option value="image">Photos</option><option value="audio">Audio</option></select><select aria-label="Library state" className="h-12 rounded-md border border-[#D7D9D3] bg-white px-4 text-sm font-bold" onChange={(event) => setState(event.currentTarget.value as LibraryState)} value={state}><option value="active">Active</option><option value="archived">Archived</option><option value="all">All states</option></select><button aria-pressed={favoritesOnly} className={`inline-flex h-12 items-center justify-center gap-2 rounded-md border px-4 text-sm font-bold ${favoritesOnly ? "border-[#AFC7D5] bg-[#EFF6FA] text-[#174D73]" : "border-[#D7D9D3] bg-white text-[#666862]"}`} onClick={() => setFavoritesOnly((current) => !current)} type="button"><HeartIcon className={`size-4 ${favoritesOnly ? "fill-[#174D73]" : ""}`} />Favorites</button></div>
          <div className="mt-3 flex flex-col justify-between gap-3 border-t border-[#E7E8E4] pt-3 sm:flex-row sm:items-center"><p className="text-xs text-[#666862]">{query.trim() ? <><strong className="text-[#173F5F]">{assets.length} source matches</strong> · speech and visual evidence ranked together</> : <><strong className="text-[#173F5F]">{assets.length} originals</strong> in this view</>}</p><div className="flex flex-col gap-2 sm:flex-row"><label className="flex min-h-10 items-center gap-2 rounded-md border border-[#D7D9D3] bg-[#FAFAF8] px-3"><FolderPlusIcon className="size-4 text-[#174D73]" /><input aria-label="New collection name" className="min-w-0 bg-transparent text-xs outline-none" maxLength={120} onChange={(event) => setCollectionName(event.currentTarget.value)} onKeyDown={(event) => { if (event.key === "Enter") void addCollection(); }} placeholder="New collection" value={collectionName} /></label><button className="min-h-10 rounded-md border border-[#AFC7D5] px-3 text-xs font-bold text-[#174D73] disabled:opacity-50" disabled={!collectionName.trim()} onClick={() => void addCollection()} type="button">Create collection</button></div></div>
        </section>

        {error ? <p className="mt-4 rounded-md border border-[#D8B4AA] bg-[#FFF7F4] p-4 text-sm text-[#A23B2A]" role="alert">{error}</p> : null}
        <div className={`mt-4 grid gap-4 ${selectedId ? "lg:grid-cols-[minmax(0,1.5fr)_minmax(360px,0.8fr)]" : ""}`}>
          <section aria-label="Media originals" className="min-w-0 space-y-3">
            {loading ? <div className="flex min-h-72 items-center justify-center"><LoaderCircleIcon aria-label="Searching media library" className="size-8 animate-spin text-[#173F5F]" /></div> : null}
            {!loading && assets.length ? assets.map((asset) => <AssetCard asset={asset} evidence={evidence.get(asset.id)} key={asset.id} onSelect={() => setSelectedId(asset.id)} selected={selectedId === asset.id} />) : null}
            {!loading && !assets.length ? <div className="rounded-md border border-dashed border-[#C7CBD0] bg-white p-8 text-center"><SparklesIcon className="mx-auto size-7 text-[#174D73]" /><h2 className="mt-3 text-base font-bold text-[#173F5F]">No originals match this view</h2><p className="mx-auto mt-2 max-w-lg text-sm leading-6 text-[#666862]">Try a broader phrase, another media type, or include archived sources. Visual search improves as the local index finishes scanning representative frames.</p></div> : null}
          </section>
          {selectedId ? <AssetInspector allCollections={collections} assetId={selectedId} onChanged={refreshVisible} onClose={() => setSelectedId(undefined)} onCollectionsChanged={refreshSummary} /> : null}
        </div>
        <footer className="mt-6 flex flex-col items-center justify-between gap-4 border-t border-[#D7D9D3] pt-5 text-sm sm:flex-row"><p className="flex items-center gap-2 font-mono text-[10px] text-[#666862]"><TagIcon className="size-3.5" />SOURCE-ONLY · LOCALLY INDEXED</p><div className="flex gap-5"><Link className="font-bold text-[#173F5F] underline underline-offset-4" href="/library/duplicates">Duplicate audit</Link><Link className="font-bold text-[#173F5F] underline underline-offset-4" href="/jobs/new">Start a new job</Link></div></footer>
      </div>
    </main>
  );
}
