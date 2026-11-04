"use client";

import { useEffect, useState } from "react";
import { readMediaBasket, writeMediaBasket } from "@/lib/media-basket";
import {
  browseLibrary, getLibraryCollections, getLibraryPickerProjects, getSelectedLibraryAssets, searchCatalog,
  type CatalogSearchResult, type LibraryAsset, type LibraryCollection,
} from "@/lib/media-api";

const message = (error: unknown) => error instanceof Error ? error.message : "Server media could not be loaded.";
type Filters = { query: string; kind: "all" | "video" | "image" | "audio"; purpose: string; projectId: string; folderId: string; offset: number };
const initialFilters: Filters = { query: "", kind: "all", purpose: "all", projectId: "all", folderId: "", offset: 0 };

export function useJobLibrary() {
  const [filters, setFilters] = useState(initialFilters);
  const [revision, setRevision] = useState(0);
  const [folders, setFolders] = useState<readonly LibraryCollection[]>([]);
  const [projects, setProjects] = useState<readonly { readonly id: string; readonly name: string }[]>([]);
  const [optionsError, setOptionsError] = useState<string>();
  const [selectedIds, setSelectedIds] = useState<ReadonlySet<string>>(new Set());
  const [selectedRecords, setSelectedRecords] = useState<Readonly<Record<string, LibraryAsset>>>({});
  const [checkedIds, setCheckedIds] = useState<ReadonlySet<string>>(new Set());
  const [basketLoaded, setBasketLoaded] = useState(false);
  const [selectionError, setSelectionError] = useState<string>();
  const [search, setSearch] = useState<{ key: string; matches: ReadonlyMap<string, CatalogSearchResult>; error?: string }>();
  const [page, setPage] = useState<{ key: string; items: readonly LibraryAsset[]; total: number }>();
  const [failure, setFailure] = useState<{ key: string; message: string }>();
  const normalizedQuery = filters.query.trim();
  const searchKey = JSON.stringify([normalizedQuery, filters.kind, filters.projectId, revision]);
  const searching = normalizedQuery.length >= 2 && search?.key !== searchKey;
  const matches = search?.key === searchKey ? search.matches : new Map<string, CatalogSearchResult>();
  const pageKey = JSON.stringify([filters, searchKey, search?.key]);

  useEffect(() => { setSelectedIds(new Set(readMediaBasket())); setBasketLoaded(true); }, []);
  useEffect(() => { if (basketLoaded) writeMediaBasket([...selectedIds]); }, [basketLoaded, selectedIds]);
  useEffect(() => {
    let active = true;
    Promise.all([getLibraryCollections(), getLibraryPickerProjects()]).then(([collections, choices]) => {
      if (active) { setFolders(collections); setProjects(choices); setOptionsError(undefined); }
    }).catch(error => { if (active) setOptionsError(message(error)); });
    return () => { active = false; };
  }, [revision]);

  useEffect(() => {
    if (!basketLoaded) return;
    // Selections have their own bounded metadata lookup, independent of the open page.
    const missing = [...selectedIds].filter(id => !selectedRecords[id]);
    if (!missing.length) { setSelectionError(undefined); return; }
    let active = true;
    const groups = Array.from({ length: Math.ceil(missing.length / 100) }, (_, index) => missing.slice(index * 100, index * 100 + 100));
    Promise.all(groups.map(getSelectedLibraryAssets)).then(results => {
      if (!active) return;
      setSelectedRecords(current => ({ ...current, ...Object.fromEntries(results.flat().map(asset => [asset.id, asset])) }));
      setCheckedIds(current => new Set([...current, ...missing])); setSelectionError(undefined);
    }).catch(error => { if (active) setSelectionError(message(error)); });
    return () => { active = false; };
    // Records are hydrated by this effect or a selected row, not a reason to refetch.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [basketLoaded, selectedIds, revision]);

  useEffect(() => {
    if (normalizedQuery.length < 2) return;
    let active = true;
    const timer = window.setTimeout(() => {
      searchCatalog({ query: normalizedQuery, mediaKind: filters.kind, projectId: filters.projectId }).then(result => {
        if (!active) return;
        const found = new Map<string, CatalogSearchResult>();
        for (const row of result.results) if (!found.has(row.asset_id)) found.set(row.asset_id, row);
        setSearch({ key: searchKey, matches: found });
      }).catch(error => { if (active) setSearch({ key: searchKey, matches: new Map(), error: message(error) }); });
    }, 250);
    return () => { active = false; window.clearTimeout(timer); };
  }, [searchKey, normalizedQuery, filters.kind, filters.projectId]);

  useEffect(() => {
    if (searching) return;
    let active = true;
    void browseLibrary({ view: filters.purpose === "all" ? "all" : filters.purpose === "auto" ? "unsorted" : filters.purpose,
      category: "all", favorite: false, collectionId: filters.folderId === "unfiled" ? "" : filters.folderId,
      unfiled: filters.folderId === "unfiled", query: normalizedQuery, matchIds: [...matches.keys()],
      copies: false, sort: "newest", offset: filters.offset, mediaKind: filters.kind, projectId: filters.projectId, forEditing: true,
    }).then(result => { if (active) { setPage({ key: pageKey, items: result.items, total: result.total }); setFailure(undefined); } })
      .catch(error => { if (active) setFailure({ key: pageKey, message: message(error) }); });
    return () => { active = false; };
    // pageKey covers every filter and the settled search identity; paging reuses its results.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pageKey, searching]);

  function toggle(asset: LibraryAsset) {
    if (!selectedIds.has(asset.id)) setSelectedRecords(current => ({ ...current, [asset.id]: asset }));
    else setSelectedRecords(current => Object.fromEntries(Object.entries(current).filter(([id]) => id !== asset.id)));
    setSelectedIds(current => { const next = new Set(current); if (next.has(asset.id)) next.delete(asset.id); else next.add(asset.id); return next; });
  }
  function remove(id: string) {
    setSelectedRecords(current => Object.fromEntries(Object.entries(current).filter(([value]) => value !== id)));
    setSelectedIds(current => new Set([...current].filter(value => value !== id)));
  }
  const unavailableIds = [...selectedIds].filter(id => checkedIds.has(id) && !selectedRecords[id]);
  const selectedAssets = [...selectedIds].map(id => selectedRecords[id]).filter((asset): asset is LibraryAsset => Boolean(asset));
  return {
    filters, changeFilters: (patch: Partial<Filters>) => setFilters(current => ({ ...current, ...patch, offset: patch.offset ?? 0 })),
    folders, projects, optionsError, selectedIds, selectedAssets, unavailableIds, selectionError,
    selectionReady: basketLoaded && selectedAssets.length === selectedIds.size && selectedIds.size <= 100,
    remove, clear: () => { setSelectedIds(new Set()); setSelectedRecords({}); }, toggle, refresh: () => setRevision(current => current + 1),
    matches, searching, searchError: search?.key === searchKey ? search.error : undefined,
    items: page?.key === pageKey ? page.items : [], total: page?.key === pageKey ? page.total : 0,
    loading: searching || (page?.key !== pageKey && failure?.key !== pageKey),
    error: failure?.key === pageKey ? failure.message : undefined,
  };
}
