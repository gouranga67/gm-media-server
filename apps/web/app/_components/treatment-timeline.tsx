"use client";

import { useState } from "react";

type Event = { kind: string; label: string; start: number; end: number; detail: string; clip_index?: number | null };

function isEvent(value: unknown): value is Event {
  if (!value || typeof value !== "object") return false;
  const event = value as Record<string, unknown>;
  return typeof event.kind === "string" && typeof event.label === "string" && typeof event.detail === "string"
    && typeof event.start === "number" && Number.isFinite(event.start) && event.start >= 0
    && typeof event.end === "number" && Number.isFinite(event.end) && event.end >= event.start;
}

const names: Record<string, string> = {
  cut: "Cuts", transition: "Transitions", framing: "Framing", framing_beat: "Rhythmic changes",
  broll: "B-roll", sound: "Sounds", graphic: "Graphics", captions: "Captions", callout: "Text labels",
  music: "Music", voice: "Voice", layer: "Picture layers", colour: "Colour",
};

export function TreatmentTimeline({ report, onSeek }: {
  readonly report: unknown;
  readonly onSeek?: (seconds: number) => void;
}) {
  const [kind, setKind] = useState("all");
  if (!report || typeof report !== "object" || !("events" in report) || !Array.isArray(report.events)) return null;
  const events = report.events.filter(isEvent).slice(0, 240);
  const types = [...new Set(events.map(event => event.kind))];
  const activeKind = types.includes(kind) ? kind : "all";
  const visible = events.filter(event => activeKind === "all" || event.kind === activeKind);
  const count = "event_count" in report && typeof report.event_count === "number" && Number.isFinite(report.event_count)
    ? Math.max(events.length, Math.floor(report.event_count)) : events.length;
  return <details className="rounded-md border border-[#BFD2DE] bg-white p-4">
    <summary className="min-h-11 cursor-pointer text-sm font-bold text-[#173F5F]">Treatment timeline · {count} events</summary>
    <p className="mt-2 text-xs leading-5 text-[#53646F]">Saved treatments, not an engagement score. Cutaways and layers can cover framing. Jump to a time to inspect the preview; this does not play, render or call AI.</p>
    {events.length ? <>
      <label className="mt-3 block text-xs font-bold text-[#173F5F]">Show treatments
        <select aria-label="Treatment kind" className="mt-1 min-h-11 w-full rounded border border-[#BFD2DE] bg-white px-3" value={activeKind} onChange={event => setKind(event.currentTarget.value)}>
          <option value="all">All treatments</option>{types.map(type => <option key={type} value={type}>{names[type] ?? type}</option>)}
        </select>
      </label>
      <ol className="mt-3 max-h-80 space-y-2 overflow-y-auto" aria-label="Saved treatment events">{visible.map((event, index) => <li className="rounded bg-[#F5F8FA] p-3 text-xs text-[#53646F]" key={`${event.kind}-${event.start}-${index}`}>
        <p className="font-bold text-[#173F5F]">{event.label}{typeof event.clip_index === "number" ? ` · clip ${event.clip_index + 1}` : ""}</p>
        {onSeek ? <button type="button" className="min-h-11 text-[#174D73] underline underline-offset-4" aria-label={`Jump to ${event.label} at ${event.start.toFixed(1)} seconds`} onClick={() => onSeek(event.start)}>{event.start.toFixed(1)}{event.end > event.start ? `–${event.end.toFixed(1)}` : ""}s · Jump in preview</button> : <p className="mt-1">{event.start.toFixed(1)}–{event.end.toFixed(1)}s</p>}
        {event.detail ? <p className="mt-1 leading-5">{event.detail}</p> : null}
      </li>)}</ol>
      {count > events.length ? <p className="mt-2 text-xs text-[#53646F]">Showing {events.length} of {count} saved events.</p> : null}
    </> : <p className="mt-3 text-xs text-[#53646F]">No additional treatments are listed for this saved cut.</p>}
  </details>;
}
