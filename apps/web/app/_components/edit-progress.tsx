"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ChevronDownIcon, LoaderCircleIcon } from "lucide-react";

import type { EditRun, JobEvent } from "@/lib/media-api";

const MILESTONES = [
  "Upload complete",
  "Source checks",
  "Building edit",
  "Preview ready",
] as const;
const EMPTY_EVENTS: readonly JobEvent[] = [];

function secondsSince(value: string | number | null, now: number | null) {
  if (value === null || now === null) return null;
  const time = typeof value === "number" ? value : Date.parse(value);
  return Number.isFinite(time)
    ? Math.max(0, Math.floor((now - time) / 1000))
    : null;
}

function duration(seconds: number) {
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  return minutes < 60
    ? `${minutes}m ${seconds % 60}s`
    : `${Math.floor(minutes / 60)}h ${minutes % 60}m`;
}

export function EditProgress({
  run,
  checkedAt,
  connectionError,
  events = EMPTY_EVENTS,
}: {
  readonly run: EditRun;
  readonly checkedAt: number | null;
  readonly connectionError: boolean;
  readonly events?: readonly JobEvent[];
}) {
  const [now, setNow] = useState<number | null>(null);

  useEffect(() => {
    setNow(Date.now());
    const timer = setInterval(() => setNow(Date.now()), 5_000);
    return () => clearInterval(timer);
  }, []);

  const queued = run.status === "pending";
  const stage = queued ? 1 : run.status === "ready" ? 3 : 2;
  const elapsed = secondsSince(queued ? run.updated_at : run.started_at, now);
  // updated_at is renewed by the worker lease heartbeat, not by rendered frames.
  const activityAge = secondsSince(run.updated_at, now);
  const checkedAge = secondsSince(checkedAt, now);
  const staleWorker = !queued && activityAge !== null && activityAge > 120;
  const title = queued
    ? "Preparing your sources"
    : run.status === "planning"
      ? "Building your edit"
      : "Rendering your preview";
  const description = queued
    ? "The server is checking your media and waiting for an editor when needed."
    : run.status === "planning"
      ? "The editor is choosing the story, cuts and effects from your footage."
      : "The server is assembling the video, sound and captions from the edit plan.";

  return (
    <div className="space-y-4">
      <section className="rounded-md border border-[#D7D9D3] bg-white p-5 sm:p-6">
        <div className="flex items-start gap-3">
          <span className="mt-0.5 size-5 shrink-0 animate-spin text-[#173F5F] motion-reduce:animate-none">
            <LoaderCircleIcon aria-hidden="true" className="size-5" />
          </span>
          <div>
            <h1 className="text-xl font-bold tracking-tight text-[#173F5F]">
              {title}
            </h1>
            <p className="mt-2 text-sm leading-relaxed text-[#666862]">
              {description}
            </p>
          </div>
        </div>

        <ol
          aria-label="Edit progress"
          className="mt-6 grid grid-cols-4 gap-1.5 text-[10px] leading-tight sm:gap-3 sm:text-xs"
        >
          {MILESTONES.map((label, index) => (
            <li
              key={label}
              aria-current={index === stage ? "step" : undefined}
              className={`border-t-4 pt-2 ${index <= stage ? "text-[#173F5F]" : "text-[#666862]"}`}
              style={{ borderTopColor: index <= stage ? "#173F5F" : "#D7D9D3" }}
            >
              <span className={index === stage ? "font-bold" : undefined}>
                {label}
              </span>
              <span className="sr-only">
                {index < stage
                  ? " completed"
                  : index === stage
                    ? " current stage"
                    : " not reached"}
              </span>
            </li>
          ))}
        </ol>
      </section>

      {connectionError ? (
        <p
          role="status"
          className="rounded-md bg-[#FFF0EB] p-4 text-sm leading-relaxed text-[#A23B2A]"
        >
          Cannot refresh status right now. Reconnecting automatically; the last
          known stage is shown above.
        </p>
      ) : staleWorker ? (
        <p
          role="status"
          className="rounded-md bg-[#FFF0EB] p-4 text-sm leading-relaxed text-[#A23B2A]"
        >
          The worker has not checked in for over two minutes. It may be
          reconnecting; this does not confirm the edit has stopped.
        </p>
      ) : null}

      <aside className="rounded-md bg-[#EFF6FA] p-4 text-sm leading-relaxed text-[#173F5F]">
        <p className="font-bold">You can safely close this page.</p>
        <p className="mt-1">
          The server will continue working. Return anytime from{" "}
          <Link className="font-bold underline underline-offset-4" href="/jobs">
            Jobs
          </Link>
          .
        </p>
      </aside>

      <details className="group rounded-md border border-[#D7D9D3] bg-white">
        <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-3 px-4 py-3 text-sm font-bold text-[#173F5F] [&::-webkit-details-marker]:hidden">
          Live status &amp; technical details
          <ChevronDownIcon
            aria-hidden="true"
            className="size-4 shrink-0 transition-transform group-open:rotate-180"
          />
        </summary>
        <div className="space-y-4 border-t border-[#E5E6E1] px-4 py-4">
          <div className="space-y-1 text-xs text-[#666862]" aria-live="off">
            {elapsed !== null ? (
              <p>
                {queued ? "Waiting" : "Run elapsed"}: {duration(elapsed)}
              </p>
            ) : null}
            {!queued && activityAge !== null ? (
              <p>Worker checked in {duration(activityAge)} ago</p>
            ) : null}
            {checkedAge !== null ? (
              <p>Last status check: {duration(checkedAge)} ago</p>
            ) : null}
            <p>
              Milestones show saved server state, not a percentage or time
              estimate.
            </p>
          </div>

          {events.length > 0 ? (
            <div className="border-t border-[#E5E6E1] pt-4">
              <h2 className="font-mono text-[10px] font-bold tracking-wide text-[#173F5F] uppercase">
                Job timeline
              </h2>
              <ol className="mt-3 space-y-2">
                {events.slice(0, 8).map((event) => (
                  <li
                    className="flex items-center justify-between gap-4 text-xs"
                    key={event.id}
                  >
                    <span className="font-bold text-[#20211F]">
                      {event.event_type.replaceAll("_", " ")}
                    </span>
                    <time
                      className="shrink-0 font-mono text-[10px] text-[#666862]"
                      dateTime={event.created_at}
                    >
                      {new Date(event.created_at).toLocaleString(undefined, {
                        dateStyle: "short",
                        timeStyle: "short",
                      })}
                    </time>
                  </li>
                ))}
              </ol>
            </div>
          ) : null}
        </div>
      </details>
    </div>
  );
}
