"use client";

import Link from "next/link";
import { useEffect, useState, type ReactNode } from "react";
import { LoaderCircleIcon } from "lucide-react";

import {
  getUsageDashboard,
  type UsageDashboard as UsageData,
  type UsageJobSummary,
} from "@/lib/media-api";

type UsageScope = 0 | 30;
type JobFilter = "editing" | "verification" | "all";

function tokens(value: number) {
  return new Intl.NumberFormat().format(value);
}

function date(value: string) {
  return new Intl.DateTimeFormat(undefined, { day: "numeric", month: "short" }).format(new Date(value));
}

function recipe(value: UsageJobSummary["recipe"]) {
  return value === "montage" ? "Montage" : "Talking-head";
}

function status(value: string) {
  if (["delivered", "complete"].includes(value)) return { dot: "bg-[#3A8F63]", label: "Delivered" };
  if (value === "awaiting_review") return { dot: "bg-[#3A8F63]", label: "Preview ready" };
  if (value === "failed") return { dot: "bg-[#A23B2A]", label: "Failed" };
  if (value === "cancelled") return { dot: "bg-[#777A75]", label: "Cancelled" };
  if (["approved", "rendering", "exporting"].includes(value)) return { dot: "bg-[#FF8C69]", label: "Exporting" };
  if (["planning", "previewing", "revising"].includes(value)) return { dot: "bg-[#FF8C69]", label: "Editing" };
  if (["ingesting", "analyzing"].includes(value)) return { dot: "bg-[#FF8C69]", label: "Analyzing" };
  if (value === "uploading") return { dot: "bg-[#FF8C69]", label: "Uploading" };
  if (value === "draft") return { dot: "bg-[#F4D35E]", label: "Draft" };
  return { dot: "bg-[#F4D35E]", label: "Queued" };
}

function Metric({ label, value, prominent = false }: { readonly label: string; readonly value: string; readonly prominent?: boolean }) {
  return (
    <div className="rounded-md border border-[#D7D9D3] bg-white p-4">
      <p className="font-mono text-[10px] font-bold text-[#666862] uppercase">{label}</p>
      <p className={`mt-2 font-bold text-[#173F5F] ${prominent ? "text-xl" : "text-lg"}`}>{value}</p>
    </div>
  );
}

function MobileLabel({ children }: { readonly children: string }) {
  return <span className="font-mono text-[10px] font-bold text-[#666862] uppercase md:hidden">{children}</span>;
}

function JobCell({ alignRight = false, children, label, mono = false, narrow = false }: { readonly alignRight?: boolean; readonly children: ReactNode; readonly label: string; readonly mono?: boolean; readonly narrow?: boolean }) {
  return (
    <div className={`flex items-center justify-between md:block ${narrow ? "md:col-span-1" : "md:col-span-2"} ${alignRight ? "md:text-right" : ""} ${mono ? "font-mono text-xs text-[#666862]" : "text-[#20211F]"}`}>
      <MobileLabel>{label}</MobileLabel>
      <span className="min-w-0 truncate">{children}</span>
    </div>
  );
}

function JobRow({ job }: { readonly job: UsageJobSummary }) {
  const jobStatus = status(job.status);
  return (
    <Link className="group block rounded-md border border-[#D7D9D3] bg-white p-4 transition-colors hover:bg-[#EFF6FA] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#173F5F] md:rounded-none md:border-x-0 md:border-t-0 md:p-0 md:last:border-b-0" href={`/jobs/${job.id}`}>
      <div className="grid grid-cols-1 gap-y-3 text-sm md:grid-cols-12 md:items-center md:gap-4 md:px-4 md:py-3">
        <div className="md:col-span-3"><div className="flex min-w-0 items-center gap-2"><p className="truncate font-bold text-[#173F5F] group-hover:underline group-hover:underline-offset-2">{job.project_name}</p>{job.history_kind === "verification" ? <span className="shrink-0 rounded-full bg-[#E9EDF0] px-2 py-0.5 font-mono text-[9px] font-bold text-[#53646F] uppercase">Test</span> : null}</div><p className="mt-0.5 font-mono text-[10px] text-[#666862]">{job.id.slice(0, 8)}</p></div>
        <JobCell label="Recipe">{recipe(job.recipe)}</JobCell>
        <div className="flex items-center justify-between md:col-span-2 md:justify-start"><MobileLabel>Status</MobileLabel><span className="inline-flex items-center gap-1.5"><span aria-hidden="true" className={`size-1.5 rounded-full ${jobStatus.dot}`} />{jobStatus.label}</span></div>
        <JobCell label="Date" mono narrow>{date(job.created_at)}</JobCell>
        <JobCell label="Model">{job.model ?? "No model call"}</JobCell>
        <JobCell alignRight label="Requests" mono narrow>{job.requests}</JobCell>
        <JobCell alignRight label="Tokens" mono narrow>{tokens(job.total_tokens)}</JobCell>
      </div>
    </Link>
  );
}

