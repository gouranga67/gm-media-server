"use client";

import Link from "next/link";
import { useEffect, useState, type ReactNode } from "react";
import {
  AudioLinesIcon,
  CheckIcon,
  ChevronDownIcon,
  ChevronUpIcon,
  CopyCheckIcon,
  FilesIcon,
  HardDriveIcon,
  ImageIcon,
  Layers3Icon,
  LibraryIcon,
  LoaderCircleIcon,
  SearchIcon,
  ShieldCheckIcon,
  VideoIcon,
} from "lucide-react";

import {
  getDuplicateAudit,
  libraryAssetThumbnailUrl,
  reviewDuplicateGroup,
  cleanupDuplicateGroup,
  type DuplicateAssetCopy,
  type DuplicateAudit as DuplicateAuditData,
  type DuplicateGroup,
} from "@/lib/media-api";

type ReviewFilter = "all" | "unreviewed" | "reviewed";
type AuditSort = "most_storage" | "most_copies" | "newest";
const EMPTY_GROUPS: readonly DuplicateGroup[] = [];

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

function formatDate(value: string) {
  return new Intl.DateTimeFormat(undefined, { day: "numeric", month: "short", year: "numeric" }).format(new Date(value));
}

function mediaLabel(group: DuplicateGroup) {
  return group.media_kind === "image" ? "Photo" : group.media_kind[0].toUpperCase() + group.media_kind.slice(1);
}

function MediaIcon({ kind }: { readonly kind: DuplicateGroup["media_kind"] }) {
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
      <div className="flex items-center justify-between gap-3">
        <p className={`font-mono text-[10px] font-bold tracking-wide uppercase ${highlighted ? "text-[#174D73]" : "text-[#666862]"}`}>{label}</p>
        <span className="text-[#174D73]">{icon}</span>
      </div>
      <p className="mt-3 text-2xl font-bold tracking-tight text-[#173F5F]">{value}</p>
      <p className="mt-1 text-xs text-[#666862]">{note}</p>
    </article>
  );
}

function CopyRow({ copy, selected, onSelect }: {
  readonly copy: DuplicateAssetCopy;
  readonly selected: boolean;
  readonly onSelect: () => void;
}) {
  return (
    <label className={`grid cursor-pointer gap-3 border-b border-[#E7E8E4] p-4 last:border-b-0 md:grid-cols-[minmax(220px,1.4fr)_minmax(150px,1fr)_120px_90px_150px] md:items-center md:gap-4 ${selected ? "bg-[#EFF6FA]" : "bg-white hover:bg-[#FAFAF8]"}`}>
      <span className="flex min-w-0 items-center gap-3">
        <input checked={selected} className="size-4 shrink-0 accent-[#173F5F]" name="canonical-copy" onChange={onSelect} type="radio" />
        <span className="min-w-0"><span className="block truncate text-sm font-bold text-[#20211F]">{copy.source_name}</span><span className="mt-0.5 block font-mono text-[10px] text-[#666862]">ORIGINAL · VERIFIED</span></span>
      </span>
      <span><span className="block text-sm font-medium text-[#20211F]">{copy.project_name}</span><span className="font-mono text-[9px] font-bold text-[#666862] uppercase md:hidden">Project</span></span>
      <span><span className="block text-sm text-[#20211F]">{formatDate(copy.created_at)}</span><span className="font-mono text-[9px] font-bold text-[#666862] uppercase md:hidden">Uploaded</span></span>
      <span><span className="block text-sm font-bold text-[#20211F]">{copy.job_references} {copy.job_references === 1 ? "job" : "jobs"}</span><span className="font-mono text-[9px] font-bold text-[#666862] uppercase md:hidden">References</span></span>
      <span className={selected ? "inline-flex w-fit items-center gap-1.5 rounded-full bg-[#E4F1E9] px-2.5 py-1.5 text-xs font-bold text-[#307455]" : "font-mono text-[10px] font-bold tracking-wide text-[#666862] uppercase"}>
        {selected ? <><CheckIcon aria-hidden="true" className="size-3.5" />Canonical</> : copy.storage_optimized ? "Storage shared" : "Identical copy"}
      </span>
    </label>
  );
}

