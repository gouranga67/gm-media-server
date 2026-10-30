"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { CreativeImportError, importCreativeAsset } from "@/lib/media-api";

type Entry = {
  id: string;
  file: File;
  title: string;
  source: string;
  state: "pending" | "uploading" | "imported" | "duplicate" | "failed";
  error?: string;
};
const field =
  "mt-1 min-h-11 w-full rounded-md border border-[#C7CBD0] bg-white px-3 text-sm text-[#20211F]";
const statusText = {
  pending: "Ready to import",
  uploading: "Importing…",
  imported: "Imported",
  duplicate: "Already in library",
  failed: "Needs attention",
};

function LocalPreview({ file }: { readonly file: File }) {
  const [url, setUrl] = useState("");
  useEffect(() => {
    const value = URL.createObjectURL(file);
    setUrl(value);
    return () => URL.revokeObjectURL(value);
  }, [file]);
  if (!url)
    return <p className="mt-2 text-xs text-[#666862]">Preparing preview…</p>;
  if (file.type.startsWith("image/"))
    return (
      <img
        alt={`Preview of ${file.name}`}
        src={url}
        className="mt-2 h-16 max-w-24 object-contain"
      />
    );
  return (
    <audio
      aria-label={`Preview ${file.name}`}
      className="mt-2 w-full max-w-xs"
      controls
      preload="none"
      src={url}
    />
  );
}

