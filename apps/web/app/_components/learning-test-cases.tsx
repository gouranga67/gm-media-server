"use client";
import { useRef, useState } from "react";
import { saveLearningCase, setLearningCaseStatus, type LearningLab } from "@/lib/media-api";

const control = "min-h-11 w-full rounded border border-[#D7D9D3] bg-white px-3 text-sm text-[#173F5F] disabled:opacity-50";
export function LearningTestCases({ data, busy, action }: {
  readonly data: LearningLab; readonly busy: boolean; readonly action: (task: () => Promise<unknown>) => Promise<void>;
}) {
  const [jobId,setJobId] = useState("");
  const [label,setLabel] = useState("");
  const [group,setGroup] = useState("");
  const [category,setCategory] = useState("story");
  const [expectations,setExpectations] = useState("");
  const [tokens,setTokens] = useState("");
  const request = useRef<{ key: string; id: string } | undefined>(undefined);
  const jobs = data.jobs.filter(job => job.ordinary !== false && !(data.cases ?? []).some(saved => saved.job_id === job.id && saved.version === job.version));
  const selected = jobs.find(job => job.id === jobId);
  const validTokens = !tokens || Number.isInteger(Number(tokens)) && Number(tokens) >= 1 && Number(tokens) <= 2_000_000;
  function save() {
    if (busy || !selected || !label.trim() || !group.trim() || !expectations.trim() || !validTokens) return;
    const payload = { job_id:selected.id,base_version:selected.version,label:label.trim(),recording_group:group.trim(),category,
      expectations:expectations.trim(),max_candidate_tokens:tokens ? Number(tokens) : null };
    const key = JSON.stringify(payload);
    if (request.current?.key !== key) request.current = { key, id:crypto.randomUUID() };
    const id = request.current.id;
    void action(() => saveLearningCase({id,...payload}));
  }
  return <details className="my-5 rounded-lg border border-[#BFD2DE] bg-[#EFF6FA] p-4">
    <summary className="min-h-11 cursor-pointer content-center font-bold text-[#173F5F]">Reusable playback test cases · {data.cases?.length ?? 0}</summary>
    <p className="mt-2 text-sm leading-6 text-[#666862]">Save a good ordinary edit and describe what a better edit must preserve. Use different recording sessions for independent tests. Clips from the same shoot should share a footage group, even if they are separate files.</p>
    <p className="mt-2 text-xs leading-5 text-[#666862]">Saving is local and uses no model tokens. It freezes the brief, source checksums, analysis, labels and exact baseline. The preview stays protected from routine cleanup until you archive the case. Criteria guide your review; they are not extra instructions sent to the editor.</p>
    <form className="mt-4 grid gap-3 sm:grid-cols-2" onSubmit={event => {event.preventDefault();save();}}>
      <label className="min-w-0 text-xs font-bold">Ordinary ready baseline<select aria-label="Test case baseline" className={`${control} mt-1`} value={jobId} disabled={busy} onChange={event=>setJobId(event.currentTarget.value)}><option value="">Choose a completed ordinary edit…</option>{jobs.map(job=><option key={job.id} value={job.id}>{job.name} · v{job.version}</option>)}</select></label>
      <label className="min-w-0 text-xs font-bold">Test name<input aria-label="Test case name" className={`${control} mt-1`} value={label} disabled={busy} maxLength={120} onChange={event=>setLabel(event.currentTarget.value)} placeholder="e.g. Complete product explanation" /></label>
      <label className="min-w-0 text-xs font-bold">Footage group<input aria-label="Test recording group" className={`${control} mt-1`} value={group} disabled={busy} maxLength={120} onChange={event=>setGroup(event.currentTarget.value)} placeholder="e.g. Monday cream shoot" /></label>
      <label className="min-w-0 text-xs font-bold">Main test<select className={`${control} mt-1`} value={category} disabled={busy} onChange={event=>setCategory(event.currentTarget.value)}>{["story","speech","captions","visuals","audio","effects"].map(value=><option key={value} value={value}>{value[0].toUpperCase()+value.slice(1)}</option>)}</select></label>
      <label className="min-w-0 text-xs font-bold sm:col-span-2">What must a successful edit preserve?<textarea aria-label="Test case expectations" className={`${control} mt-1 min-h-24 py-2`} value={expectations} disabled={busy} maxLength={1200} onChange={event=>setExpectations(event.currentTarget.value)} placeholder="Keep all five points, complete words, synchronised speech and a clear ending. Check that any cutaways show the correct product." /></label>
      <details className="sm:col-span-2"><summary className="min-h-11 cursor-pointer content-center text-xs font-bold text-[#173F5F]">Optional cost qualification limit</summary><label className="block max-w-md text-xs">Maximum candidate tokens<input aria-label="Test case token ceiling" className={`${control} mt-1`} type="number" min={1} max={2_000_000} value={tokens} disabled={busy} onChange={event=>setTokens(event.currentTarget.value)} /></label><p className="mt-2 text-xs leading-5 text-[#666862]">A result above this limit cannot qualify the lesson. This checks recorded usage after a trial; it is not a provider spending cap. Leave blank to compare measured usage without a limit.</p></details>
      <button className={`${control} w-auto font-bold sm:justify-self-start`} disabled={busy || !selected || !label.trim() || !group.trim() || !expectations.trim() || !validTokens} type="submit">Save playback test case · no AI</button>
    </form>
    <div className="mt-5 space-y-3">{(data.cases ?? []).map(saved=><article key={saved.id} className="rounded border border-[#D7D9D3] bg-white p-3"><div className="flex flex-wrap items-center justify-between gap-2"><div className="min-w-0"><h3 className="break-words font-bold text-[#173F5F]">{saved.label}</h3><p className="mt-1 text-xs text-[#666862]">{saved.category} · {saved.recording_group} · {saved.source_count} sources · v{saved.version}{saved.archived_at ? " · archived" : " · protected baseline"}</p></div><button className={`${control} w-auto`} disabled={busy} onClick={()=>void action(()=>setLearningCaseStatus(saved.id,saved.archived_at ? "restore" : "archive"))} type="button">{saved.archived_at ? "Restore case" : "Archive case"}</button></div><p className="mt-2 break-words text-sm leading-6 text-[#53646F]">{saved.expectations}</p>{saved.baseline_available ? <a className="mt-2 inline-flex min-h-11 items-center text-sm font-bold text-[#173F5F] underline" href={`/api/media/jobs/${saved.job_id}/preview/file?version=${saved.version}`} target="_blank" rel="noreferrer">Open exact baseline v{saved.version}</a> : <p className="mt-2 text-xs text-[#A23B2A]">The baseline preview is unavailable. Restore it before starting a trial.</p>}</article>)}</div>
  </details>;
}
