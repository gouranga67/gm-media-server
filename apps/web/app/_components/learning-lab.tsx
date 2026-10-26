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
  async function action(task: () => Promise<unknown>) {
    setBusy(true);
    setError("");
    try {
      await task();
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
        different jobs. Suggestions stay inactive until they improve held-out
        footage in playback comparisons. Existing tag-based preferences continue
        separately.
      </p>
      <p className="mt-2 text-xs leading-5 text-[#666862]">
        Proposing and scoring are local. Creating a trial preview uses a normal
        editor-model request. Promotion requires three separate jobs with
        footage excluded from the lesson&apos;s training examples, no lower
        ratings and at least one improvement.
      </p>
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
        {lesson.evaluation.held_out_jobs}/3 held-out comparisons ·{" "}
        {lesson.evaluation.regressions} lower ratings
      </p>
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
                <option key={job.id} value={job.id}>
                  {job.name} · version {job.version}
                </option>
              ))}
            </select>
          </label>
          <button
            className={control}
            disabled={busy || !jobId}
            type="button"
            onClick={() => {
              const job = jobs.find((j) => j.id === jobId);
              if (
                job &&
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
        {lesson.status === "promoted" ? (
          <button
            className={control}
            disabled={busy}
            onClick={() =>
              void action(() => setLearningLessonStatus(lesson.id, "rollback"))
            }
            type="button"
          >
            Roll back lesson
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
  const [baseline, setBaseline] = useState(0);
  const [candidate, setCandidate] = useState(0);
  return (
    <details className="rounded border border-[#D7D9D3] p-3">
      <summary className="min-h-11 cursor-pointer content-center text-sm font-bold text-[#173F5F]">
        {trial.project_name} · trial v{trial.version} · {trial.status}
      </summary>
      {trial.status === "ready" ? (
        <>
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            {[
              ["Baseline", trial.baseline_version],
              ["Trial", trial.version],
            ].map(([label, version]) => (
              <figure key={label}>
                <figcaption className="mb-2 text-xs font-bold">
                  {label} v{version}
                </figcaption>
                <video
                  className="max-h-80 w-full rounded bg-black"
                  controls
                  playsInline
                  preload="none"
                  src={`/api/media/jobs/${trial.job_id}/preview/file?version=${version}`}
                />
              </figure>
            ))}
          </div>
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
              disabled={busy || !baseline || !candidate}
              onClick={() =>
                void action(() =>
                  evaluateLearningLesson(
                    trial.evaluation_lesson_id,
                    trial.id,
                    baseline,
                    candidate,
                  ),
                )
              }
              type="button"
            >
              Save playback comparison
            </button>
          </div>
        </>
      ) : (
        <p className="mt-2 text-xs text-[#666862]">
          Review this trial after its preview finishes. Failed trials cannot
          qualify a lesson.
        </p>
      )}
    </details>
  );
}
