"use client";

import { useState, type FormEvent } from "react";
import { getFinishingTools, requestRevision, type FinishingTools } from "@/lib/media-api";

type VisualReport = {
  readonly smart_framing?: "off" | "face";
  readonly shot_match?: boolean;
  readonly safe_overlays?: boolean;
  readonly profiles?: FinishingTools["visual_profiles"];
};

export function VisualFinishingControls({ jobId, version, report, onUpdated }: {
  readonly jobId: string;
  readonly version: number;
  readonly report?: VisualReport;
  readonly onUpdated: () => void;
}) {
  const [face, setFace] = useState(report?.smart_framing === "face");
  const [balance, setBalance] = useState(Boolean(report?.shot_match));
  const [safe, setSafe] = useState(Boolean(report?.safe_overlays));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const profiles = report?.profiles ?? [];
  const followed = profiles.filter((profile) => profile.framing_applied).length;

  async function apply(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const current = await getFinishingTools(jobId);
      if (current.version !== version) throw new Error("A newer edit is available. Refresh before changing its picture.");
      await requestRevision(jobId, {
        note: "", captionCorrections: [], baseVersion: version,
        finishingSettings: { ...current.settings, smart_framing: face ? "face" : "off", shot_match: balance,
          safe_overlays: safe, visual_profiles: [] },
      });
      onUpdated();
    } catch (error) {
      setError(error instanceof Error ? error.message : "Could not create a visual preview.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <details className="rounded-md border border-[#D7D9D3] bg-white p-5">
      <summary className="min-h-11 cursor-pointer content-center text-sm font-bold text-[#173F5F]">
        Smart visual finishing {followed ? `· ${followed} ${followed === 1 ? "shot" : "shots"} followed` : "· optional"}
      </summary>
      <p className="mt-2 text-xs leading-5 text-[#666862]">Keeps your story, speech timing, captions, music and effects. Creates a new preview with zero AI tokens.</p>
      <form onSubmit={(event) => void apply(event)} className="mt-3 space-y-2">
        <fieldset disabled={busy} className="space-y-2">
          <legend className="sr-only">Choose visual adjustments</legend>
          <label className="flex min-h-11 cursor-pointer items-start gap-3 rounded-md border border-[#D7D9D3] p-3">
            <input type="checkbox" checked={face} onChange={(event) => setFace(event.target.checked)} className="mt-1 size-4 shrink-0 accent-[#173F5F]" />
            <span className="text-xs leading-5"><strong className="block text-[#173F5F]">Follow a single face</strong><span className="text-[#666862]">Reframes selected 1.5–12 second shots before cropping. Groups, unclear faces and manual camera anchors keep their existing framing. Does not track products.</span></span>
          </label>
          <label className="flex min-h-11 cursor-pointer items-start gap-3 rounded-md border border-[#D7D9D3] p-3">
            <input type="checkbox" checked={balance} onChange={(event) => setBalance(event.target.checked)} className="mt-1 size-4 shrink-0 accent-[#173F5F]" />
            <span className="text-xs leading-5"><strong className="block text-[#173F5F]">Gently balance shot brightness</strong><span className="text-[#666862]">Small measured exposure differences only. Manual colour choices and HDR conversion take priority.</span></span>
          </label>
          <label className="flex min-h-11 cursor-pointer items-start gap-3 rounded-md border border-[#D7D9D3] p-3">
            <input type="checkbox" checked={safe} onChange={(event) => setSafe(event.target.checked)} className="mt-1 size-4 shrink-0 accent-[#173F5F]" />
            <span className="text-xs leading-5"><strong className="block text-[#173F5F]">Keep image cards clear of captions</strong><span className="text-[#666862]">Fits the whole image around your timed caption positions. Crowded captions may leave only a small card; check readability.</span></span>
          </label>
        </fieldset>
        <p className="text-xs leading-5 text-[#666862]">Checks up to eight selected shots using small local samples. Uncertain shots stay unchanged. Review the new preview before export.</p>
        {error ? <p role="alert" className="text-sm text-[#A23B2A]">{error}</p> : null}
        <button type="submit" disabled={busy} className="min-h-11 rounded-md border border-[#173F5F] px-3 text-xs font-bold text-[#173F5F] disabled:opacity-50">
          {busy ? "Creating visual preview…" : "Create visual preview"}
        </button>
      </form>
      {profiles.length ? <details className="mt-3">
        <summary className="min-h-11 cursor-pointer content-center text-xs font-bold text-[#173F5F]">What changed or stayed · {profiles.length} shots</summary>
        <ul className="space-y-2 text-xs leading-5 text-[#666862]">
          {profiles.map((profile) => <li key={profile.clip_index}><strong>Clip {profile.clip_index + 1}:</strong> {profile.note}</li>)}
        </ul>
      </details> : null}
    </details>
  );
}
