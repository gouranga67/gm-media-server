import { libraryViews, mediaCategories, type LibraryView } from "./library-organization";
import type { MediaCategory } from "./media-api";

const KEY = "gm-studio:library-browser:v1";
export type LibraryBrowserState = {
  home: boolean; folder: string; unfiled: boolean; view: LibraryView;
  layout: "grid" | "list"; query: string; sort: string; category: MediaCategory | "all";
  favorites: boolean; copies: boolean;
};
export const defaultLibraryBrowser: LibraryBrowserState = {
  home: true, folder: "", unfiled: false, view: "all", layout: "grid", query: "",
  sort: "newest", category: "all", favorites: false, copies: false,
};
export function readLibraryBrowser(): LibraryBrowserState {
  try {
    const value = JSON.parse(window.sessionStorage.getItem(KEY) ?? "null");
    if (!value || typeof value !== "object") return defaultLibraryBrowser;
    return {
      home: value.home !== false, folder: typeof value.folder === "string" ? value.folder.slice(0, 120) : "",
      unfiled: value.unfiled === true,
      view: libraryViews.some((item) => item.id === value.view) ? value.view : "all",
      layout: value.layout === "list" ? "list" : "grid",
      query: typeof value.query === "string" ? value.query.slice(0, 160) : "",
      sort: ["newest", "name", "largest"].includes(value.sort) ? value.sort : "newest",
      category: value.category === "all" || mediaCategories.some((item) => item.id === value.category) ? value.category : "all",
      favorites: value.favorites === true, copies: value.copies === true,
    };
  } catch { return defaultLibraryBrowser; }
}
export function saveLibraryBrowser(value: LibraryBrowserState) {
  try { window.sessionStorage.setItem(KEY, JSON.stringify(value)); } catch { /* Browsing works without storage. */ }
}
export function saveLibraryScroll(value: number) {
  try { window.sessionStorage.setItem(`${KEY}:scroll`, String(value)); } catch { /* Optional per-tab convenience. */ }
}
export function readLibraryScroll() {
  try { const value = Number(window.sessionStorage.getItem(`${KEY}:scroll`)); return Number.isFinite(value) && value > 0 ? value : 0; } catch { return 0; }
}
