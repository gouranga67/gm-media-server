"use client";

import Link from "next/link";
import { LibraryUpload } from "@/app/_components/library-upload";
import { useEffect, useMemo, useState } from "react";
import {
  ArchiveIcon, AudioLinesIcon, CheckIcon, FilmIcon, HeartIcon, ImageIcon,
  LoaderCircleIcon, RotateCcwIcon, SearchIcon, SparklesIcon, VideoIcon, XIcon,
  PlusIcon, PencilIcon, ChevronDownIcon,
} from "lucide-react";
import {
  createLibraryCollection, getLibraryAssetDetail, getLibraryCollections,
  getAllManagedLibraryAssets, libraryAssetPreviewUrl, libraryAssetThumbnailUrl,
  searchCatalog, setLibraryAssetState, setLibraryCollectionMembership,
  updateLibraryAsset, updateLibraryBatch, visualIndexFrameUrl,
  type CatalogSearchResult, type LibraryAssetDetail, type LibraryCollection,
  type ManagedLibraryAsset, type MediaRole,
} from "@/lib/media-api";
import { libraryRoleLabel, libraryViews, matchesLibraryView, type LibraryView } from "@/lib/library-organization";

type MediaKind = "all" | "video" | "image" | "audio";

const control = "min-h-11 rounded-md border border-[#D7D9D3] bg-white px-3 text-sm font-medium text-[#173F5F] disabled:opacity-50";

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

