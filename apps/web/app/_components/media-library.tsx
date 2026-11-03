"use client";

import Link from "next/link";
import { StudioNav } from "./studio-nav";
import { writeMediaBasket } from "@/lib/media-basket";
import { SourceRanges } from "./source-ranges";
import { LibraryInbox } from "./library-inbox";
import { LibraryUpload } from "@/app/_components/library-upload";
import { LibraryAutoSort } from "@/app/_components/library-auto-sort";
import { LibraryFolders, LibraryFolderCards } from "./library-folders";
import { readLibraryBrowser, saveLibraryBrowser, readLibraryScroll, saveLibraryScroll } from "@/lib/library-browser-state";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  ArchiveIcon, AudioLinesIcon, CheckIcon, FilmIcon, HeartIcon, ImageIcon,
  LoaderCircleIcon, RotateCcwIcon, SearchIcon, SparklesIcon, VideoIcon, XIcon,
  PlusIcon, PencilIcon, FolderIcon, LayoutGridIcon, ListIcon, ChevronRightIcon,
} from "lucide-react";
import {
  createLibraryCollection, getLibraryAssetDetail, getLibraryCollections,
  browseLibrary, libraryAssetPreviewUrl, libraryAssetThumbnailUrl,
  searchCatalog, setLibraryAssetState, setLibraryCollectionMembership,
  updateLibraryAsset, updateLibraryBatch, visualIndexFrameUrl,
  updateLibraryFolder, deleteLibraryFolder, updateLibraryFolderMembers,
  type CatalogSearchResult, type LibraryAssetDetail, type LibraryCollection,
  type ManagedLibraryAsset, type MediaRole, type MediaCategory,
} from "@/lib/media-api";
import { libraryRoleLabel, libraryViews, mediaCategories, type LibraryView } from "@/lib/library-organization";

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

