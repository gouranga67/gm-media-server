"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { CheckIcon, DownloadIcon, LoaderCircleIcon, RefreshCwIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { getPreview, requestPreview, type EditRun } from "@/lib/media-api";

const POLL_INTERVAL_MS = 2_000;
const PLAN_NOTICE_KEY = "gm-studio:chatgpt-plan-notice-v1";

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : "Preview status is unavailable";
}

export function JobPreview({ jobId }: { readonly jobId: string }) {
  const [run, setRun] = useState<EditRun>();
  const [error, setError] = useState<string>();
  const [retrying, setRetrying] = useState(false);
  const [pollGeneration, setPollGeneration] = useState(0);
  const [showPlanNotice, setShowPlanNotice] = useState(false);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const poll = async () => {
      try {
        const latest = await getPreview(jobId);
        if (cancelled) return;
        setRun(latest);
        setError(undefined);
        if (latest.status !== "ready" && latest.status !== "failed") {
          timer = setTimeout(poll, POLL_INTERVAL_MS);
        }
      } catch (pollError) {
        if (cancelled) return;
        setError(errorMessage(pollError));
        timer = setTimeout(poll, POLL_INTERVAL_MS * 2);
      }
    };

    void poll();
    return () => {
      cancelled = true;
      if (timer !== undefined) clearTimeout(timer);
    };
  }, [jobId, pollGeneration]);

  const retry = async () => {
    setRetrying(true);
    setError(undefined);
    try {
      setRun(await requestPreview(jobId));
      setPollGeneration((current) => current + 1);
    } catch (retryError) {
      setError(errorMessage(retryError));
    } finally {
      setRetrying(false);
    }
  };

  const fileUrl = `/api/media/jobs/${encodeURIComponent(jobId)}/preview/file`;
  const status = run?.status ?? "pending";
  const usesChatGptPlan = run?.provider === "chatgpt_plan";
  const failureMessage = run?.error ?? error ?? "";
  const hasPlanUsageIssue = /subscription_sharing_usage_|chatgpt plan usage is unavailable/i.test(failureMessage);

  useEffect(() => {
    if (!usesChatGptPlan) return;
    try {
      if (window.localStorage.getItem(PLAN_NOTICE_KEY) !== "dismissed") {
        setShowPlanNotice(true);
      }
    } catch {
      setShowPlanNotice(true);
    }
  }, [usesChatGptPlan]);

  const updatePlanNotice = (open: boolean) => {
    setShowPlanNotice(open);
    if (!open) {
      try {
        window.localStorage.setItem(PLAN_NOTICE_KEY, "dismissed");
      } catch {
        // The notice remains dismissible when private storage is unavailable.
      }
    }
  };

  return (
    <>
    <main className="min-h-dvh bg-[#F7F7F5] px-4 pt-[max(1.25rem,env(safe-area-inset-top))] pb-[max(2rem,env(safe-area-inset-bottom))] text-[#20211F] [color-scheme:light]">
      <div className="mx-auto w-full max-w-lg">
        <header className="border-b border-[#D7D9D3] pb-4">
          <p className="text-sm font-bold tracking-tight text-[#173F5F]">GM Studio</p>
          <p className="mt-1 font-mono text-[10px] text-[#666862]">Job {jobId.slice(0, 8)} · source-only edit</p>
        </header>

        <section aria-live="polite" className="py-8">
          {status === "ready" ? (
            <div className="space-y-5">
              <div>
                <p className="flex items-center gap-2 font-mono text-xs font-bold tracking-wide text-[#3A8F63] uppercase">
                  <CheckIcon aria-hidden="true" className="size-4" /> Preview ready
                </p>
                <h1 className="mt-2 text-2xl font-bold tracking-tight text-[#173F5F]">Your reel is ready to review</h1>
              </div>
              <video
                className="aspect-[9/16] w-full rounded-md bg-black object-contain"
                controls
                playsInline
                preload="metadata"
                src={fileUrl}
              >
                Your browser cannot play this preview.
              </video>
              <Button asChild className="h-14 w-full bg-[#173F5F] text-white hover:bg-[#12344F]">
                <a href={`${fileUrl}?download=true`}>
                  <DownloadIcon aria-hidden="true" /> Download MP4
                </a>
              </Button>
              <p className="text-center font-mono text-[10px] leading-relaxed text-[#666862]">
                Version {run?.version} · edited from your uploaded source media only
              </p>
            </div>
          ) : status === "failed" ? (
            <div className="rounded-md border border-[#E7C4BC] bg-white p-5">
              <p className="font-mono text-xs font-bold tracking-wide text-[#A23B2A] uppercase">
                {hasPlanUsageIssue ? "ChatGPT" : "Preview needs attention"}
              </p>
              <h1 className="mt-2 text-xl font-bold text-[#173F5F]">
                {hasPlanUsageIssue ? "Usage limit reached" : "The edit did not finish"}
              </h1>
              <p className="mt-3 text-sm leading-relaxed text-[#666862]">{run?.error ?? "The worker reported an unknown error."}</p>
              {hasPlanUsageIssue ? (
                <Button asChild className="mt-5 h-12 w-full bg-[#173F5F] text-white hover:bg-[#12344F]">
                  <a href="https://chatgpt.com/settings/usage" rel="noreferrer" target="_blank">Manage usage</a>
                </Button>
              ) : null}
              <Button
                className="mt-3 h-12 w-full"
                disabled={retrying}
                onClick={() => void retry()}
                type="button"
                variant={hasPlanUsageIssue ? "outline" : "default"}
              >
                {retrying ? <LoaderCircleIcon aria-hidden="true" className="animate-spin" /> : <RefreshCwIcon aria-hidden="true" />}
                Try again
              </Button>
            </div>
          ) : (
            <div className="flex min-h-[60dvh] flex-col items-center justify-center text-center">
              <LoaderCircleIcon aria-hidden="true" className="size-9 animate-spin text-[#173F5F] motion-reduce:animate-none" />
              <h1 className="mt-5 text-2xl font-bold tracking-tight text-[#173F5F]">
                {status === "rendering" ? "Rendering your preview" : "Planning your edit"}
              </h1>
              <p className="mt-3 max-w-sm text-sm leading-relaxed text-[#666862]">
                You can leave this page. The server keeps working and this screen will update when you return.
              </p>
              <p className="mt-4 font-mono text-[10px] text-[#666862] uppercase">{status}</p>
            </div>
          )}
          {usesChatGptPlan && !hasPlanUsageIssue ? (
            <div className="mt-5 flex items-center justify-between gap-4 rounded-md border border-[#D7D9D3] bg-white px-4 py-3 text-xs">
              <span className="font-mono font-bold text-[#173F5F]">Using ChatGPT plan</span>
              <a
                className="font-bold text-[#173F5F] underline underline-offset-4"
                href="https://chatgpt.com/settings/usage"
                rel="noreferrer"
                target="_blank"
              >
                Manage usage
              </a>
            </div>
          ) : null}
          {error ? <p className="mt-4 text-center text-xs text-[#A23B2A]" role="alert">{error}</p> : null}
        </section>

        <footer className="text-center">
          <Link className="text-sm font-bold text-[#173F5F] underline underline-offset-4" href="/jobs/new">
            Start another job
          </Link>
        </footer>
      </div>
    </main>
    <Dialog onOpenChange={updatePlanNotice} open={showPlanNotice}>
      <DialogContent className="border-[#D7D9D3] bg-white text-[#20211F]" showCloseButton={false}>
        <DialogHeader>
          <DialogTitle className="text-xl text-[#173F5F]">You&apos;re using your ChatGPT plan</DialogTitle>
          <DialogDescription className="leading-relaxed text-[#666862]">
            Eligible editor requests in GM Studio use your ChatGPT plan. You can review usage and adjust this app&apos;s limits in ChatGPT settings.
          </DialogDescription>
        </DialogHeader>
        <a
          className="text-sm font-bold text-[#173F5F] underline underline-offset-4"
          href="https://chatgpt.com/settings/usage"
          rel="noreferrer"
          target="_blank"
        >
          Manage usage
        </a>
        <DialogFooter>
          <DialogClose asChild>
            <Button className="h-12 bg-[#173F5F] text-white hover:bg-[#12344F]">Got it</Button>
          </DialogClose>
        </DialogFooter>
      </DialogContent>
    </Dialog>
    </>
  );
}
