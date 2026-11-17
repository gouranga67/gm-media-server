"use client";

import { useEffect, useMemo, useState, type FormEvent } from "react";
import { CheckCircle2Icon, Layers3Icon, LoaderCircleIcon, RotateCcwIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  getFinishingTools,
  requestRevision,
  setJobComposition,
  type FinishingInspection,
  type JobComposition,
} from "@/lib/media-api";
import { VideoKeyColourSampler } from "./video-key-colour-sampler";

const DEFAULT_KEY = {
  chroma_key_color: "#00FF00",
  chroma_similarity: 0.12,
  chroma_blend: 0.08,
  spill_suppression: 0.15,
} as const;

function percent(value: number, maximum: number) {
  return `${Math.round((value / maximum) * 100)}%`;
}

export function GreenScreenCompositionControls({
  jobId,
  version,
  composition,
  onUpdated,
  getPreviewVideo,
}: {
  readonly jobId: string;
  readonly version: number;
  readonly composition: JobComposition;
  readonly onUpdated: () => void;
  readonly getPreviewVideo?: () => HTMLVideoElement | null;
}) {
  const [inspection, setInspection] = useState<FinishingInspection>();
  const [keyColor, setKeyColor] = useState(composition.chroma_key_color || DEFAULT_KEY.chroma_key_color);
  const [similarity, setSimilarity] = useState(composition.chroma_similarity ?? DEFAULT_KEY.chroma_similarity);
  const [blend, setBlend] = useState(composition.chroma_blend ?? DEFAULT_KEY.chroma_blend);
  const [spill, setSpill] = useState(composition.spill_suppression ?? DEFAULT_KEY.spill_suppression);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    getFinishingTools(jobId)
      .then((value) => {
        if (active) setInspection(value);
      })
      .catch((loadError: unknown) => {
        if (active) setError(loadError instanceof Error ? loadError.message : "Composition tools could not be loaded.");
      });
    return () => {
      active = false;
    };
  }, [jobId]);

  const sources = useMemo(() => {
    const source = (id: string | null) => inspection?.sources.find((item) => item.asset_id === id);
    return {
      foreground: source(composition.foreground_asset_id),
      background: source(composition.background_asset_id),
    };
  }, [composition.background_asset_id, composition.foreground_asset_id, inspection]);

  const reset = () => {
    setKeyColor(DEFAULT_KEY.chroma_key_color);
    setSimilarity(DEFAULT_KEY.chroma_similarity);
    setBlend(DEFAULT_KEY.chroma_blend);
    setSpill(DEFAULT_KEY.spill_suppression);
    setError("");
  };

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!inspection || inspection.version !== version) {
      setError("This preview changed. Refresh before adjusting the composition.");
      return;
    }
    setBusy(true);
    setError("");
    let saved = false;
    try {
      await setJobComposition(jobId, {
        ...composition,
        chroma_key_color: keyColor.toUpperCase(),
        chroma_similarity: similarity,
        chroma_blend: blend,
        spill_suppression: spill,
      });
      saved = true;
      await requestRevision(jobId, {
        note: "",
        captionCorrections: [],
        baseVersion: version,
        finishingSettings: inspection.settings,
      });
      onUpdated();
    } catch (submitError) {
      const detail = submitError instanceof Error ? submitError.message : "The composition preview could not be created.";
      setError(saved ? `The key settings were saved, but the preview was not queued: ${detail}` : detail);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="rounded-md border border-[#BFD2DE] bg-white" aria-labelledby="composition-title">
      <div className="flex items-start gap-3 p-4">
        <span className="mt-0.5 rounded-md bg-[#EFF6FA] p-2 text-[#173F5F]"><Layers3Icon aria-hidden="true" className="size-5" /></span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-3">
            <h2 className="text-sm font-bold text-[#173F5F]" id="composition-title">Green-screen composition</h2>
            <span className="inline-flex items-center gap-1 font-mono text-[9px] font-bold text-[#307455] uppercase"><CheckCircle2Icon className="size-3" /> Ready</span>
          </div>
          <p className="mt-1 truncate text-xs text-[#666862]">
            {sources.foreground?.name ?? "Assigned presenter"} over {sources.background?.name ?? "assigned background"}
          </p>
        </div>
      </div>
      <details className="border-t border-[#E5E6E1]">
        <summary className="min-h-12 cursor-pointer content-center px-4 text-xs font-bold text-[#173F5F]">Adjust key and create a local preview</summary>
        <form className="space-y-5 border-t border-[#E5E6E1] p-4" onSubmit={submit}>
          <div>
            <div className="flex items-center justify-between gap-3">
              <label className="text-xs font-bold text-[#173F5F]" htmlFor="composition-key-colour">Background colour to remove</label>
              <input aria-label="Green-screen key colour" className="h-10 w-14 cursor-pointer rounded border border-[#C7CBD0] bg-white p-1" id="composition-key-colour" onChange={(event) => setKeyColor(event.currentTarget.value)} type="color" value={keyColor} />
            </div>
            <div className="mt-2 flex gap-2">
              <button className={`min-h-10 flex-1 rounded border px-3 text-xs font-bold ${keyColor.toUpperCase() === "#00FF00" ? "border-[#173F5F] bg-[#EFF6FA] text-[#173F5F]" : "border-[#D7D9D3]"}`} onClick={() => setKeyColor("#00FF00")} type="button">Green screen</button>
              <button className={`min-h-10 flex-1 rounded border px-3 text-xs font-bold ${keyColor.toUpperCase() === "#0000FF" ? "border-[#173F5F] bg-[#EFF6FA] text-[#173F5F]" : "border-[#D7D9D3]"}`} onClick={() => setKeyColor("#0000FF")} type="button">Blue screen</button>
            </div>
            <div className="mt-2">
              <VideoKeyColourSampler getPreviewVideo={getPreviewVideo} onSelect={setKeyColor} />
            </div>
          </div>

          <label className="block text-xs font-bold text-[#173F5F]">
            Remove more of the background <span className="float-right font-mono font-normal text-[#666862]">{percent(similarity, 0.4)}</span>
            <input className="mt-2 w-full accent-[#173F5F]" max={0.4} min={0.01} onChange={(event) => setSimilarity(Number(event.currentTarget.value))} step={0.01} type="range" value={similarity} />
            <span className="mt-1 block font-normal leading-5 text-[#666862]">Raise this if green remains. Lower it if clothing or skin begins to disappear.</span>
          </label>

          <label className="block text-xs font-bold text-[#173F5F]">
            Soften the edge <span className="float-right font-mono font-normal text-[#666862]">{percent(blend, 0.3)}</span>
            <input className="mt-2 w-full accent-[#173F5F]" max={0.3} min={0} onChange={(event) => setBlend(Number(event.currentTarget.value))} step={0.01} type="range" value={blend} />
            <span className="mt-1 block font-normal leading-5 text-[#666862]">Use a small amount to reduce a hard cut-out edge around hair and shoulders.</span>
          </label>

          <label className="block text-xs font-bold text-[#173F5F]">
            Reduce green or blue spill <span className="float-right font-mono font-normal text-[#666862]">{Math.round(spill * 100)}%</span>
            <input className="mt-2 w-full accent-[#173F5F]" max={1} min={0} onChange={(event) => setSpill(Number(event.currentTarget.value))} step={0.05} type="range" value={spill} />
            <span className="mt-1 block font-normal leading-5 text-[#666862]">Removes colour reflected onto the presenter. Strong settings can desaturate clothing.</span>
          </label>

          {error ? <p className="rounded-md bg-[#FFF0EC] p-3 text-xs leading-5 text-[#A23B2A]" role="alert">{error}</p> : null}
          <div className="grid gap-2 sm:grid-cols-[auto_1fr]">
            <Button className="h-12" disabled={busy} onClick={reset} type="button" variant="outline"><RotateCcwIcon aria-hidden="true" /> Reset</Button>
            <Button className="h-12 bg-[#173F5F] text-white hover:bg-[#12344F]" disabled={busy || !inspection} type="submit">
              {busy ? <LoaderCircleIcon aria-hidden="true" className="animate-spin" /> : null}
              {busy ? "Creating preview…" : "Create composition preview"}
            </Button>
          </div>
          <p className="text-center text-[11px] leading-5 text-[#666862]">Keeps the current cut, speech, captions, music and effects · zero AI tokens</p>
        </form>
      </details>
    </section>
  );
}
