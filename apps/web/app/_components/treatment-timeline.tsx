"use client";

import { useMemo, useState } from "react";
import { PlayIcon, WrenchIcon } from "lucide-react";

import { Button } from "@/components/ui/button";

type TreatmentEvent = {
  readonly kind: string;
  readonly label: string;
  readonly start: number;
  readonly end: number;
  readonly detail: string;
  readonly clip_index?: number | null;
};

type Category = "story" | "picture" | "layers" | "sound" | "captions" | "other";

const categories: readonly {
  readonly id: Category;
  readonly label: string;
  readonly editorLabel: string;
  readonly kinds: readonly string[];
  readonly eventClassName: string;
}[] = [
  {
    id: "story",
    label: "Story",
    editorLabel: "Story & timing",
    kinds: ["cut", "transition"],
    eventClassName: "border-[#173F5F] bg-[#173F5F] text-white",
  },
  {
    id: "picture",
    label: "Picture",
    editorLabel: "Picture",
    kinds: ["framing", "framing_beat", "broll", "colour"],
    eventClassName: "border-[#173F5F] bg-[#BFE3FF] text-[#173F5F]",
  },
  {
    id: "layers",
    label: "Layers",
    editorLabel: "Layers & graphics",
    kinds: ["graphic", "callout", "layer"],
    eventClassName: "border-[#FF8C69] bg-[#FFDDD2] text-[#7D3521]",
  },
  {
    id: "sound",
    label: "Sound",
    editorLabel: "Sound & captions",
    kinds: ["sound", "music", "voice"],
    eventClassName: "border-[#3A8F63] bg-[#DCEFE4] text-[#215B43]",
  },
  {
    id: "captions",
    label: "Captions",
    editorLabel: "Sound & captions",
    kinds: ["captions"],
    eventClassName: "border-[#666862] bg-[#E9EDF0] text-[#20211F]",
  },
  {
    id: "other",
    label: "Other",
    editorLabel: "Finishing tools",
    kinds: [],
    eventClassName: "border-[#666862] bg-white text-[#20211F]",
  },
];

function isEvent(value: unknown): value is TreatmentEvent {
  if (!value || typeof value !== "object") return false;
  const event = value as Record<string, unknown>;
  return (
    typeof event.kind === "string" &&
    typeof event.label === "string" &&
    typeof event.detail === "string" &&
    typeof event.start === "number" &&
    Number.isFinite(event.start) &&
    event.start >= 0 &&
    typeof event.end === "number" &&
    Number.isFinite(event.end) &&
    event.end >= event.start
  );
}

function categoryFor(kind: string) {
  return (
    categories.find(
      (category) => category.id !== "other" && category.kinds.includes(kind),
    ) ?? categories[categories.length - 1]
  );
}

function eventKey(event: TreatmentEvent, index: number) {
  return `${event.kind}-${event.start}-${event.end}-${event.label}-${index}`;
}

function formatTime(seconds: number) {
  const safe = Math.max(0, Math.round(seconds));
  const minutes = Math.floor(safe / 60);
  return `${minutes}:${String(safe % 60).padStart(2, "0")}`;
}

function eventTime(event: TreatmentEvent) {
  return event.end > event.start
    ? `${event.start.toFixed(1)}–${event.end.toFixed(1)}s`
    : `${event.start.toFixed(1)}s`;
}

