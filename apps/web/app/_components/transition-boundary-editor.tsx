"use client";

import { useMemo, useState } from "react";
import { CheckIcon, LoaderCircleIcon, PlayIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  requestRevision,
  type EditorialClip,
} from "@/lib/media-api";

type PictureTransition = "cut" | "cross_dissolve" | "dip_to_black";

const transitionChoices: readonly {
  readonly value: PictureTransition;
  readonly label: string;
  readonly shortLabel: string;
  readonly description: string;
}[] = [
  {
    value: "cut",
    label: "Cut",
    shortLabel: "Cut",
    description:
      "Changes picture immediately. Best when the speech or action should feel continuous.",
  },
  {
    value: "cross_dissolve",
    label: "Short dissolve",
    shortLabel: "Dissolve",
    description:
      "Briefly blends the two pictures. Good for a gentle change; speech and total duration do not move.",
  },
  {
    value: "dip_to_black",
    label: "Dip to black",
    shortLabel: "Dip to black",
    description:
      "Fades through black. Use it to mark a clear change in time, place, or topic.",
  },
];

function normalizedTransition(value: string): PictureTransition {
  return value === "cross_dissolve" || value === "dip_to_black"
    ? value
    : "cut";
}

function transitionLabel(value: PictureTransition) {
  return (
    transitionChoices.find((choice) => choice.value === value)?.shortLabel ??
    "Cut"
  );
}

function clipName(clip: EditorialClip) {
  return clip.source_name?.trim() || `Clip ${clip.clip_index + 1}`;
}

