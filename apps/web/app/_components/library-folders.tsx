"use client";

import { useState } from "react";
import { FolderIcon, FolderOpenIcon, HeartIcon, InboxIcon, ImagesIcon, MenuIcon, PlusIcon, Trash2Icon } from "lucide-react";
import { libraryAssetThumbnailUrl, type LibraryCollection } from "@/lib/media-api";
import { folderLabel, folderTree, folderDestinations } from "@/lib/library-folder-tree";

export function LibraryFolders({ folders, active, busy, onOpen, onNew }: {
  readonly folders: readonly LibraryCollection[]; readonly active: string; readonly busy: boolean;
  readonly onOpen: (id: string) => void; readonly onNew: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const shortcuts = [
    { id: "home", name: "Folders", Icon: FolderOpenIcon },
    { id: "inbox", name: "Inbox", Icon: InboxIcon },
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
      <nav aria-label="Saved folders" className="max-h-72 space-y-1 overflow-y-auto lg:max-h-[50vh]">{folderTree(folders).map(({ folder, depth }) => <button aria-current={active === folder.id ? "page" : undefined} title={folderLabel(folders, folder.id)} style={{ paddingLeft: 12 + depth * 16 }} className={itemClass(folder.id)} disabled={busy} key={folder.id} onClick={() => open(folder.id)} type="button"><FolderIcon aria-hidden="true" className="size-4 shrink-0" /><span className="min-w-0 flex-1 break-words line-clamp-2">{folder.name}</span><span className="text-xs tabular-nums">{folder.asset_count}</span></button>)}</nav>
      {!folders.length ? <p className="px-3 text-xs leading-5 text-[#666862]">Group footage by product, subject or campaign.</p> : null}
    </div>
  </aside>;
}

export function LibraryFolderCards({ folders, busy, onOpen, onNew, compact = false, canCreate = true }: {
  readonly folders: readonly LibraryCollection[]; readonly busy: boolean;
  readonly onOpen: (id: string) => void; readonly onNew: () => void;
  readonly compact?: boolean;
  readonly canCreate?: boolean;
}) {
  return <section aria-label="Folder overview" className="grid grid-cols-2 gap-3 xl:grid-cols-3">
    {folders.map((folder) => <button aria-label={`Open folder ${folder.name}`} className="group flex min-w-0 flex-col overflow-hidden rounded-lg border border-[#D7D9D3] bg-white text-left transition-colors hover:border-[#173F5F] disabled:opacity-50" disabled={busy} key={folder.id} onClick={() => onOpen(folder.id)} type="button">
      {!compact ? <span className="relative flex aspect-[16/9] items-center justify-center overflow-hidden bg-[#E4EBEF] text-[#446579]">{folder.cover_asset_id ? <img alt="" className="size-full object-cover" loading="lazy" src={libraryAssetThumbnailUrl(folder.cover_asset_id)} /> : <FolderIcon aria-hidden="true" className="size-12" />}<span className="absolute bottom-2 left-2 rounded bg-white/95 p-1.5"><FolderIcon aria-hidden="true" className="size-4" /></span></span> : null}
      <span className="block p-3 sm:p-4"><strong className="block break-words text-sm text-[#173F5F] sm:text-base">{folder.name}</strong><span className="mt-1 block text-xs text-[#666862]">{folder.asset_count} {folder.asset_count === 1 ? "item" : "items"} · {folder.child_count ?? 0} {(folder.child_count ?? 0) === 1 ? "subfolder" : "subfolders"}</span>{folder.description ? <span className="mt-2 line-clamp-2 block text-xs text-[#666862]">{folder.description}</span> : null}</span>
    </button>)}
    {canCreate ? <button className={`flex ${compact ? "min-h-24" : "min-h-44"} flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-[#AFC7D5] text-sm font-bold text-[#173F5F] hover:bg-white disabled:opacity-50`} disabled={busy} onClick={onNew} type="button"><PlusIcon aria-hidden="true" className="size-6" />{compact ? "Create a subfolder" : "Create a folder"}</button> : <p className="col-span-full text-xs text-[#666862]">Four folder levels maximum. You can still add media here.</p>}
  </section>;
}

export type FolderFormMode = "new" | "rename" | "delete" | "move";

export function LibraryFolderSettings({ mode, folders, current, name, parent, busy, onName, onParent, onSave, onCancel }: {
  readonly mode: FolderFormMode; readonly folders: readonly LibraryCollection[];
  readonly current?: LibraryCollection; readonly name: string; readonly parent: string; readonly busy: boolean;
  readonly onName: (value: string) => void; readonly onParent: (value: string) => void;
  readonly onSave: () => void; readonly onCancel: () => void;
}) {
  const control = "min-h-11 rounded-md border border-[#D7D9D3] bg-white px-3 text-sm font-medium text-[#173F5F] disabled:opacity-50";
  const hasChildren = Boolean(current && folders.some((folder) => folder.parent_id === current.id));
  return <section aria-label="Folder settings" className="mb-4 rounded-lg border border-[#AFC7D5] bg-white p-4">
    <h3 className="mb-3 text-sm font-bold text-[#173F5F]">{mode === "new" ? "New folder" : mode === "move" ? "Move folder" : mode === "rename" ? "Rename folder" : "Remove folder"}</h3>
    {mode === "delete" ? <>
      <p className="text-sm leading-6 text-[#173F5F]">Remove “{current?.name}”? {hasChildren ? "Move or remove its subfolders first. " : ""}Only the folder grouping is removed. Its media remains in All media, other folders and existing edits.</p>
      <div className="mt-3 flex gap-2"><button className={`${control} text-[#A23B2A]`} disabled={busy || hasChildren} onClick={onSave} type="button">Confirm remove folder</button><button className={control} disabled={busy} onClick={onCancel} type="button">Cancel</button></div>
    </> : <>
      <form className="flex flex-wrap items-end gap-3" onSubmit={(event) => { event.preventDefault(); onSave(); }}>
        {mode !== "move" ? <label className="min-w-0 basis-full flex-1 text-xs font-bold text-[#173F5F] sm:basis-48">Folder name<input autoFocus className={`${control} mt-1 w-full`} maxLength={120} onChange={(event) => onName(event.currentTarget.value)} placeholder="e.g. Castor oil cream" value={name} /></label> : null}
        {mode !== "rename" ? <label className="min-w-0 basis-full flex-1 text-xs font-bold text-[#173F5F] sm:basis-48">Parent folder<select autoFocus={mode === "move"} aria-label="Parent folder" className={`${control} mt-1 w-full`} disabled={busy} value={parent} onChange={(event) => onParent(event.currentTarget.value)}>
          <option value="">Top level</option>{folderDestinations(folders, mode === "move" ? current?.id : undefined).map((folder) => <option key={folder.id} value={folder.id}>{folderLabel(folders, folder.id)}</option>)}
        </select></label> : null}
        <button className={control} disabled={busy || (mode !== "move" && !name.trim()) || (mode === "move" && parent === (current?.parent_id ?? ""))} type="submit">{mode === "new" ? "Create folder" : mode === "move" ? "Move folder" : "Save folder name"}</button>
        <button className={control} disabled={busy} onClick={onCancel} type="button">Cancel</button>
      </form>
      <p className="mt-3 text-xs leading-5 text-[#666862]">{mode === "move" ? "Subfolders move with this folder. Media and existing edits keep working." : "Use a unique name across your library, such as Cream B-roll. Up to four folder levels."}</p>
    </>}
  </section>;
}
