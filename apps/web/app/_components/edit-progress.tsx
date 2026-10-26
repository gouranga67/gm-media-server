"use client";

import { useEffect, useState } from "react";
import { LoaderCircleIcon } from "lucide-react";

import type { EditRun } from "@/lib/media-api";

const STAGES = ["Queued", "Planning", "Rendering", "Ready"] as const;

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
}: {
  readonly run: EditRun;
  readonly checkedAt: number | null;
  readonly connectionError: boolean;
}) {
  const [now, setNow] = useState<number | null>(null);

  useEffect(() => {
    setNow(Date.now());
    const timer = setInterval(() => setNow(Date.now()), 5_000);
    return () => clearInterval(timer);
  }, []);

  const queued = run.status === "pending";
  const stage = queued ? 0 : run.status === "planning" ? 1 : 2;
  const elapsed = secondsSince(queued ? run.updated_at : run.started_at, now);
  // updated_at is renewed by the worker lease heartbeat, not by rendered frames.
  const activityAge = secondsSince(run.updated_at, now);
  const checkedAge = secondsSince(checkedAt, now);
  const staleWorker = !queued && activityAge !== null && activityAge > 120;
  const title = queued
    ? "Your edit is queued"
    : run.status === "planning"
      ? "Planning your edit"
      : "Rendering your preview";
  const description = queued
    ? "Waiting for source analysis or an available worker. Planning has not started yet."
    : run.status === "planning"
      ? "The editor is choosing the story, cuts and effects from your footage."
      : "The server is assembling the video, sound and captions from the edit plan.";

  return (
    <div className="flex min-h-[45dvh] flex-col items-center justify-center text-center">
      <LoaderCircleIcon
        aria-hidden="true"
        className="size-9 animate-spin text-[#173F5F] motion-reduce:animate-none"
      />
      <h1 className="mt-5 text-2xl font-bold tracking-tight text-[#173F5F]">
        {title}
      </h1>
      <p className="mt-3 max-w-sm text-sm leading-relaxed text-[#666862]">
        {description}
      </p>
      <ol
        aria-label="Edit progress"
        className="mt-6 grid w-full grid-cols-4 gap-2 text-xs"
      >
        {STAGES.map((label, index) => (
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
      <div className="mt-5 space-y-1 text-xs text-[#666862]" aria-live="off">
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
      </div>
      {connectionError ? (
        <p
          role="status"
          className="mt-4 rounded-md bg-[#FFF0EB] p-3 text-sm text-[#A23B2A]"
        >
          Cannot refresh status right now. Reconnecting automatically; the last
          known stage is shown above.
        </p>
      ) : staleWorker ? (
        <p
          role="status"
          className="mt-4 rounded-md bg-[#FFF0EB] p-3 text-sm text-[#A23B2A]"
        >
          The worker has not checked in for over two minutes. It may be
          reconnecting; this does not confirm the edit has stopped.
        </p>
      ) : null}
      <p className="mt-5 max-w-sm text-xs leading-relaxed text-[#666862]">
        You can leave this page and return later. Stages show actual server
        status; they are not a percentage or a time estimate.
      </p>
    </div>
  );
}
