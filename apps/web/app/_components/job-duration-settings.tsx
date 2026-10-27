"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import {
  getJobDuration,
  updateJobDuration,
  type DurationPreview,
  type DurationSettings,
} from "@/lib/media-api";
import { DurationFields } from "./duration-fields";

export function JobDurationSettings({
  jobId,
  failed,
  onUpdated,
}: {
  readonly jobId: string;
  readonly failed: boolean;
  readonly onUpdated: () => void;
}) {
  const [opened, setOpened] = useState(false);
  const [preview, setPreview] = useState<DurationPreview>();
  const [settings, setSettings] = useState<DurationSettings>();
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string>();
  const [attempt, setAttempt] = useState(0);
  const settingsChanged =
    settings &&
    preview &&
    (settings.duration_mode !== preview.settings.duration_mode ||
      settings.target_duration_seconds !==
        preview.settings.target_duration_seconds ||
      settings.max_duration_seconds !== preview.settings.max_duration_seconds);
  useEffect(() => {
    if (!opened) return;
    let cancelled = false;
    void getJobDuration(jobId)
      .then((result) => {
        if (cancelled) return;
        setPreview(result);
        setSettings(result.settings);
        setError(undefined);
      })
      .catch((cause: unknown) => {
        if (!cancelled)
          setError(
            cause instanceof Error
              ? cause.message
              : "Could not load duration settings.",
          );
      });
    return () => {
      cancelled = true;
    };
  }, [jobId, opened, attempt]);
  return (
    <section
      id="duration"
      className="mt-5 space-y-3 rounded-md border border-[#D7D9D3] bg-white p-5"
      aria-label="Duration settings"
    >
      <Button
        type="button"
        variant="outline"
        className="min-h-12 w-full"
        aria-expanded={opened}
        disabled={saving}
        onClick={() => setOpened(!opened)}
      >
        Duration settings
      </Button>
      {opened ? (
        <>
          <p className="text-sm text-[#666862]">
            Adjust the length without uploading again. Saving settings does not
            start an edit.
          </p>
          {settings ? (
            <form
              className="space-y-4"
              onSubmit={async (event) => {
                event.preventDefault();
                if (saving) return;
                setSaving(true);
                setError(undefined);
                setSaved(false);
                try {
                  const result = await updateJobDuration(jobId, settings);
                  setPreview(result);
                  setSettings(result.settings);
                  setSaved(true);
                  onUpdated();
                } catch (cause) {
                  setError(
                    cause instanceof Error
                      ? cause.message
                      : "Could not save duration settings.",
                  );
                } finally {
                  setSaving(false);
                }
              }}
            >
              <DurationFields
                settings={settings}
                disabled={saving}
                onChange={(value) => {
                  setSettings(value);
                  setSaved(false);
                }}
              />
              {settingsChanged ? (
                <p className="text-xs text-[#666862]">
                  Save to refresh the source-speech check for these limits.
                </p>
              ) : preview?.assessment.warning ? (
                <p className="rounded-md bg-[#EFF6FA] p-3 text-sm text-[#173F5F]">
                  {preview.assessment.warning}
                </p>
              ) : null}
              <Button
                type="submit"
                disabled={saving}
                className="min-h-12 w-full"
              >
                {saving ? "Saving…" : "Save duration settings"}
              </Button>
            </form>
          ) : (
            <p className="text-sm">
              {error
                ? "Duration settings are unavailable."
                : "Loading duration settings…"}
            </p>
          )}
          <p className="text-xs text-[#666862]">
            Completed versions keep their saved duration for exact re-renders
            and exports. New AI edits use these settings.
          </p>
          {saved ? (
            <p role="status" className="text-sm text-[#215B43]">
              Settings saved.{" "}
              {failed
                ? "Press Try again to retry this edit."
                : "They will apply when you next start an AI edit."}
            </p>
          ) : null}
          {error ? (
            <div role="alert" className="text-sm text-[#A23B2A]">
              {error}
              {!settings ? (
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setAttempt(attempt + 1)}
                >
                  Load again
                </Button>
              ) : null}
            </div>
          ) : null}
        </>
      ) : null}
    </section>
  );
}
