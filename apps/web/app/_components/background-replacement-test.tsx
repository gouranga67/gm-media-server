"use client";

import { useState } from "react";
import { CheckIcon, LoaderCircleIcon, ScanLineIcon, TriangleAlertIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  createCutoutComparison,
  cutoutArtifactUrl,
  type CutoutLabReport,
} from "@/lib/media-api";

export function BackgroundReplacementTest({
  jobId,
  version,
}: {
  readonly jobId: string;
  readonly version: number;
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

  return (
    <section className="rounded-md border border-[#BFD2DE] bg-white p-5" aria-labelledby="background-replacement-title">
      <div className="flex items-start gap-3">
        <ScanLineIcon aria-hidden="true" className="mt-0.5 size-5 shrink-0 text-[#174D73]" />
        <div>
          <p className="font-mono text-[10px] font-bold tracking-wide text-[#174D73] uppercase">Replace background · Beta</p>
          <h2 className="mt-1 text-lg font-bold text-[#173F5F]" id="background-replacement-title">Test your ordinary wall before using the effect</h2>
          <p className="mt-2 text-sm leading-6 text-[#53646F]">
            GM Studio will isolate the presenter in a two-second sample and place the chosen image or video behind them. A white, timber or normal room background is allowed.
          </p>
        </div>
      </div>

      <div className="mt-4 rounded-md border border-[#E7C4BC] bg-[#FFF8F4] p-3 text-xs leading-5 text-[#6E3B2F]">
        <p className="flex items-start gap-2 font-bold"><TriangleAlertIcon aria-hidden="true" className="mt-0.5 size-4 shrink-0" />Experimental quality check</p>
        <p className="mt-1">Inspect hair, hands and anything being held. The current local model can remove fine edges or held products. This test does not change the edit or final export.</p>
      </div>

      {!report ? (
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
                ? "Test marked usable. This beta records no production approval yet; the exported reel still keeps its original background."
                : "Original background retained. Nothing in the edit was changed."}
            </p>
          ) : null}
          <button className="min-h-11 text-sm font-bold text-[#173F5F] underline underline-offset-4" disabled={busy} onClick={() => void createTest()} type="button">Run the sample again</button>
        </div>
      )}
      {error ? <p className="mt-3 text-xs leading-5 text-[#A23B2A]" role="alert">{error}</p> : null}
    </section>
  );
}