function AssetRow({ asset, evidence, checked, focused, disabled, onCheck, onOpen, onRename }: {
  readonly asset: ManagedLibraryAsset;
  readonly evidence?: CatalogSearchResult;
  readonly checked: boolean;
  readonly focused: boolean;
  readonly disabled: boolean;
  readonly onCheck: () => void;
  readonly onOpen: () => void;
  readonly onRename: () => void;
}) {
  return (
    <article className={`flex items-center gap-3 border-b border-[#E7E8E4] p-3 last:border-b-0 ${checked || focused ? "bg-[#EFF6FA]" : "bg-white"}`}>
      <label className="flex min-h-11 min-w-11 items-center justify-center">
        <input aria-label={`Select ${asset.display_name}`} checked={checked} className="size-4 accent-[#173F5F]" disabled={disabled} onChange={onCheck} type="checkbox" />
      </label>
      <button aria-label={`Details for ${asset.display_name}`} aria-pressed={focused} className="flex min-w-0 flex-1 items-center gap-3 text-left" onClick={onOpen} type="button">
        <span className="flex size-16 shrink-0 items-center justify-center overflow-hidden rounded bg-[#E4EBEF] text-[#173F5F]">
          {asset.thumbnail_available ? <img alt="" className="size-full object-cover" loading="lazy" src={libraryAssetThumbnailUrl(asset.id)} /> : <MediaIcon kind={mediaKind(asset)} />}
        </span>
        <span className="min-w-0 flex-1">
          <strong className="block truncate text-sm text-[#173F5F]">{asset.display_name}{asset.favorite ? " ♥" : ""}</strong>
          <span className="mt-0.5 block truncate text-xs text-[#666862]">{asset.source_name} · {asset.project_name}</span>
          <span className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs text-[#666862]"><span className="font-medium text-[#173F5F]">{libraryRoleLabel(asset)}</span><span>{formatDuration(asset.duration_seconds)} · {formatBytes(asset.byte_size)}</span><span>{asset.job_references ? `Used in ${asset.job_references} ${asset.job_references === 1 ? "job" : "jobs"}` : "Not used in a job"}</span></span>
          {evidence ? <span className="mt-1 line-clamp-2 block text-xs text-[#173F5F]">{evidence.segment_kind === "transcript" ? "Speech" : "Scene"} · {evidence.text || `${formatTime(evidence.start_seconds)}–${formatTime(evidence.end_seconds)}`}</span> : null}
        </span>
      </button>
      <button aria-label={`Rename ${asset.display_name}`} className="flex min-h-11 min-w-11 items-center justify-center text-[#173F5F] disabled:opacity-50" disabled={disabled} onClick={onRename} type="button"><PencilIcon aria-hidden="true" className="size-4" /></button>
    </article>
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
  const [mediaRole, setMediaRole] = useState<MediaRole>("auto");

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
      setMediaRole(result.asset.media_role ?? "auto");
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
        mediaRole,
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
          <section className="space-y-3">{detail.asset.mime_type.startsWith("video/") ? <label className="block text-xs font-bold text-[#666862]">Use this footage as<select aria-label="Footage role" className={`${control} mt-1 w-full`} value={mediaRole} onChange={(event) => setMediaRole(event.currentTarget.value as MediaRole)}><option value="auto">Unsorted</option><option value="talking">Talking footage</option><option value="broll">B-roll</option></select></label> : null}<p className="font-mono text-[9px] font-bold tracking-wider text-[#666862] uppercase">Library details</p><label className="block text-xs font-bold text-[#666862]">Display name<input className="mt-1 h-11 w-full rounded-md border border-[#D7D9D3] px-3 text-sm text-[#20211F] outline-none focus:border-[#173F5F]" maxLength={255} onChange={(event) => setDisplayName(event.currentTarget.value)} value={displayName} /></label><label className="block text-xs font-bold text-[#666862]">Notes<textarea className="mt-1 min-h-24 w-full resize-y rounded-md border border-[#D7D9D3] p-3 text-sm text-[#20211F] outline-none focus:border-[#173F5F]" maxLength={4000} onChange={(event) => setNotes(event.currentTarget.value)} value={notes} /></label><label className="block text-xs font-bold text-[#666862]">Tags <span className="font-normal">· comma separated</span><input className="mt-1 h-11 w-full rounded-md border border-[#D7D9D3] px-3 text-sm text-[#20211F] outline-none focus:border-[#173F5F]" onChange={(event) => setTags(event.currentTarget.value)} placeholder="aviation, travel, b-roll" value={tags} /></label><label className="flex min-h-11 items-center gap-3 rounded-md border border-[#D7D9D3] px-3 text-sm font-bold text-[#173F5F]"><input checked={favorite} className="size-4 accent-[#173F5F]" onChange={(event) => setFavorite(event.currentTarget.checked)} type="checkbox" /><HeartIcon className="size-4" />Favorite source</label></section>
          <section><p className="font-mono text-[9px] font-bold tracking-wider text-[#666862] uppercase">Collections</p>{allCollections.length ? <div className="mt-2 space-y-2">{allCollections.map((collection) => { const selected = detail.collections.some((item) => item.id === collection.id); return <label className="flex min-h-11 items-center justify-between gap-3 rounded-md border border-[#D7D9D3] bg-[#FAFAF8] px-3 text-sm" key={collection.id}><span className="font-medium">{collection.name}</span><input checked={selected} className="size-4 accent-[#173F5F]" disabled={saving} onChange={(event) => void toggleCollection(collection, event.currentTarget.checked)} type="checkbox" /></label>; })}</div> : <p className="mt-2 text-xs leading-5 text-[#666862]">Create a collection above to group reusable sources without copying them.</p>}</section>
          <div className="flex flex-col gap-2 sm:flex-row"><button className="inline-flex min-h-11 flex-1 items-center justify-center gap-2 rounded-md bg-[#173F5F] px-4 text-sm font-bold text-white disabled:opacity-60" disabled={saving || !displayName.trim()} onClick={() => void save()} type="button">{saving ? <LoaderCircleIcon className="size-4 animate-spin" /> : <CheckIcon className="size-4" />}Save details</button><button className="inline-flex min-h-11 items-center justify-center gap-2 rounded-md border border-[#D7D9D3] px-4 text-sm font-bold text-[#A23B2A] disabled:opacity-60" disabled={saving} onClick={() => void changeState()} type="button">{detail.asset.library_status === "active" ? <ArchiveIcon className="size-4" /> : <RotateCcwIcon className="size-4" />}{detail.asset.library_status === "active" ? "Move to Trash" : "Restore"}</button></div>
          <p className="text-xs leading-5 text-[#666862]">Trash hides an original from new jobs. You can restore it here. Existing edits keep working; the original stays on disk.</p>
        </div>
      </> : null}
    </aside>
  );
}

