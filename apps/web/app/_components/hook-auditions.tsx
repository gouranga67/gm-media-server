"use client";
import { useState } from "react";
import {
  getHookOptions,
  requestRevision,
  type HookOptions,
} from "@/lib/media-api";
export function HookAuditions({
  jobId,
  version,
  onUpdated,
}: {
  readonly jobId: string;
  readonly version: number;
  readonly onUpdated: () => void;
}) {
  const [options, setOptions] = useState<HookOptions>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function load() {
    setBusy(true);
    setError("");
    try {
      setOptions(await getHookOptions(jobId));
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "Could not inspect hook options",
      );
    } finally {
      setBusy(false);
    }
  }
  async function apply(option: HookOptions["options"][number]) {
    setBusy(true);
    setError("");
    try {
      await requestRevision(jobId, {
        note: "",
        captionCorrections: [],
        baseVersion: version,
        clipAdjustments: [{ ...option.adjustment, action: "keep" }],
      });
      onUpdated();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not make hook preview");
    } finally {
      setBusy(false);
    }
  }
  return (
    <details className="rounded-md border border-[#D7D9D3] bg-white p-4">
      <summary className="min-h-11 cursor-pointer content-center text-sm font-bold text-[#173F5F]">
        Audition recorded hooks
      </summary>
      <p className="my-3 text-xs leading-5 text-[#666862]">
        Compare up to three locally ranked spoken openings. Each choice replaces
        only the first clip in a new preview; it does not rewrite the story. No
        additional model tokens.
      </p>
      <button
        className="min-h-11 rounded border border-[#C7CBD0] px-3 text-sm text-[#173F5F]"
        disabled={busy}
        onClick={() => void load()}
        type="button"
      >
        Find recorded alternatives
      </button>
      {error ? (
        <p role="alert" className="my-3 text-xs text-[#A23B2A]">
          {error}
        </p>
      ) : null}
      {options?.options.length === 0 ? (
        <p className="mt-3 text-xs text-[#666862]">
          No safe alternative qualified. A story rebuild can make a broader
          change.
        </p>
      ) : null}
      {options?.options.map((option, index) => (
        <article
          className="mt-3 rounded border border-[#D7D9D3] p-3"
          key={index}
        >
          <p className="text-sm text-[#173F5F]">{option.text}</p>
          <p className="my-2 text-xs text-[#666862]">
            {option.source_name} · {option.adjustment.source_in.toFixed(2)}–
            {option.adjustment.source_out.toFixed(2)}s
          </p>
          <button
            className="min-h-11 text-xs font-bold text-[#173F5F] underline"
            disabled={busy || options.version !== version}
            onClick={() => void apply(option)}
            type="button"
          >
            Create preview with this opening
          </button>
        </article>
      ))}
    </details>
  );
}
