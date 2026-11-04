"use client";
import { useEffect, useState } from "react";
import { LearningComparisonHistory } from "./learning-comparison-history";
import { LearningTestCases } from "./learning-test-cases";
import {
  getLearningLab,
  proposeLearningLessons,
  tryLearningLesson,
  evaluateLearningLesson,
  setLearningLessonStatus,
  type LearningLab,
  type LearningLesson,
  type LearningTrial,
  type PlaybackDimension, type PlaybackVerdict, type PlaybackRubric,
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
      {data ? <LearningTestCases data={data} busy={busy} action={action} /> : null}
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
      {data?.history?.length ? <details className="mt-5 rounded border border-[#D7D9D3] p-3"><summary className="min-h-11 cursor-pointer content-center text-sm font-bold text-[#173F5F]">Promotion and rollback history</summary><ul className="mt-3 space-y-3">{data.history.map(event=><li className="break-words text-xs leading-5 text-[#53646F]" key={event.id}><strong>{event.action} · deployment {event.deployment_version}</strong> · {new Date(event.created_at).toLocaleString()}<br />{data.lessons.find(lesson=>lesson.id===event.lesson_id)?.directive ?? "Saved lesson"}<br />{event.previous_status} → {event.status} · rule {event.directive_hash.slice(0,12)}</li>)}</ul></details> : null}
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
  const [fullHistory, setFullHistory] = useState(false);
  const [drafts, setDrafts] = useState<Readonly<Record<string, PlaybackDraft>>>({});
  function renderTrial(trial: LearningTrial) {
    return <TrialReview key={trial.id} trial={trial} busy={busy} action={action} strict={(lesson.evaluation_protocol ?? 1) >= 2}
      draft={drafts[trial.id] ?? playbackDraft(trial)} onDraft={(patch) => setDrafts(current => ({...current,[trial.id]:{...(current[trial.id] ?? playbackDraft(trial)),...patch}}))} />;
  }
  const [jobId, setJobId] = useState("");
  const [caseId, setCaseId] = useState("");
  const caseMode = (lesson.evaluation_protocol ?? 1) >= 2;
  const cases = (data.cases ?? []).filter(saved=>saved.recipe===lesson.recipe && saved.edit_style===lesson.edit_style && !saved.archived_at);
  const selectedCase = cases.find(saved=>saved.id===caseId);
  const caseReason = lesson.case_options?.find(option=>option.case_id===caseId);
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
      <p className="mt-2 text-xs text-[#53646F]">{caseMode ? "Saved-case protocol · complete playback checklist and measured usage required." : "Legacy protocol · existing ratings are preserved. Upgrade before starting new saved-case evaluations."} Deployment {lesson.deployment_version ?? 0}.</p>
      {lesson.evaluation.history_scope === "all_saved_trials" ? <p className="mt-2 text-xs text-[#53646F]">Readiness checks all {lesson.evaluation.total_trials ?? 0} saved trials for this lesson, including older pages. It does not depend on which comparisons are open.</p> : null}
      {lesson.evaluation.blockers?.length ? <ul className="mt-2 list-disc space-y-1 pl-4 text-xs leading-5 text-[#A23B2A]">{lesson.evaluation.blockers.map(reason=><li key={reason}>{reason}</li>)}</ul> : null}
      {lesson.evaluation.excluded_comparisons ? <p className="mt-2 text-xs text-[#A23B2A]">{lesson.evaluation.excluded_comparisons} comparison(s) do not qualify. {caseMode ? "Older scores remain visible; use fresh saved-case trials for the new protocol." : "Review and save those pairs again before relying on them."}</p> : null}
      {lesson.evaluation.overlapping_comparisons ? <p className="mt-2 text-xs text-[#666862]">{lesson.evaluation.overlapping_comparisons} comparison(s) reuse footage and do not add independent evidence.</p> : null}
      {typeof lesson.evaluation.token_delta === "number" ? <p className="mt-2 text-xs text-[#53646F]">Average trial token change: {lesson.evaluation.token_delta > 0 ? "+" : ""}{lesson.evaluation.token_delta.toLocaleString()} across {lesson.evaluation.costed_comparisons} measured pair(s). Cost does not determine creative quality; inspect both before promoting.</p> : null}
      <p className="mt-2 text-xs leading-5 text-[#666862]">Playback ratings are subjective. A trial can vary for reasons beyond this rule; these comparisons do not prove causality or guarantee better future edits.</p>
      {lesson.status === "proposed" ? (
        <div className="mt-3 space-y-3">
          {caseMode ? <label className="block text-xs">Try a saved independent test case<select aria-label="Saved test case for lesson" className={`${control} mt-1 w-full`} value={caseId} disabled={busy} onChange={event=>setCaseId(event.currentTarget.value)}><option value="">Choose a saved case with fresh footage…</option>{cases.map(saved=>{const option=lesson.case_options?.find(option=>option.case_id===saved.id);return <option key={saved.id} value={saved.id} disabled={option?.eligible!==true}>{saved.label} · {saved.recording_group} · v{saved.version}{option?.reason ? ` · ${option.reason}` : ""}</option>;})}</select></label> : <label className="block text-xs">
            Try on a separate ready job
            <select
              aria-label="Independent ready job for lesson"
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
          </label>}
          <button
            className={control}
            disabled={busy || (caseMode ? !selectedCase || caseReason?.eligible!==true : !selected || blocked)}
            type="button"
            onClick={() => {
              const job = caseMode ? selectedCase && {id:selectedCase.job_id,version:selectedCase.version} : jobs.find((j) => j.id === jobId);
              if (
                job && (caseMode ? caseReason?.eligible===true : !blocked) &&
                window.confirm(
                  "Create a trial preview using a normal editor-model request? This uses model tokens and preserves the baseline preview.",
                )
              )
                void action(() =>
                  tryLearningLesson(lesson.id, job.id, job.version,caseMode ? caseId : undefined),
                );
            }}
          >
            Create trial preview · uses model tokens
          </button>
          {selectedCase ? <p className="text-xs leading-5 text-[#53646F]">Review criteria: {selectedCase.expectations}{caseReason?.reason ? ` ${caseReason.reason}` : " The server rechecks the saved task before queueing."}</p> : null}
          {caseMode && !cases.some(saved=>lesson.case_options?.some(option=>option.case_id===saved.id && option.eligible)) ? <p className="text-xs leading-5 text-[#666862]">Save an ordinary baseline using independent footage in Reusable playback test cases above. Training footage and reused trial footage cannot add evidence.</p> : null}
          {selected && optionFor(selected.id)?.reason ? <p className="text-xs text-[#A23B2A]">{optionFor(selected.id)?.reason}</p> : null}
          {lesson.trial_options && !jobs.some(job => optionFor(job.id)?.eligible) ? <p className="text-xs leading-5 text-[#666862]">No independent ready baseline is available in this list. Use different footage and finish an ordinary edit first. Uploading the same file again does not make it independent.</p> : null}
        </div>
      ) : null}
      <div className="mt-3 space-y-3">
        <button className={control} disabled={busy} onClick={() => setFullHistory(current=>!current)} type="button">{fullHistory ? "Return to recent comparisons" : "Browse all comparisons for this lesson"}</button>
        {fullHistory ? <LearningComparisonHistory lessonId={lesson.id} busy={busy} refreshToken={data} renderTrial={renderTrial} />
          : data.trials.filter(trial=>trial.evaluation_lesson_id===lesson.id).map(renderTrial)}
      </div>
      <div className="mt-4 flex flex-wrap gap-3">
        {!caseMode && lesson.status!=="promoted" ? <button className={control} disabled={busy} onClick={()=>{if(window.confirm("Use saved-case evaluation? Existing ratings remain visible, but new promotion will require three saved independent playback comparisons with the full checklist and measured usage."))void action(()=>setLearningLessonStatus(lesson.id,"upgrade"));}} type="button">Upgrade to saved-case evaluation</button> : null}
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
type PlaybackDraft = { baseline: number; candidate: number; note: string; watched: boolean; rubric: Partial<Record<PlaybackDimension,PlaybackVerdict>> };
function playbackDraft(trial: LearningTrial): PlaybackDraft {
  return {baseline:trial.comparison?.baseline_rating ?? 0,candidate:trial.comparison?.candidate_rating ?? 0,note:trial.comparison?.note ?? "",watched:false,rubric:trial.comparison?.rubric ?? {}};
}
function TrialReview({
  trial,
  busy,
  action,
  strict, draft, onDraft,
}: {
  readonly trial: LearningTrial;
  readonly busy: boolean;
  readonly action: (task: () => Promise<unknown>) => Promise<void>;
  readonly strict: boolean;
  readonly draft: PlaybackDraft; readonly onDraft: (patch: Partial<PlaybackDraft>) => void;
}) {
  const {baseline,candidate,note,watched,rubric} = draft;
  const rubricRequired = Boolean(trial.evaluation_case_id);
  const dimensions: readonly {key:PlaybackDimension;label:string}[] = [
    {key:"brief",label:"Brief and test criteria"},{key:"story",label:"Story and ending"},{key:"speech",label:"Complete words and sync"},
    {key:"captions",label:"Caption timing and readability"},{key:"visuals",label:"Colour, framing and cutaways"},{key:"audio",label:"Sound, music and effects"}];
  const complete = dimensions.every(item=>rubric[item.key]);
  const playable = trial.status === "ready" && trial.baseline_available !== false && trial.candidate_available !== false;
  return (
    <details className="rounded border border-[#D7D9D3] p-3">
      <summary className="min-h-11 cursor-pointer content-center text-sm font-bold text-[#173F5F]">
        {trial.project_name} · trial v{trial.version} · {trial.status}
      </summary>
      {playable ? (
        <>
          {trial.test_case ? <div className="mt-3 rounded bg-[#EFF6FA] p-3 text-sm leading-6 text-[#173F5F]"><strong>{trial.test_case.label}</strong><p>{trial.test_case.expectations}</p><p className="mt-1 text-xs">{trial.test_case.max_candidate_tokens ? `Qualification ceiling: ${trial.test_case.max_candidate_tokens.toLocaleString()} candidate tokens.` : "Compare recorded tokens and model latency alongside playback."}</p></div> : strict ? <p className="mt-2 text-xs text-[#A23B2A]">This legacy trial has no saved test case. Its ratings remain visible, but it cannot qualify the upgraded lesson.</p> : null}
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
          {rubricRequired ? <fieldset className="mt-4 grid gap-3 sm:grid-cols-2"><legend className="mb-2 text-sm font-bold text-[#173F5F]">How does the trial compare with the baseline?</legend>{dimensions.map(({key,label})=><label className="min-w-0 text-xs" key={key}>{label}<select aria-label={`Compare ${key}`} className={`${control} mt-1 w-full`} disabled={busy} value={rubric[key] ?? ""} onChange={event=>{const value=event.currentTarget.value as PlaybackVerdict;onDraft({rubric:{...rubric,[key]:value}});}}><option value="">Choose…</option><option value="better">Better</option><option value="same">Same</option><option value="worse">Worse</option><option value="not_applicable">Not applicable</option></select></label>)}</fieldset> : null}
          <div className="mt-3 flex flex-wrap items-end gap-3">
            <label className="text-xs">
              Baseline rating
              <select
                className={`${control} mt-1 block`}
                value={baseline}
                onChange={(e) => onDraft({baseline:Number(e.currentTarget.value)})}
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
                onChange={(e) => onDraft({candidate:Number(e.currentTarget.value)})}
              >
                <option value={0}>Choose…</option>
                {[1, 2, 3, 4, 5].map((r) => (
                  <option key={r}>{r}</option>
                ))}
              </select>
            </label>
            <button
              className={control}
              disabled={busy || !baseline || !candidate || !watched || (rubricRequired && !complete) || (strict && !rubricRequired)}
              onClick={() =>
                void action(() =>
                  evaluateLearningLesson(
                    trial.evaluation_lesson_id,
                    trial.id,
                    baseline,
                    candidate,
                    note,
                    rubricRequired ? {rubric:rubric as PlaybackRubric,reviewed_both:watched} : undefined,
                  ),
                )
              }
              type="button"
            >
              Save playback comparison
            </button>
          </div>
          <label className="mt-3 block text-xs">Comparison note
            <textarea aria-label="Playback comparison note" className={`${control} mt-1 min-h-20 w-full py-2`} maxLength={1200} value={note} onChange={event => onDraft({note:event.currentTarget.value})} placeholder="What changed? Check story, speech, captions, colour and effects." />
          </label>
          <label className="mt-3 flex min-h-11 items-center gap-2 text-xs"><input type="checkbox" checked={watched} onChange={event => onDraft({watched:event.currentTarget.checked})} />I reviewed both exact previews, including any regressions.</label>
        </>
      ) : (
        <p className="mt-2 text-xs text-[#666862]">
          {trial.status === "ready" ? "Both exact preview files are needed to score this pair. One is unavailable; refresh after restoring it." : "Review this trial after its preview finishes. Failed trials cannot qualify a lesson."}
        </p>
      )}
    </details>
  );
}
