"use client";

import { useState } from "react";
import { CheckIcon, LoaderCircleIcon, RotateCcwIcon, ScanLineIcon, TriangleAlertIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  createCutoutComparison,
  cutoutArtifactUrl,
  setFullReelCutout,
  type CutoutLabReport,
} from "@/lib/media-api";

export function BackgroundReplacementTest({
  jobId,
  version,
  applied,
  onUpdated,
}: {
  readonly jobId: string;
  readonly version: number;
  readonly applied: boolean;
  readonly onUpdated: () => void;
}) {
  const [report, setReport] = useState<CutoutLabReport>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const [verdict, setVerdict] = useState<"usable" | "original">();

  const createTest = async () => {
    setBusy(true);
    setError(undefined);
    setVerdict(undefined);
    try {
      setReport(await createCutoutComparison(jobId, version));
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "The background test could not be created.");
    } finally {
      setBusy(false);
    }
  };

  const applyToReel = async (enabled: boolean) => {
    setBusy(true);
    setError(undefined);
    try {
      await setFullReelCutout(jobId, version, enabled, enabled ? report?.cache_key : undefined);
      onUpdated();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "The full-reel preview could not be started.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="rounded-md border border-[#BFD2DE] bg-white p-5" aria-labelledby="background-replacement-title">
      <div className="flex items-start gap-3">
        <ScanLineIcon aria-hidden="true" className="mt-0.5 size-5 shrink-0 text-[#174D73]" />
        <div>
          <p className="font-mono text-[10px] font-bold tracking-wide text-[#174D73] uppercase">Replace background · Beta</p>
          <h2 className="mt-1 text-lg font-bold text-[#173F5F]" id="background-replacement-title">Test your ordinary wall before using the effect</h2>
          <p className="mt-2 text-sm leading-6 text-[#53646F]">
            {applied
              ? "This preview uses the chosen background throughout the reel. Captions, B-roll and finishing are added after person isolation so they remain intact."
              : "GM Studio will isolate the presenter in a two-second sample and place the chosen image or video behind them. A white, timber or normal room background is allowed."}
          </p>
        </div>
      </div>

      <div className="mt-4 rounded-md border border-[#E7C4BC] bg-[#FFF8F4] p-3 text-xs leading-5 text-[#6E3B2F]">
        <p className="flex items-start gap-2 font-bold"><TriangleAlertIcon aria-hidden="true" className="mt-0.5 size-4 shrink-0" />Experimental quality check</p>
        <p className="mt-1">Inspect hair, hands and anything being held. The current local model can remove fine edges or held products. Applying it creates a new preview; the original version remains available.</p>
      </div>

      {applied ? (
        <div className="mt-4 space-y-3">
          <p className="rounded-md bg-[#EDF7F1] p-3 text-xs leading-5 text-[#215B43]" role="status">
            Background replacement is applied to this version. If a longer motion looks wrong, restore the original background to create another safe preview.
          </p>
          <Button className="h-12 w-full" disabled={busy} onClick={() => void applyToReel(false)} type="button" variant="outline">
            {busy ? <LoaderCircleIcon aria-hidden="true" className="animate-spin" /> : <RotateCcwIcon aria-hidden="true" />}
            {busy ? "Preparing original-background preview…" : "Restore original background"}
          </Button>
        </div>
      ) : !report ? (
        <Button className="mt-4 h-12 w-full" disabled={busy} onClick={() => void createTest()} type="button" variant="outline">
          {busy ? <LoaderCircleIcon aria-hidden="true" className="animate-spin" /> : <ScanLineIcon aria-hidden="true" />}
          {busy ? "Creating two-second test…" : "Create background replacement test"}
        </Button>
      ) : (
        <div className="mt-4 space-y-4">
          <div>
            <video
              className="aspect-[3/1] w-full rounded-md bg-black object-contain"
              controls
              playsInline
              preload="metadata"
              src={cutoutArtifactUrl(jobId, report.cache_key, "comparison.mp4")}
            >
              Your browser cannot play this comparison.
            </video>
            <div className="mt-2 grid grid-cols-3 text-center font-mono text-[10px] text-[#666862]">
              <span>Original</span><span>Chosen background</span><span>Mask</span>
            </div>
          </div>
          <ul className="space-y-2 text-xs leading-5 text-[#53646F]">
            {report.human_review_items.slice(0, 5).map((item) => (
              <li className="flex gap-2" key={item}><span aria-hidden="true">□</span><span>{item}</span></li>
            ))}
          </ul>
          <div className="grid gap-2 sm:grid-cols-2">
            <Button className="h-12" onClick={() => setVerdict("usable")} type="button" variant="outline"><CheckIcon aria-hidden="true" />Looks usable for this shot</Button>
            <Button className="h-12" onClick={() => setVerdict("original")} type="button" variant="outline">Keep the original background</Button>
          </div>
          {verdict ? (
            <p className={`rounded-md p-3 text-xs leading-5 ${verdict === "usable" ? "bg-[#EDF7F1] text-[#215B43]" : "bg-[#F2F3F1] text-[#53646F]"}`} role="status">
              {verdict === "usable"
                ? "The sample is accepted. Apply it to create a new full-reel preview; this current original-background version remains available."
                : "Original background retained. Nothing in the edit was changed."}
            </p>
          ) : null}
          {verdict === "usable" ? (
            <Button className="h-14 w-full bg-[#173F5F] text-white hover:bg-[#12344F]" disabled={busy} onClick={() => void applyToReel(true)} type="button">
              {busy ? <LoaderCircleIcon aria-hidden="true" className="animate-spin" /> : <CheckIcon aria-hidden="true" />}
              {busy ? "Creating full-reel preview…" : "Apply background to full reel"}
            </Button>
          ) : null}
          <button className="min-h-11 text-sm font-bold text-[#173F5F] underline underline-offset-4" disabled={busy} onClick={() => void createTest()} type="button">Run the sample again</button>
        </div>
      )}
      {error ? <p className="mt-3 text-xs leading-5 text-[#A23B2A]" role="alert">{error}</p> : null}
    </section>
  );
}
