"use client";

import { useState } from "react";
import { getFinishingTools, productSourceFrameUrl, type ProductTrack, type StabilizationChoice } from "@/lib/media-api";

const control = "min-h-11 w-full rounded-md border border-[#D7D9D3] bg-white px-2 text-xs text-[#173F5F] disabled:opacity-50";

export function ProductTrackingControls({ jobId, version, value, onChange, onDraftChange, disabled }: {
  readonly jobId: string; readonly version: number; readonly value: readonly ProductTrack[];
  readonly onChange: (value: readonly ProductTrack[]) => void; readonly disabled: boolean;
  readonly onDraftChange: (pending: boolean) => void;
}) {
  const [choices, setChoices] = useState<readonly StabilizationChoice[]>();
  const [selected, setSelected] = useState("");
  const [box, setBox] = useState({ x: .5, y: .5, width: .25, height: .25 });
  const [frameReady, setFrameReady] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const clip = choices?.find((c) => String(c.clip_index) === selected);
  const full = value.length >= 2 && !value.some((s) => String(s.clip_index) === selected);

  async function load() {
    setLoading(true); setError("");
    try {
      const current = await getFinishingTools(jobId);
      if (current.version !== version) throw new Error("A newer edit is available. Refresh before marking a product.");
      if (!current.product_tracking_candidates) throw new Error("Deploy the product tracking build before marking a shot.");
      setChoices(current.product_tracking_candidates);
    } catch (e) { setError(e instanceof Error ? e.message : "Could not load shots."); }
    finally { setLoading(false); }
  }

  function changeBox(field: keyof typeof box, input: number) {
    if (!Number.isFinite(input)) return;
    const next = { ...box, [field]: input / 100 };
    next.width = Math.max(.04, Math.min(.8, next.width));
    next.height = Math.max(.04, Math.min(.8, next.height));
    next.x = Math.max(next.width / 2, Math.min(1 - next.width / 2, next.x));
    next.y = Math.max(next.height / 2, Math.min(1 - next.height / 2, next.y));
    setBox(next);
    onDraftChange(true);
  }

  return <section aria-label="Marked product follow" className="rounded-md border border-[#D7D9D3] p-3">
    <h3 className="text-xs font-bold text-[#173F5F]">Follow a marked product · {value.length} of 2 shots</h3>
    <p className="mt-1 text-xs leading-5 text-[#666862]">Choose a 1–8 second main-picture shot. Mark the product in its full first source frame. Local appearance tracking follows small movements; rotation, size changes, hidden or unclear targets keep the existing framing. No AI tokens.</p>
    <button type="button" className={`${control} mt-2 w-auto px-3`} disabled={disabled || loading} onClick={() => void load()}>{loading ? "Loading shots…" : "Choose a product shot"}</button>
    <fieldset disabled={disabled || loading} className="mt-2 space-y-2">
      <legend className="sr-only">Mark the product in a source shot</legend>
      {choices ? <label className="block text-xs text-[#173F5F]">Source shot<select className={`${control} mt-1`} value={selected} onChange={(event) => {
        const index = event.target.value;
        setSelected(index); setFrameReady(false); setError("");
        const saved = value.find((s) => String(s.clip_index) === index);
        onDraftChange(Boolean(index) && !saved);
        setBox(saved ? { x: saved.x, y: saved.y, width: saved.width, height: saved.height } : { x: .5, y: .5, width: .25, height: .25 });
      }}><option value="">Choose a shot…</option>{choices.map((c) => <option key={c.clip_index} value={c.clip_index} disabled={!c.eligible}>Clip {c.clip_index + 1} · {c.duration_seconds}s{c.note ? ` · ${c.note}` : ""}</option>)}</select></label> : null}
      {clip?.eligible ? <>
        <p className="text-xs leading-5 text-[#666862]">Source {clip.source_in.toFixed(2)}–{clip.source_out.toFixed(2)}s. Tap the product to centre the box, then adjust its size. Include a detailed label or edge. This box marks what to follow; it is not a zoom control.</p>
        <div className="relative mx-auto w-full max-w-sm overflow-hidden rounded-md bg-[#EEF3F5]">
          {/* Full-source aspect: the image and marker share decoder geometry. */}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img key={selected} src={productSourceFrameUrl(jobId, version, clip.clip_index)} alt={`Full first source frame of clip ${clip.clip_index + 1}`} draggable={false}
            className="block h-auto w-full" onLoad={() => setFrameReady(true)} onError={() => { setFrameReady(false); setError("The source frame is unavailable. Refresh the page or choose another shot."); }}
            onClick={(event) => {
              if (!frameReady || disabled) return;
              const bounds = event.currentTarget.getBoundingClientRect();
              const x = (event.clientX - bounds.left) / bounds.width, y = (event.clientY - bounds.top) / bounds.height;
              setBox({ ...box, x: Math.max(box.width / 2, Math.min(1 - box.width / 2, x)), y: Math.max(box.height / 2, Math.min(1 - box.height / 2, y)) });
              onDraftChange(true);
            }} />
          {frameReady ? <div aria-hidden="true" className="pointer-events-none absolute border-2 border-[#173F5F] bg-[#173F5F]/10" style={{ boxShadow: "0 0 0 1px white", left: `${(box.x - box.width / 2) * 100}%`, top: `${(box.y - box.height / 2) * 100}%`, width: `${box.width * 100}%`, height: `${box.height * 100}%` }} /> : null}
        </div>
        <div className="grid grid-cols-2 gap-2">{(["x", "y", "width", "height"] as const).map((field) => <label className="text-xs text-[#173F5F]" key={field}>
          {({ x: "Horizontal centre (%)", y: "Vertical centre (%)", width: "Box width (%)", height: "Box height (%)" })[field]}
          <input className={`${control} mt-1`} type="number" step="0.1" min={field === "width" || field === "height" ? 4 : 0} max={field === "width" || field === "height" ? 80 : 100} value={Math.round(box[field] * 1000) / 10} onChange={(event) => changeBox(field, event.currentTarget.valueAsNumber)} />
        </label>)}</div>
        <button type="button" className={control} disabled={!frameReady || full} onClick={() => {
          onChange([...value.filter((s) => s.clip_index !== clip.clip_index), { clip_index: clip.clip_index, ...box }].sort((a, b) => a.clip_index - b.clip_index));
          onDraftChange(false);
        }}>
          {full ? "Remove a shot to add another" : value.some((s) => s.clip_index === clip.clip_index) ? "Update marked shot" : "Add marked shot"}
        </button>
      </> : null}
      {value.length ? <ul className="space-y-2 text-xs text-[#173F5F]">{value.map((s) => <li key={s.clip_index} className="flex min-h-11 items-center justify-between gap-2"><span>Clip {s.clip_index + 1} · product marked</span><button className="min-h-11 rounded-md border border-[#D7D9D3] px-3" type="button" onClick={() => {
        onChange(value.filter((c) => c.clip_index !== s.clip_index));
        if (String(s.clip_index) === selected) { setSelected(""); setFrameReady(false); onDraftChange(false); }
      }}>Remove clip {s.clip_index + 1}</button></li>)}</ul> : null}
    </fieldset>
    <p className="mt-2 text-xs leading-5 text-[#666862]">Adding a mark does not start processing. Use Create visual preview below. Review product visibility and speech sync before exporting. Timeline changes clear these marks.</p>
    {error ? <p role="alert" className="mt-2 text-xs text-[#A23B2A]">{error}</p> : null}
  </section>;
}