export function UsageDashboard() {
  const [scope, setScope] = useState<UsageScope>(0);
  const [jobFilter, setJobFilter] = useState<JobFilter>("editing");
  const [usage, setUsage] = useState<UsageData>();
  const [error, setError] = useState<string>();

  useEffect(() => {
    let cancelled = false;
    setUsage(undefined);
    setError(undefined);
    void getUsageDashboard(scope).then((result) => { if (!cancelled) setUsage(result); }).catch((requestError: unknown) => {
      if (!cancelled) setError(requestError instanceof Error ? requestError.message : "Usage is unavailable");
    });
    return () => { cancelled = true; };
  }, [scope]);

  const visibleJobs = usage?.job_history.filter((job) => jobFilter === "all" || job.history_kind === jobFilter) ?? [];
  const verificationJobs = usage?.job_history.filter((job) => job.history_kind === "verification").length ?? 0;
  const jobFilterLabel = jobFilter === "editing" ? "Editing jobs" : jobFilter === "verification" ? "Test jobs" : "All jobs";
  return (
    <main className="min-h-dvh bg-[#F7F7F5] px-4 pt-[max(1.25rem,env(safe-area-inset-top))] pb-[max(2rem,env(safe-area-inset-bottom))] text-[#20211F] [color-scheme:light]">
      <div className="mx-auto w-full max-w-5xl">
        <header className="border-b border-[#D7D9D3] pb-4">
          <div className="flex flex-wrap items-center gap-4"><Link className="text-sm font-bold tracking-tight text-[#173F5F]" href="/jobs/new">GM Studio</Link><Link className="font-mono text-[10px] font-bold text-[#173F5F] underline underline-offset-4" href="/library">Media library</Link><Link className="font-mono text-[10px] font-bold text-[#173F5F] underline underline-offset-4" href="/library/duplicates">Duplicate audit</Link><Link className="font-mono text-[10px] font-bold text-[#173F5F] underline underline-offset-4" href="/system">System</Link></div>
          <div className="mt-3 flex flex-wrap items-end justify-between gap-4">
            <div><h1 className="text-2xl font-bold tracking-tight text-[#173F5F]">AI usage &amp; jobs</h1><p className="mt-2 text-sm leading-relaxed text-[#666862]">Local editing history and measured model usage.</p></div>
            <div aria-label="Usage period" className="flex rounded-md border border-[#D7D9D3] bg-white p-1" role="group">
              {([0, 30] as const).map((days) => <button aria-pressed={scope === days} className={`min-h-9 rounded px-3 font-mono text-[10px] font-bold uppercase ${scope === days ? "bg-[#173F5F] text-white" : "text-[#666862]"}`} key={days} onClick={() => setScope(days)} type="button">{days === 0 ? "All time" : "30 days"}</button>)}
            </div>
          </div>
        </header>

        {!usage && !error ? <div className="flex min-h-64 items-center justify-center"><LoaderCircleIcon aria-label="Loading usage" className="size-8 animate-spin text-[#173F5F]" /></div> : null}
        {error ? <p className="mt-6 text-sm text-[#A23B2A]" role="alert">{error}</p> : null}
        {usage ? (
          <div className="space-y-8 py-6">
            <section className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
              <Metric label="Total tokens" prominent value={tokens(usage.total_tokens)} /><Metric label="Requests" prominent value={tokens(usage.requests)} /><Metric label="Input" value={tokens(usage.input_tokens)} /><Metric label="Output" value={tokens(usage.output_tokens)} /><Metric label="Cached input" value={tokens(usage.cached_input_tokens)} /><Metric label="Reasoning" value={tokens(usage.reasoning_tokens)} />
            </section>

            <section className="rounded-md border border-[#D7D9D3] bg-white p-5">
              <h2 className="font-mono text-xs font-bold tracking-wide text-[#173F5F] uppercase">By model</h2>
              {usage.by_model.length ? <ul className="mt-4 divide-y divide-[#E7E8E4]">{usage.by_model.map((item) => <li className="flex items-center justify-between gap-4 py-3 text-sm" key={item.model}><span className="font-bold">{item.model}</span><span className="font-mono text-xs text-[#666862]">{tokens(item.total_tokens)} · {item.requests} calls</span></li>)}</ul> : <p className="mt-3 text-sm text-[#666862]">No hosted editor requests in this period.</p>}
            </section>

            <section>
              <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
                <div><h2 className="font-mono text-xs font-bold tracking-wide text-[#173F5F] uppercase">{jobFilterLabel}</h2><p className="mt-1 text-xs text-[#666862]">{visibleJobs.length} shown · {usage.jobs} stored in this period</p></div>
                <div aria-label="Job history filter" className="flex w-full rounded-md border border-[#D7D9D3] bg-white p-1 sm:w-auto" role="group">
                  {(["editing", "verification", "all"] as const).map((filter) => (
                    <button aria-pressed={jobFilter === filter} className={`min-h-9 flex-1 rounded px-3 font-mono text-[10px] font-bold uppercase sm:flex-none ${jobFilter === filter ? "bg-[#173F5F] text-white" : "text-[#666862]"}`} key={filter} onClick={() => setJobFilter(filter)} type="button">
                      {filter === "editing" ? "Editing" : filter === "verification" ? `Tests (${verificationJobs})` : "All"}
                    </button>
                  ))}
                </div>
              </div>
              {visibleJobs.length ? (
                <div className="flex flex-col gap-3 md:gap-0 md:overflow-hidden md:rounded-md md:border md:border-[#D7D9D3] md:bg-white">
                  <div className="hidden grid-cols-12 gap-4 border-b border-[#D7D9D3] px-4 py-3 font-mono text-[10px] font-bold text-[#666862] uppercase md:grid"><div className="col-span-3">Job</div><div className="col-span-2">Recipe</div><div className="col-span-2">Status</div><div>Date</div><div className="col-span-2">Model</div><div className="text-right">Requests</div><div className="text-right">Tokens</div></div>
                  {visibleJobs.map((job) => <JobRow job={job} key={job.id} />)}
                </div>
              ) : <div className="rounded-md border border-[#D7D9D3] bg-white p-5 text-sm text-[#666862]">No {jobFilter === "verification" ? "test" : jobFilter === "editing" ? "editing" : ""} jobs in this period.</div>}
            </section>

            <div className="space-y-4 pt-2"><p className="text-xs leading-relaxed text-[#666862]">Usage totals include every recorded model call, including verification work. Filters only organize job history; they never delete jobs, media, usage, or provenance. These are measured tokens, not a dollar invoice.</p><a className="inline-block text-sm font-bold text-[#173F5F] underline underline-offset-4" href="https://chatgpt.com/settings/usage" rel="noreferrer" target="_blank">Manage ChatGPT usage</a></div>
          </div>
        ) : null}
        <footer className="border-t border-[#D7D9D3] pt-5"><Link className="text-sm font-bold text-[#173F5F] underline underline-offset-4" href="/jobs/new">Start a new job</Link></footer>
      </div>
    </main>
  );
}