export function TransitionBoundaryEditor({
  jobId,
  version,
  clips,
  onUpdated,
  onSeek,
}: {
  readonly jobId: string;
  readonly version: number;
  readonly clips: readonly EditorialClip[];
  readonly onUpdated: () => void;
  readonly onSeek?: (seconds: number) => void;
}) {
  const boundaries = useMemo(() => {
    let elapsed = 0;
    return clips.slice(1).map((incoming, index) => {
      elapsed += clips[index]?.duration ?? 0;
      return {
        incoming,
        outgoing: clips[index],
        time: elapsed,
      };
    });
  }, [clips]);
  const [selectedClipIndex, setSelectedClipIndex] = useState(
    boundaries[0]?.incoming.clip_index,
  );
  const selectedBoundary =
    boundaries.find(
      ({ incoming }) => incoming.clip_index === selectedClipIndex,
    ) ?? boundaries[0];
  const savedTransition = selectedBoundary
    ? normalizedTransition(selectedBoundary.incoming.transition)
    : "cut";
  const [draftTransition, setDraftTransition] =
    useState<PictureTransition>(savedTransition);
  const [showAll, setShowAll] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  if (!selectedBoundary) return null;

  const visibleBoundaries = showAll ? boundaries : boundaries.slice(0, 4);
  const selectedChoice =
    transitionChoices.find(
      (choice) => choice.value === draftTransition,
    ) ?? transitionChoices[0];

  async function submit() {
    if (draftTransition === savedTransition) return;
    setBusy(true);
    setError("");
    try {
      await requestRevision(jobId, {
        note: "",
        captionCorrections: [],
        baseVersion: version,
        clipAdjustments: [
          {
            clip_index: selectedBoundary.incoming.clip_index,
            clip_id: selectedBoundary.incoming.clip_id || undefined,
            action: "keep",
            transition: draftTransition,
          },
        ],
      });
      onUpdated();
    } catch (submitError) {
      setError(
        submitError instanceof Error
          ? submitError.message
          : "The transition preview could not be created.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <details className="scroll-mt-4 rounded-md border border-[#D7D9D3] bg-white" id="transition-editor">
      <summary className="min-h-16 cursor-pointer px-4 py-3 text-[#173F5F] marker:text-[#173F5F]">
        <span className="ml-2 inline-flex max-w-[calc(100%-2rem)] flex-col align-middle">
          <span className="text-sm font-bold">Transitions between clips</span>
          <span className="mt-1 text-xs font-normal leading-relaxed text-[#666862]">
            {boundaries.length} picture {boundaries.length === 1 ? "change" : "changes"} · speech timing stays fixed
          </span>
        </span>
      </summary>
      <div className="space-y-4 border-t border-[#E5E6E1] p-4">
        <div>
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-xs font-bold text-[#173F5F]">
                Choose a boundary
              </p>
              <p className="mt-1 text-xs leading-5 text-[#666862]">
                A transition changes only the picture between two clips. It
                does not reorder clips, change the words, or shorten the edit.
              </p>
            </div>
            <span className="shrink-0 rounded border border-[#D7D9D3] bg-[#F7F7F5] px-2 py-1 font-mono text-[10px] text-[#666862]">
              {boundaries.length} {boundaries.length === 1 ? "BOUNDARY" : "BOUNDARIES"}
            </span>
          </div>
          <div className="mt-3 space-y-2">
            {visibleBoundaries.map((boundary) => {
              const selected =
                boundary.incoming.clip_index ===
                selectedBoundary.incoming.clip_index;
              const transition = normalizedTransition(
                boundary.incoming.transition,
              );
              return (
                <button
                  aria-pressed={selected}
                  className={`flex min-h-14 w-full items-center justify-between gap-3 rounded-md p-3 text-left ${
                    selected
                      ? "border-2 border-[#173F5F] bg-[#EFF6FA]"
                      : "border border-[#D7D9D3] bg-white"
                  }`}
                  key={boundary.incoming.clip_id || boundary.incoming.clip_index}
                  onClick={() => {
                    setSelectedClipIndex(boundary.incoming.clip_index);
                    setDraftTransition(transition);
                    setError("");
                  }}
                  type="button"
                >
                  <span className="min-w-0">
                    <span className="block text-xs font-bold text-[#173F5F]">
                      Clip {boundary.outgoing.clip_index + 1} → Clip {boundary.incoming.clip_index + 1}
                    </span>
                    <span className="mt-1 block truncate text-[11px] text-[#666862]">
                      {clipName(boundary.outgoing)} → {clipName(boundary.incoming)} · {boundary.time.toFixed(1)}s
                    </span>
                  </span>
                  <span className="shrink-0 rounded border border-[#D7D9D3] bg-white px-2 py-1 font-mono text-[9px] font-bold uppercase text-[#173F5F]">
                    {transitionLabel(transition)}
                  </span>
                </button>
              );
            })}
          </div>
          {boundaries.length > 4 ? (
            <Button
              className="mt-2 h-11 w-full"
              onClick={() => setShowAll((current) => !current)}
              type="button"
              variant="outline"
            >
              {showAll
                ? "Show fewer boundaries"
                : `Show ${boundaries.length - 4} more ${boundaries.length - 4 === 1 ? "boundary" : "boundaries"}`}
            </Button>
          ) : null}
        </div>

        <div className="rounded-md border border-[#BFD2DE] bg-[#EFF6FA] p-3">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="text-xs font-bold text-[#173F5F]">
                Clip {selectedBoundary.outgoing.clip_index + 1} → Clip {selectedBoundary.incoming.clip_index + 1}
              </p>
              <p className="mt-1 font-mono text-[10px] text-[#666862]">
                PICTURE CHANGE AT {selectedBoundary.time.toFixed(1)}s
              </p>
            </div>
            <Button
              className="h-11 shrink-0"
              disabled={!onSeek}
              onClick={() =>
                onSeek?.(Math.max(0, selectedBoundary.time - 1))
              }
              size="sm"
              type="button"
              variant="outline"
            >
              <PlayIcon aria-hidden="true" /> Preview
            </Button>
          </div>
          <div
            aria-label="Picture transition"
            className="mt-3 grid grid-cols-3 gap-2"
            role="group"
          >
            {transitionChoices.map((choice) => (
              <button
                aria-pressed={draftTransition === choice.value}
                className={`min-h-12 rounded-md bg-white px-1 text-xs font-bold text-[#173F5F] ${
                  draftTransition === choice.value
                    ? "border-2 border-[#173F5F]"
                    : "border border-[#D7D9D3]"
                }`}
                key={choice.value}
                onClick={() => setDraftTransition(choice.value)}
                type="button"
              >
                {choice.shortLabel}
              </button>
            ))}
          </div>
          <div className="mt-3 rounded-md border border-[#D7D9D3] bg-white p-3">
            <p className="text-xs font-bold text-[#173F5F]">
              {selectedChoice.label}
            </p>
            <p className="mt-1 text-xs leading-5 text-[#666862]">
              {selectedChoice.description}
            </p>
          </div>
          <p className="mt-3 text-[11px] leading-5 text-[#666862]">
            Only this boundary will change. Nothing saves or renders until you
            create the preview.
          </p>
          {error ? (
            <p className="mt-3 text-xs text-[#A23B2A]" role="alert">
              {error}
            </p>
          ) : null}
          <Button
            className="mt-3 h-12 w-full bg-[#173F5F] text-white hover:bg-[#12344F]"
            disabled={busy || draftTransition === savedTransition}
            onClick={() => void submit()}
            type="button"
          >
            {busy ? (
              <LoaderCircleIcon aria-hidden="true" className="animate-spin" />
            ) : (
              <CheckIcon aria-hidden="true" />
            )}
            {draftTransition === savedTransition
              ? "This transition is already used"
              : "Create transition preview"}
          </Button>
        </div>
      </div>
    </details>
  );
}
