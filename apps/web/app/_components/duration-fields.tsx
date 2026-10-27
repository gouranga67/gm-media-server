"use client";

import { useId } from "react";
import type { DurationSettings } from "@/lib/media-api";

export function DurationFields({
  settings,
  onChange,
  disabled = false,
}: {
  readonly settings: DurationSettings;
  readonly onChange: (value: DurationSettings) => void;
  readonly disabled?: boolean;
}) {
  const id = useId();
  const field =
    "mt-1 min-h-12 w-full rounded-md border border-[#D7D9D3] bg-white px-3 text-sm text-[#173F5F]";
  const maximum =
    settings.duration_mode === "aim"
      ? Math.min(
          settings.max_duration_seconds,
          Math.ceil(settings.target_duration_seconds * 1.2),
        )
      : settings.max_duration_seconds;
  return (
    <fieldset disabled={disabled} className="space-y-3 text-[#173F5F]">
      <legend className="mb-3 text-xs font-bold">DURATION</legend>
      <label className="block text-sm font-bold" htmlFor={`${id}-mode`}>
        Length preference
        <select
          id={`${id}-mode`}
          className={field}
          value={settings.duration_mode}
          onChange={(event) =>
            onChange({
              ...settings,
              duration_mode: event.currentTarget
                .value as DurationSettings["duration_mode"],
            })
          }
        >
          <option value="follow_story">Follow the story</option>
          <option value="aim">Aim for a length</option>
          <option value="strict">Strict maximum</option>
        </select>
      </label>
      {settings.duration_mode === "aim" ? (
        <label className="block text-sm font-bold" htmlFor={`${id}-preferred`}>
          Preferred length
          <select
            id={`${id}-preferred`}
            className={field}
            value={settings.target_duration_seconds}
            onChange={(event) =>
              onChange({
                ...settings,
                target_duration_seconds: Number(
                  event.currentTarget.value,
                ) as DurationSettings["target_duration_seconds"],
              })
            }
          >
            {[15, 20, 30, 45, 60].map((value) => (
              <option value={value} key={value}>
                {value} seconds
              </option>
            ))}
          </select>
        </label>
      ) : null}
      <label className="block text-sm font-bold" htmlFor={`${id}-maximum`}>
        Maximum seconds
        <input
          id={`${id}-maximum`}
          className={field}
          type="number"
          min={5}
          max={120}
          step={1}
          required
          value={
            Number.isFinite(settings.max_duration_seconds)
              ? settings.max_duration_seconds
              : ""
          }
          onChange={(event) =>
            onChange({
              ...settings,
              max_duration_seconds: event.currentTarget.valueAsNumber,
            })
          }
        />
      </label>
      <p className="text-xs leading-relaxed text-[#666862]">
        {settings.duration_mode === "follow_story"
          ? "Make the shortest complete story, up to your maximum."
          : settings.duration_mode === "aim"
            ? `Allow up to 20% beyond the preferred length, within your maximum: ${Number.isFinite(maximum) ? maximum : "—"} seconds for this edit.`
            : "Stay within this limit. If the required content cannot fit, change the maximum or request a condensed version or split."}{" "}
        Complete words and required points come first. No padding to fill time.
        Maximum supported: 120 seconds.
      </p>
    </fieldset>
  );
}
