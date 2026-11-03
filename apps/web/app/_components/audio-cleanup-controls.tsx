"use client";

import { useState } from "react";
import { getFinishingTools, requestRevision, type FinishingTools } from "@/lib/media-api";

type AudioReport = {
  readonly mode?: "off" | "auto";
  readonly profiles?: FinishingTools["voice_cleanup_profiles"];
};

export function AudioCleanupControls({ jobId, version, report, onUpdated }: {
  readonly jobId: string;
  readonly version: number;
  readonly report?: AudioReport;
  readonly onUpdated: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const automatic = report?.mode === "auto";
  const profiles = report?.profiles ?? [];
  const measured = profiles.filter((profile) => profile.status === "measured").length;
  async function apply(mode: "off" | "auto") {
    setBusy(true);
    setError("");
    try {
      const current = await getFinishingTools(jobId);
      if (current.version !== version) throw new Error("A newer edit is available. Refresh before changing its audio.");
      await requestRevision(jobId, {
        note: "", captionCorrections: [], baseVersion: version,
        finishingSettings: { ...current.settings, voice_cleanup: mode, voice_cleanup_profiles: [] },
      });
      onUpdated();
    } catch (error) {
      setError(error instanceof Error ? error.message : "Could not create an audio preview.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <section aria-label="Voice cleanup" className="rounded-md border border-[#D7D9D3] bg-white p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-bold text-[#173F5F]">Voice cleanup &amp; balance</h3>
        <span className="font-mono text-[10px] text-[#666862]">{automatic ? "AUTOMATIC" : "AVAILABLE"} · LOCAL</span>
      </div>
      <p className="mt-2 text-xs leading-5 text-[#666862]">
        {automatic ? `${measured} of ${profiles.length} sources checked for steady noise and uneven voice levels. ` : "Filmed without a mic? Check for steady noise and uneven voice levels. "}
        Keeps the cut, captions, music and effects. Creates a new preview with zero AI tokens.
      </p>
      {profiles.length ? (
        <details className="mt-2">
          <summary className="min-h-11 cursor-pointer content-center text-xs font-bold text-[#173F5F]">What was checked · {profiles.length} sources</summary>
          <ul className="space-y-2 text-xs leading-5 text-[#666862]">
            {profiles.map((profile, index) => <li key={profile.asset_id}><strong>Source {index + 1}:</strong> {profile.note}</li>)}
          </ul>
          <p className="mt-2 text-xs leading-5 text-[#666862]">Inspection uses short source samples. Distant, echoing or clipped speech may still need a better recording. Listen before approving.</p>
        </details>
      ) : null}
      {error ? <p role="alert" className="mt-3 text-sm text-[#A23B2A]">{error}</p> : null}
      <div className="mt-3 flex flex-wrap gap-2">
        <button type="button" disabled={busy} onClick={() => void apply("auto")} className="min-h-11 rounded-md border border-[#173F5F] px-3 text-xs font-bold text-[#173F5F] disabled:opacity-50">
          {busy ? "Creating audio preview…" : automatic ? "Recheck audio in a new preview" : "Clean up & balance audio"}
        </button>
        {automatic ? <button type="button" disabled={busy} onClick={() => void apply("off")} className="min-h-11 rounded-md border border-[#D7D9D3] px-3 text-xs text-[#666862] disabled:opacity-50">Turn off automatic cleanup</button> : null}
      </div>
    </section>
  );
}
