"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { LoaderCircleIcon, SearchIcon } from "lucide-react";

import { getPromptHistory, type PromptHistory } from "@/lib/media-api";
import { StudioNav } from "./studio-nav";

export function PromptHistoryWorkspace() {
  const [query, setQuery] = useState("");
  const [history, setHistory] = useState<PromptHistory>();
  const [error, setError] = useState<string>();
  const [loadingMore, setLoadingMore] = useState(false);
  const requestGeneration = useRef(0);

  useEffect(() => {
    const generation = ++requestGeneration.current;
    setHistory(undefined);
    setError(undefined);
    setLoadingMore(false);
    const timer = window.setTimeout(() => {
      void getPromptHistory(query).then((result) => {
        if (requestGeneration.current === generation) setHistory(result);
      }).catch((reason: unknown) => {
        if (requestGeneration.current === generation) setError(reason instanceof Error ? reason.message : "Prompt history is unavailable");
      });
    }, 180);
    return () => {
      window.clearTimeout(timer);
      requestGeneration.current++;
    };
  }, [query]);

  async function loadMore() {
    if (!history || loadingMore || !history.has_more) return;
    const generation = requestGeneration.current;
    setLoadingMore(true);
    setError(undefined);
    try {
      const next = await getPromptHistory(query, history.next_offset);
      if (requestGeneration.current !== generation) return;
      setHistory((current) => current ? {
        ...next,
        items: Array.from(new Map([...current.items, ...next.items].map((entry) => [entry.id, entry])).values()),
      } : next);
    } catch (reason) {
      if (requestGeneration.current === generation) setError(reason instanceof Error ? reason.message : "More prompts could not be loaded");
    } finally {
      if (requestGeneration.current === generation) setLoadingMore(false);
    }
  }

  return (
    <main className="min-h-dvh bg-[#F7F7F5] px-4 py-[max(1.25rem,env(safe-area-inset-top))] text-[#20211F] sm:px-6">
      <div className="mx-auto max-w-4xl">
        <header className="border-b border-[#D7D9D3] pb-5">
          <StudioNav current="/prompts" />
          <h1 className="mt-7 text-3xl font-black tracking-tight text-[#173F5F]">Prompt history</h1>
          <p className="mt-2 text-sm leading-relaxed text-[#666862]">Your original prompts and revision requests across jobs, including failed attempts and archived work.</p>
        </header>
        <section className="py-6" aria-label="Saved prompts">
          <label className="flex min-h-12 items-center gap-3 rounded-md border border-[#C7CBD0] bg-white px-4 focus-within:ring-2 focus-within:ring-[#173F5F]/30">
            <SearchIcon aria-hidden="true" className="size-4 shrink-0 text-[#666862]" />
            <span className="sr-only">Search prompts or job names</span>
            <input className="w-full bg-transparent text-sm outline-none" onChange={(event) => setQuery(event.currentTarget.value)} placeholder="Search prompts or job names" type="search" value={query} />
          </label>
          {error ? <p className="mt-4 text-sm text-[#A23B2A]" role="alert">{error}</p> : null}
          {!history && !error ? <p className="flex min-h-48 items-center justify-center gap-2 text-sm text-[#53646F]" role="status"><LoaderCircleIcon aria-hidden="true" className="size-5 animate-spin motion-reduce:animate-none" />Loading prompt history…</p> : null}
          {history && history.items.length === 0 ? <p className="mt-5 rounded-md border border-dashed border-[#C7CBD0] bg-white p-8 text-center text-sm text-[#666862]">{query.trim() ? "No prompts match your search." : "Your original prompts and revision requests will appear here when you submit them."}</p> : null}
          <ol className="mt-5 space-y-4">
            {history?.items.map((entry) => (
              <li className="rounded-md border border-[#D7D9D3] bg-white p-5" key={entry.id}>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <Link className="font-bold text-[#173F5F] underline-offset-4 hover:underline" href={`/jobs/${entry.job_id}`}>{entry.project_name}</Link>
                  <span className="font-mono text-[10px] text-[#53646F]">{entry.kind === "original" ? "Original prompt" : `Revision · version ${entry.version}`}{entry.archived ? " · archived job" : ""}</span>
                </div>
                <p className="mt-3 whitespace-pre-wrap break-words text-sm leading-relaxed">{entry.prompt}</p>
                <div className="mt-4 flex flex-wrap items-center justify-between gap-3 text-xs text-[#666862]">
                  <time dateTime={entry.created_at}>{new Date(entry.created_at).toLocaleString()}</time>
                  <span>{entry.status.replaceAll("_", " ")}</span>
                  <Link className="font-bold text-[#173F5F] underline underline-offset-4" href={`/jobs/${entry.job_id}`}>Open edit &amp; version history</Link>
                </div>
              </li>
            ))}
          </ol>
          {history?.has_more ? <button className="mt-5 flex min-h-12 w-full items-center justify-center gap-2 rounded-md border border-[#A9C0D0] bg-white px-5 text-sm font-bold text-[#173F5F] disabled:opacity-50" disabled={loadingMore} onClick={() => void loadMore()} type="button">{loadingMore ? <LoaderCircleIcon aria-hidden="true" className="size-4 animate-spin" /> : null}{loadingMore ? "Loading…" : "Load older prompts"}</button> : null}
        </section>
      </div>
    </main>
  );
}
