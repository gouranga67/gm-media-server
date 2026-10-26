import type { ManagedLibraryAsset, MediaRole } from "@/lib/media-api";

export const mediaRoleLabels: Record<MediaRole, string> = {
  auto: "Unsorted video", talking: "Talking footage", broll: "B-roll",
};
export function libraryRoleLabel(asset: { readonly mime_type: string; readonly media_role?: MediaRole }) {
  if (asset.mime_type.startsWith("image/")) return "Photo";
  if (asset.mime_type.startsWith("audio/")) return "Audio";
  return mediaRoleLabels[asset.media_role ?? "auto"];
}
export type LibraryView = "all" | "talking" | "broll" | "image" | "audio" | "unsorted" | "trash";
export const libraryViews: readonly { readonly id: LibraryView; readonly label: string }[] = [
  { id: "all", label: "All media" }, { id: "talking", label: "Talking footage" },
  { id: "broll", label: "B-roll" }, { id: "image", label: "Photos" },
  { id: "audio", label: "Audio" }, { id: "unsorted", label: "Unsorted" }, { id: "trash", label: "Trash" },
];
export function matchesLibraryView(asset: ManagedLibraryAsset, view: LibraryView) {
  if (view === "trash") return asset.library_status === "archived";
  if (asset.library_status !== "active") return false;
  if (view === "all") return true;
  if (view === "image" || view === "audio") return asset.mime_type.startsWith(`${view}/`);
  return asset.mime_type.startsWith("video/") && (asset.media_role ?? "auto") === (view === "unsorted" ? "auto" : view);
}
