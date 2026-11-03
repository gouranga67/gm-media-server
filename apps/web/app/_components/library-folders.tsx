"use client";

import { useState } from "react";
import { FolderIcon, FolderOpenIcon, HeartIcon, InboxIcon, ImagesIcon, MenuIcon, PlusIcon, Trash2Icon } from "lucide-react";
import { libraryAssetThumbnailUrl, type LibraryCollection } from "@/lib/media-api";

export function LibraryFolders({ folders, active, busy, onOpen, onNew }: {
  readonly folders: readonly LibraryCollection[]; readonly active: string; readonly busy: boolean;
  readonly onOpen: (id: string) => void; readonly onNew: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const shortcuts = [
    { id: "home", name: "Folders", Icon: FolderOpenIcon },
    { id: "all", name: "All media", Icon: ImagesIcon },
    { id: "unfiled", name: "Not in folders", Icon: InboxIcon },
    { id: "favorites", name: "Favourites", Icon: HeartIcon },
    { id: "trash", name: "Trash", Icon: Trash2Icon },
  ];
  function open(id: string) { onOpen(id); setExpanded(false); }
  const itemClass = (id: string) => `flex min-h-11 w-full items-center gap-3 rounded-md px-3 py-2 text-left text-sm ${active === id ? "bg-[#E4EBEF] font-bold text-[#173F5F]" : "text-[#666862] hover:bg-white"}`;
  return <aside aria-label="Library folders" className="min-w-0 lg:sticky lg:top-4 lg:self-start">
    <button aria-expanded={expanded} aria-controls="library-folder-navigation" className="flex min-h-11 w-full items-center gap-2 rounded-md border border-[#D7D9D3] bg-white px-3 text-sm font-bold text-[#173F5F] lg:hidden" onClick={() => setExpanded(!expanded)} type="button"><MenuIcon aria-hidden="true" className="size-4" />Browse folders</button>
    <div className={`${expanded ? "block" : "hidden"} mt-2 lg:mt-0 lg:block`} id="library-folder-navigation">
      <nav aria-label="Library locations" className="space-y-1">{shortcuts.map(({ id, name, Icon }) => <button aria-current={active === id ? "page" : undefined} className={itemClass(id)} disabled={busy} key={id} onClick={() => open(id)} type="button"><Icon aria-hidden="true" className="size-4 shrink-0" />{name}</button>)}</nav>
      <div className="mt-6 flex items-center justify-between px-3"><h2 className="text-xs font-bold uppercase tracking-wider text-[#666862]">Your folders</h2><button aria-label="New folder" className="flex size-11 items-center justify-center text-[#173F5F]" disabled={busy} onClick={onNew} type="button"><PlusIcon aria-hidden="true" className="size-4" /></button></div>
      <nav aria-label="Saved folders" className="max-h-72 space-y-1 overflow-y-auto lg:max-h-[50vh]">{folders.map((folder) => <button aria-current={active === folder.id ? "page" : undefined} className={itemClass(folder.id)} disabled={busy} key={folder.id} onClick={() => open(folder.id)} type="button"><FolderIcon aria-hidden="true" className="size-4 shrink-0" /><span className="min-w-0 flex-1 truncate">{folder.name}</span><span className="text-xs tabular-nums">{folder.asset_count}</span></button>)}</nav>
      {!folders.length ? <p className="px-3 text-xs leading-5 text-[#666862]">Group footage by product, subject or campaign.</p> : null}
    </div>
  </aside>;
}

export function LibraryFolderCards({ folders, busy, onOpen, onNew }: {
  readonly folders: readonly LibraryCollection[]; readonly busy: boolean;
  readonly onOpen: (id: string) => void; readonly onNew: () => void;
}) {
  return <section aria-label="Folder overview" className="grid grid-cols-2 gap-3 xl:grid-cols-3">
    {folders.map((folder) => <button aria-label={`Open folder ${folder.name}`} className="group flex min-w-0 flex-col overflow-hidden rounded-lg border border-[#D7D9D3] bg-white text-left transition-colors hover:border-[#173F5F] disabled:opacity-50" disabled={busy} key={folder.id} onClick={() => onOpen(folder.id)} type="button">
      <span className="relative flex aspect-[16/9] items-center justify-center overflow-hidden bg-[#E4EBEF] text-[#446579]">{folder.cover_asset_id ? <img alt="" className="size-full object-cover" loading="lazy" src={libraryAssetThumbnailUrl(folder.cover_asset_id)} /> : <FolderIcon aria-hidden="true" className="size-12" />}<span className="absolute bottom-2 left-2 rounded bg-white/95 p-1.5"><FolderIcon aria-hidden="true" className="size-4" /></span></span>
      <span className="block p-3 sm:p-4"><strong className="block truncate text-sm text-[#173F5F] sm:text-base">{folder.name}</strong><span className="mt-1 block text-xs text-[#666862]">{folder.asset_count} {folder.asset_count === 1 ? "item" : "items"}</span>{folder.description ? <span className="mt-2 line-clamp-2 block text-xs text-[#666862]">{folder.description}</span> : null}</span>
    </button>)}
    <button className="flex min-h-44 flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-[#AFC7D5] text-sm font-bold text-[#173F5F] hover:bg-white disabled:opacity-50" disabled={busy} onClick={onNew} type="button"><PlusIcon aria-hidden="true" className="size-6" />Create a folder</button>
  </section>;
}
