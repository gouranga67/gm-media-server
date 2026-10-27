"use client";

import { useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  requestAlternative,
  requestRevision,
  type EditRun,
} from "@/lib/media-api";

type Kind = "different_cut" | "different_story";
type Assessment = {
  kind: Kind;
  status: string;
  notice: string;
  compared_versions: readonly number[];
};

export function AlternativeVersions({
  jobId,
  run,
  versions,
  onUpdated,
}: {
  readonly jobId: string;
  readonly run: EditRun;
  readonly versions: readonly EditRun[];
  readonly onUpdated: () => void;
}) {
  const [opened, setOpened] = useState(false);
  const [kind, setKind] = useState<Kind>("different_cut");
  const [direction, setDirection] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const [selected, setSelected] = useState("");
  const nonce = useRef<string | undefined>(undefined);
  const submitting = useRef(false);
  const ready = versions.filter(
    (version) => version.status === "ready" && version.preview_available,
  );
  const comparison =
    ready.find((version) => String(version.version) === selected) ??
    ready.find((version) => version.version !== run.version) ??
    ready[0];
  const playable = run.status === "ready";
  const active = ["pending", "planning", "rendering"].includes(run.status);
  const report = (
    run.manifest.revision_report as { alternative?: Assessment } | undefined
  )?.alternative;
  const root = `/api/media/jobs/${encodeURIComponent(jobId)}/preview/file`;
  const latestReady = versions
    .filter((version) => version.status === "ready")
    .reduce((latest, version) => Math.max(latest, version.version), 0);

  async function submit(restore = false) {
    if (submitting.current) return;
    submitting.current = true;
    setBusy(true);
    setError(undefined);
    try {
      if (restore && comparison) {
        await requestRevision(jobId, {
          note: "",
          captionCorrections: [],
          baseVersion: latestReady,
          restoreVersion: comparison.version,
        });
      } else {
        nonce.current ??= crypto.randomUUID();
        await requestAlternative(jobId, {
          requestId: nonce.current,
          baseVersion: run.version,
          kind,
          direction: direction.trim(),
        });
      }
      onUpdated();
    } catch (value) {
      setError(
        value instanceof Error
          ? value.message
          : "The version request could not complete.",
      );
    } finally {
      submitting.current = false;
      setBusy(false);
    }
  }

  return (
    <section
      aria-label="Creative alternatives and saved versions"
      className="mb-6 space-y-4 rounded-md border border-[#D7D9D3] bg-white p-5"
    >
      <h2 className="font-bold text-[#173F5F]">Explore another version</h2>
      {report ? (
        <div
          role="status"
          className="rounded-md bg-[#EFF6FA] p-3 text-sm text-[#173F5F]"
        >
          <p className="font-bold">
            {report.status === "similar"
              ? "Still similar to an earlier edit"
              : report.kind === "different_story"
                ? "Different recorded selections"
                : "Different cut or treatment"}
          </p>
          <p className="mt-2">{report.notice}</p>
          <p className="mt-2 text-xs">
            Compared with versions {report.compared_versions.join(", ")}. This
            checks source overlap and treatment; story quality needs your
            review.
          </p>
        </div>
      ) : null}
      {playable ? (
        <>
          <p className="text-sm text-[#666862]">
            Keep this edit and ask for a separate option from the same sources.
          </p>
          <Button
            className="min-h-12 w-full"
            type="button"
            variant="outline"
            aria-expanded={opened}
            disabled={busy}
            onClick={() => setOpened(!opened)}
          >
            {opened ? "Close alternative options" : "Make another version"}
          </Button>
          {opened ? (
            <div className="space-y-4">
              <fieldset disabled={busy} className="space-y-2">
                <legend className="mb-2 text-sm font-bold text-[#173F5F]">
                  What should be different?
                </legend>
                {(
                  [
                    [
                      "different_cut",
                      "Different cut, same story",
                      "Keep the message; explore another opening, takes, pacing, B-roll and framing.",
                    ],
                    [
                      "different_story",
                      "Find a different story",
                      "Explore another supported angle and recorded script. The earlier concept’s script is unlocked.",
                    ],
                  ] as const
                ).map(([value, label, help]) => (
                  <label
                    key={value}
                    className="flex min-h-12 gap-3 rounded-md border border-[#D7D9D3] p-3"
                  >
                    <input
                      type="radio"
                      name={`alternative-kind-${run.id}`}
                      checked={kind === value}
                      onChange={() => {
                        setKind(value);
                        nonce.current = undefined;
                      }}
                    />
                    <span>
                      <span className="block text-sm font-bold text-[#173F5F]">
                        {label}
                      </span>
                      <span className="mt-1 block text-xs text-[#666862]">
                        {help}
                      </span>
                    </span>
                  </label>
                ))}
              </fieldset>
              <label className="block text-sm font-bold text-[#173F5F]">
                Optional direction for this alternative
                <Textarea
                  className="mt-2 min-h-24"
                  maxLength={600}
                  disabled={busy}
                  value={direction}
                  onChange={(event) => {
                    setDirection(event.currentTarget.value);
                    nonce.current = undefined;
                  }}
                  placeholder="For example: explore how the product started, rather than the ingredients."
                />
              </label>
              <p className="text-xs leading-relaxed text-[#666862]">
                Uses another AI editing request and a local render. Stored
                source analysis is reused. No automatic retries for novelty, and
                nothing is approved or posted automatically.
              </p>
              <Button
                className="min-h-12 w-full bg-[#173F5F] text-white"
                type="button"
                disabled={busy}
                onClick={() => void submit()}
              >
                {busy
                  ? "Creating alternative…"
                  : "Create one alternative preview"}
              </Button>
            </div>
          ) : null}
        </>
      ) : (
        <p className="text-sm text-[#666862]">
          {active
            ? "The new version is being prepared. Your earlier previews stay available below."
            : "Your earlier previews remain available below."}
        </p>
      )}
      {ready.length ? (
        <details className="border-t border-[#D7D9D3] pt-3">
          <summary className="cursor-pointer py-2 text-sm font-bold text-[#173F5F]">
            Watch or choose a saved version
          </summary>
          <label
            className="mt-3 block text-sm"
            htmlFor={`saved-preview-${run.id}`}
          >
            Saved preview
          </label>
          <select
            id={`saved-preview-${run.id}`}
            className="mt-2 min-h-12 w-full rounded-md border border-[#D7D9D3] bg-white px-3"
            value={comparison ? String(comparison.version) : ""}
            disabled={busy}
            onChange={(event) => setSelected(event.currentTarget.value)}
          >
            {ready.map((version) => (
              <option key={version.id} value={version.version}>
                Version {version.version}
                {version.version === run.version ? " · current" : ""}
                {version.alternative_kind === "different_story"
                  ? " · different story"
                  : version.alternative_kind === "different_cut"
                    ? " · different cut"
                    : ""}
              </option>
            ))}
          </select>
          {comparison ? (
            <div className="mt-3 space-y-3">
              <video
                key={comparison.id}
                aria-label={`Saved preview version ${comparison.version}`}
                className="mx-auto max-h-96 w-full rounded bg-black"
                controls
                playsInline
                preload="none"
                src={`${root}?version=${comparison.version}`}
              />
              <a
                className="inline-block min-h-11 py-2 font-bold text-[#173F5F] underline"
                href={`${root}?download=true&version=${comparison.version}`}
              >
                Download version {comparison.version}
              </a>
              {comparison.version !== run.version ? (
                <Button
                  className="min-h-12 w-full"
                  type="button"
                  variant="outline"
                  disabled={busy || active}
                  onClick={() => void submit(true)}
                >
                  Use version {comparison.version} as current · zero AI
                </Button>
              ) : null}
              <p className="text-xs text-[#666862]">
                Choosing an earlier edit makes a new current version from its
                saved plan. Existing versions and exports remain recorded.
                Retention rules still apply to preview files.
              </p>
            </div>
          ) : null}
        </details>
      ) : null}
      {error ? (
        <p role="alert" className="text-sm text-[#A23B2A]">
          {error}
        </p>
      ) : null}
    </section>
  );
}
