"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { BrainCircuitIcon, CheckIcon, LoaderCircleIcon, PauseCircleIcon } from "lucide-react";

import { LearningLabPanel } from "./learning-lab";
import { StudioNav } from "@/app/_components/studio-nav";
import { Button } from "@/components/ui/button";
import { getLearningSummary, updateLearningSettings, type LearningSummary } from "@/lib/media-api";

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : "Learning summary is unavailable";
}

function percent(value: number | null) {
  return value === null ? "—" : `${Math.round(value * 100)}%`;
}

export function LearningDashboard() {
  const [summary, setSummary] = useState<LearningSummary>();
  const [error, setError] = useState<string>();
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    try {
      setSummary(await getLearningSummary());
      setError(undefined);
    } catch (loadError) {
      setError(errorMessage(loadError));
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const saveSettings = async (enabled: boolean, minimumSamples: number) => {
    setSaving(true);
    setError(undefined);
    try {
      await updateLearningSettings({ enabled, minimumSamples });
      await load();
    } catch (saveError) {
      setError(errorMessage(saveError));
    } finally {
      setSaving(false);
    }
  };

  return (
    <main className="min-h-dvh bg-[#F7F7F5] px-4 py-6 text-[#20211F] [color-scheme:light]">
      <div className="mx-auto w-full max-w-5xl">
        <StudioNav current="/learning" />
        <header className="mt-10 flex flex-col justify-between gap-5 border-b border-[#D7D9D3] pb-8 md:flex-row md:items-end">
          <div>
            <p className="font-mono text-xs font-bold tracking-wide text-[#215B43] uppercase">Local improvement loop</p>
            <h1 className="mt-2 text-3xl font-black tracking-tight text-[#173F5F]">What GM Studio is learning</h1>
            <p className="mt-3 max-w-2xl text-sm leading-relaxed text-[#666862]">
              Ratings are attached to exact edit versions. Repeated patterns become recipe-specific guidance; source evidence and job instructions always take priority.
            </p>
          </div>
          <div className="rounded-full bg-[#E4F1E9] px-4 py-2 font-mono text-xs font-bold text-[#307455]">
            ZERO EXTRA MODEL CALLS
          </div>
        </header>

        {!summary && !error ? <div className="flex min-h-72 items-center justify-center"><LoaderCircleIcon className="animate-spin text-[#173F5F]" /></div> : null}
        {error ? <p className="mt-6 rounded-md border border-[#E7C4BC] bg-white p-4 text-sm text-[#A23B2A]" role="alert">{error}</p> : null}

        {summary ? (
          <div className="mt-8 space-y-8">
            <LearningLabPanel />
            <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {[
                ["Feedback", summary.feedback_count.toString()],
                ["Average rating", summary.average_rating?.toFixed(1) ?? "—"],
                ["Would use", summary.would_use_again_count.toString()],
                ["First-pass approval", percent(summary.first_pass_approval_rate)],
              ].map(([label, value]) => (
                <div className="rounded-md border border-[#D7D9D3] bg-white p-5" key={label}>
                  <p className="font-mono text-[10px] font-bold tracking-wide text-[#666862] uppercase">{label}</p>
                  <p className="mt-3 text-3xl font-black text-[#173F5F]">{value}</p>
                </div>
              ))}
            </section>

            <section className="rounded-md border border-[#D7D9D3] bg-white p-6">
              <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
                <div>
                  <p className="font-mono text-xs font-bold tracking-wide text-[#173F5F] uppercase">Learning controls</p>
                  <p className="mt-2 text-sm text-[#666862]">The safety threshold prevents one-off opinions from changing future plans.</p>
                </div>
                <Button disabled={saving} onClick={() => void saveSettings(!summary.settings.enabled, summary.settings.minimum_samples)} type="button" variant={summary.settings.enabled ? "outline" : "default"}>
                  {saving ? <LoaderCircleIcon className="animate-spin" /> : summary.settings.enabled ? <PauseCircleIcon /> : <BrainCircuitIcon />}
                  {summary.settings.enabled ? "Pause learning" : "Resume learning"}
                </Button>
              </div>
              <label className="mt-5 block text-xs font-bold text-[#173F5F]" htmlFor="minimum-learning-samples">MINIMUM REPEATED EXAMPLES</label>
              <select
                className="mt-2 h-11 w-full rounded-md border border-[#D7D9D3] bg-white px-3 text-sm sm:w-52"
                disabled={saving}
                id="minimum-learning-samples"
                onChange={(event) => void saveSettings(summary.settings.enabled, Number(event.currentTarget.value))}
                value={summary.settings.minimum_samples}
              >
                {[3, 4, 5, 6, 8, 10].map((value) => <option key={value} value={value}>{value} edits</option>)}
              </select>
            </section>

            <section>
              <div className="flex items-end justify-between gap-4">
                <div>
                  <p className="font-mono text-xs font-bold tracking-wide text-[#173F5F] uppercase">Active preferences</p>
                  <h2 className="mt-2 text-2xl font-black text-[#173F5F]">Evidence behind future choices</h2>
                </div>
                <span className={`rounded-full px-3 py-2 font-mono text-[10px] font-bold ${summary.settings.enabled ? "bg-[#E4F1E9] text-[#307455]" : "bg-[#F0F0ED] text-[#666862]"}`}>
                  {summary.settings.enabled ? "ACTIVE" : "PAUSED"}
                </span>
              </div>
              <div className="mt-5 grid gap-4 lg:grid-cols-2">
                {(["talking_head", "montage"] as const).map((scopeName) => {
                  const scope = summary.scopes[scopeName];
                  return (
                    <article className="rounded-md border border-[#D7D9D3] bg-white p-5" key={scopeName}>
                      <div className="flex items-start justify-between gap-4">
                        <div>
                          <h3 className="text-lg font-bold text-[#173F5F]">{scopeName === "talking_head" ? "Talking-head edits" : "Montages"}</h3>
                          <p className="mt-1 text-xs text-[#666862]">{scope.sample_size} rated edits · {scope.average_rating?.toFixed(1) ?? "—"} average</p>
                        </div>
                        {scope.feedback_needed > 0 ? <span className="rounded-full bg-[#FFF6DC] px-2 py-1 font-mono text-[9px] font-bold text-[#775C08]">{scope.feedback_needed} MORE NEEDED</span> : <CheckIcon className="text-[#215B43]" />}
                      </div>
                      {scope.preferences.length ? (
                        <ul className="mt-4 space-y-3">
                          {scope.preferences.map((preference) => (
                            <li className="rounded-md bg-[#EFF6FA] p-3" key={preference.tag}>
                              <p className="text-sm leading-relaxed text-[#173F5F]">{preference.directive}</p>
                              <p className="mt-2 font-mono text-[9px] text-[#53646F]">{preference.evidence_count}/{preference.sample_size} edits · {Math.round(preference.confidence * 100)}% confidence</p>
                            </li>
                          ))}
                        </ul>
                      ) : <p className="mt-5 text-sm leading-relaxed text-[#666862]">No preference is active yet. Rate more completed edits and mark what worked or needs improvement.</p>}
                    </article>
                  );
                })}
              </div>
            </section>

            <section className="rounded-md border border-[#D7D9D3] bg-white p-6">
              <p className="font-mono text-xs font-bold tracking-wide text-[#173F5F] uppercase">Recent teaching examples</p>
              {summary.recent_feedback.length ? (
                <div className="mt-4 divide-y divide-[#E4E5E1]">
                  {summary.recent_feedback.map((feedback) => (
                    <Link className="flex items-start justify-between gap-4 py-4 hover:bg-[#FAFAF8]" href={`/jobs/${feedback.job_id}`} key={feedback.id}>
                      <div>
                        <p className="text-sm font-bold text-[#173F5F]">{feedback.project_name} · version {feedback.version}</p>
                        <p className="mt-1 text-xs text-[#666862]">{feedback.recipe.replace("_", " ")} · {feedback.tags.map((tag) => tag.replaceAll("_", " ")).join(" · ") || "rating only"}</p>
                      </div>
                      <span className="shrink-0 rounded-full bg-[#EFF6FA] px-3 py-1 text-sm font-black text-[#173F5F]">{feedback.rating}/5</span>
                    </Link>
                  ))}
                </div>
              ) : <p className="mt-4 text-sm text-[#666862]">No edits have been rated yet. Open a finished job and use “Teach future edits.”</p>}
            </section>
          </div>
        ) : null}
      </div>
    </main>
  );
}