export function TreatmentTimeline({
  report,
  onSeek,
  onEdit,
}: {
  readonly report: unknown;
  readonly onSeek?: (seconds: number) => void;
  readonly onEdit?: (kind: string) => void;
}) {
  const [activeCategory, setActiveCategory] = useState<"all" | Category>("all");
  const [selectedKey, setSelectedKey] = useState<string>();

  const parsed = useMemo(() => {
    if (
      !report ||
      typeof report !== "object" ||
      !("events" in report) ||
      !Array.isArray(report.events)
    ) {
      return null;
    }
    const events = report.events.filter(isEvent).slice(0, 240);
    const reportedDuration =
      "duration_seconds" in report &&
      typeof report.duration_seconds === "number" &&
      Number.isFinite(report.duration_seconds) &&
      report.duration_seconds > 0
        ? report.duration_seconds
        : 0;
    const duration = Math.max(
      1,
      reportedDuration,
      ...events.map((event) => event.end),
    );
    const count =
      "event_count" in report &&
      typeof report.event_count === "number" &&
      Number.isFinite(report.event_count)
        ? Math.max(events.length, Math.floor(report.event_count))
        : events.length;
    return { events, duration, count };
  }, [report]);

  if (!parsed) return null;

  const eventRecords = parsed.events.map((event, index) => ({
    event,
    key: eventKey(event, index),
    category: categoryFor(event.kind),
  }));
  const categoryCounts = new Map<Category, number>();
  for (const record of eventRecords) {
    categoryCounts.set(
      record.category.id,
      (categoryCounts.get(record.category.id) ?? 0) + 1,
    );
  }
  const availableCategories = categories.filter(
    (category) => (categoryCounts.get(category.id) ?? 0) > 0,
  );
  const effectiveCategory =
    activeCategory === "all" || (categoryCounts.get(activeCategory) ?? 0) > 0
      ? activeCategory
      : "all";
  const visibleRecords = eventRecords.filter(
    (record) =>
      effectiveCategory === "all" || record.category.id === effectiveCategory,
  );
  const selected =
    visibleRecords.find((record) => record.key === selectedKey) ??
    visibleRecords[0] ??
    eventRecords[0];
  const ticks = [0, parsed.duration / 3, (parsed.duration * 2) / 3, parsed.duration];

  return (
    <details className="overflow-hidden rounded-md border border-[#BFD2DE] bg-white">
      <summary className="min-h-16 cursor-pointer px-4 py-3 text-[#173F5F] marker:text-[#173F5F]">
        <span className="ml-2 inline-flex max-w-[calc(100%-2rem)] flex-col align-middle">
          <span className="text-sm font-bold">Edit map</span>
          <span className="mt-1 text-xs font-normal leading-relaxed text-[#666862]">
            {parsed.count} saved {parsed.count === 1 ? "treatment" : "treatments"} across {formatTime(parsed.duration)}
          </span>
        </span>
      </summary>
      <div className="space-y-4 border-t border-[#E5E6E1] p-4">
        <p className="text-xs leading-5 text-[#53646F]">
          See where picture, sound, captions and transitions occur. Select a
          mark to inspect it; this map never changes the edit, renders a
          preview or calls AI.
        </p>

        {eventRecords.length ? (
          <>
            <div
              aria-label="Edit map filters"
              className="flex gap-2 overflow-x-auto pb-1"
              role="group"
            >
              <button
                aria-pressed={effectiveCategory === "all"}
                className={`min-h-11 shrink-0 rounded-full px-4 text-xs font-bold ${
                  effectiveCategory === "all"
                    ? "bg-[#173F5F] text-white"
                    : "border border-[#D7D9D3] bg-white text-[#173F5F]"
                }`}
                onClick={() => setActiveCategory("all")}
                type="button"
              >
                All · {parsed.count}
              </button>
              {availableCategories.map((category) => (
                <button
                  aria-pressed={effectiveCategory === category.id}
                  className={`min-h-11 shrink-0 rounded-full px-4 text-xs font-bold ${
                    effectiveCategory === category.id
                      ? "bg-[#173F5F] text-white"
                      : "border border-[#D7D9D3] bg-white text-[#173F5F]"
                  }`}
                  key={category.id}
                  onClick={() => setActiveCategory(category.id)}
                  type="button"
                >
                  {category.label} · {categoryCounts.get(category.id)}
                </button>
              ))}
            </div>

            <div className="rounded-md border border-[#D7D9D3] bg-[#F7F7F5] p-3">
              <div className="ml-[72px] flex justify-between font-mono text-[9px] text-[#666862]">
                {ticks.map((tick) => (
                  <span key={tick}>{formatTime(tick)}</span>
                ))}
              </div>
              <div className="mt-2 space-y-2" role="list" aria-label="Saved treatment map">
                {availableCategories
                  .filter(
                    (category) =>
                      effectiveCategory === "all" || effectiveCategory === category.id,
                  )
                  .map((category) => (
                    <div
                      className="grid grid-cols-[64px_1fr] items-center gap-2"
                      key={category.id}
                      role="listitem"
                    >
                      <span className="truncate text-[10px] font-bold text-[#173F5F]">
                        {category.label}
                      </span>
                      <div className="relative h-10 overflow-hidden rounded bg-white">
                        <span aria-hidden="true" className="absolute inset-y-0 left-1/3 border-l border-dashed border-[#D7D9D3]" />
                        <span aria-hidden="true" className="absolute inset-y-0 left-2/3 border-l border-dashed border-[#D7D9D3]" />
                        {eventRecords
                          .filter((record) => record.category.id === category.id)
                          .map((record) => {
                            const point = record.event.end - record.event.start < 0.08;
                            const left = Math.min(
                              100,
                              Math.max(0, (record.event.start / parsed.duration) * 100),
                            );
                            const width = Math.max(
                              4,
                              ((record.event.end - record.event.start) /
                                parsed.duration) *
                                100,
                            );
                            return (
                              <button
                                aria-label={`Inspect ${record.event.label} at ${eventTime(record.event)}`}
                                aria-pressed={selected?.key === record.key}
                                className={`absolute top-1 min-h-8 rounded border-2 shadow-sm ${category.eventClassName} ${
                                  selected?.key === record.key
                                    ? "z-20 ring-2 ring-[#173F5F] ring-offset-1"
                                    : "z-10"
                                }`}
                                key={record.key}
                                onClick={() => setSelectedKey(record.key)}
                                style={
                                  point
                                    ? {
                                        left: `${left}%`,
                                        width: "1.75rem",
                                        transform: "translateX(-50%)",
                                      }
                                    : {
                                        left: `${left}%`,
                                        width: `${Math.min(100 - left, width)}%`,
                                      }
                                }
                                title={`${record.event.label} · ${eventTime(record.event)}`}
                                type="button"
                              >
                                <span className="sr-only">{record.event.label}</span>
                              </button>
                            );
                          })}
                      </div>
                    </div>
                  ))}
              </div>
            </div>

            {selected ? (
              <div className="rounded-md border border-[#BFD2DE] bg-[#EFF6FA] p-3" aria-live="polite">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="font-mono text-[9px] font-bold tracking-wide text-[#666862] uppercase">
                      Selected · {selected.category.label} · {eventTime(selected.event)}
                    </p>
                    <h3 className="mt-1 text-sm font-bold text-[#173F5F]">
                      {selected.event.label}
                      {typeof selected.event.clip_index === "number"
                        ? ` · clip ${selected.event.clip_index + 1}`
                        : ""}
                    </h3>
                  </div>
                  <Button
                    className="h-11 shrink-0"
                    disabled={!onSeek}
                    onClick={() => onSeek?.(selected.event.start)}
                    size="sm"
                    type="button"
                    variant="outline"
                  >
                    <PlayIcon aria-hidden="true" /> Preview
                  </Button>
                </div>
                {selected.event.detail ? (
                  <p className="mt-2 text-xs leading-5 text-[#53646F]">
                    {selected.event.detail}
                  </p>
                ) : (
                  <p className="mt-2 text-xs leading-5 text-[#53646F]">
                    This treatment is saved in the current edit plan.
                  </p>
                )}
                {onEdit ? (
                  <Button
                    className="mt-3 h-11 w-full"
                    onClick={() => onEdit(selected.event.kind)}
                    type="button"
                    variant="outline"
                  >
                    <WrenchIcon aria-hidden="true" /> Open {selected.category.editorLabel}
                  </Button>
                ) : null}
              </div>
            ) : null}

            <details className="rounded-md border border-[#D7D9D3] bg-white px-3 py-2">
              <summary className="min-h-11 cursor-pointer content-center text-xs font-bold text-[#173F5F]">
                List {effectiveCategory === "all" ? "all" : selected?.category.label.toLowerCase()} {visibleRecords.length} saved {visibleRecords.length === 1 ? "event" : "events"}
              </summary>
              <ol className="max-h-80 space-y-2 overflow-y-auto pb-2" aria-label="Saved treatment events">
                {visibleRecords.map((record) => (
                  <li className="rounded bg-[#F5F8FA] p-3 text-xs text-[#53646F]" key={record.key}>
                    <button
                      className="min-h-11 w-full text-left"
                      onClick={() => setSelectedKey(record.key)}
                      type="button"
                    >
                      <span className="block font-bold text-[#173F5F]">
                        {record.event.label}
                        {typeof record.event.clip_index === "number"
                          ? ` · clip ${record.event.clip_index + 1}`
                          : ""}
                      </span>
                      <span className="mt-1 block font-mono text-[10px]">
                        {eventTime(record.event)} · {record.category.label}
                      </span>
                      {record.event.detail ? (
                        <span className="mt-1 block leading-5">
                          {record.event.detail}
                        </span>
                      ) : null}
                    </button>
                  </li>
                ))}
              </ol>
              {parsed.count > parsed.events.length ? (
                <p className="pb-2 text-xs text-[#53646F]">
                  Showing {parsed.events.length} of {parsed.count} saved events.
                </p>
              ) : null}
            </details>
          </>
        ) : (
          <p className="rounded-md bg-[#F7F7F5] p-3 text-xs leading-5 text-[#53646F]">
            No additional treatments are listed for this saved cut.
          </p>
        )}
      </div>
    </details>
  );
}