function AssetRow({ asset, evidence, checked, focused, disabled, layout, onCheck, onOpen, onRename }: {
  readonly asset: ManagedLibraryAsset;
  readonly evidence?: CatalogSearchResult;
  readonly checked: boolean;
  readonly focused: boolean;
  readonly disabled: boolean;
  readonly layout: "grid" | "list";
  readonly onCheck: () => void;
  readonly onOpen: () => void;
  readonly onRename: () => void;
}) {
  return (
    <article className={`${layout === "grid" ? "relative min-w-0 overflow-hidden rounded-lg border border-[#D7D9D3]" : "flex items-center gap-3 border-b border-[#E7E8E4] p-3 last:border-b-0"} ${checked || focused ? "bg-[#EFF6FA]" : "bg-white"}`}>
      <label className={`flex min-h-11 min-w-11 items-center justify-center ${layout === "grid" ? "absolute top-2 left-2 z-10 rounded-md bg-white/95" : ""}`}>
        <input aria-label={`Select ${asset.display_name}`} checked={checked} className="size-4 accent-[#173F5F]" disabled={disabled} onChange={onCheck} type="checkbox" />
      </label>
      <button title={`Details for ${asset.display_name}`} aria-pressed={focused} disabled={disabled} className={`${layout === "grid" ? "block w-full" : "flex flex-1 items-center gap-3"} min-w-0 text-left`} onClick={onOpen} type="button">
        <span className={`flex shrink-0 items-center justify-center overflow-hidden bg-[#E4EBEF] text-[#173F5F] ${layout === "grid" ? "aspect-[4/3] w-full" : "size-16 rounded"}`}>
          {asset.thumbnail_available ? <img alt="" className="size-full object-cover" loading="lazy" src={libraryAssetThumbnailUrl(asset.id)} /> : <MediaIcon kind={mediaKind(asset)} />}
        </span>
        <span className={`min-w-0 flex-1 ${layout === "grid" ? "block p-3" : ""}`}>
          <strong className="block truncate text-sm text-[#173F5F]">{asset.display_name}{asset.favorite ? " ♥" : ""}</strong>
          <span className="mt-0.5 block truncate text-xs text-[#666862]">{asset.source_name} · {asset.project_name}</span>
          {asset.media_category && asset.media_category !== "auto" ? <span className="mt-1 block text-xs font-medium text-[#173F5F]">{mediaCategories.find((item) => item.id === asset.media_category)?.label}</span> : null}
          <span className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs text-[#666862]"><span className="font-medium text-[#173F5F]">{libraryRoleLabel(asset)}</span><span>{formatDuration(asset.duration_seconds)} · {formatBytes(asset.byte_size)}</span><span>{asset.job_references ? `Used in ${asset.job_references} ${asset.job_references === 1 ? "job" : "jobs"}` : "Not used in a job"}</span></span>
          {evidence ? <span className="mt-1 line-clamp-2 block text-xs text-[#173F5F]">{evidence.segment_kind === "transcript" ? "Speech" : "Scene"} · {evidence.text || `${formatTime(evidence.start_seconds)}–${formatTime(evidence.end_seconds)}`}</span> : null}
        </span>
      </button>
      <button aria-label={`Rename ${asset.display_name}`} className={`flex min-h-11 min-w-11 items-center justify-center text-[#173F5F] disabled:opacity-50 ${layout === "grid" ? "absolute top-2 right-2 rounded-md bg-white/95" : ""}`} disabled={disabled} onClick={onRename} type="button"><PencilIcon aria-hidden="true" className="size-4" /></button>
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
  const panel = useRef<HTMLElement>(null);
  const [detail, setDetail] = useState<LibraryAssetDetail>();
  const [error, setError] = useState<string>();
  const [saving, setSaving] = useState(false);
  const [displayName, setDisplayName] = useState("");
  const [notes, setNotes] = useState("");
  const [tags, setTags] = useState("");
  const [favorite, setFavorite] = useState(false);
  const [mediaRole, setMediaRole] = useState<MediaRole>("auto");
  const [mediaCategory, setMediaCategory] = useState<MediaCategory>("auto");

  useEffect(() => {
    const previous = document.activeElement;
    panel.current?.focus({ preventScroll: true });
    const escape = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    document.addEventListener("keydown", escape);
    return () => { document.removeEventListener("keydown", escape); if (previous instanceof HTMLElement && previous.isConnected) previous.focus({ preventScroll: true }); };
  }, [onClose]);

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
      setMediaCategory(result.asset.media_category ?? "auto");
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
        mediaCategory,
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
    <aside ref={panel} tabIndex={-1} aria-label="Selected original details" className="fixed inset-3 z-40 overflow-y-auto rounded-md border border-[#AFC7D5] bg-white shadow-xl outline-none lg:sticky lg:inset-auto lg:top-4 lg:z-auto lg:max-h-[90vh] lg:h-fit lg:shadow-none">
      <div className="flex items-start justify-between gap-4 border-b border-[#D7D9D3] p-4"><div><p className="font-mono text-[9px] font-bold tracking-widest text-[#174D73] uppercase">Selected original</p><h2 className="mt-1 text-lg font-bold text-[#173F5F]">{detail?.asset.display_name ?? "Loading original…"}</h2></div><button aria-label="Close details" className="flex min-h-11 min-w-11 items-center justify-center rounded-md p-2 text-[#666862] hover:bg-[#F0F0EC]" onClick={onClose} type="button"><XIcon className="size-4" /></button></div>
      {!detail && !error ? <div className="flex min-h-80 items-center justify-center"><LoaderCircleIcon aria-label="Loading selected original" className="size-7 animate-spin text-[#173F5F]" /></div> : null}
      {error ? <p className="m-4 rounded-md border border-[#D8B4AA] bg-[#FFF7F4] p-3 text-sm text-[#A23B2A]" role="alert">{error}</p> : null}
      {detail ? <>
        <AssetPreview detail={detail} />
        <div className="space-y-5 p-4">
          <section><div className="flex items-center justify-between gap-3"><p className="font-mono text-[9px] font-bold tracking-wider text-[#666862] uppercase">Representative scenes</p><span className="font-mono text-[9px] text-[#666862]">LOCAL INDEX</span></div>{detail.visual_frames.length ? <div className="mt-2 grid grid-cols-4 gap-2">{detail.visual_frames.slice(0, 8).map((frame) => <figure key={frame.id}><img alt={`Frame at ${formatTime(frame.frame_seconds)}`} className="aspect-video w-full rounded-sm bg-[#E4EBEF] object-cover" loading="lazy" src={visualIndexFrameUrl(frame.id)} /><figcaption className="mt-1 font-mono text-[8px] text-[#666862]">{formatTime(frame.frame_seconds)}</figcaption></figure>)}</div> : <p className="mt-2 text-xs leading-5 text-[#666862]">No visual frames are indexed for this original yet.</p>}</section>
          {detail.asset.duration_seconds ? <SourceRanges key={assetId} assetId={assetId} duration={detail.asset.duration_seconds} /> : null}
          <section><p className="font-mono text-[9px] font-bold tracking-wider text-[#666862] uppercase">Speech and scene evidence</p>{detail.evidence.length ? <div className="mt-2 max-h-56 space-y-2 overflow-y-auto overscroll-contain pr-1">{detail.evidence.slice(0, 30).map((segment) => <article className="rounded-md border border-[#E7E8E4] bg-[#FAFAF8] p-3" key={segment.id}><p className="text-xs leading-5 text-[#20211F]">{segment.text}</p><p className="mt-1 font-mono text-[8px] font-bold text-[#666862]">{segment.segment_kind.toUpperCase()} · {formatTime(segment.start_seconds)}–{formatTime(segment.end_seconds)}</p></article>)}</div> : <p className="mt-2 text-xs leading-5 text-[#666862]">No transcript or scene descriptions are available yet.</p>}</section>
          <section className="space-y-3"><label className="block text-xs font-bold text-[#666862]">Category<select aria-label="Media category" className={`${control} mt-1 w-full`} value={mediaCategory} onChange={(event) => setMediaCategory(event.currentTarget.value as MediaCategory)}>{mediaCategories.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select></label>{detail.asset.mime_type.startsWith("video/") ? <label className="block text-xs font-bold text-[#666862]">Use this footage as<select aria-label="Footage role" className={`${control} mt-1 w-full`} value={mediaRole} onChange={(event) => setMediaRole(event.currentTarget.value as MediaRole)}><option value="auto">Unsorted</option><option value="talking">Talking footage</option><option value="broll">B-roll</option></select></label> : null}<p className="font-mono text-[9px] font-bold tracking-wider text-[#666862] uppercase">Library details</p><label className="block text-xs font-bold text-[#666862]">Display name<input className="mt-1 h-11 w-full rounded-md border border-[#D7D9D3] px-3 text-sm text-[#20211F] outline-none focus:border-[#173F5F]" maxLength={255} onChange={(event) => setDisplayName(event.currentTarget.value)} value={displayName} /></label><label className="block text-xs font-bold text-[#666862]">Notes<textarea className="mt-1 min-h-24 w-full resize-y rounded-md border border-[#D7D9D3] p-3 text-sm text-[#20211F] outline-none focus:border-[#173F5F]" maxLength={4000} onChange={(event) => setNotes(event.currentTarget.value)} value={notes} /></label><label className="block text-xs font-bold text-[#666862]">Tags <span className="font-normal">· comma separated</span><input className="mt-1 h-11 w-full rounded-md border border-[#D7D9D3] px-3 text-sm text-[#20211F] outline-none focus:border-[#173F5F]" onChange={(event) => setTags(event.currentTarget.value)} placeholder="aviation, travel, b-roll" value={tags} /></label><label className="flex min-h-11 items-center gap-3 rounded-md border border-[#D7D9D3] px-3 text-sm font-bold text-[#173F5F]"><input checked={favorite} className="size-4 accent-[#173F5F]" onChange={(event) => setFavorite(event.currentTarget.checked)} type="checkbox" /><HeartIcon className="size-4" />Favorite source</label></section>
          <section><p className="font-mono text-[9px] font-bold tracking-wider text-[#666862] uppercase">Folders</p>{allCollections.length ? <div className="mt-2 space-y-2">{allCollections.map((collection) => { const selected = detail.collections.some((item) => item.id === collection.id); return <label className="flex min-h-11 items-center justify-between gap-3 rounded-md border border-[#D7D9D3] bg-[#FAFAF8] px-3 text-sm" key={collection.id}><span className="font-medium">{collection.name}</span><input checked={selected} className="size-4 accent-[#173F5F]" disabled={saving} onChange={(event) => void toggleCollection(collection, event.currentTarget.checked)} type="checkbox" /></label>; })}</div> : <p className="mt-2 text-xs leading-5 text-[#666862]">Create a folder to group reusable sources without copying them.</p>}</section>
          <div className="flex flex-col gap-2 sm:flex-row"><button className="inline-flex min-h-11 flex-1 items-center justify-center gap-2 rounded-md bg-[#173F5F] px-4 text-sm font-bold text-white disabled:opacity-60" disabled={saving || !displayName.trim()} onClick={() => void save()} type="button">{saving ? <LoaderCircleIcon className="size-4 animate-spin" /> : <CheckIcon className="size-4" />}Save details</button><button className="inline-flex min-h-11 items-center justify-center gap-2 rounded-md border border-[#D7D9D3] px-4 text-sm font-bold text-[#A23B2A] disabled:opacity-60" disabled={saving} onClick={() => void changeState()} type="button">{detail.asset.library_status === "active" ? <ArchiveIcon className="size-4" /> : <RotateCcwIcon className="size-4" />}{detail.asset.library_status === "active" ? "Move to Trash" : "Restore"}</button></div>
          <p className="text-xs leading-5 text-[#666862]">Trash hides an original from new jobs. You can restore it here. Existing edits keep working; the original stays on disk.</p>
        </div>
      </> : null}
    </aside>
  );
}

export function MediaLibrary() {
  const [home, setHome] = useState(true);
  const [unfiled, setUnfiled] = useState(false);
  const [inbox, setInbox] = useState(false);
  const [layout, setLayout] = useState<"grid" | "list">("grid");
  const [restored, setRestored] = useState(false);
  const scrollRestored = useRef(false);
  const [folderForm, setFolderForm] = useState<"new" | "rename" | "delete">();
  const [folderDestination, setFolderDestination] = useState("");
  const [query, setQuery] = useState("");
  const [view, setView] = useState<LibraryView>("all");
  const [favoritesOnly, setFavoritesOnly] = useState(false);
  const [showCopies, setShowCopies] = useState(false);
  const [sort, setSort] = useState("newest");
  const [category, setCategory] = useState<MediaCategory | "all">("all");
  const [autoSortIds, setAutoSortIds] = useState<readonly string[]>();
  const [assets, setAssets] = useState<readonly ManagedLibraryAsset[]>([]);
  const [evidence, setEvidence] = useState<ReadonlyMap<string, CatalogSearchResult>>(new Map());
  const catalogCache = useRef<{ query: string; revision: number; matches: ReadonlyMap<string, CatalogSearchResult> } | undefined>(undefined);
  const [selectedId, setSelectedId] = useState<string>();
  const closeInspector = useCallback(() => setSelectedId(undefined), []);
  const [checked, setChecked] = useState<ReadonlySet<string>>(new Set());
  const [collections, setCollections] = useState<readonly LibraryCollection[]>([]);
  const [collectionId, setCollectionId] = useState("");
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
  const [pageOffset, setPageOffset] = useState(0);
  const [total, setTotal] = useState(0);
  const [summary, setSummary] = useState({ active: 0, trash: 0, stored_bytes: 0 });

  async function refresh() {
    const nextCollections = await getLibraryCollections();
    setCollections(nextCollections);
    setRevision((current) => current + 1);
  }
  useEffect(() => {
    let cancelled = false;
    const saved = readLibraryBrowser();
    setHome(saved.home); setInbox(saved.inbox ?? false); setUnfiled(saved.unfiled); setLayout(saved.layout); setQuery(saved.query);
    setView(saved.view); setSort(saved.sort); setCategory(saved.category);
    setFavoritesOnly(saved.favorites); setShowCopies(saved.copies);
    setCollectionId(saved.folder); setRestored(true);
    void getLibraryCollections().then((nextCollections) => {
      if (!cancelled) {
        setCollections(nextCollections);
        if (saved.folder && !nextCollections.some((folder) => folder.id === saved.folder)) {
          setCollectionId(""); setHome(true); setUnfiled(false);
          setNotice("That folder is no longer available. Your media is still in All media.");
        }
      }
    }).catch((requestError: unknown) => { if (!cancelled) { setError(String(requestError instanceof Error ? requestError.message : requestError)); setLoading(false); } });
    return () => { cancelled = true; };
  }, []);
  useEffect(() => {
    if (restored) saveLibraryBrowser({ home, inbox, unfiled, layout, query, view, sort, category, folder: collectionId, favorites: favoritesOnly, copies: showCopies });
  }, [restored, home, inbox, unfiled, layout, query, view, sort, category, collectionId, favoritesOnly, showCopies]);
  useEffect(() => {
    if (!loading && !scrollRestored.current) {
      scrollRestored.current = true;
      const frame = window.requestAnimationFrame(() => window.scrollTo(0, readLibraryScroll()));
      return () => window.cancelAnimationFrame(frame);
    }
  }, [loading]);
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined;
    const record = () => { clearTimeout(timer); timer = setTimeout(() => saveLibraryScroll(window.scrollY), 150); };
    window.addEventListener("scroll", record, { passive: true });
    return () => { clearTimeout(timer); window.removeEventListener("scroll", record); };
  }, []);
  useEffect(() => {
    if (!restored || inbox) return;
    let cancelled = false;
    setLoading(true); setAssets([]); setChecked(new Set()); setEvidence(new Map());
    setSelectedId(undefined); setRename(undefined); setPendingTrash(false);
    setSearching(Boolean(query.trim()));
    const timer = window.setTimeout(() => {
      async function load() {
        let matches = new Map<string, CatalogSearchResult>();
        if (query.trim()) {
          try {
            const cached = catalogCache.current;
            if (cached?.query === query.trim() && cached.revision === revision) matches = new Map(cached.matches);
            else {
              const catalog = await searchCatalog({ query: query.trim(), mediaKind: "all", limit: 100 });
              for (const match of catalog.results) if (!matches.has(match.asset_id)) matches.set(match.asset_id, match);
              if (!cancelled) catalogCache.current = { query: query.trim(), revision, matches };
            }
          } catch (error) {
            if (!cancelled) setError(error instanceof Error ? error.message : "Speech search unavailable; searching names.");
          }
        }
        if (cancelled) return;
        try {
          const result = await browseLibrary({ view, category, favorite: favoritesOnly, collectionId,
            unfiled, query: query.trim(), matchIds: [...matches.keys()], copies: showCopies, sort, offset: pageOffset });
          if (cancelled) return;
          if (pageOffset && !result.items.length) { setPageOffset(0); return; }
          setAssets(result.items); setTotal(result.total); setSummary(result.summary); setEvidence(matches);
        } catch (error) { if (!cancelled) setError(error instanceof Error ? error.message : "Library unavailable"); }
        finally { if (!cancelled) { setLoading(false); setSearching(false); } }
      }
      void load();
    }, query.trim() ? 220 : 0);
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [restored, inbox, query, revision, view, category, favoritesOnly, collectionId, unfiled, showCopies, sort, pageOffset]);

  const currentFolder = collections.find((folder) => folder.id === collectionId);
  const visible = assets;
  // Only displayed selections can be acted on: hidden search results never get moved accidentally.
  const selected = visible.filter((asset) => checked.has(asset.id));
  const selectedIds = selected.map((asset) => asset.id);
  const selectedVideos = selected.length > 0 && selected.every((asset) => asset.mime_type.startsWith("video/"));
  const shown = visible;
  const allShownSelected = shown.length > 0 && shown.every((asset) => checked.has(asset.id));
  const activeCount = summary.active;

  function clearSelection() { setChecked(new Set()); setSelectedId(undefined); setRename(undefined); setPendingTrash(false); setPageOffset(0); setFolderDestination(""); }
  function changeView(next: LibraryView) { setView(next); clearSelection(); }
  function openLocation(id: string) {
    setHome(id === "home"); setInbox(id === "inbox"); setUnfiled(id === "unfiled");
    setCollectionId(collections.some((folder) => folder.id === id) ? id : "");
    setFavoritesOnly(id === "favorites"); setView(id === "trash" ? "trash" : "all");
    setQuery(""); setCategory("all"); setFolderForm(undefined); setError(undefined); clearSelection(); saveLibraryScroll(0);
  }
  function toggle(id: string) { setChecked((current) => { const next = new Set(current); if (next.has(id)) next.delete(id); else next.add(id); return next; }); setRename(undefined); setPendingTrash(false); }
  async function apply(action: "rename" | "role" | "category" | "trash" | "restore", mediaRole?: MediaRole, mediaCategory?: MediaCategory) {
    if (busy || !selected.length || selected.length > 500) return;
    setBusy(true); setError(undefined); setNotice(undefined);
    try {
      await updateLibraryBatch(selectedIds, action, { namePrefix: rename?.trim(), mediaRole, mediaCategory });
      setChecked(new Set()); setRename(undefined); setPendingTrash(false); setSelectedId(undefined);
      await refresh();
      setNotice(action === "trash" ? `${selected.length} moved to Trash. Restore them from the Trash view. Originals remain on disk and existing edits keep working.`
        : action === "restore" ? `${selected.length} restored to the library.` : `${selected.length} ${action === "rename" ? "renamed" : action === "category" ? "categorized" : "labelled"}.`);
    } catch (requestError) { setError(requestError instanceof Error ? requestError.message : "The change could not be saved. Your selection is unchanged."); }
    finally { setBusy(false); }
  }
  async function addCollection() {
    if (!collectionName.trim() || busy) return;
    setBusy(true); setError(undefined);
    try {
      const folder = await createLibraryCollection(collectionName.trim());
      setCollectionName(""); setFolderForm(undefined); await refresh();
      setHome(false); setInbox(false); setUnfiled(false); setFavoritesOnly(false); setView("all"); setQuery(""); setCategory("all");
      setCollectionId(folder.id); clearSelection();
      setNotice(`Created ${folder.name}. Select media in All media and choose Add to folder.`);
    }
    catch (requestError) { setError(requestError instanceof Error ? requestError.message : "Collection could not be created"); }
    finally { setBusy(false); }
  }

  async function changeFolder() {
    if (!currentFolder || busy) return;
    setBusy(true); setError(undefined);
    try {
      if (folderForm === "delete") {
        await deleteLibraryFolder(currentFolder.id);
        openLocation("home"); setNotice("Folder removed. Its media remains in All media and existing edits.");
      } else {
        await updateLibraryFolder(currentFolder.id, collectionName.trim(), currentFolder.description);
        setFolderForm(undefined); setCollectionName(""); setNotice("Folder renamed.");
      }
      await refresh();
    } catch (error) { setError(error instanceof Error ? error.message : "Folder could not be changed."); }
    finally { setBusy(false); }
  }

  async function changeMembership(action: "add" | "remove") {
    const target = action === "add" ? folderDestination : collectionId;
    if (!target || busy || !selected.length || selected.length > 500) return;
    setBusy(true); setError(undefined);
    try {
      await updateLibraryFolderMembers(target, selectedIds, action);
      setNotice(`${selected.length} ${selected.length === 1 ? "item" : "items"} ${action === "add" ? "added to folder" : "removed from this folder"}. Original files stay in your library.`);
      await refresh(); clearSelection();
    } catch (error) { setError(error instanceof Error ? error.message : "Folder membership could not be saved. Your selection is unchanged."); }
    finally { setBusy(false); }
  }

  return (
    <main className="min-h-dvh bg-[#F7F7F5] px-3 py-5 text-[#20211F] [color-scheme:light] sm:px-6">
      <div className="mx-auto max-w-[1440px]">
        <header className="border-b border-[#D7D9D3] pb-5">
          <StudioNav current="/library" />
          <div className="mt-7 flex flex-wrap items-center justify-between gap-4">
            <div><h1 className="text-2xl font-bold tracking-tight text-[#173F5F]">Media library</h1><p className="mt-1 text-sm text-[#666862]">{loading ? "Loading your media…" : `${activeCount} active files · ${formatBytes(summary.stored_bytes)} stored`}</p></div>
            <div className="flex flex-wrap gap-2"><button aria-controls="library-import" aria-expanded={uploadOpen} className="inline-flex min-h-11 items-center gap-2 rounded-md bg-[#173F5F] px-4 text-sm font-bold text-white" onClick={() => setUploadOpen((current) => !current)} type="button"><PlusIcon aria-hidden="true" className="size-4" />Add media</button><button className={control} disabled={busy || loading} onClick={() => { setFolderForm("new"); setCollectionName(""); }} type="button"><FolderIcon aria-hidden="true" className="mr-2 inline size-4" />New folder</button></div>
          </div>
        </header>
        {/* Stay mounted when hidden so collapsing the panel does not interrupt transfers. */}
        <div hidden={!uploadOpen} id="library-import"><LibraryUpload onReady={refresh} folders={collections} destination={collectionId} /></div>
        {autoSortIds ? <LibraryAutoSort assetIds={autoSortIds} onApplied={async () => { setChecked(new Set()); setSelectedId(undefined); await refresh(); }} onClose={() => setAutoSortIds(undefined)} /> : null}
        <div className="mt-6 grid gap-5 lg:grid-cols-[200px_minmax(0,1fr)] lg:gap-7">
          <LibraryFolders folders={collections} active={inbox ? "inbox" : home ? "home" : collectionId || (view === "trash" ? "trash" : unfiled ? "unfiled" : favoritesOnly ? "favorites" : "all")} busy={busy || loading} onOpen={openLocation} onNew={() => { setFolderForm("new"); setCollectionName(""); }} />
          <div className="min-w-0">
            <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0"><nav aria-label="Library breadcrumb" className="mb-2 flex min-h-8 items-center gap-2 text-xs text-[#666862]"><button className="min-h-8 font-medium hover:underline" onClick={() => openLocation("home")} type="button">Library</button><ChevronRightIcon aria-hidden="true" className="size-3" /><span className="truncate">{inbox ? "Inbox" : home ? "Folders" : currentFolder?.name ?? (view === "trash" ? "Trash" : unfiled ? "Not in folders" : favoritesOnly ? "Favourites" : "All media")}</span></nav><h2 className="break-words text-xl font-bold text-[#173F5F]">{inbox ? "New import Inbox" : home ? "A place for every story" : currentFolder?.name ?? (view === "trash" ? "Trash" : unfiled ? "Not in folders" : favoritesOnly ? "Favourites" : "All media")}</h2><p className="mt-1 text-sm leading-6 text-[#666862]">{inbox ? "Uploaded files waiting for your review. Analysis continues here after transfer." : home ? "Group your footage by product, subject or campaign. An item can belong to several folders." : currentFolder ? `${currentFolder.asset_count} items` : unfiled ? "Ready media that has not been added to any folder." : "Find a source, preview it, then choose what to use."}</p></div>
              {home ? <div className="flex flex-wrap gap-2"><Link className={`${control} inline-flex items-center gap-2`} href="/concepts"><SparklesIcon aria-hidden="true" className="size-4" />Find reel ideas</Link><button className={control} disabled={loading} onClick={() => openLocation("all")} type="button">Browse all media</button></div> : currentFolder ? <div className="flex flex-wrap gap-2"><Link className={`${control} inline-flex items-center gap-2`} href={`/concepts?collection=${encodeURIComponent(currentFolder.id)}`}><SparklesIcon aria-hidden="true" className="size-4" />Find reel ideas from this folder</Link><details><summary className={`${control} flex cursor-pointer items-center`}>Folder options</summary><div className="mt-2 flex flex-wrap gap-2"><button className={control} disabled={busy} onClick={() => { setFolderForm("rename"); setCollectionName(currentFolder.name); }} type="button">Rename folder</button><button className={control} disabled={busy} onClick={() => setFolderForm("delete")} type="button">Remove folder</button></div></details></div> : null}
            </div>
            {folderForm ? <section aria-label="Folder settings" className="mb-4 rounded-lg border border-[#AFC7D5] bg-white p-4">
              {folderForm === "delete" ? <><p className="text-sm leading-6 text-[#173F5F]">Remove “{currentFolder?.name}”? Only the folder grouping is removed. Its media remains in All media, other folders and existing edits.</p><div className="mt-3 flex gap-2"><button className={`${control} text-[#A23B2A]`} disabled={busy} onClick={() => void changeFolder()} type="button">Confirm remove folder</button><button className={control} disabled={busy} onClick={() => setFolderForm(undefined)} type="button">Cancel</button></div></> : <form className="flex flex-wrap items-end gap-2" onSubmit={(event) => { event.preventDefault(); if (folderForm === "new") void addCollection(); else void changeFolder(); }}><label className="min-w-0 flex-1 text-xs font-bold text-[#173F5F]">Folder name<input autoFocus className={`${control} mt-1 w-full`} maxLength={120} onChange={(event) => setCollectionName(event.currentTarget.value)} placeholder="e.g. Castor oil cream" value={collectionName} /></label><button className={control} disabled={busy || !collectionName.trim()} type="submit">{folderForm === "new" ? "Create folder" : "Save folder name"}</button><button className={control} disabled={busy} onClick={() => setFolderForm(undefined)} type="button">Cancel</button></form>}
            </section> : null}
            {error ? <p className="my-3 rounded-md border border-[#D8B4AA] bg-[#FFF7F4] p-3 text-sm text-[#A23B2A]" role="alert">{error}</p> : null}
            {notice ? <p className="my-3 rounded-md bg-[#E4F1E9] p-3 text-sm text-[#215B43]" role="status">{notice}</p> : null}
            {inbox ? <><LibraryInbox folders={collections} revision={revision} onOpenAsset={setSelectedId} onAutoSort={setAutoSortIds} onChanged={refresh} />{selectedId ? <div className="mt-4"><AssetInspector allCollections={collections} assetId={selectedId} key={`${selectedId}:${revision}`} onChanged={refresh} onClose={closeInspector} onCollectionsChanged={refresh} /></div> : null}</> : home ? loading ? <p role="status" className="p-8 text-sm text-[#666862]">Loading your folders…</p> : <LibraryFolderCards folders={collections} busy={busy} onOpen={openLocation} onNew={() => { setFolderForm("new"); setCollectionName(""); }} /> : <>
        <nav aria-label="Library views" className="mt-5 flex gap-1 overflow-x-auto border-b border-[#D7D9D3] pb-2">
          {libraryViews.filter((item) => item.id !== "trash").map((item) => <button aria-current={view === item.id ? "page" : undefined} className={`min-h-11 shrink-0 rounded-md px-4 text-sm font-bold ${view === item.id ? "bg-[#173F5F] text-white" : "text-[#666862] hover:bg-white"}`} disabled={busy} key={item.id} onClick={() => changeView(item.id)} type="button">{item.id === "all" ? "All types" : item.label}</button>)}
        </nav>
        <section aria-label="Search and organize media" className="mt-4 space-y-3">
          <div className="flex flex-wrap gap-2">
            <label className="relative min-w-48 flex-1"><span className="sr-only">Search library</span><SearchIcon aria-hidden="true" className="absolute top-3.5 left-3 size-4 text-[#666862]" /><input className={`${control} w-full pl-10`} disabled={busy} maxLength={160} onChange={(event) => { setQuery(event.currentTarget.value); setError(undefined); setChecked(new Set()); setPageOffset(0); setPendingTrash(false); setRename(undefined); }} placeholder="Search names, spoken words or scenes" type="search" value={query} /></label>

            <select aria-label="Sort library" className={control} disabled={busy} onChange={(event) => { setSort(event.currentTarget.value); setPageOffset(0); }} value={sort}><option value="newest">Newest first</option><option value="name">Name A–Z</option><option value="largest">Largest first</option></select>
            <select aria-label="Filter media category" className={control} disabled={busy} onChange={(event) => { setCategory(event.currentTarget.value as typeof category); setChecked(new Set()); setPageOffset(0); }} value={category}><option value="all">All categories</option>{mediaCategories.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select>
          </div>
          <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-[#666862]">
            <button className={control} disabled={busy || loading || view === "trash"} onClick={() => setAutoSortIds((selected.length ? selected : visible.filter((asset) => asset.display_name === asset.source_name || (asset.media_category ?? "auto") === "auto")).slice(0,24).map((asset) => asset.id))} type="button">Auto-sort</button>
            <label className="flex min-h-11 items-center gap-2"><input checked={favoritesOnly} className="accent-[#173F5F]" disabled={busy} onChange={(event) => { setFavoritesOnly(event.currentTarget.checked); setPageOffset(0); setChecked(new Set()); setRename(undefined); setPendingTrash(false); }} type="checkbox" />Favorites only</label>
            {view !== "trash" ? <label className="flex min-h-11 items-center gap-2"><input checked={showCopies} className="accent-[#173F5F]" disabled={busy} onChange={(event) => { setShowCopies(event.currentTarget.checked); setPageOffset(0); setChecked(new Set()); setRename(undefined); setPendingTrash(false); }} type="checkbox" />Show repeated uploads</label> : null}
            <div aria-label="Library display" className="ml-auto flex rounded-md border border-[#D7D9D3] bg-white p-1"><button aria-label="Grid view" aria-pressed={layout === "grid"} className={`flex min-h-11 items-center gap-2 rounded px-3 ${layout === "grid" ? "bg-[#E4EBEF] font-bold text-[#173F5F]" : ""}`} onClick={() => setLayout("grid")} type="button"><LayoutGridIcon aria-hidden="true" className="size-4" />Grid</button><button aria-label="List view" aria-pressed={layout === "list"} className={`flex min-h-11 items-center gap-2 rounded px-3 ${layout === "list" ? "bg-[#E4EBEF] font-bold text-[#173F5F]" : ""}`} onClick={() => setLayout("list")} type="button"><ListIcon aria-hidden="true" className="size-4" />List</button></div>
          </div>
        </section>
        {view === "trash" ? <p className="my-3 rounded-md border border-[#D7D9D3] bg-white p-3 text-sm text-[#666862]">Trash hides files from new jobs. Restore them whenever you need them. Originals stay on disk, and existing edits keep working. To reclaim space from exact copies, use <Link className="font-bold text-[#173F5F] underline" href="/library/duplicates">Duplicate audit</Link>.</p> : view === "unsorted" ? <p className="my-3 text-sm text-[#666862]">Select videos and label them Talking footage or B-roll. We do not guess a role just because a clip has no transcript.</p> : null}
        {selected.length ? <section aria-label="Selected media actions" className="sticky top-2 z-10 my-3 space-y-3 rounded-md border border-[#AFC7D5] bg-[#EFF6FA] p-3">
          <div className="flex flex-wrap items-center gap-2"><strong className="mr-2 text-sm text-[#173F5F]">{selected.length} selected</strong>
            <select aria-label="Label selected videos" className={control} disabled={busy || !selectedVideos || selected.length > 500} onChange={(event) => { if (event.currentTarget.value) void apply("role", event.currentTarget.value as MediaRole); }} value=""><option value="">Label videos as…</option><option value="talking">Talking footage</option><option value="broll">B-roll</option><option value="auto">Unsorted</option></select>
            {view !== "trash" ? <><label className="sr-only" htmlFor="folder-destination">Destination folder</label><select id="folder-destination" className={`${control} max-w-full`} disabled={busy} value={folderDestination} onChange={(event) => setFolderDestination(event.currentTarget.value)}><option value="">Choose folder…</option>{collections.map((folder) => <option key={folder.id} value={folder.id}>{folder.name}</option>)}</select><button className={control} disabled={busy || !folderDestination || selected.length > 500} onClick={() => void changeMembership("add")} type="button">Add to folder</button>{currentFolder ? <button className={control} disabled={busy || selected.length > 500} onClick={() => void changeMembership("remove")} type="button">Remove from this folder</button> : null}</> : null}
            <button className={control} disabled={busy || selected.length > 500} onClick={() => { setRename(selected.length === 1 ? selected[0].display_name : ""); setPendingTrash(false); }} type="button">Rename{selected.length > 1 ? " batch" : ""}</button>
            <select aria-label="Categorize selected files" className={control} disabled={busy || selected.length > 500} onChange={(event) => { if (event.currentTarget.value) void apply("category", undefined, event.currentTarget.value as MediaCategory); }} value=""><option value="">Categorize files as…</option>{mediaCategories.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select>
            {view !== "trash" ? <button className={control} disabled={busy || selected.length > 24} onClick={() => setAutoSortIds(selectedIds)} type="button">Auto-sort selected</button> : null}
            <button className={control} disabled={busy || selected.length > 500} onClick={() => { if (view === "trash") void apply("restore"); else { setPendingTrash(true); setRename(undefined); } }} type="button">{view === "trash" ? "Restore selected" : "Move to Trash"}</button>
            {view !== "trash" ? <Link className={`${control} inline-flex items-center bg-[#173F5F] text-white`} href="/jobs/new" onClick={() => writeMediaBasket(selectedIds)}>Use selected in new edit →</Link> : null}
            <button aria-label="Clear selection" className={`${control} ml-auto`} disabled={busy} onClick={() => { setChecked(new Set()); setPendingTrash(false); setRename(undefined); }} type="button"><XIcon aria-hidden="true" className="size-4" /></button>
          </div>
          {selected.length > 500 ? <p className="text-xs text-[#A23B2A]">Select up to 500 files for one action.</p> : null}
          {!selectedVideos ? <p className="text-xs text-[#666862]">Use categories for photos and audio, including Reviews and Products. Talking/B-roll labels apply to videos.</p> : null}
          {selected.length > 24 ? <p className="text-xs text-[#666862]">Auto-sort processes up to 24 files per request; manual actions support up to 500.</p> : null}
          {rename !== undefined ? <form className="flex flex-wrap items-end gap-2" onSubmit={(event) => { event.preventDefault(); void apply("rename"); }}><label className="min-w-48 flex-1 text-xs font-bold text-[#173F5F]">{selected.length === 1 ? "New name" : "Batch name"}<input autoFocus className={`${control} mt-1 w-full`} disabled={busy} maxLength={selected.length > 1 ? 251 : 255} onChange={(event) => setRename(event.currentTarget.value)} placeholder="e.g. Cream close-up" value={rename} /></label><button className={control} disabled={busy || !rename.trim()} type="submit">Save names</button><p className="w-full text-xs text-[#666862]">{selected.length > 1 ? `Preview: ${rename.trim() || "Cream close-up"} 001, ${rename.trim() || "Cream close-up"} 002… (in the current list order). ` : ""}Original filenames and existing edits stay unchanged.</p></form> : null}
          {pendingTrash ? <div className="flex flex-wrap items-center gap-3"><p className="min-w-48 flex-1 text-sm text-[#173F5F]">Hide {selected.length} files from the library and new jobs? {selected.filter((asset) => asset.job_references > 0).length} are used by existing jobs; those jobs keep their files. You can restore everything from Trash.</p><button className={`${control} text-[#A23B2A]`} disabled={busy} onClick={() => void apply("trash")} type="button">Confirm move to Trash</button><button className={control} disabled={busy} onClick={() => setPendingTrash(false)} type="button">Cancel</button></div> : null}
          {busy ? <p aria-live="polite" className="text-sm text-[#173F5F]">Saving changes…</p> : null}
        </section> : null}
        <div className={`mt-2 grid items-start gap-4 ${selectedId ? "lg:grid-cols-[minmax(0,1fr)_minmax(320px,380px)]" : ""}`}>
          <section aria-label="Media originals" className="min-w-0 overflow-hidden rounded-md border border-[#D7D9D3] bg-white">
            <div className="flex min-h-14 flex-wrap items-center justify-between gap-3 border-b border-[#D7D9D3] px-3 text-xs text-[#666862]"><label className="flex min-h-11 items-center gap-3"><span className="flex min-w-11 justify-center"><input aria-label="Select displayed files" checked={allShownSelected} className="size-4 accent-[#173F5F]" disabled={busy || !shown.length} onChange={() => { setChecked((current) => { const next = new Set(current); for (const item of shown) { if (allShownSelected) next.delete(item.id); else next.add(item.id); } return next; }); setRename(undefined); setPendingTrash(false); }} type="checkbox" /></span>{total} files{query.trim() && searching ? " · searching speech and scenes…" : ""}</label><span>{!showCopies && view !== "trash" ? "Reviewed duplicates grouped" : "Every upload shown"}</span></div>
            {loading ? <div className="flex min-h-56 items-center justify-center"><LoaderCircleIcon aria-label="Loading library" className="size-6 animate-spin text-[#173F5F]" /></div> : <div className={layout === "grid" ? "grid grid-cols-2 gap-3 p-3 xl:grid-cols-3" : ""}>{shown.map((asset) => <AssetRow layout={layout} asset={asset} checked={checked.has(asset.id)} disabled={busy} evidence={evidence.get(asset.id)} focused={selectedId === asset.id} key={asset.id} onCheck={() => toggle(asset.id)} onOpen={() => setSelectedId(asset.id)} onRename={() => { setChecked(new Set([asset.id])); setRename(asset.display_name); setPendingTrash(false); }} />)}</div>}
            {!loading && !visible.length ? <div className="p-10 text-center"><SparklesIcon aria-hidden="true" className="mx-auto size-6 text-[#173F5F]" /><p className="mt-3 font-bold text-[#173F5F]">{view === "trash" ? "Trash is empty" : "No media in this view"}</p><p className="mt-2 text-sm text-[#666862]">{view === "broll" || view === "talking" ? "Open Unsorted, select your videos, and choose a footage label." : "Try another view or add media from your device."}</p></div> : null}
            {total > 60 ? <nav aria-label="Library pages" className="flex flex-wrap items-center gap-3 border-t border-[#D7D9D3] p-3"><button className={control} disabled={loading || !pageOffset} onClick={() => setPageOffset(Math.max(0, pageOffset - 60))} type="button">Previous files</button><span className="text-xs text-[#666862]">{pageOffset + 1}–{Math.min(total, pageOffset + 60)} of {total}</span><button className={control} disabled={loading || pageOffset + 60 >= total} onClick={() => setPageOffset(pageOffset + 60)} type="button">Next files</button></nav> : null}
          </section>
          {selectedId ? <AssetInspector allCollections={collections} assetId={selectedId} key={`${selectedId}:${revision}`} onChanged={refresh} onClose={closeInspector} onCollectionsChanged={refresh} /> : null}
        </div>
        <p className="mt-5 text-xs leading-5 text-[#666862]">Names and footage labels carry through to New job. B-roll is a silent visual cutaway over your main voice. <Link className="font-bold text-[#173F5F] underline" href="/library/duplicates">Review exact duplicates</Link> to reclaim space from repeated uploads.</p>
            </>}
          </div>
        </div>
      </div>
    </main>
  );
}
