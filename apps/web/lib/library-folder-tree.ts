import type { LibraryCollection } from "./media-api";

export const MAX_FOLDER_DEPTH = 4;
const indexes = new WeakMap<readonly LibraryCollection[], Map<string, LibraryCollection>>();

function folderIndex(folders: readonly LibraryCollection[]) {
  let index = indexes.get(folders);
  if (!index) { index = new Map(folders.map((folder) => [folder.id, folder])); indexes.set(folders, index); }
  return index;
}

export function folderTrail(folders: readonly LibraryCollection[], id: string): readonly LibraryCollection[] {
  const byId = folderIndex(folders);
  const path: LibraryCollection[] = [], seen = new Set<string>();
  let current = byId.get(id);
  while (current && !seen.has(current.id) && path.length < MAX_FOLDER_DEPTH) {
    path.unshift(current); seen.add(current.id);
    current = current.parent_id ? byId.get(current.parent_id) : undefined;
  }
  return path;
}

export function folderLabel(folders: readonly LibraryCollection[], id: string): string {
  return folderTrail(folders, id).map((folder) => folder.name).join(" / ");
}

export function folderTree(folders: readonly LibraryCollection[]): readonly { folder: LibraryCollection; depth: number }[] {
  const children = new Map<string, LibraryCollection[]>();
  for (const folder of folders) {
    const parent = folder.parent_id ?? "";
    const siblings = children.get(parent);
    if (siblings) siblings.push(folder);
    else children.set(parent, [folder]);
  }
  const result: { folder: LibraryCollection; depth: number }[] = [], seen = new Set<string>();
  function append(parent: string, depth: number) {
    if (depth >= MAX_FOLDER_DEPTH) return;
    for (const folder of (children.get(parent) ?? []).sort((a, b) => a.name.localeCompare(b.name) || a.id.localeCompare(b.id))) {
      if (seen.has(folder.id)) continue;
      seen.add(folder.id); result.push({ folder, depth: Math.min(depth, MAX_FOLDER_DEPTH - 1) });
      append(folder.id, depth + 1);
    }
  }
  append("", 0);
  // Keep malformed legacy/orphan data reachable without an unbounded recursion.
  for (const folder of folders) if (!seen.has(folder.id)) {
    seen.add(folder.id); result.push({ folder, depth: 0 }); append(folder.id, 1);
  }
  return result;
}

export function folderDestinations(folders: readonly LibraryCollection[], moving?: string): readonly LibraryCollection[] {
  const subtree = moving ? folders.filter((folder) => folderTrail(folders, folder.id).some((item) => item.id === moving)) : [];
  const subtreeIds = new Set(subtree.map((folder) => folder.id));
  const height = moving ? subtree.reduce((maximum, folder) => {
    const trail = folderTrail(folders, folder.id);
    return Math.max(maximum, trail.length - trail.findIndex((item) => item.id === moving));
  }, 1) : 1;
  return folderTree(folders).map(({ folder }) => folder).filter((folder) =>
    !subtreeIds.has(folder.id) && folderTrail(folders, folder.id).length + height <= MAX_FOLDER_DEPTH);
}
