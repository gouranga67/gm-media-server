"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { getReleaseReadiness, saveReleaseObservation, type ReleaseReadiness, type ReleaseObservation } from "@/lib/release-api";
import { StudioNav } from "./studio-nav";

const control = "min-h-11 rounded-md border border-[#D7D9D3] bg-white px-3 text-sm text-[#173F5F] disabled:opacity-50";
const stateLabel = (result?: string) => result === "pass" ? "Passed" : result === "fail" ? "Needs work" : result === "not_applicable" ? "Not applicable" : "Not tested";
export function PilotChecklist() {
  const [report,setReport] = useState<ReleaseReadiness>();
  const [error,setError] = useState("");
  const [busy,setBusy] = useState(false);
  const [saved,setSaved] = useState(false);
  useEffect(()=>{
    let active=true;
    getReleaseReadiness().then(value=>{if(active)setReport(value);}).catch((e:unknown)=>{if(active)setError(e instanceof Error ? e.message : "Release readiness is unavailable.");});
    return ()=>{active=false;};
  },[]);
  async function action(task?:()=>Promise<unknown>) {
    if(busy)return;
    setBusy(true);setError("");setSaved(false);
    try {if(task)await task();setReport(await getReleaseReadiness());setSaved(Boolean(task));}
    catch(e){setError(e instanceof Error ? e.message : "Acceptance could not be saved.");}
    finally{setBusy(false);}
  }
  return <main className="min-h-dvh bg-[#F7F7F5] px-4 py-5 text-[#20211F] [color-scheme:light]"><div className="mx-auto max-w-5xl">
    <StudioNav current="/studio/pilot" />
    <header className="mt-8 flex flex-wrap items-start justify-between gap-4"><div><p className="font-mono text-xs font-bold uppercase text-[#215B43]">One shared private studio</p><h1 className="mt-2 text-3xl font-black text-[#173F5F]">Release acceptance</h1></div><button className={control} disabled={busy} onClick={()=>void action()} type="button">Refresh readiness</button></header>
    <p className="mt-3 max-w-3xl text-sm leading-6 text-[#666862]">Check the full workflow with real footage. Saved observations belong to this deployed build; earlier results remain in history. Passing source tests cannot judge a story or certify a public customer service.</p>
    {error ? <p role="alert" className="my-4 rounded bg-[#FFF0EC] p-3 text-sm text-[#A23B2A]">{error}</p> : null}
    {saved ? <p role="status" className="my-4 rounded bg-[#E4F1E9] p-3 text-sm text-[#215B43]">Observation saved. No edit, model request or post was created.</p> : null}
    {!report && !error ? <p className="my-8 text-sm">Reading release readiness…</p> : null}
    {report ? <div className="mt-6 space-y-6">
      <div className="grid gap-3 sm:grid-cols-2"><div className="rounded-lg border border-[#D7D9D3] bg-white p-5"><h2 className="font-bold text-[#173F5F]">Private pilot</h2><p className="mt-2 text-sm">{report.private_pilot_complete ? "Recorded checks complete" : "Checks still needed"}</p></div><div className="rounded-lg border border-[#D7D9D3] bg-white p-5"><h2 className="font-bold text-[#173F5F]">Publishing acceptance</h2><p className="mt-2 text-sm">{report.publishing_acceptance_complete ? "Recorded checks complete" : "Setup or real post checks still needed"}</p><Link className="mt-2 inline-flex min-h-11 items-center text-sm font-bold text-[#173F5F] underline" href="/publishing">Open Publishing</Link></div></div>
      <p className="break-words text-xs leading-5 text-[#53646F]">Build {report.build_id.slice(0,12)} · read {new Date(report.generated_at).toLocaleString()}. A new deployment needs fresh observations. Account configuration alone does not establish remote posting permissions.</p>
      <section className="rounded-lg border border-[#BFD2DE] bg-[#EFF6FA] p-5"><p className="font-mono text-xs font-bold uppercase text-[#215B43]">Recommended next test</p><h2 className="mt-2 text-lg font-bold text-[#173F5F]">Ordinary-wall background replacement · Beta</h2><ol className="mt-3 list-decimal space-y-2 pl-5 text-sm leading-6"><li>Start a new edit, choose <strong>Replace background · Beta</strong>, then assign the presenter and intended background.</li><li>Let the normal edit finish, then create the two-second comparison shown before approval.</li><li>Watch the original, result and mask. Check hair, both hands, anything being held, background holes and flicker.</li><li>Mark the sample usable or keep the original. The beta never changes the edit or export, so you can test difficult walls safely.</li></ol><div className="mt-3 flex flex-wrap gap-x-5"><Link className="inline-flex min-h-11 items-center font-bold text-[#173F5F] underline" href="/jobs/new">Start background test</Link><Link className="inline-flex min-h-11 items-center font-bold text-[#173F5F] underline" href="/guide#review">Open the Guide</Link></div><p className="mt-3 text-xs leading-5 text-[#53646F]">The formal green-screen acceptance check below remains for real prepared green/blue-screen footage. Do not record an ordinary-wall beta sample as a green-screen pass.</p></section>
      <section className="rounded-lg border border-[#D7D9D3] bg-white p-5"><h2 className="text-lg font-bold text-[#173F5F]">Human playback and workflow checks</h2><p className="mt-2 text-sm leading-6 text-[#666862]">Record what you actually tested, including failures. Saving is an owner attestation. It never starts the test, connects an account or approves publication.</p><ul className="mt-4 divide-y divide-[#E7E8E4]">{report.checks.map(item=><li key={item.key} className="py-3"><div className="flex flex-wrap items-center justify-between gap-2"><strong className="text-sm text-[#173F5F]">{item.label}</strong><span className={`rounded px-2 py-1 text-xs ${item.observation?.result === "pass" ? "bg-[#E4F1E9] text-[#215B43]" : item.observation?.result === "fail" ? "bg-[#FFF0EC] text-[#A23B2A]" : "bg-[#EFF6FA] text-[#53646F]"}`}>{stateLabel(item.observation?.result)}</span></div>{item.observation ? <p className="mt-2 break-words text-xs leading-5 text-[#666862]">{item.observation.note}</p> : null}</li>)}</ul></section>
      <ObservationForm key={report.build_id} report={report} busy={busy} action={action} />
      <details className="rounded-lg border border-[#D7D9D3] bg-white p-5" open><summary className="min-h-11 cursor-pointer content-center font-bold text-[#173F5F]">Machine evidence and next actions</summary><ul className="mt-3 space-y-3">{report.technical.map(item=><li className="rounded bg-[#F7F7F5] p-3 text-sm" key={item.key}><strong className="text-[#173F5F]">{item.label}</strong> · {item.status === "pass" ? "Recorded" : "Needs attention"}<p className="mt-1 text-xs leading-5 text-[#666862]">{item.detail ?? item.method}{item.completed_at ? ` · ${new Date(item.completed_at).toLocaleString()}` : ""}</p></li>)}</ul><p className="mt-4 text-xs leading-5 text-[#53646F]">Active work: {report.queues.edits} edits · {report.queues.analysis} analyses · {report.queues.exports} exports · {report.queues.posts} posts. {report.queues.failed_posts} failed and {report.queues.uncertain_posts} uncertain posting records. Historical failures are shown separately from current service health.</p><div className="mt-2 flex flex-wrap gap-x-5"><Link className="inline-flex min-h-11 items-center text-sm font-bold text-[#173F5F] underline" href="/system">System & backup</Link><Link className="inline-flex min-h-11 items-center text-sm font-bold text-[#173F5F] underline" href="/operations">Operations</Link></div><p className="mt-2 text-xs leading-5 text-[#666862]">Run the existing isolated restore verifier to record machine evidence. Reboot recovery is a separate deliberate maintenance drill; this page never runs it.</p></details>
      <details className="rounded-lg border border-[#D7D9D3] bg-white p-5"><summary className="min-h-11 cursor-pointer content-center font-bold text-[#173F5F]">Saved acceptance history · {report.history.length} recent records</summary><ul className="mt-3 divide-y divide-[#E7E8E4]">{report.history.map(item=><li key={item.id} className="py-3 text-xs leading-5"><strong className="text-[#173F5F]">{report.checks.find(check=>check.key===item.check_key)?.label ?? item.check_key} · {stateLabel(item.result)}</strong><p className="break-words">{item.note}</p><p className="text-[#666862]">Build {item.build_id.slice(0,12)} · {new Date(item.created_at).toLocaleString()}</p></li>)}</ul></details>
    </div> : null}
  </div></main>;
}

