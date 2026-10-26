"use client";
import { useState, type FormEvent } from "react";
import { requestRevision, type EditorialClip } from "@/lib/media-api";

export function PreciseClipEditor({
  jobId,
  version,
  clip,
  onUpdated,
}: {
  readonly jobId: string;
  readonly version: number;
  readonly clip: EditorialClip;
  readonly onUpdated: () => void;
}) {
  const [start, setStart] = useState(clip.source_in.toFixed(3));
  const [end, setEnd] = useState(clip.source_out.toFixed(3));
  const [split, setSplit] = useState(
    ((clip.source_in + clip.source_out) / 2).toFixed(3),
  );
  const [mode, setMode] = useState("trim");
  const [transition, setTransition] = useState<
    "cut" | "dip_to_black" | "cross_dissolve"
  >("cross_dissolve");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await requestRevision(jobId, {
        note: "",
        captionCorrections: [],
        baseVersion: version,
        clipAdjustments: [
          {
            clip_index: clip.clip_index,
            clip_id: clip.clip_id || undefined,
            action: "keep",
            ...(mode === "transition"
              ? { transition }
              : mode === "split"
                ? { split_at: Number(split) }
                : { source_in: Number(start), source_out: Number(end) }),
          },
        ],
      });
      onUpdated();
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "The precise edit could not be made",
      );
    } finally {
      setBusy(false);
    }
  }
  const input =
    "mt-1 min-h-11 w-full rounded-md border border-[#C7CBD0] bg-white px-2 text-sm";
  return (
    <details className="mt-3 border-t border-[#E7E8E4] pt-2">
      <summary className="min-h-11 cursor-pointer content-center text-xs font-bold text-[#173F5F]">
        Precise trim &amp; split
      </summary>
      <form className="space-y-3 py-2" onSubmit={submit}>
        <p className="text-xs leading-5 text-[#666862]">
          Source seconds. Trim changes the reel length; following overlays move
          with the retained footage. Splitting preserves the cut. A new preview
          keeps this version available.
        </p>
        <label className="block text-xs">
          Operation
          <select
            className={input}
            value={mode}
            onChange={(e) => setMode(e.currentTarget.value)}
          >
            <option value="trim">Trim / slip source range</option>
            <option value="split">Split at source time</option>
            {clip.clip_index > 0 ? (
              <option value="transition">
                Picture transition into this clip
              </option>
            ) : null}
          </select>
        </label>
        {mode === "trim" ? (
          <>
            <div className="grid grid-cols-2 gap-2">
              <label className="text-xs">
                Source in
                <input
                  className={input}
                  min={0}
                  step="0.001"
                  type="number"
                  required
                  value={start}
                  onChange={(e) => setStart(e.currentTarget.value)}
                />
              </label>
              <label className="text-xs">
                Source out
                <input
                  className={input}
                  min={0.001}
                  step="0.001"
                  type="number"
                  required
                  value={end}
                  onChange={(e) => setEnd(e.currentTarget.value)}
                />
              </label>
            </div>
            {clip.words?.length ? (
              <div
                className="flex flex-wrap gap-1"
                aria-label="Word timing shortcuts"
              >
                {clip.words.slice(0, 80).map((word, i) => (
                  <span
                    className="rounded border border-[#D7D9D3] p-1 text-xs"
                    key={`${word.start}-${i}`}
                  >
                    <span>{word.text}</span>
                    <button
                      aria-label={`Start before ${word.text} at ${word.start.toFixed(2)} seconds`}
                      className="min-h-9 px-2 text-[#173F5F] underline"
                      type="button"
                      onClick={() =>
                        setStart(Math.max(0, word.start - 0.08).toFixed(3))
                      }
                    >
                      in
                    </button>
                    <button
                      aria-label={`End after ${word.text} at ${word.end.toFixed(2)} seconds`}
                      className="min-h-9 px-2 text-[#173F5F] underline"
                      type="button"
                      onClick={() => setEnd((word.end + 0.12).toFixed(3))}
                    >
                      out
                    </button>
                  </span>
                ))}
              </div>
            ) : null}
          </>
        ) : mode === "transition" ? (
          <label className="block text-xs">
            Picture transition
            <select
              className={input}
              value={transition}
              onChange={(e) =>
                setTransition(e.currentTarget.value as typeof transition)
              }
            >
              <option value="cross_dissolve">
                Soft dissolve · speech stays in time
              </option>
              <option value="dip_to_black">Dip to black</option>
              <option value="cut">Cut</option>
            </select>
          </label>
        ) : (
          <label className="block text-xs">
            Split at
            <input
              className={input}
              min={clip.source_in + 0.25}
              max={clip.source_out - 0.25}
              step="0.001"
              type="number"
              value={split}
              required
              onChange={(e) => setSplit(e.currentTarget.value)}
            />
          </label>
        )}
        {error ? (
          <p role="alert" className="text-xs text-[#A23B2A]">
            {error}
          </p>
        ) : null}
        <button
          className="min-h-11 rounded-md bg-[#173F5F] px-3 text-xs font-bold text-white disabled:opacity-50"
          disabled={
            busy || (mode === "trim" && Number(end) - Number(start) < 0.25)
          }
        >
          {busy ? "Making preview…" : "Create preview with this change"}
        </button>
      </form>
    </details>
  );
}