export function CreativeBatchImport({
  onImported,
}: {
  readonly onImported: () => Promise<void>;
}) {
  const [entries, setEntries] = useState<readonly Entry[]>([]);
  const [kind, setKind] = useState("music");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const stop = useRef(false);
  const alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
      stop.current = true;
    };
  }, []);
  function update(id: string, change: Partial<Entry>) {
    if (alive.current)
      setEntries((old) =>
        old.map((row) => (row.id === id ? { ...row, ...change } : row)),
      );
  }
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const waiting = entries.filter(
      (row) => row.state === "pending" || row.state === "failed",
    );
    if (!waiting.length) return;
    if (
      waiting.some(
        (row) => !row.title.trim() || !/^https:\/\//i.test(row.source),
      )
    ) {
      setNotice(
        "Give every file a title and its HTTPS source page before importing.",
      );
      return;
    }
    stop.current = false;
    setBusy(true);
    setNotice("");
    let imported = 0,
      duplicates = 0,
      failed = 0;
    const metadata = Object.fromEntries(
      [
        "creator",
        "tags",
        "purpose",
        "mood",
        "energy",
        "license_name",
        "license_proof",
        "attribution",
        "allowed_platforms",
        "use_when",
        "avoid_when",
      ].map((key) => [key, String(form.get(key) ?? "")]),
    );
    for (const row of waiting) {
      if (stop.current) break;
      update(row.id, { state: "uploading", error: undefined });
      try {
        await importCreativeAsset(row.file, {
          ...metadata,
          kind,
          title: row.title.trim(),
          license_source_url: row.source.trim(),
          commercial_use_confirmed:
            form.get("commercial_use_confirmed") === "on",
        });
        imported++;
        update(row.id, { state: "imported" });
      } catch (error) {
        if (
          error instanceof CreativeImportError &&
          error.status === 409 &&
          error.message.includes("this exact creative file")
        ) {
          duplicates++;
          update(row.id, { state: "duplicate" });
        } else {
          failed++;
          update(row.id, {
            state: "failed",
            error: error instanceof Error ? error.message : "Import failed",
          });
        }
      }
    }
    let refreshFailed = false;
    try {
      await onImported();
    } catch {
      refreshFailed = true;
    }
    if (alive.current) {
      setBusy(false);
      setNotice(
        `${imported} imported · ${duplicates} already in library · ${failed} failed${stop.current ? " · stopped after the current file" : ""}. Completed files are kept; retry imports only unfinished files.${refreshFailed ? " The library list could not refresh. Reload to see imported files." : ""}`,
      );
    }
  }
  return (
    <details className="mt-6 rounded-md border border-[#D7D9D3] bg-white p-5">
      <summary className="min-h-11 cursor-pointer content-center font-bold text-[#173F5F]">
        Import several files
      </summary>
      <p className="mt-2 text-sm text-[#666862]">
        Preview and name each file, then import the selection. Files from one
        pack can share its licence; music needs each track’s own source page.
      </p>
      <form className="mt-4 space-y-4" onSubmit={(event) => void submit(event)}>
        <fieldset disabled={busy} className="space-y-4 disabled:opacity-70">
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="text-xs font-bold">
              Type
              <select
                className={field}
                value={kind}
                onChange={(event) => setKind(event.target.value)}
              >
                <option value="music">Music</option>
                <option value="sound_effect">Sound effects</option>
                <option value="meme_sound">Meme sounds</option>
                <option value="sticker">Stickers / emoji</option>
                <option value="gif">GIFs</option>
                <option value="meme_image">Meme images</option>
              </select>
            </label>
            <label className="text-xs font-bold">
              Files
              <input
                aria-label="Batch files"
                type="file"
                multiple
                accept={
                  kind.includes("sound") || kind === "music"
                    ? "audio/*"
                    : "image/png,image/jpeg,image/webp,image/gif"
                }
                className={`${field} py-2`}
                onChange={(event) => {
                  const files = Array.from(event.target.files ?? []);
                  if (files.length + entries.length > 50) {
                    setNotice("Import up to 50 files in one batch.");
                    event.target.value = "";
                    return;
                  }
                  setEntries((old) => [
                    ...old,
                    ...files.map((file) => ({
                      id: crypto.randomUUID(),
                      file,
                      title: file.name
                        .replace(/\.[^.]+$/, "")
                        .replace(/[_-]+/g, " "),
                      source: "",
                      state: "pending" as const,
                    })),
                  ]);
                  event.target.value = "";
                }}
              />
            </label>
          </div>
          <div className="grid gap-3 sm:grid-cols-3">
            <label className="text-xs font-bold">
              Creator
              <input name="creator" className={field} />
            </label>
            <label className="text-xs font-bold">
              Licence
              <input
                name="license_name"
                required
                className={field}
                placeholder="Pixabay Content License / CC0-1.0"
              />
            </label>
            <label className="text-xs font-bold">
              Proof / certificate note
              <input name="license_proof" className={field} />
            </label>
          </div>
          <details className="space-y-4">
            <summary className="min-h-11 cursor-pointer content-center text-sm font-bold text-[#173F5F]">
              Mood, tags & agent guidance
            </summary>
            <div className="grid gap-3 sm:grid-cols-3">
              <label className="text-xs font-bold">
                Mood
                <input
                  name="mood"
                  defaultValue="playful"
                  required
                  maxLength={80}
                  className={field}
                />
              </label>
              <label className="text-xs font-bold">
                Energy
                <select name="energy" className={field}>
                  <option value="low">Low</option>
                  <option value="medium">Medium</option>
                  <option value="high">High</option>
                </select>
              </label>
              <label className="text-xs font-bold">
                Purpose
                <select
                  name="purpose"
                  className={field}
                  defaultValue="emphasis"
                >
                  {[
                    "hook",
                    "transition",
                    "emphasis",
                    "reveal",
                    "reaction",
                    "payoff",
                  ].map((value) => (
                    <option key={value} value={value}>
                      {value}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="text-xs font-bold">
                Use when
                <input
                  name="use_when"
                  maxLength={240}
                  className={field}
                  placeholder="A product reveal or list item"
                />
              </label>
              <label className="text-xs font-bold">
                Avoid when
                <input
                  name="avoid_when"
                  maxLength={240}
                  className={field}
                  placeholder="Serious explanation or important speech"
                />
              </label>
            </div>
            <div className="grid gap-3 sm:grid-cols-3">
              <label className="text-xs font-bold">
                Tags
                <input
                  name="tags"
                  className={field}
                  placeholder="pop, playful, reveal"
                />
              </label>
              <label className="text-xs font-bold">
                Attribution
                <input name="attribution" className={field} />
              </label>
              <label className="text-xs font-bold">
                Platforms
                <input
                  name="allowed_platforms"
                  defaultValue="all_social"
                  required
                  className={field}
                />
              </label>
            </div>
          </details>
          <div className="space-y-3">
            {entries.map((row) => (
              <article
                key={row.id}
                className="rounded-md border border-[#D7D9D3] p-3"
              >
                <div className="flex flex-wrap justify-between gap-2">
                  <p className="break-all text-xs text-[#666862]">
                    {row.file.name} · {(row.file.size / 1_000_000).toFixed(1)}{" "}
                    MB
                  </p>
                  <span className="text-xs font-bold">
                    {statusText[row.state]}
                  </span>
                </div>
                <div className="grid gap-3 sm:grid-cols-2">
                  <label className="text-xs font-bold">
                    Title
                    <input
                      aria-label={`Title for ${row.file.name}`}
                      className={field}
                      value={row.title}
                      disabled={
                        row.state === "imported" || row.state === "duplicate"
                      }
                      onChange={(e) =>
                        update(row.id, { title: e.target.value })
                      }
                    />
                  </label>
                  <label className="text-xs font-bold">
                    Source page
                    <input
                      aria-label={`Source for ${row.file.name}`}
                      className={field}
                      type="url"
                      value={row.source}
                      disabled={
                        row.state === "imported" || row.state === "duplicate"
                      }
                      placeholder="https://…"
                      onChange={(e) =>
                        update(row.id, { source: e.target.value })
                      }
                    />
                  </label>
                </div>
                <LocalPreview file={row.file} />
                {row.error ? (
                  <p className="mt-2 text-sm text-[#A23B2A]" role="alert">
                    {row.error}
                  </p>
                ) : null}
                <button
                  type="button"
                  className="mt-2 min-h-11 text-xs underline"
                  onClick={() =>
                    setEntries((old) =>
                      old.filter((item) => item.id !== row.id),
                    )
                  }
                >
                  Remove from batch
                </button>
              </article>
            ))}
          </div>
          <label className="flex min-h-11 items-center gap-3 text-sm">
            <input type="checkbox" name="commercial_use_confirmed" required />I
            confirm the recorded licence permits the intended commercial use of
            these files.
          </label>
        </fieldset>
        <p role="status" aria-live="polite" className="text-sm text-[#53646F]">
          {busy
            ? `${entries.filter((row) => ["imported", "duplicate"].includes(row.state)).length} of ${entries.length} completed`
            : notice}
        </p>
        <div className="flex flex-wrap gap-3">
          <button
            className="min-h-11 rounded-md bg-[#173F5F] px-5 text-sm font-bold text-white disabled:opacity-50"
            disabled={
              busy ||
              !entries.some(
                (row) => row.state === "pending" || row.state === "failed",
              )
            }
          >
            Import unfinished files
          </button>
          {busy ? (
            <button
              type="button"
              className="min-h-11 px-4 text-sm underline"
              onClick={() => {
                stop.current = true;
              }}
            >
              Stop after current file
            </button>
          ) : null}
        </div>
      </form>
    </details>
  );
}