function ObservationForm({report,busy,action}:{readonly report:ReleaseReadiness;readonly busy:boolean;readonly action:(task:()=>Promise<unknown>)=>Promise<void>}) {
  const [key,setKey]=useState(report.checks[0]?.key ?? "");
  const [result,setResult]=useState<ReleaseObservation["result"]>("pass");
  const [note,setNote]=useState("");const [job,setJob]=useState("");const [version,setVersion]=useState("");const [post,setPost]=useState("");const [observed,setObserved]=useState(false);
  const request=useRef<{key:string;id:string}|undefined>(undefined);
  const check=report.checks.find(item=>item.key===key);
  const uuid=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
  const needsEdit=check?.evidence_kind==="edit";
  const needsPost=check?.evidence_kind==="post";
  const playbackOptions=report.playback_options.filter(item=>(key!=="story_playback" || item.has_final) &&
    (key!=="green_screen_playback" || item.composition_mode==="green_screen"));
  const previewHelp=key==="green_screen_playback"
    ? "Only completed green-screen previews appear. Inspect the exact preview on this screen and your phone before recording the result."
    : key==="story_playback"
      ? "Choose an exported version for the downloaded-phone check. A pass needs its exact available preview."
      : "Choose the exact completed preview you inspected. A failure can be recorded without one when the preview is unavailable; describe the job or problem in your note.";
  const selectedPosts=report.published_posts.filter(item=>key==="scheduled_post" ? item.schedule_requested===true : item.platform===key.replace("_post",""));
  const valid=Boolean(check && /^[0-9a-f]{7,64}$/.test(report.build_id) && observed && note.trim().length>=8 &&
    (result!=="not_applicable" || check.allow_na) &&
    (!needsEdit || result!=="pass" || uuid.test(job.trim()) && Number.isInteger(Number(version)) && Number(version)>0) &&
    (!needsPost || result!=="pass" || selectedPosts.some(item=>item.id===post)));
  function submit() {
    if(busy || !valid)return;
    const fields={build_id:report.build_id,check_key:key,result,note:note.trim(),job_id:needsEdit && job.trim() ? job.trim() : null,
      version:needsEdit && version ? Number(version) : null,publishing_post_id:needsPost && post ? post : null,observed:true as const};
    const fingerprint=JSON.stringify(fields);if(request.current?.key!==fingerprint)request.current={key:fingerprint,id:crypto.randomUUID()};
    const payload={id:request.current.id,...fields};void action(()=>saveReleaseObservation(payload));
  }
  return <section className="rounded-lg border border-[#BFD2DE] bg-[#EFF6FA] p-5"><h2 className="text-lg font-bold text-[#173F5F]">Record an observed check</h2><form className="mt-4 grid gap-4 sm:grid-cols-2" onSubmit={event=>{event.preventDefault();submit();}}>
    <label className="min-w-0 text-xs font-bold">Check<select aria-label="Acceptance check" className={`${control} mt-1 w-full`} disabled={busy} value={key} onChange={event=>{setKey(event.currentTarget.value);setObserved(false);setPost("");setResult("pass");}}>{report.checks.map(item=><option key={item.key} value={item.key}>{item.label}</option>)}</select></label>
    <label className="min-w-0 text-xs font-bold">Result<select aria-label="Acceptance result" className={`${control} mt-1 w-full`} disabled={busy} value={result} onChange={event=>setResult(event.currentTarget.value as ReleaseObservation["result"])}><option value="pass">Pass</option><option value="fail">Fail — needs work</option>{check?.allow_na ? <option value="not_applicable">Not applicable</option> : null}</select></label>
    {needsEdit ? <label className="min-w-0 text-xs font-bold sm:col-span-2">Exact preview you reviewed<select aria-label="Acceptance preview" className={`${control} mt-1 w-full`} disabled={busy} value={job && version ? `${job}/${version}` : ""} onChange={event=>{const [id,revision]=event.currentTarget.value.split("/");setJob(id ?? "");setVersion(revision ?? "");}}><option value="">Choose a completed preview…</option>{playbackOptions.map(item=><option key={`${item.job_id}/${item.version}`} value={`${item.job_id}/${item.version}`}>{item.project_name} · version {item.version}</option>)}</select><span className="mt-2 block font-normal leading-5">{previewHelp}</span></label> : null}
    {needsPost ? <label className="min-w-0 text-xs font-bold sm:col-span-2">Published record you checked<select aria-label="Acceptance published post" className={`${control} mt-1 w-full`} disabled={busy} value={post} onChange={event=>setPost(event.currentTarget.value)}><option value="">Choose a published result…</option>{selectedPosts.map(item=><option key={item.id} value={item.id}>{item.platform} · {item.account_name} · v{item.version} · {new Date(item.publish_at).toLocaleString()}</option>)}</select><span className="mt-2 block font-normal leading-5">Only already published records appear. Scheduling checks require explicit scheduling intent saved by this build; older unknown intent is not guessed.</span></label> : null}
    <label className="min-w-0 text-xs font-bold sm:col-span-2">What did you check?<textarea aria-label="Acceptance observation note" className={`${control} mt-1 min-h-24 w-full py-2`} maxLength={2000} disabled={busy} value={note} onChange={event=>setNote(event.currentTarget.value)} placeholder="Describe the actual result, device, expected behaviour and anything that needs work. Do not enter passwords or tokens." /></label>
    <label className="flex min-h-11 items-center gap-3 text-sm sm:col-span-2"><input type="checkbox" aria-label="Confirm actual observation" checked={observed} disabled={busy} onChange={event=>setObserved(event.currentTarget.checked)} />I actually checked this result for the displayed build.</label>
    <button className={`${control} font-bold sm:justify-self-start`} disabled={busy || !valid} type="submit">Save acceptance observation</button>
  </form></section>;
}