function GroupCard({ group, expanded, selectedCanonicalId, reviewing, cleaning, onExpand, onSelectCanonical, onReview, onCleanup }: {
  readonly group: DuplicateGroup;
  readonly expanded: boolean;
  readonly selectedCanonicalId: string;
  readonly reviewing: boolean;
  readonly cleaning: boolean;
  readonly onExpand: () => void;
  readonly onSelectCanonical: (assetId: string) => void;
  readonly onReview: () => void;
  readonly onCleanup: () => void;
}) {
  const representative = group.copies.find((copy) => copy.id === group.canonical_asset_id) ?? group.copies[0];
  return (
    <article className="overflow-hidden rounded-md border border-[#D7D9D3] bg-white [content-visibility:auto] [contain-intrinsic-size:240px]">
      <div className="grid gap-5 p-4 sm:p-5 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-center">
        <div className="flex min-w-0 gap-4">
          <span className="flex size-20 shrink-0 items-center justify-center overflow-hidden rounded-sm bg-[#E4EBEF] text-[#174D73] sm:h-24 sm:w-28">
            {representative.thumbnail_available ? <img alt="" className="h-full w-full object-cover" loading="lazy" src={libraryAssetThumbnailUrl(representative.id)} /> : <MediaIcon kind={group.media_kind} />}
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="max-w-full truncate text-lg font-bold tracking-tight text-[#173F5F] sm:text-xl">{representative.source_name}</h2>
              <span className="rounded-full bg-[#E4F1E9] px-2.5 py-1 font-mono text-[9px] font-bold tracking-wide text-[#307455]">EXACT MATCH</span>
              <span className={`rounded-full px-2.5 py-1 font-mono text-[9px] font-bold tracking-wide ${group.reviewed ? "bg-[#F0F0EC] text-[#666862]" : "bg-[#EFF6FA] text-[#174D73]"}`}>{group.reviewed ? "REVIEWED" : "UNREVIEWED"}</span>
            </div>
            <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 font-mono text-[10px] text-[#666862] sm:text-[11px]"><span>SHA-256 · {group.sha256.slice(0, 8)}…{group.sha256.slice(-4)}</span><span>{mediaLabel(group).toUpperCase()} · {formatBytes(group.byte_size)} EACH</span></div>
            <p className="mt-3 text-sm leading-5 text-[#666862]"><strong className="text-[#20211F]">{group.copy_count} identical copies</strong> across {new Set(group.copies.map((copy) => copy.project_id)).size} projects · <strong className="text-[#174D73]">{group.reclaimable_bytes ? `${formatBytes(group.reclaimable_bytes)} reclaimable` : "storage optimized"}</strong></p>
          </div>
        </div>
        <button className="inline-flex min-h-11 items-center justify-center gap-2 rounded-md border border-[#AFC7D5] bg-white px-4 text-sm font-bold text-[#174D73] hover:bg-[#EFF6FA] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#173F5F]" onClick={onExpand} type="button">
          {expanded ? "Hide details" : group.reviewed ? "View review" : "Review group"}
          {expanded ? <ChevronUpIcon aria-hidden="true" className="size-4" /> : <ChevronDownIcon aria-hidden="true" className="size-4" />}
        </button>
      </div>
      {expanded ? (
        <div className="border-t border-[#D7D9D3] bg-[#F7F7F5] p-4 sm:p-5">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div><p className="font-mono text-[10px] font-bold tracking-wide text-[#666862] uppercase">Copies and origins</p><p className="mt-1 max-w-2xl text-xs leading-5 text-[#666862]">{group.canonical_reason} Choose a different intact record if its project context is more useful to you.</p></div>
            <span className="inline-flex w-fit items-center gap-1.5 rounded-full border border-[#AFC7D5] bg-white px-3 py-1.5 text-xs font-bold text-[#174D73]"><ShieldCheckIcon aria-hidden="true" className="size-3.5" />Every library path stays valid</span>
          </div>
          <div className="mt-4 overflow-hidden rounded-md border border-[#D7D9D3]">
            <div className="hidden grid-cols-[minmax(220px,1.4fr)_minmax(150px,1fr)_120px_90px_150px] gap-4 border-b border-[#D7D9D3] bg-[#FAFAF8] px-4 py-3 font-mono text-[9px] font-bold tracking-wide text-[#666862] uppercase md:grid"><span>Original file</span><span>Project</span><span>Uploaded</span><span>Jobs</span><span>Status</span></div>
            {group.copies.map((copy) => <CopyRow copy={copy} key={copy.id} onSelect={() => onSelectCanonical(copy.id)} selected={selectedCanonicalId === copy.id} />)}
          </div>
          <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-xs leading-5 text-[#666862]">Cleanup verifies every SHA-256 again, then lets exact copies share disk blocks while retaining their records and paths.</p>
            <div className="flex flex-col gap-2 sm:flex-row">
              <button className="inline-flex min-h-11 items-center justify-center gap-2 rounded-md border border-[#AFC7D5] bg-white px-5 text-sm font-bold text-[#174D73] hover:bg-[#EFF6FA] disabled:cursor-not-allowed disabled:opacity-60" disabled={reviewing || cleaning} onClick={onReview} type="button">
                {reviewing ? <LoaderCircleIcon aria-hidden="true" className="size-4 animate-spin" /> : <CheckIcon aria-hidden="true" className="size-4" />}
                {group.reviewed ? "Update review" : "Confirm canonical"}
              </button>
              {group.reviewed ? <button className="inline-flex min-h-11 items-center justify-center gap-2 rounded-md bg-[#173F5F] px-5 text-sm font-bold text-white hover:bg-[#12334D] disabled:cursor-not-allowed disabled:opacity-60" disabled={!group.cleanup_ready || cleaning || reviewing || selectedCanonicalId !== group.canonical_asset_id} onClick={onCleanup} type="button">
                {cleaning ? <LoaderCircleIcon aria-hidden="true" className="size-4 animate-spin" /> : <HardDriveIcon aria-hidden="true" className="size-4" />}
                {selectedCanonicalId !== group.canonical_asset_id ? "Save review first" : group.cleanup_ready ? `Optimize ${formatBytes(group.reclaimable_bytes)}` : "Storage optimized"}
              </button> : null}
            </div>
          </div>
        </div>
      ) : null}
    </article>
  );
}

export function DuplicateAudit() {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<ReviewFilter>("all");
  const [sort, setSort] = useState<AuditSort>("most_storage");
  const [audit, setAudit] = useState<DuplicateAuditData>();
  const [error, setError] = useState<string>();
  const [expandedSha, setExpandedSha] = useState<string | null>(null);
  const [selectedCanonical, setSelectedCanonical] = useState<Record<string, string>>({});
  const [reviewingSha, setReviewingSha] = useState<string>();
  const [cleaningSha, setCleaningSha] = useState<string>();
  const [notice, setNotice] = useState<string>();

  useEffect(() => {
    let cancelled = false;
    const timer = window.setTimeout(() => {
      setError(undefined);
      void getDuplicateAudit({ query, reviewState: filter, sort }).then((result) => {
        if (cancelled) return;
        setAudit(result);
        setSelectedCanonical((current) => {
          const next = { ...current };
          for (const group of result.groups) next[group.sha256] ??= group.canonical_asset_id;
          return next;
        });
      }).catch((requestError: unknown) => {
        if (!cancelled) setError(requestError instanceof Error ? requestError.message : "Duplicate audit is unavailable");
      });
    }, 200);
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [filter, query, sort]);

  const shownGroups = audit?.groups ?? EMPTY_GROUPS;

  async function confirmReview(group: DuplicateGroup) {
    const canonicalAssetId = selectedCanonical[group.sha256] ?? group.canonical_asset_id;
    setReviewingSha(group.sha256);
    setError(undefined);
    try {
      await reviewDuplicateGroup(group.sha256, canonicalAssetId);
      const refreshed = await getDuplicateAudit({ query, reviewState: filter, sort });
      setAudit(refreshed);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "The review could not be saved");
    } finally {
      setReviewingSha(undefined);
    }
  }

  async function confirmCleanup(group: DuplicateGroup) {
    const confirmed = window.confirm(
      `Optimize ${formatBytes(group.reclaimable_bytes)}? GM Studio will verify every copy again and preserve all filenames, projects, jobs, and library paths.`,
    );
    if (!confirmed) return;
    setCleaningSha(group.sha256);
    setError(undefined);
    setNotice(undefined);
    try {
      const result = await cleanupDuplicateGroup(group.sha256, group.canonical_asset_id);
      setNotice(`${result.optimized_copies} verified copies now share storage. ${formatBytes(result.bytes_reclaimed)} was reclaimed in this run.`);
      setAudit(await getDuplicateAudit({ query, reviewState: filter, sort }));
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Safe cleanup could not finish");
    } finally {
      setCleaningSha(undefined);
    }
  }

  return (
    <main className="min-h-dvh bg-[#F7F7F5] px-4 pt-[max(1.25rem,env(safe-area-inset-top))] pb-[max(2rem,env(safe-area-inset-bottom))] text-[#20211F] [color-scheme:light] sm:px-6">
      <div className="mx-auto w-full max-w-6xl">
        <header className="border-b border-[#D7D9D3] pb-5">
          <div className="flex items-center justify-between gap-4"><Link className="text-sm font-bold tracking-tight text-[#173F5F]" href="/jobs/new">GM Studio</Link><span className="inline-flex items-center gap-1.5 rounded-full border border-[#D7D9D3] bg-white px-3 py-2 font-mono text-[10px] font-bold text-[#173F5F]"><span className="size-1.5 rounded-full bg-[#3A8F63]" />PRIVATE · ONLINE</span></div>
          <div className="mt-6 flex flex-col justify-between gap-5 lg:flex-row lg:items-end">
            <div className="max-w-3xl"><p className="font-mono text-[10px] font-bold tracking-widest text-[#174D73] uppercase">Library health</p><h1 className="mt-2 text-3xl font-bold tracking-tight text-[#173F5F]">Exact duplicate audit</h1><p className="mt-3 max-w-2xl text-sm leading-6 text-[#666862]">Find byte-for-byte copies already stored on this server and choose the record that should represent each group.</p></div>
            <div className="flex flex-wrap gap-2"><Link className="inline-flex min-h-11 items-center gap-2 rounded-md border border-[#D7D9D3] bg-white px-4 text-sm font-bold text-[#173F5F]" href="/library"><LibraryIcon aria-hidden="true" className="size-4" />Media library</Link><Link className="inline-flex min-h-11 items-center rounded-md bg-[#173F5F] px-4 text-sm font-bold text-white" href="/jobs/new">Start a new job</Link></div>
          </div>
        </header>

        <aside className="mt-6 flex items-start gap-3 rounded-md border border-[#AFC7D5] bg-[#EFF6FA] p-4 text-sm"><ShieldCheckIcon aria-hidden="true" className="mt-0.5 size-5 shrink-0 text-[#174D73]" /><div><p className="font-bold text-[#173F5F]">Safe exact-copy cleanup</p><p className="mt-1 leading-5 text-[#666862]">Canonical review is read-only. Cleanup is a separate confirmed step that preserves every record and path while exact copies share physical storage.</p></div></aside>

        {!audit && !error ? <div className="flex min-h-64 items-center justify-center"><LoaderCircleIcon aria-label="Loading duplicate audit" className="size-8 animate-spin text-[#173F5F]" /></div> : null}
        {error ? <p className="mt-5 rounded-md border border-[#D8B4AA] bg-[#FFF7F4] p-4 text-sm text-[#A23B2A]" role="alert">{error}</p> : null}
        {notice ? <p className="mt-5 rounded-md border border-[#B8D8C5] bg-[#F2FAF5] p-4 text-sm font-medium text-[#307455]" role="status">{notice}</p> : null}
        {audit ? (
          <div className="space-y-6 py-6">
            <section aria-label="Audit summary" className="grid grid-cols-2 gap-3 lg:grid-cols-4">
              <Metric icon={<FilesIcon className="size-4" />} label="Originals scanned" note="Analyzed library media" value={audit.summary.originals_scanned.toLocaleString()} />
              <Metric icon={<CopyCheckIcon className="size-4" />} label="Duplicate groups" note={`${audit.summary.unreviewed_groups} still unreviewed`} value={audit.summary.duplicate_groups.toLocaleString()} />
              <Metric icon={<Layers3Icon className="size-4" />} label="Storage optimized" note={`${audit.summary.redundant_copies} logical copies retained`} value={audit.summary.optimized_copies.toLocaleString()} />
              <Metric highlighted icon={<HardDriveIcon className="size-4" />} label="Reclaimable storage" note="Estimate only" value={formatBytes(audit.summary.reclaimable_bytes)} />
            </section>

            <section aria-label="Duplicate filters" className="rounded-md border border-[#D7D9D3] bg-white p-4">
              <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                <label className="relative block min-w-0 flex-1 lg:max-w-xl"><span className="sr-only">Search duplicate groups</span><SearchIcon aria-hidden="true" className="pointer-events-none absolute top-1/2 left-4 size-4 -translate-y-1/2 text-[#666862]" /><input className="h-12 w-full rounded-md border border-[#D7D9D3] bg-[#F7F7F5] pr-4 pl-11 text-sm outline-none placeholder:text-[#777A75] focus:border-[#173F5F] focus:ring-2 focus:ring-[#173F5F]/10" onChange={(event) => setQuery(event.currentTarget.value)} placeholder="Search filenames, projects or checksum" type="search" value={query} /></label>
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
                  <div aria-label="Review status" className="inline-flex rounded-md border border-[#D7D9D3] bg-[#F7F7F5] p-1" role="group">{(["all", "unreviewed", "reviewed"] as const).map((value) => <button aria-pressed={filter === value} className={`min-h-10 rounded px-3 text-sm font-bold ${filter === value ? "bg-white text-[#173F5F] shadow-sm" : "text-[#666862]"}`} key={value} onClick={() => setFilter(value)} type="button">{value === "all" ? "All" : value === "unreviewed" ? "Unreviewed" : "Reviewed"}</button>)}</div>
                  <label className="flex min-h-12 items-center gap-2 rounded-md border border-[#D7D9D3] bg-white px-3"><span className="font-mono text-[9px] font-bold tracking-wide text-[#666862] uppercase">Sort</span><select className="bg-transparent text-sm font-bold text-[#20211F] outline-none" onChange={(event) => setSort(event.currentTarget.value as AuditSort)} value={sort}><option value="most_storage">Most storage</option><option value="most_copies">Most copies</option><option value="newest">Newest found</option></select></label>
                </div>
              </div>
            </section>

            {shownGroups.length ? <section aria-label="Exact duplicate groups" className="space-y-4">{shownGroups.map((group) => <GroupCard cleaning={cleaningSha === group.sha256} expanded={expandedSha === group.sha256} group={group} key={group.sha256} onCleanup={() => void confirmCleanup(group)} onExpand={() => setExpandedSha((current) => current === group.sha256 ? null : group.sha256)} onReview={() => void confirmReview(group)} onSelectCanonical={(assetId) => setSelectedCanonical((current) => ({ ...current, [group.sha256]: assetId }))} reviewing={reviewingSha === group.sha256} selectedCanonicalId={selectedCanonical[group.sha256] ?? group.canonical_asset_id} />)}</section> : <section className="rounded-md border border-dashed border-[#C7CBD0] bg-white p-8 text-center"><CopyCheckIcon aria-hidden="true" className="mx-auto size-7 text-[#174D73]" /><h2 className="mt-3 text-base font-bold text-[#173F5F]">{audit.summary.duplicate_groups ? "No groups match these filters" : "No exact duplicates found"}</h2><p className="mx-auto mt-2 max-w-lg text-sm leading-6 text-[#666862]">{audit.summary.duplicate_groups ? "Try another filename, project, checksum, or review filter." : "Every analyzed original currently has a unique SHA-256. Similar-looking takes are intentionally not treated as exact duplicates."}</p></section>}

            <section className="rounded-md border border-dashed border-[#C7CBD0] bg-white/50 p-5 text-center"><p className="text-sm font-bold text-[#20211F]">Only verified byte-for-byte matches appear here.</p><p className="mt-1 text-xs leading-5 text-[#666862]">Visually similar clips and repeated takes will be handled later as suggestions, never automatic duplicates.</p></section>
          </div>
        ) : null}
        <footer className="flex flex-col items-center justify-between gap-4 border-t border-[#D7D9D3] pt-5 text-sm sm:flex-row"><p className="font-mono text-[10px] text-[#666862]">SHA-256 VERIFIED · PATHS PRESERVED · AUDITED</p><div className="flex gap-5"><Link className="font-bold text-[#173F5F] underline underline-offset-4" href="/library">Media library</Link><Link className="font-bold text-[#173F5F] underline underline-offset-4" href="/jobs/new">Start a new job</Link></div></footer>
      </div>
    </main>
  );
}
