"use client";
import { useEffect, useState } from "react";
import {
  getLearningLab,
  proposeLearningLessons,
  tryLearningLesson,
  evaluateLearningLesson,
  setLearningLessonStatus,
  type LearningLab,
  type LearningLesson,
  type LearningTrial,
} from "@/lib/media-api";
const control =
  "min-h-11 rounded-md border border-[#C7CBD0] bg-white px-3 text-sm text-[#173F5F] disabled:opacity-50";
export function LearningLabPanel() {
  const [data, setData] = useState<LearningLab>();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let active = true;
    getLearningLab()
      .then((value) => {
        if (active) setData(value);
      })
      .catch((e: unknown) => {
        if (active)
          setError(e instanceof Error ? e.message : "Learning lab unavailable");
      });
    return () => {
      active = false;
    };
  }, []);
  async function action(task?: () => Promise<unknown>) {
    setBusy(true);
    setError("");
    try {
      if (task) await task();
      setData(await getLearningLab());
    } catch (e) {
      setError(e instanceof Error ? e.message : "The learning action failed");
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="rounded-lg border border-[#BFD2DE] bg-white p-5">
      <h2 className="text-xl font-bold text-[#173F5F]">Evaluate new lessons</h2>
      <p className="mt-3 text-sm leading-6 text-[#666862]">
        Saved notes can suggest scoped editing lessons after feedback from three
        different jobs. Suggestions stay inactive until you review independent
        playback comparisons and explicitly promote one. Existing tag-based
        preferences continue separately.
      </p>
      <p className="mt-2 text-xs leading-5 text-[#666862]">
        Proposing and scoring are local. Creating a trial preview uses a normal
        editor-model request. Promotion requires three independent footage groups,
        excluded from the lesson&apos;s training examples, no lower ratings and
        at least one improvement to an executable edit. Reused footage counts once.
      </p>
      <p className="mt-2 text-xs leading-5 text-[#666862]">Trial pairs are kept out of routine preview cleanup while their lesson is proposed. Promote or retire the lesson to release normal retention; comparison records remain.</p>
      {error ? (
        <p
          role="alert"
          className="my-4 rounded bg-[#FFF0EC] p-3 text-sm text-[#A23B2A]"
        >
          {error}
        </p>
      ) : null}
      <button
        className={`${control} my-4`}
        disabled={busy}
        onClick={() => void action(proposeLearningLessons)}
        type="button"
      >
        {busy ? "Working…" : "Propose lessons from saved notes"}
      </button>
      <button className={`${control} my-4 ml-3`} disabled={busy} onClick={() => void action()} type="button">Refresh comparisons</button>
      {data?.lessons.length === 0 ? (
        <p className="text-sm text-[#666862]">
          No repeated note pattern has qualified yet. Keep rating different
          edits and describe the specific issue.
        </p>
      ) : null}
      <div className="space-y-4">
        {data?.lessons.map((lesson) => (
          <LessonCard
            key={lesson.id}
            lesson={lesson}
            data={data}
            busy={busy}
            action={action}
          />
        ))}
      </div>
    </section>
  );
}
function LessonCard({
  lesson,
  data,
  busy,
  action,
}: {
  readonly lesson: LearningLesson;
  readonly data: LearningLab;
  readonly busy: boolean;
  readonly action: (task: () => Promise<unknown>) => Promise<void>;
}) {
  const [jobId, setJobId] = useState("");
  const jobs = data.jobs.filter(
    (job) =>
      job.recipe === lesson.recipe &&
      job.edit_style === lesson.edit_style &&
      !lesson.training_job_ids.includes(job.id),
  );
  const optionFor = (id: string) => lesson.trial_options?.find(option => option.job_id === id);
  const selected = jobs.find(job => job.id === jobId);
  const blocked = lesson.trial_options ? optionFor(jobId)?.eligible !== true : false;
  return (
    <article className="rounded-lg border border-[#D7D9D3] p-4">
      <p className="text-xs font-bold uppercase text-[#53646F]">
        {lesson.recipe.replaceAll("_", " ")} ·{" "}
        {lesson.edit_style.replaceAll("_", " ")} ·{" "}
        {lesson.status.replaceAll("_", " ")}
      </p>
      <p className="mt-2 text-sm leading-6 text-[#173F5F]">
        {lesson.directive}
      </p>
      <p className="mt-2 text-xs text-[#666862]">
        {lesson.training_job_ids.length} training jobs ·{" "}
        {lesson.evaluation.held_out_jobs}/3 independent comparisons ·{" "}
        {lesson.evaluation.regressions} lower ratings
      </p>
      {lesson.evaluation.excluded_comparisons ? <p className="mt-2 text-xs text-[#A23B2A]">{lesson.evaluation.excluded_comparisons} comparison(s) lack qualifying provenance. Review and save those pairs again before relying on them.</p> : null}
      {lesson.evaluation.overlapping_comparisons ? <p className="mt-2 text-xs text-[#666862]">{lesson.evaluation.overlapping_comparisons} comparison(s) reuse footage and do not add independent evidence.</p> : null}
      {typeof lesson.evaluation.token_delta === "number" ? <p className="mt-2 text-xs text-[#53646F]">Average trial token change: {lesson.evaluation.token_delta > 0 ? "+" : ""}{lesson.evaluation.token_delta.toLocaleString()} across {lesson.evaluation.costed_comparisons} measured pair(s). Cost does not determine creative quality; inspect both before promoting.</p> : null}
      <p className="mt-2 text-xs leading-5 text-[#666862]">Playback ratings are subjective. A trial can vary for reasons beyond this rule; these comparisons do not prove causality or guarantee better future edits.</p>
      {lesson.status === "proposed" ? (
        <div className="mt-3 space-y-3">
          <label className="block text-xs">
            Try on a separate ready job
            <select
              className={`${control} mt-1 w-full`}
              value={jobId}
              onChange={(e) => setJobId(e.currentTarget.value)}
            >
              <option value="">Choose a job with fresh footage…</option>
              {jobs.map((job) => (
                <option key={job.id} value={job.id} disabled={lesson.trial_options ? optionFor(job.id)?.eligible !== true : false}>
                  {job.name} · version {job.version}{optionFor(job.id)?.reason ? ` · ${optionFor(job.id)?.reason}` : ""}
                </option>
              ))}
            </select>
          </label>
          <button
            className={control}
            disabled={busy || !selected || blocked}
            type="button"
            onClick={() => {
              const job = jobs.find((j) => j.id === jobId);
              if (
                job && !blocked &&
                window.confirm(
                  "Create a trial preview using a normal editor-model request? This uses model tokens and preserves the baseline preview.",
                )
              )
                void action(() =>
                  tryLearningLesson(lesson.id, job.id, job.version),
                );
            }}
          >
            Create trial preview · uses model tokens
          </button>
          {selected && optionFor(selected.id)?.reason ? <p className="text-xs text-[#A23B2A]">{optionFor(selected.id)?.reason}</p> : null}
          {lesson.trial_options && !jobs.some(job => optionFor(job.id)?.eligible) ? <p className="text-xs leading-5 text-[#666862]">No independent ready baseline is available in this list. Use different footage and finish an ordinary edit first. Uploading the same file again does not make it independent.</p> : null}
        </div>
      ) : null}
      <div className="mt-3 space-y-3">
        {data.trials
          .filter((t) => t.evaluation_lesson_id === lesson.id)
          .map((trial) => (
            <TrialReview
              key={trial.id}
              trial={trial}
              busy={busy}
              action={action}
            />
          ))}
      </div>
      <div className="mt-4 flex gap-3">
        <button
          className={control}
          disabled={
            busy ||
            !lesson.evaluation.can_promote ||
            lesson.status === "promoted"
          }
          onClick={() =>
            void action(() => setLearningLessonStatus(lesson.id, "promote"))
          }
          type="button"
        >
          Promote passed lesson
        </button>
        {lesson.status !== "rolled_back" ? (
          <button
            className={control}
            disabled={busy}
            onClick={() =>
              void action(() => setLearningLessonStatus(lesson.id, "rollback"))
            }
            type="button"
          >
            {lesson.status === "promoted" ? "Roll back lesson" : "Retire proposed lesson"}
          </button>
        ) : null}
      </div>
    </article>
  );
}
function TrialReview({
  trial,
  busy,
  action,
}: {
  readonly trial: LearningTrial;
  readonly busy: boolean;
  readonly action: (task: () => Promise<unknown>) => Promise<void>;
}) {
  const [baseline, setBaseline] = useState(trial.comparison?.baseline_rating ?? 0);
  const [candidate, setCandidate] = useState(trial.comparison?.candidate_rating ?? 0);
  const [note, setNote] = useState(trial.comparison?.note ?? "");
  const [watched, setWatched] = useState(false);
  const playable = trial.status === "ready" && trial.baseline_available !== false && trial.candidate_available !== false;
  return (
    <details className="rounded border border-[#D7D9D3] p-3">
      <summary className="min-h-11 cursor-pointer content-center text-sm font-bold text-[#173F5F]">
        {trial.project_name} · trial v{trial.version} · {trial.status}
      </summary>
      {playable ? (
        <>
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            {[
              {label:"Baseline",version:trial.baseline_version,usage:trial.baseline_usage},
              {label:"Trial",version:trial.version,usage:trial.candidate_usage},
            ].map(({label, version, usage}) => (
              <figure key={label}>
                <figcaption className="mb-2 text-xs font-bold">
                  {label} v{version}
                </figcaption>
                <video
                  aria-label={`${label} preview version ${version}`}
                  className="max-h-80 w-full rounded bg-black"
                  controls
                  playsInline
                  preload="none"
                  src={`/api/media/jobs/${trial.job_id}/preview/file?version=${version}`}
                />
                <p className="mt-2 text-xs leading-5 text-[#53646F]">{usage
                  ? `${usage.total_tokens.toLocaleString()} tokens · ${usage.requests} model request(s) · ${(usage.model_latency_ms / 1000).toFixed(1)}s recorded model latency`
                  : "Model usage not recorded for this version."}</p>
              </figure>
            ))}
          </div>
          <p className="mt-2 text-xs text-[#666862]">Usage includes recorded planning/repair requests for each exact version. Tokens are not a price; model latency excludes upload, queueing and rendering.</p>
          <p className="mt-2 text-xs text-[#53646F]">Local technical checks: baseline {trial.baseline_quality ?? "not recorded"} · trial {trial.candidate_quality ?? "not recorded"}. Inspect any warnings on the job page; passing checks do not prove a good story.</p>
          {trial.comparison ? <p className="mt-2 text-xs font-bold text-[#173F5F]">Saved comparison: baseline {trial.comparison.baseline_rating}/5 · trial {trial.comparison.candidate_rating}/5.</p> : null}
          {trial.executable_changed === false ? <p className="mt-2 text-xs text-[#A23B2A]">The executable edit was unchanged. A higher rating alone will not count as an improvement.</p> : null}
          <div className="mt-3 flex flex-wrap items-end gap-3">
            <label className="text-xs">
              Baseline rating
              <select
                className={`${control} mt-1 block`}
                value={baseline}
                onChange={(e) => setBaseline(Number(e.currentTarget.value))}
              >
                <option value={0}>Choose…</option>
                {[1, 2, 3, 4, 5].map((r) => (
                  <option key={r}>{r}</option>
                ))}
              </select>
            </label>
            <label className="text-xs">
              Trial rating
              <select
                className={`${control} mt-1 block`}
                value={candidate}
                onChange={(e) => setCandidate(Number(e.currentTarget.value))}
              >
                <option value={0}>Choose…</option>
                {[1, 2, 3, 4, 5].map((r) => (
                  <option key={r}>{r}</option>
                ))}
              </select>
            </label>
            <button
              className={control}
              disabled={busy || !baseline || !candidate || !watched}
              onClick={() =>
                void action(() =>
                  evaluateLearningLesson(
                    trial.evaluation_lesson_id,
                    trial.id,
                    baseline,
                    candidate,
                    note,
                  ),
                )
              }
              type="button"
            >
              Save playback comparison
            </button>
          </div>
          <label className="mt-3 block text-xs">Comparison note
            <textarea className={`${control} mt-1 min-h-20 w-full py-2`} maxLength={1200} value={note} onChange={event => setNote(event.currentTarget.value)} placeholder="What changed? Check story, speech, captions, colour and effects." />
          </label>
          <label className="mt-3 flex min-h-11 items-center gap-2 text-xs"><input type="checkbox" checked={watched} onChange={event => setWatched(event.currentTarget.checked)} />I reviewed both exact previews, including any regressions.</label>
        </>
      ) : (
        <p className="mt-2 text-xs text-[#666862]">
          {trial.status === "ready" ? "Both exact preview files are needed to score this pair. One is unavailable; refresh after restoring it." : "Review this trial after its preview finishes. Failed trials cannot qualify a lesson."}
        </p>
      )}
    </details>
  );
}
