// Per-tab source selection only; never stores media, tokens, transcripts or credentials.
export const MEDIA_BASKET_KEY = "gm-studio:media-basket:v1";
export function readMediaBasket(): readonly string[] {
  try { const value: unknown = JSON.parse(window.sessionStorage.getItem(MEDIA_BASKET_KEY) ?? "[]"); return Array.isArray(value) ? [...new Set(value.filter((id): id is string => typeof id === "string" && /^[a-f0-9-]{36}$/i.test(id)))].slice(0, 500) : []; } catch { return []; }
}
export function writeMediaBasket(ids: readonly string[]) { try { window.sessionStorage.setItem(MEDIA_BASKET_KEY, JSON.stringify([...new Set(ids)].slice(0, 500))); } catch { /* Editing still works without session storage. */ } }
