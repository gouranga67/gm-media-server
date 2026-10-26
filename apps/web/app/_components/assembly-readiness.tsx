"use client";

import { useEffect, useRef, useState } from "react";
import {
  getJobAssembly,
  updateJobAssembly,
  type AssemblyPreview,
  type AssemblySettings,
} from "@/lib/media-api";
import { Button } from "@/components/ui/button";

export function AssemblyReadiness({
  jobId,
  onReady,
  onApplied,
}: {
  readonly jobId: string;
  readonly onReady: (ready: boolean) => void;
  readonly onApplied?: (settings: AssemblySettings) => void;
}) {
  const panelRef = useRef<HTMLElement>(null);
  useEffect(() => {
    panelRef.current?.scrollIntoView?.({
      block: "nearest",
      behavior: "smooth",
    });
  }, []);
  const [preview, setPreview] = useState<AssemblyPreview | null>(null);
  const [settings, setSettings] = useState<AssemblySettings | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    onReady(false);
    async function inspect() {
      try {
        const result = await getJobAssembly(jobId);
        if (cancelled) return;
        setPreview(result);
        setSettings(result.settings);
        setError(null);
        onReady(result.ready);
        if (!result.ready && result.error === "Waiting for source analysis.") {
          timer = setTimeout(() => void inspect(), 2000);
        }
      } catch (cause) {
        if (!cancelled)
          setError(
            cause instanceof Error
              ? cause.message
              : "Could not check the edit direction.",
          );
      }
    }
    void inspect();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [jobId, onReady, attempt]);

  async function apply() {
    if (!settings || saving) return;
    setSaving(true);
    onReady(false);
    try {
      const result = await updateJobAssembly(jobId, settings);
      setPreview(result);
      setError(null);
      onApplied?.(result.settings);
      onReady(result.ready);
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Could not save the override.",
      );
    } finally {
      setSaving(false);
    }
  }
  const selectClass =
    "mt-1 min-h-12 w-full rounded-md border border-[#D7D9D3] bg-white px-3 text-sm text-[#173F5F]";
  return (
    <section
      ref={panelRef}
      aria-label="Edit interpretation"
      className="space-y-3 rounded-md border border-[#BFD2DE] bg-[#EFF6FA] p-4 text-[#173F5F]"
    >
      <h2 className="text-lg font-bold">How this edit will be assembled</h2>
      <div aria-live="polite" className="space-y-2 text-sm">
        {preview?.decision ? (
          <>
            <p className="font-bold">{preview.decision.label}</p>
            <p>{preview.decision.reason}</p>
            <p>
              Purpose:{" "}
              {preview.decision.purpose === "auto"
                ? "Follow the brief"
                : preview.decision.purpose}
              . Pacing:{" "}
              {(preview.decision.edit_style ?? "legacy").replaceAll("_", " ")}.
            </p>
          </>
        ) : (
          <p>{preview?.error ?? "Checking the analysed sources…"}</p>
        )}
        <p className="text-xs">
          This compatibility check uses stored analysis and no extra model
          calls. Your brief guides the story; preview quality still needs your
          review.
        </p>
      </div>
      {preview?.error && preview.error !== "Waiting for source analysis." ? (
        <p className="text-xs">
          You can adjust Advanced below, add suitable device footage, or{" "}
          <a className="font-bold underline" href="/jobs/new">
            start a new job with a different brief or sources
          </a>
          .
        </p>
      ) : null}
      {error ? (
        <div role="alert" className="text-sm text-[#A23B2A]">
          {error}
          <Button
            type="button"
            variant="outline"
            className="ml-2 min-h-11"
            onClick={() => setAttempt((value) => value + 1)}
          >
            Check again
          </Button>
        </div>
      ) : null}
      {preview?.locked ? (
        <p className="text-xs">
          Assembly is fixed for this edit and its revisions.
        </p>
      ) : settings ? (
        <details>
          <summary className="min-h-11 cursor-pointer content-center text-sm font-bold">
            Advanced: override before editing
          </summary>
          <fieldset
            disabled={
              saving || preview?.error === "Waiting for source analysis."
            }
            className="mt-2 grid gap-3 sm:grid-cols-2"
          >
            <label className="text-xs font-bold" htmlFor="ready-assembly">
              Assembly
              <select
                id="ready-assembly"
                className={selectClass}
                value={settings.assembly_mode}
                onChange={(event) => {
                  setSettings({
                    ...settings,
                    assembly_mode: event.currentTarget
                      .value as AssemblySettings["assembly_mode"],
                  });
                  onReady(false);
                }}
              >
                <option value="auto">Automatic from brief and sources</option>
                <option value="talking_head">
                  Speech with supporting pictures
                </option>
                <option value="montage">Visual montage</option>
              </select>
            </label>
            <label className="text-xs font-bold" htmlFor="ready-purpose">
              Purpose
              <select
                id="ready-purpose"
                className={selectClass}
                value={settings.reel_intent}
                onChange={(event) => {
                  setSettings({
                    ...settings,
                    reel_intent: event.currentTarget
                      .value as AssemblySettings["reel_intent"],
                  });
                  onReady(false);
                }}
              >
                <option value="auto">Follow my brief</option>
                <option value="story">Story / explanation</option>
                <option value="promotion">Product / promotion</option>
                <option value="bloopers">Bloopers / outtakes</option>
              </select>
            </label>
            <label className="text-xs font-bold" htmlFor="ready-pacing">
              Pacing
              <select
                id="ready-pacing"
                className={selectClass}
                value={
                  settings.pacing_mode === "auto" ? "auto" : settings.edit_style
                }
                onChange={(event) => {
                  const value = event.currentTarget.value;
                  setSettings({
                    ...settings,
                    pacing_mode: value === "auto" ? "auto" : "manual",
                    edit_style:
                      value === "auto"
                        ? settings.edit_style
                        : (value as AssemblySettings["edit_style"]),
                  });
                  onReady(false);
                }}
              >
                <option value="auto">Follow my brief</option>
                <option value="clean">Clean</option>
                <option value="energetic">Energetic</option>
                <option value="calm">Calm</option>
                <option value="high_impact">High impact</option>
              </select>
            </label>
            <div className="self-end">
              <Button
                type="button"
                className="min-h-12"
                disabled={
                  saving || preview?.error === "Waiting for source analysis."
                }
                onClick={() => void apply()}
              >
                {saving ? "Applying…" : "Apply overrides"}
              </Button>
            </div>
          </fieldset>
          <p className="mt-2 text-xs">
            Changing a field does not submit it. Apply overrides, check the
            interpretation, then press Start editing.
          </p>
        </details>
      ) : null}
    </section>
  );
}