export function MediaLibrary() {
  const [query, setQuery] = useState("");
  const [view, setView] = useState<LibraryView>("all");
  const [favoritesOnly, setFavoritesOnly] = useState(false);
  const [showCopies, setShowCopies] = useState(false);
  const [sort, setSort] = useState("newest");
  const [assets, setAssets] = useState<readonly ManagedLibraryAsset[]>([]);
  const [evidence, setEvidence] = useState<ReadonlyMap<string, CatalogSearchResult>>(new Map());
  const [selectedId, setSelectedId] = useState<string>();
  const [checked, setChecked] = useState<ReadonlySet<string>>(new Set());
  const [collections, setCollections] = useState<readonly LibraryCollection[]>([]);
  const [collectionId, setCollectionId] = useState("");
  const [collectionAssets, setCollectionAssets] = useState<ReadonlySet<string>>();
  const [collectionName, setCollectionName] = useState("");
  const [rename, setRename] = useState<string>();
  const [pendingTrash, setPendingTrash] = useState(false);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [searching, setSearching] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const [notice, setNotice] = useState<string>();
  const [revision, setRevision] = useState(0);
  const [pageSize, setPageSize] = useState(60);

  async function refresh() {
    const [nextAssets, nextCollections] = await Promise.all([getAllManagedLibraryAssets(), getLibraryCollections()]);
    setAssets(nextAssets);
    setCollections(nextCollections);
    setRevision((current) => current + 1);
  }
  useEffect(() => {
    let cancelled = false;
    void Promise.all([getAllManagedLibraryAssets(), getLibraryCollections()]).then(([nextAssets, nextCollections]) => {
      if (!cancelled) { setAssets(nextAssets); setCollections(nextCollections); setLoading(false); }
    }).catch((requestError: unknown) => { if (!cancelled) { setError(String(requestError instanceof Error ? requestError.message : requestError)); setLoading(false); } });
    return () => { cancelled = true; };
  }, []);
  useEffect(() => {
    let cancelled = false;
    setEvidence(new Map());
    if (!query.trim()) { setSearching(false); return; }
    setSearching(true);
    const timer = window.setTimeout(() => {
      void searchCatalog({ query: query.trim(), mediaKind: "all", limit: 100 }).then((catalog) => {
        if (cancelled) return;
        const matches = new Map<string, CatalogSearchResult>();
        for (const match of catalog.results) if (!matches.has(match.asset_id)) matches.set(match.asset_id, match);
        setEvidence(matches); setSearching(false);
      }).catch((requestError: unknown) => { if (!cancelled) { setSearching(false); setError(requestError instanceof Error ? requestError.message : "Speech and scene search is unavailable; name search still works."); } });
    }, 220);
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [query, revision]);
  useEffect(() => {
    let cancelled = false;
    setCollectionAssets(undefined);
    if (collectionId) void getAllManagedLibraryAssets(collectionId).then((items) => {
      if (!cancelled) setCollectionAssets(new Set(items.map((item) => item.id)));
    }).catch((requestError: unknown) => { if (!cancelled) setError(requestError instanceof Error ? requestError.message : "Collection unavailable"); });
    return () => { cancelled = true; };
  }, [collectionId, revision]);

  const normalizedQuery = query.trim().toLocaleLowerCase();
  const visible = useMemo(() => {
    const candidates = assets.filter((asset) => matchesLibraryView(asset, view)
      && (!favoritesOnly || asset.favorite)
      && (!collectionId || collectionAssets?.has(asset.id))
      && (!normalizedQuery || [asset.display_name, asset.source_name, asset.project_name, asset.notes, ...asset.tags].some((value) => value.toLocaleLowerCase().includes(normalizedQuery)) || evidence.has(asset.id)));
    const candidateIds = new Set(candidates.map((asset) => asset.id));
    return candidates.filter((asset) => showCopies || view === "trash" || !asset.canonical_asset_id || asset.canonical_asset_id === asset.id || !candidateIds.has(asset.canonical_asset_id))
      .sort((left, right) => {
        if (sort === "name") return left.display_name.localeCompare(right.display_name) || left.id.localeCompare(right.id);
        if (sort === "largest") return right.byte_size - left.byte_size || left.id.localeCompare(right.id);
        if (normalizedQuery) {
          const rank = (evidence.get(right.id)?.rank ?? 0) - (evidence.get(left.id)?.rank ?? 0);
          if (rank) return rank;
        }
        return Date.parse(right.created_at) - Date.parse(left.created_at) || left.id.localeCompare(right.id);
      });
  }, [assets, view, favoritesOnly, collectionId, collectionAssets, normalizedQuery, evidence, showCopies, sort]);
  // Only displayed selections can be acted on: hidden search results never get moved accidentally.
  const selected = visible.filter((asset) => checked.has(asset.id));
  const selectedIds = selected.map((asset) => asset.id);
  const selectedVideos = selected.length > 0 && selected.every((asset) => asset.mime_type.startsWith("video/"));
  const shown = visible.slice(0, pageSize);
  const allShownSelected = shown.length > 0 && shown.every((asset) => checked.has(asset.id));
  const activeCount = assets.filter((asset) => asset.library_status === "active").length;
  const trashCount = assets.length - activeCount;

  function changeView(next: LibraryView) { setView(next); setChecked(new Set()); setSelectedId(undefined); setRename(undefined); setPendingTrash(false); setPageSize(60); }
  function toggle(id: string) { setChecked((current) => { const next = new Set(current); if (next.has(id)) next.delete(id); else next.add(id); return next; }); setRename(undefined); setPendingTrash(false); }
  async function apply(action: "rename" | "role" | "trash" | "restore", mediaRole?: MediaRole) {
    if (busy || !selected.length || selected.length > 500) return;
    setBusy(true); setError(undefined); setNotice(undefined);
    try {
      await updateLibraryBatch(selectedIds, action, { namePrefix: rename?.trim(), mediaRole });
      setChecked(new Set()); setRename(undefined); setPendingTrash(false); setSelectedId(undefined);
      await refresh();
      setNotice(action === "trash" ? `${selected.length} moved to Trash. Restore them from the Trash view. Originals remain on disk and existing edits keep working.`
        : action === "restore" ? `${selected.length} restored to the library.` : `${selected.length} ${action === "rename" ? "renamed" : "labelled"}.`);
    } catch (requestError) { setError(requestError instanceof Error ? requestError.message : "The change could not be saved. Your selection is unchanged."); }
    finally { setBusy(false); }
  }
  async function addCollection() {
    if (!collectionName.trim() || busy) return;
    setBusy(true); setError(undefined);
    try { await createLibraryCollection(collectionName.trim()); setCollectionName(""); await refresh(); }
    catch (requestError) { setError(requestError instanceof Error ? requestError.message : "Collection could not be created"); }
    finally { setBusy(false); }
  }

  return (
    <main className="min-h-dvh bg-[#F7F7F5] px-3 py-5 text-[#20211F] [color-scheme:light] sm:px-6">
      <div className="mx-auto max-w-[1440px]">
        <header className="border-b border-[#D7D9D3] pb-5">
          <div className="flex flex-wrap items-center gap-x-6 gap-y-3"><Link className="font-bold text-[#173F5F]" href="/jobs/new">GM Studio</Link><nav aria-label="Studio" className="flex flex-wrap gap-4 text-xs font-bold text-[#666862]"><Link href="/jobs">Jobs</Link><Link aria-current="page" className="text-[#173F5F]" href="/library">Library</Link><Link href="/library/duplicates">Duplicate audit</Link><Link href="/system">System</Link></nav></div>
          <div className="mt-7 flex flex-wrap items-center justify-between gap-4">
            <div><h1 className="text-2xl font-bold tracking-tight text-[#173F5F]">Media library</h1><p className="mt-1 text-sm text-[#666862]">{loading ? "Loading your media…" : `${activeCount} active files · ${formatBytes(assets.reduce((total, asset) => total + asset.byte_size, 0))} stored`}</p></div>
            <div className="flex flex-wrap gap-2"><Link className={`${control} inline-flex items-center gap-2`} href="/concepts"><SparklesIcon aria-hidden="true" className="size-4" />Find reel ideas</Link><button aria-controls="library-import" aria-expanded={uploadOpen} className="inline-flex min-h-11 items-center gap-2 rounded-md bg-[#173F5F] px-4 text-sm font-bold text-white" onClick={() => setUploadOpen((current) => !current)} type="button"><PlusIcon aria-hidden="true" className="size-4" />Add media</button><Link className={`${control} inline-flex items-center gap-2`} href="/jobs/new"><FilmIcon aria-hidden="true" className="size-4" />New job</Link></div>
          </div>
        </header>
        {/* Stay mounted when hidden so collapsing the panel does not interrupt transfers. */}
        <div hidden={!uploadOpen} id="library-import"><LibraryUpload onReady={refresh} /></div>
        <nav aria-label="Library views" className="mt-5 flex gap-1 overflow-x-auto border-b border-[#D7D9D3] pb-2">
          {libraryViews.map((item) => <button aria-current={view === item.id ? "page" : undefined} className={`min-h-11 shrink-0 rounded-md px-4 text-sm font-bold ${view === item.id ? "bg-[#173F5F] text-white" : "text-[#666862] hover:bg-white"}`} disabled={busy} key={item.id} onClick={() => changeView(item.id)} type="button">{item.label}{item.id === "trash" && trashCount ? ` (${trashCount})` : ""}</button>)}
        </nav>
        <section aria-label="Search and organize media" className="mt-4 space-y-3">
          <div className="flex flex-wrap gap-2">
            <label className="relative min-w-48 flex-1"><span className="sr-only">Search library</span><SearchIcon aria-hidden="true" className="absolute top-3.5 left-3 size-4 text-[#666862]" /><input className={`${control} w-full pl-10`} disabled={busy} maxLength={160} onChange={(event) => { setQuery(event.currentTarget.value); setError(undefined); setChecked(new Set()); setPageSize(60); setPendingTrash(false); setRename(undefined); }} placeholder="Search names, spoken words or scenes" type="search" value={query} /></label>
            <select aria-label="Filter collection" className={`${control} max-w-full`} disabled={busy} onChange={(event) => { setCollectionId(event.currentTarget.value); setChecked(new Set()); setRename(undefined); setPendingTrash(false); }} value={collectionId}><option value="">All collections</option>{collections.map((collection) => <option key={collection.id} value={collection.id}>{collection.name}</option>)}</select>
            <select aria-label="Sort library" className={control} disabled={busy} onChange={(event) => setSort(event.currentTarget.value)} value={sort}><option value="newest">Newest first</option><option value="name">Name A–Z</option><option value="largest">Largest first</option></select>
          </div>
          <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-[#666862]">
            <label className="flex min-h-11 items-center gap-2"><input checked={favoritesOnly} className="accent-[#173F5F]" disabled={busy} onChange={(event) => { setFavoritesOnly(event.currentTarget.checked); setChecked(new Set()); setRename(undefined); setPendingTrash(false); }} type="checkbox" />Favorites only</label>
            {view !== "trash" ? <label className="flex min-h-11 items-center gap-2"><input checked={showCopies} className="accent-[#173F5F]" disabled={busy} onChange={(event) => { setShowCopies(event.currentTarget.checked); setChecked(new Set()); setRename(undefined); setPendingTrash(false); }} type="checkbox" />Show repeated uploads</label> : null}
            <details className="ml-auto"><summary className="flex min-h-11 cursor-pointer items-center gap-2 font-medium text-[#173F5F]">New collection<ChevronDownIcon aria-hidden="true" className="size-3" /></summary><div className="flex flex-wrap gap-2 py-2"><input aria-label="New collection name" className={control} maxLength={120} onChange={(event) => setCollectionName(event.currentTarget.value)} placeholder="Collection name" value={collectionName} /><button className={control} disabled={busy || !collectionName.trim()} onClick={() => void addCollection()} type="button">Create collection</button></div></details>
          </div>
        </section>
        {view === "trash" ? <p className="my-3 rounded-md border border-[#D7D9D3] bg-white p-3 text-sm text-[#666862]">Trash hides files from new jobs. Restore them whenever you need them. Originals stay on disk, and existing edits keep working. To reclaim space from exact copies, use <Link className="font-bold text-[#173F5F] underline" href="/library/duplicates">Duplicate audit</Link>.</p> : view === "unsorted" ? <p className="my-3 text-sm text-[#666862]">Select videos and label them Talking footage or B-roll. We do not guess a role just because a clip has no transcript.</p> : null}
        {error ? <p className="my-3 rounded-md border border-[#D8B4AA] bg-[#FFF7F4] p-3 text-sm text-[#A23B2A]" role="alert">{error}</p> : null}
        {notice ? <p className="my-3 rounded-md bg-[#E4F1E9] p-3 text-sm text-[#215B43]" role="status">{notice}</p> : null}
        {selected.length ? <section aria-label="Selected media actions" className="sticky top-2 z-10 my-3 space-y-3 rounded-md border border-[#AFC7D5] bg-[#EFF6FA] p-3">
          <div className="flex flex-wrap items-center gap-2"><strong className="mr-2 text-sm text-[#173F5F]">{selected.length} selected</strong>
            <select aria-label="Label selected videos" className={control} disabled={busy || !selectedVideos || selected.length > 500} onChange={(event) => { if (event.currentTarget.value) void apply("role", event.currentTarget.value as MediaRole); }} value=""><option value="">Label videos as…</option><option value="talking">Talking footage</option><option value="broll">B-roll</option><option value="auto">Unsorted</option></select>
            <button className={control} disabled={busy || selected.length > 500} onClick={() => { setRename(selected.length === 1 ? selected[0].display_name : ""); setPendingTrash(false); }} type="button">Rename{selected.length > 1 ? " batch" : ""}</button>
            <button className={control} disabled={busy || selected.length > 500} onClick={() => { if (view === "trash") void apply("restore"); else { setPendingTrash(true); setRename(undefined); } }} type="button">{view === "trash" ? "Restore selected" : "Move to Trash"}</button>
            <button aria-label="Clear selection" className={`${control} ml-auto`} disabled={busy} onClick={() => { setChecked(new Set()); setPendingTrash(false); setRename(undefined); }} type="button"><XIcon aria-hidden="true" className="size-4" /></button>
          </div>
          {selected.length > 500 ? <p className="text-xs text-[#A23B2A]">Select up to 500 files for one action.</p> : null}
          {!selectedVideos ? <p className="text-xs text-[#666862]">Footage labels apply to videos. Photos and audio have their own views.</p> : null}
          {rename !== undefined ? <form className="flex flex-wrap items-end gap-2" onSubmit={(event) => { event.preventDefault(); void apply("rename"); }}><label className="min-w-48 flex-1 text-xs font-bold text-[#173F5F]">{selected.length === 1 ? "New name" : "Batch name"}<input autoFocus className={`${control} mt-1 w-full`} disabled={busy} maxLength={selected.length > 1 ? 251 : 255} onChange={(event) => setRename(event.currentTarget.value)} placeholder="e.g. Cream close-up" value={rename} /></label><button className={control} disabled={busy || !rename.trim()} type="submit">Save names</button><p className="w-full text-xs text-[#666862]">{selected.length > 1 ? `Preview: ${rename.trim() || "Cream close-up"} 001, ${rename.trim() || "Cream close-up"} 002… (in the current list order). ` : ""}Original filenames and existing edits stay unchanged.</p></form> : null}
          {pendingTrash ? <div className="flex flex-wrap items-center gap-3"><p className="min-w-48 flex-1 text-sm text-[#173F5F]">Hide {selected.length} files from the library and new jobs? {selected.filter((asset) => asset.job_references > 0).length} are used by existing jobs; those jobs keep their files. You can restore everything from Trash.</p><button className={`${control} text-[#A23B2A]`} disabled={busy} onClick={() => void apply("trash")} type="button">Confirm move to Trash</button><button className={control} disabled={busy} onClick={() => setPendingTrash(false)} type="button">Cancel</button></div> : null}
          {busy ? <p aria-live="polite" className="text-sm text-[#173F5F]">Saving changes…</p> : null}
        </section> : null}
        <div className={`mt-2 grid items-start gap-4 ${selectedId ? "lg:grid-cols-[minmax(0,1fr)_minmax(320px,380px)]" : ""}`}>
          <section aria-label="Media originals" className="min-w-0 overflow-hidden rounded-md border border-[#D7D9D3] bg-white">
            <div className="flex min-h-14 flex-wrap items-center justify-between gap-3 border-b border-[#D7D9D3] px-3 text-xs text-[#666862]"><label className="flex min-h-11 items-center gap-3"><span className="flex min-w-11 justify-center"><input aria-label="Select displayed files" checked={allShownSelected} className="size-4 accent-[#173F5F]" disabled={busy || !shown.length} onChange={() => { setChecked((current) => { const next = new Set(current); for (const item of shown) { if (allShownSelected) next.delete(item.id); else next.add(item.id); } return next; }); setRename(undefined); setPendingTrash(false); }} type="checkbox" /></span>{visible.length} files{query.trim() && searching ? " · searching speech and scenes…" : ""}</label><span>{!showCopies && view !== "trash" ? "Reviewed duplicates grouped" : "Every upload shown"}</span></div>
            {loading ? <div className="flex min-h-56 items-center justify-center"><LoaderCircleIcon aria-label="Loading library" className="size-6 animate-spin text-[#173F5F]" /></div> : shown.map((asset) => <AssetRow asset={asset} checked={checked.has(asset.id)} disabled={busy} evidence={evidence.get(asset.id)} focused={selectedId === asset.id} key={asset.id} onCheck={() => toggle(asset.id)} onOpen={() => setSelectedId(asset.id)} onRename={() => { setChecked(new Set([asset.id])); setRename(asset.display_name); setPendingTrash(false); }} />)}
            {!loading && !visible.length ? <div className="p-10 text-center"><SparklesIcon aria-hidden="true" className="mx-auto size-6 text-[#173F5F]" /><p className="mt-3 font-bold text-[#173F5F]">{view === "trash" ? "Trash is empty" : "No media in this view"}</p><p className="mt-2 text-sm text-[#666862]">{view === "broll" || view === "talking" ? "Open Unsorted, select your videos, and choose a footage label." : "Try another view or add media from your device."}</p></div> : null}
            {visible.length > pageSize ? <button className={`${control} m-3`} onClick={() => setPageSize((current) => current + 60)} type="button">Show 60 more ({visible.length - pageSize} remaining)</button> : null}
          </section>
          {selectedId ? <AssetInspector allCollections={collections} assetId={selectedId} key={`${selectedId}:${revision}`} onChanged={refresh} onClose={() => setSelectedId(undefined)} onCollectionsChanged={refresh} /> : null}
        </div>
        <p className="mt-5 text-xs leading-5 text-[#666862]">Names and footage labels carry through to New job. B-roll is a silent visual cutaway over your main voice. <Link className="font-bold text-[#173F5F] underline" href="/library/duplicates">Review exact duplicates</Link> to reclaim space from repeated uploads.</p>
      </div>
    </main>
  );
}
