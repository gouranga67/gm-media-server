"use client";

import { useState, type FormEvent, type ReactNode } from "react";
import {
  ArchiveIcon,
  ArrowDownIcon,
  ArrowUpIcon,
  CheckIcon,
  DownloadIcon,
  FileTextIcon,
  ImageIcon,
  LoaderCircleIcon,
  RefreshCwIcon,
  SendIcon,
  Trash2Icon,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { PreciseClipEditor } from "./precise-clip-editor";
import { EditFeedbackCard } from "@/app/_components/edit-feedback-card";
import { RenderQualityCard } from "@/app/_components/render-quality-card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  approveEdit,
  requestRevision,
  requestDeliveryVariant,
  saveCreativeProfileFromJob,
  updateCoverFrame,
  type DeliveryVariant,
  type EditRun,
  type EditorialClip,
  type FinalExport,
  type EditFeedback,
  type OutputAspect,
  type Recipe,
  type JobReview,
  type TargetDuration,
} from "@/lib/media-api";

function message(error: unknown) {
  return error instanceof Error ? error.message : "The review request could not be completed";
}

type ClipChange = {
  readonly action: "keep" | "remove" | "move_up" | "move_down";
  readonly visual_preset?: EditorialClip["visual_preset"];
  readonly source_audio_gain_db?: number;
  readonly max_pause_seconds?: number;
};

function DownloadButton({
  href,
  label,
  icon,
}: {
  readonly href: string;
  readonly label: string;
  readonly icon: ReactNode;
}) {
  return (
    <Button asChild className="h-12 justify-start" variant="outline">
      <a href={href}>
        {icon}
        {label}
      </a>
    </Button>
  );
}

export function JobReviewControls({
  jobId,
  run,
  finalExport,
  outputAspect,
  recipe,
  targetDuration,
  deliveryVariants,
  editorialTimeline,
  storyAssessment,
  initialCoverTime,
  initialFeedback,
  onUpdated,
}: {
  readonly jobId: string;
  readonly run: EditRun;
  readonly finalExport: FinalExport | null;
  readonly outputAspect: OutputAspect;
  readonly recipe: Recipe;
  readonly targetDuration: TargetDuration;
  readonly deliveryVariants: readonly DeliveryVariant[];
  readonly editorialTimeline: readonly EditorialClip[];
  readonly storyAssessment: JobReview["story_assessment"] | undefined;
  readonly initialCoverTime: number;
  readonly initialFeedback: EditFeedback | null;
  readonly onUpdated: () => void;
}) {
  const [note, setNote] = useState("");
  const [originalText, setOriginalText] = useState("");
  const [replacementText, setReplacementText] = useState("");
  const [submitting, setSubmitting] = useState<"revision" | "approval" | "caption">();
  const [error, setError] = useState<string>();
  const [profileName, setProfileName] = useState("");
  const [profileSaved, setProfileSaved] = useState(false);
  const [variantAspect, setVariantAspect] = useState<OutputAspect>(outputAspect === "vertical" ? "square" : "vertical");
  const [variantDuration, setVariantDuration] = useState<TargetDuration>(targetDuration >= 30 ? 15 : targetDuration);
  const [toolSubmitting, setToolSubmitting] = useState<"profile" | "variant">();
  const [timelineSubmitting, setTimelineSubmitting] = useState<number>();
  const [pendingClipChange, setPendingClipChange] = useState<{
    readonly clip: EditorialClip;
    readonly change: ClipChange;
  }>();
  const [lockedElements, setLockedElements] = useState<readonly string[]>([]);
  const [revisionMode, setRevisionMode] = useState<"targeted" | "rebuild_story">("targeted");
  const revisionReport = run.manifest.revision_report as {
    changed?: boolean; changes?: readonly string[]; notice?: string;
    editor_explanation?: string; instruction?: string;
  } | undefined;
  const [coverTime, setCoverTime] = useState(initialCoverTime);
  const [captionPosition, setCaptionPosition] = useState<"lower_safe" | "middle" | "upper">(
    run.caption_settings.position ?? "lower_safe",
  );
  const [captionTiming, setCaptionTiming] = useState(
    run.caption_settings.timing_offset_seconds ?? 0,
  );
  const plannedEffects = Array.isArray(run.manifest.creative_effects)
    ? run.manifest.creative_effects as readonly Record<string, unknown>[]
    : [];
  const creativeDirection = run.manifest.creative_direction as { effect_level?: string } | undefined;
  const plannedBroll = Array.isArray(run.manifest.broll)
    ? run.manifest.broll as readonly Record<string, unknown>[] : [];
  const finishing = run.manifest.finishing as { mode?: string; rhythmic_punch_beats?: readonly number[] } | undefined;
  const effectMode = creativeDirection?.effect_level;
  const punchInCount = editorialTimeline.filter((clip) =>
    clip.visual_preset === "punch_in" || clip.visual_preset === "strong_punch_in").length;
  const cameraMoveCount = editorialTimeline.filter((clip) =>
    clip.visual_preset === "slow_push_in" || clip.visual_preset === "slow_pull_out").length;
  const transitionCount = editorialTimeline.filter((clip, index) =>
    index > 0 && clip.transition === "dip_to_black").length;

  const removeEffects = async () => {
    setSubmitting("revision"); setError(undefined);
    try {
      await requestRevision(jobId, { note: "", captionCorrections: [], effectsEnabled: false });
      onUpdated();
    } catch (revisionError) { setError(message(revisionError)); } finally { setSubmitting(undefined); }
  };

  const submitRevision = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const cleanNote = note.trim();
    const cleanOriginal = originalText.trim();
    const cleanReplacement = replacementText.trim();
    if (!cleanNote && !cleanOriginal && !cleanReplacement) {
      setError("Describe an edit change or enter a caption correction.");
      return;
    }
    if ((cleanOriginal && !cleanReplacement) || (!cleanOriginal && cleanReplacement)) {
      setError("Enter both the current caption text and its replacement.");
      return;
    }
    setSubmitting("revision");
    setError(undefined);
    try {
      await requestRevision(jobId, {
        note: cleanNote,
        revisionMode,
        captionCorrections:
          cleanOriginal && cleanReplacement
            ? [{ original_text: cleanOriginal, replacement_text: cleanReplacement }]
            : [],
        lockedElements: revisionMode === "rebuild_story"
          ? lockedElements.filter((item) => item !== "clip order" && item !== "spoken phrases")
          : lockedElements,
      });
      setNote("");
      setOriginalText("");
      setReplacementText("");
      onUpdated();
    } catch (revisionError) {
      setError(message(revisionError));
    } finally {
      setSubmitting(undefined);
    }
  };

  const removeBroll = async () => {
    setSubmitting("revision"); setError(undefined);
    try {
      await requestRevision(jobId, { note: "", captionCorrections: [], brollEnabled: false });
      onUpdated();
    } catch (revisionError) { setError(message(revisionError)); } finally { setSubmitting(undefined); }
  };

  const adjustClip = async (
    clip: EditorialClip,
    change: ClipChange,
  ) => {
    setTimelineSubmitting(clip.clip_index);
    setError(undefined);
    try {
      await requestRevision(jobId, {
        note: "",
        captionCorrections: [],
        baseVersion: run.version,
        clipAdjustments: [{ clip_index: clip.clip_index, clip_id: clip.clip_id || undefined, ...change }],
        lockedElements,
      });
      setPendingClipChange(undefined);
      onUpdated();
    } catch (timelineError) {
      setError(message(timelineError));
    } finally {
      setTimelineSubmitting(undefined);
    }
  };

  const adjustCaptions = async () => {
    setSubmitting("caption");
    setError(undefined);
    try {
      await requestRevision(jobId, {
        note: "",
        captionCorrections: [],
        captionSettings: {
          position: captionPosition,
          timing_offset_seconds: captionTiming,
        },
        lockedElements,
      });
      onUpdated();
    } catch (captionError) {
      setError(message(captionError));
    } finally {
      setSubmitting(undefined);
    }
  };

  const approve = async () => {
    setSubmitting("approval");
    setError(undefined);
    try {
      await updateCoverFrame(jobId, coverTime);
      await approveEdit(jobId, run.version);
      onUpdated();
    } catch (approvalError) {
      setError(message(approvalError));
    } finally {
      setSubmitting(undefined);
    }
  };

  // A job can have an older delivered version and a newer preview awaiting
  // approval. Only let a final export replace the review controls when it
  // belongs to the preview version currently on screen.
  const currentFinal = finalExport?.version === run.version ? finalExport : null;

  const saveProfile = async () => {
    if (!profileName.trim()) {
      setError("Give the creative profile a name.");
      return;
    }
    setToolSubmitting("profile");
    setError(undefined);
    try {
      await saveCreativeProfileFromJob(jobId, profileName.trim());
      setProfileSaved(true);
    } catch (profileError) {
      setError(message(profileError));
    } finally {
      setToolSubmitting(undefined);
    }
  };

  const createVariant = async () => {
    setToolSubmitting("variant");
    setError(undefined);
    try {
      await requestDeliveryVariant(jobId, {
        outputAspect: variantAspect,
        targetDurationSeconds: variantDuration,
      });
      onUpdated();
    } catch (variantError) {
      setError(message(variantError));
    } finally {
      setToolSubmitting(undefined);
    }
  };

  if (currentFinal?.status === "ready" && currentFinal.files_available) {
    const root = `/api/media/jobs/${encodeURIComponent(jobId)}/final`;
    const dimensions = outputAspect === "landscape" ? "1920 × 1080" : outputAspect === "square" ? "1080 × 1080" : "1080 × 1920";
    const deliverable = recipe === "montage" ? "montage" : "reel";
    return (
      <div className="space-y-4">
      <RenderQualityCard review={currentFinal.manifest.quality_review} />
      <section className="space-y-4 rounded-md border border-[#BFE3FF] bg-white p-5">
        <div>
          <p className="flex items-center gap-2 font-mono text-xs font-bold tracking-wide text-[#3A8F63] uppercase">
            <CheckIcon aria-hidden="true" className="size-4" /> Final delivery ready
          </p>
          <h2 className="mt-2 text-xl font-bold text-[#173F5F]">Download the finished {deliverable}</h2>
          <p className="mt-2 text-sm leading-relaxed text-[#666862]">
            Version {currentFinal.version} · {dimensions} · non-synthetic media only
          </p>
        </div>
        <Button asChild className="h-14 w-full bg-[#173F5F] text-white hover:bg-[#12344F]">
          <a href={`${root}/package`}>
            <ArchiveIcon aria-hidden="true" /> Download complete package
          </a>
        </Button>
        <div className="grid gap-2 sm:grid-cols-2">
          <DownloadButton href={`${root}/video`} icon={<DownloadIcon aria-hidden="true" />} label="Final MP4" />
          <DownloadButton href={`${root}/captions`} icon={<FileTextIcon aria-hidden="true" />} label="Captions" />
          <DownloadButton href={`${root}/cover`} icon={<ImageIcon aria-hidden="true" />} label="Cover image" />
          <DownloadButton href={`${root}/manifest`} icon={<FileTextIcon aria-hidden="true" />} label="Provenance" />
          {currentFinal.post_copy_available ? (
            <DownloadButton href={`${root}/post-copy`} icon={<FileTextIcon aria-hidden="true" />} label="Post copy" />
          ) : null}
        </div>
        <div className="border-t border-[#D7D9D3] pt-4">
          <p className="font-mono text-xs font-bold tracking-wide text-[#173F5F] uppercase">Reuse this look</p>
          <p className="mt-2 text-sm text-[#666862]">Save these creative settings for future jobs.</p>
          <div className="mt-3 flex gap-2">
            <Input
              aria-label="Creative profile name"
              disabled={profileSaved || toolSubmitting !== undefined}
              maxLength={80}
              onChange={(event) => setProfileName(event.target.value)}
              placeholder="e.g. Fast travel reel"
              value={profileName}
            />
            <Button disabled={profileSaved || toolSubmitting !== undefined} onClick={() => void saveProfile()} type="button" variant="outline">
              {toolSubmitting === "profile" ? <LoaderCircleIcon aria-hidden="true" className="animate-spin" /> : null}
              {profileSaved ? "Saved" : "Save"}
            </Button>
          </div>
        </div>
        <div className="border-t border-[#D7D9D3] pt-4">
          <p className="font-mono text-xs font-bold tracking-wide text-[#173F5F] uppercase">Create another format</p>
          <p className="mt-2 text-sm text-[#666862]">Uses this approved edit locally with zero additional model calls.</p>
          <div className="mt-3 grid grid-cols-2 gap-2">
            <select className="h-12 rounded-md border border-[#D7D9D3] bg-white px-3 text-sm" onChange={(event) => setVariantAspect(event.target.value as OutputAspect)} value={variantAspect}>
              <option value="vertical">Vertical 9:16</option>
              <option value="landscape">Landscape 16:9</option>
              <option value="square">Square 1:1</option>
            </select>
            <select className="h-12 rounded-md border border-[#D7D9D3] bg-white px-3 text-sm" onChange={(event) => setVariantDuration(Number(event.target.value) as TargetDuration)} value={variantDuration}>
              {[15, 20, 30, 45, 60].filter((seconds) => seconds <= targetDuration).map((seconds) => (
                <option key={seconds} value={seconds}>{seconds} seconds</option>
              ))}
            </select>
          </div>
          <Button className="mt-2 h-12 w-full" disabled={toolSubmitting !== undefined} onClick={() => void createVariant()} type="button" variant="outline">
            {toolSubmitting === "variant" ? <LoaderCircleIcon aria-hidden="true" className="animate-spin" /> : <RefreshCwIcon aria-hidden="true" />}
            Create local variant
          </Button>
          {deliveryVariants.length > 0 ? (
            <div className="mt-4 space-y-2">
              {deliveryVariants.map((variant) => {
                const variantRoot = `/api/media/jobs/${encodeURIComponent(jobId)}/variants/${encodeURIComponent(variant.id)}`;
                return (
                  <div className="rounded-md border border-[#D7D9D3] p-3" key={variant.id}>
                    <div className="flex items-center justify-between gap-3 text-sm">
                      <span className="font-bold text-[#173F5F]">{variant.output_aspect} · {variant.target_duration_seconds}s</span>
                      <span className="font-mono text-[10px] uppercase text-[#666862]">{variant.status}</span>
                    </div>
                    {variant.status === "ready" ? (
                      <div className="mt-3">
                        <video className={`${variant.output_aspect === "landscape" ? "aspect-video" : variant.output_aspect === "square" ? "aspect-square" : "aspect-[9/16]"} max-h-72 w-full rounded bg-black object-contain`} controls playsInline preload="metadata" src={`${variantRoot}/video?download=false`} />
                        <a className="mt-2 inline-block text-sm font-bold text-[#173F5F] underline underline-offset-4" href={`${variantRoot}/package`}>Download package</a>
                      </div>
                    ) : variant.status === "failed" ? (
                      <p className="mt-2 text-xs text-[#A23B2A]">{variant.error}</p>
                    ) : (
                      <p className="mt-2 text-xs text-[#666862]">Rendering on the Lenovo…</p>
                    )}
                  </div>
                );
              })}
            </div>
          ) : null}
        </div>
        {error ? <p className="text-xs text-[#A23B2A]" role="alert">{error}</p> : null}
      </section>
      <EditFeedbackCard editRunId={run.id} initialFeedback={initialFeedback} jobId={jobId} key={run.id} onSaved={onUpdated} version={run.version} />
      </div>
    );
  }

  if (currentFinal?.status === "pending" || currentFinal?.status === "rendering") {
    return (
      <section className="flex min-h-48 flex-col items-center justify-center rounded-md border border-[#D7D9D3] bg-white p-6 text-center">
        <LoaderCircleIcon aria-hidden="true" className="size-8 animate-spin text-[#173F5F] motion-reduce:animate-none" />
        <h2 className="mt-4 text-xl font-bold text-[#173F5F]">Rendering final delivery</h2>
        <p className="mt-2 text-sm leading-relaxed text-[#666862]">
          The Lenovo is creating the full-resolution video, captions, cover, manifest, and ZIP package.
        </p>
      </section>
    );
  }

  return (
    <div className="space-y-5">
      {currentFinal?.status === "failed" ? (
        <section className="rounded-md border border-[#E7C4BC] bg-white p-5">
          <p className="font-mono text-xs font-bold text-[#A23B2A] uppercase">Final export needs attention</p>
          <p className="mt-2 text-sm text-[#666862]">{currentFinal.error}</p>
          <Button className="mt-4 h-12 w-full" disabled={submitting !== undefined} onClick={() => void approve()} variant="outline">
            <RefreshCwIcon aria-hidden="true" /> Retry final export
          </Button>
        </section>
      ) : null}

      <RenderQualityCard review={run.manifest.quality_review} />
      <section className="rounded-md border border-[#D7D9D3] bg-white p-5">
        {storyAssessment ? (
          <div className="mb-5 rounded-md border border-[#BFE3FF] bg-[#EFF6FA] p-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="font-mono text-[10px] font-bold tracking-wide text-[#174D73] uppercase">Source story hints</p>
                <p className="mt-1 text-xs text-[#53646F]">Coverage in your uploaded footage, rather than a score of the finished edit.</p>
                <p className="mt-1 text-xs leading-relaxed text-[#53646F]">
                  {storyAssessment.source_moments_considered} source moments · {storyAssessment.clean_spoken_edit_points} clean speech edits · zero extra model calls
                </p>
              </div>
              <span className="rounded-full bg-white px-2 py-1 font-mono text-[9px] font-bold text-[#174D73]">v{storyAssessment.version}</span>
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              {(["hook", "context", "development", "payoff", "ending"] as const).map((role) => (
                <span className={`rounded-full px-2 py-1 font-mono text-[9px] font-bold uppercase ${storyAssessment.coverage[role] ? "bg-[#E4F1E9] text-[#307455]" : "bg-[#FFF0EC] text-[#A23B2A]"}`} key={role}>
                  {storyAssessment.coverage[role] ? "✓" : "!"} {role}
                </span>
              ))}
            </div>
            {storyAssessment.recommendations.length ? (
              <ul className="mt-3 space-y-1 text-xs leading-relaxed text-[#53646F]">
                {storyAssessment.recommendations.map((recommendation) => <li key={recommendation}>• {recommendation}</li>)}
              </ul>
            ) : <p className="mt-3 text-xs font-bold text-[#307455]">The selected evidence can support a complete story shape.</p>}
            {storyAssessment.duplicate_idea_groups.length ? <p className="mt-2 text-[11px] text-[#666862]">Repeated ideas detected: {storyAssessment.duplicate_idea_groups.length}. The editor was instructed to choose one strong version of each.</p> : null}
          </div>
        ) : null}
        <div className="mb-5">
          <p className="font-mono text-xs font-bold tracking-wide text-[#173F5F] uppercase">Edit breakdown</p>
          <p className="mt-2 text-sm text-[#666862]">Every change here makes a new local preview with zero additional model tokens.</p>
          <div className="mt-4 space-y-3">
            {editorialTimeline.map((clip) => (
              <article className="rounded-md border border-[#D7D9D3] p-3" key={`${clip.clip_index}-${clip.asset_id}`}>
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-bold text-[#173F5F]">{clip.clip_index + 1}. {clip.source_name}</p>
                    <p className="mt-1 font-mono text-[10px] text-[#666862]">{clip.source_in.toFixed(1)}–{clip.source_out.toFixed(1)}s · {clip.duration.toFixed(1)}s · {clip.transition.replaceAll("_", " ")}</p>
                    <p className="mt-2 inline-flex rounded-full bg-[#EFF6FA] px-2 py-1 font-mono text-[9px] font-bold tracking-wide text-[#174D73] uppercase">{clip.story_role}</p>
                  </div>
                  <div className="flex shrink-0 gap-1">
                    <Button aria-label="Move clip earlier" disabled={timelineSubmitting !== undefined || clip.clip_index === 0} onClick={() => setPendingClipChange({ clip, change: { action: "move_up" } })} size="icon" type="button" variant="outline"><ArrowUpIcon /></Button>
                    <Button aria-label="Move clip later" disabled={timelineSubmitting !== undefined || clip.clip_index === editorialTimeline.length - 1} onClick={() => setPendingClipChange({ clip, change: { action: "move_down" } })} size="icon" type="button" variant="outline"><ArrowDownIcon /></Button>
                    <Button aria-label="Remove clip" disabled={timelineSubmitting !== undefined || editorialTimeline.length <= (recipe === "montage" ? 2 : 1)} onClick={() => setPendingClipChange({ clip, change: { action: "remove" } })} size="icon" type="button" variant="outline"><Trash2Icon /></Button>
                  </div>
                </div>
                {clip.transcript_excerpt ? <p className="mt-2 line-clamp-2 text-xs leading-relaxed text-[#666862]">“{clip.transcript_excerpt}”</p> : null}
                {clip.editorial_intent ? <p className="mt-2 text-xs leading-relaxed text-[#53646F]">{clip.editorial_intent}</p> : null}
                <div className="mt-3 grid grid-cols-2 gap-2">
                  <select
                    aria-label={`Framing for clip ${clip.clip_index + 1}`}
                    className="h-10 rounded-md border border-[#D7D9D3] bg-white px-2 text-xs"
                    disabled={timelineSubmitting !== undefined}
                    onChange={(event) => setPendingClipChange({ clip, change: { action: "keep", visual_preset: event.currentTarget.value as EditorialClip["visual_preset"] } })}
                    value={pendingClipChange?.clip.clip_index === clip.clip_index && pendingClipChange.change.visual_preset ? pendingClipChange.change.visual_preset : clip.visual_preset}
                  >
                    <option value="standard">Standard frame</option>
                    <option value="punch_in">Punch in</option>
                    {clip.duration >= 3 ? <option value="rhythmic_punch">Rhythmic punch · 2.5s beats</option> : null}
                    {recipe === "talking_head" ? <option value="strong_punch_in">Strong punch in</option> : null}
                    {clip.duration >= 2 ? <option value="slow_push_in">Slow push in</option> : null}
                    {clip.duration >= 2 ? <option value="slow_pull_out">Slow pull out</option> : null}
                  </select>
                  {recipe === "montage" && clip.media_kind === "video" ? (
                    <select
                      aria-label={`Source volume for clip ${clip.clip_index + 1}`}
                      className="h-10 rounded-md border border-[#D7D9D3] bg-white px-2 text-xs"
                      disabled={timelineSubmitting !== undefined}
                      onChange={(event) => setPendingClipChange({ clip, change: { action: "keep", source_audio_gain_db: Number(event.currentTarget.value) } })}
                      value={pendingClipChange?.clip.clip_index === clip.clip_index && pendingClipChange.change.source_audio_gain_db !== undefined ? pendingClipChange.change.source_audio_gain_db : clip.source_audio_gain_db}
                    >
                      <option value={-6}>Quiet source</option><option value={0}>Normal source</option><option value={4}>Louder source</option><option value={8}>Feature source</option>
                    </select>
                  ) : <span className="flex items-center px-2 text-xs text-[#666862]">{clip.media_kind}</span>}
                </div>
                {clip.longest_pause_seconds >= 0.65 ? (
                  <label className="mt-2 block text-[11px] font-bold text-[#53646F]">
                    Longest pause: {clip.longest_pause_seconds.toFixed(1)}s
                    <select
                      aria-label={`Pause length for clip ${clip.clip_index + 1}`}
                      className="mt-1 h-10 w-full rounded-md border border-[#D7D9D3] bg-white px-2 text-xs font-normal"
                      disabled={timelineSubmitting !== undefined}
                      onChange={(event) => {
                        if (event.currentTarget.value) {
                          setPendingClipChange({
                            clip,
                            change: {
                              action: "keep",
                              max_pause_seconds: Number(event.currentTarget.value),
                            },
                          });
                        }
                      }}
                      value={pendingClipChange?.clip.clip_index === clip.clip_index && pendingClipChange.change.max_pause_seconds !== undefined ? pendingClipChange.change.max_pause_seconds : ""}
                    >
                      <option value="">Keep current pause</option>
                      <option value={0.35}>Tight beat · 0.35s</option>
                      <option value={0.6}>Short comic beat · 0.6s</option>
                      <option value={1}>Long comic beat · 1.0s</option>
                    </select>
                  </label>
                ) : null}
              <PreciseClipEditor key={`${run.version}-${clip.clip_id}`} jobId={jobId} version={run.version} clip={clip} onUpdated={onUpdated} />
              </article>
            ))}
          </div>
          {pendingClipChange ? (
            <div className="mt-4 rounded-md border border-[#BFD2DE] bg-[#EFF6FA] p-3">
              <p className="text-xs font-bold text-[#173F5F]">Timeline change ready</p>
              <p className="mt-1 text-xs text-[#53646F]">
                Clip {pendingClipChange.clip.clip_index + 1}: {pendingClipChange.change.action.replaceAll("_", " ")}
                {pendingClipChange.change.visual_preset ? ` · ${pendingClipChange.change.visual_preset.replaceAll("_", " ")}` : ""}
                {pendingClipChange.change.source_audio_gain_db !== undefined ? ` · ${pendingClipChange.change.source_audio_gain_db > 0 ? "+" : ""}${pendingClipChange.change.source_audio_gain_db} dB` : ""}
                {pendingClipChange.change.max_pause_seconds !== undefined ? ` · cap pauses at ${pendingClipChange.change.max_pause_seconds}s` : ""}
              </p>
              <div className="mt-3 grid grid-cols-2 gap-2">
                <Button disabled={timelineSubmitting !== undefined} onClick={() => setPendingClipChange(undefined)} type="button" variant="outline">Cancel</Button>
                <Button disabled={timelineSubmitting !== undefined} onClick={() => void adjustClip(pendingClipChange.clip, pendingClipChange.change)} type="button">
                  {timelineSubmitting !== undefined ? <LoaderCircleIcon aria-hidden="true" className="animate-spin" /> : <CheckIcon aria-hidden="true" />}
                  Apply &amp; render preview
                </Button>
              </div>
            </div>
          ) : null}
        </div>
        <div className="mb-5 border-t border-[#D7D9D3] pt-5">
          <p className="font-mono text-xs font-bold tracking-wide text-[#173F5F] uppercase">Caption placement</p>
          <p className="mt-2 text-xs leading-relaxed text-[#666862]">
            Lower safe stays clear of Instagram and TikTok controls. Position and sync changes preserve the exact edit and use zero model tokens.
          </p>
          <div className="mt-3 grid grid-cols-2 gap-2">
            <label className="text-[11px] font-bold text-[#53646F]">
              Position
              <select className="mt-1 h-10 w-full rounded-md border border-[#D7D9D3] bg-white px-2 text-xs font-normal" onChange={(event) => setCaptionPosition(event.currentTarget.value as typeof captionPosition)} value={captionPosition}>
                <option value="lower_safe">Lower · app-safe</option>
                <option value="middle">Centre</option>
                <option value="upper">Upper</option>
              </select>
            </label>
            <label className="text-[11px] font-bold text-[#53646F]">
              Timing
              <select className="mt-1 h-10 w-full rounded-md border border-[#D7D9D3] bg-white px-2 text-xs font-normal" onChange={(event) => setCaptionTiming(Number(event.currentTarget.value))} value={captionTiming}>
                <option value={-0.3}>0.3s earlier</option>
                <option value={-0.15}>0.15s earlier</option>
                <option value={0}>On speech</option>
                <option value={0.15}>0.15s later</option>
                <option value={0.3}>0.3s later</option>
              </select>
            </label>
          </div>
          <Button className="mt-3 h-11 w-full" disabled={submitting !== undefined || timelineSubmitting !== undefined} onClick={() => void adjustCaptions()} type="button" variant="outline">
            {submitting === "caption" ? <LoaderCircleIcon aria-hidden="true" className="animate-spin" /> : <CheckIcon aria-hidden="true" />}
            Apply caption layout &amp; render
          </Button>
        </div>
        <div className="mb-5 border-t border-[#D7D9D3] pt-4">
          <p className="font-mono text-xs font-bold text-[#173F5F] uppercase">Creative effects</p>
          {finishing?.mode === "high_impact" ? <p className="mt-2 text-xs font-bold text-[#174D73]">High impact · {finishing.rhythmic_punch_beats?.length ?? 0} rhythmic picture changes · {plannedBroll.length} B-roll cutaways</p> : null}
          {plannedBroll.length ? <div className="mt-3 space-y-2">
            {plannedBroll.map((cue, index) => <div className="rounded-md bg-[#EFF6FA] p-3 text-xs text-[#53646F]" key={`${String(cue.asset_id)}-${index}`}>
              <p className="font-bold text-[#173F5F]">{String(cue.source_name || "B-roll")} · {Number(cue.start_seconds).toFixed(1)}–{(Number(cue.start_seconds) + Number(cue.duration_seconds)).toFixed(1)}s</p>
              <p className="mt-1">{String(cue.editorial_intent || "Picture-only cutaway")} · main speech continues</p>
            </div>)}
            <Button className="h-10 w-full" disabled={submitting !== undefined} onClick={() => void removeBroll()} type="button" variant="outline"><Trash2Icon className="size-4" />Remove B-roll &amp; render · zero AI</Button>
          </div> : null}
          <p className="mt-2 text-xs leading-relaxed text-[#53646F]">
            This edit: {punchInCount} punch-ins · {cameraMoveCount} camera moves · {transitionCount} dips to black · {plannedEffects.length} sound or overlay cues.
            {" "}Other clip boundaries use hard cuts. Use the clip framing controls above to adjust a punch-in without an AI call.
          </p>
          {plannedEffects.length ? <><div className="mt-3 space-y-2">{plannedEffects.map((effect, index) => <div className="rounded-md bg-[#F7F7F5] px-3 py-2 text-xs text-[#53646F]" key={`${String(effect.asset_id)}-${index}`}><span className="font-bold text-[#173F5F]">{String(effect.title || effect.kind || "Effect")}</span> · {Number(effect.start_seconds || 0).toFixed(1)}s · {String(effect.purpose || "emphasis")}</div>)}</div><Button className="mt-3 h-10 w-full" disabled={submitting !== undefined} onClick={() => void removeEffects()} type="button" variant="outline"><Trash2Icon className="size-4" />Remove all effects &amp; render · zero AI</Button></> : <p className="mt-2 text-xs text-[#666862]">This version uses no creative effects.</p>}
          {!plannedEffects.length ? (
            <p className="mt-2 text-xs leading-relaxed text-[#666862]">
              {run.effects_enabled === false
                ? "Effects were removed in this revision."
                : effectMode === "off"
                  ? "Creative effects were Off for this job. For your next test, check the library and choose Social when creating the job."
                  : "The editor selected no sounds or overlays for this version. Check that suitable assets are available and request a specific cue in your revision."}
              {" "}<a className="font-bold text-[#173F5F] underline underline-offset-4" href="/creative">View music &amp; effects library</a>
            </p>
          ) : null}
        </div>
        <div className="mb-5 border-t border-[#D7D9D3] pt-4">
          <p className="font-mono text-xs font-bold text-[#173F5F] uppercase">Protect in AI revisions</p>
          <div className="mt-3 flex flex-wrap gap-2">
            {["clip order", "spoken phrases", "captions", "music", "effects"].map((item) => (
              <label className="flex items-center gap-2 rounded-full border border-[#D7D9D3] px-3 py-2 text-xs" key={item}>
                <input checked={lockedElements.includes(item)} onChange={() => setLockedElements((current) => current.includes(item) ? current.filter((value) => value !== item) : [...current, item])} type="checkbox" />
                Keep {item}
              </label>
            ))}
          </div>
        </div>
        <p className="font-mono text-xs font-bold tracking-wide text-[#173F5F] uppercase">Approve version {run.version}</p>
        <h2 className="mt-2 text-xl font-bold text-[#173F5F]">Happy with this edit?</h2>
        <p className="mt-2 text-sm leading-relaxed text-[#666862]">
          Approval freezes this edit plan and starts the full-quality local render.
        </p>
        <label className="mt-4 block text-xs font-bold text-[#173F5F]" htmlFor="cover-frame-time">COVER FRAME · SECONDS INTO EDIT</label>
        <Input className="mt-2" id="cover-frame-time" min={0} onChange={(event) => setCoverTime(Math.max(0, Number(event.currentTarget.value)))} step={0.1} type="number" value={coverTime} />
        <Button
          className="mt-5 h-14 w-full bg-[#173F5F] text-white hover:bg-[#12344F]"
          disabled={submitting !== undefined}
          onClick={() => void approve()}
          type="button"
        >
          {submitting === "approval" ? <LoaderCircleIcon aria-hidden="true" className="animate-spin" /> : <CheckIcon aria-hidden="true" />}
          Approve &amp; export
        </Button>
      </section>

      <form className="rounded-md border border-[#D7D9D3] bg-white p-5" onSubmit={(event) => void submitRevision(event)}>
        <p className="font-mono text-xs font-bold tracking-wide text-[#173F5F] uppercase">Request a revision</p>
        {revisionReport ? <div className="mt-4 rounded-md bg-[#EFF6FA] p-4 text-sm text-[#173F5F]" role="status">
          <p className="font-bold">What changed in version {run.version}</p>
          {revisionReport.instruction ? <p className="mt-2">Your request: {revisionReport.instruction}</p> : null}
          {revisionReport.changes?.length ? <ul className="mt-2 list-disc space-y-1 pl-5">{revisionReport.changes.map((change) => <li key={change}>{change}</li>)}</ul> : null}
          {revisionReport.notice ? <p className="mt-2">{revisionReport.notice}</p> : null}
          {revisionReport.editor_explanation ? <p className="mt-2">Editor explanation: {revisionReport.editor_explanation}</p> : null}
        </div> : null}
        <label className="mt-4 block text-sm font-bold text-[#20211F]" htmlFor="revision-mode">How much should change?</label>
        <select className="mt-2 min-h-12 w-full rounded-md border border-[#C7CBD0] bg-white px-3 text-sm" disabled={submitting !== undefined} id="revision-mode" onChange={(event) => setRevisionMode(event.currentTarget.value as "targeted" | "rebuild_story")} value={revisionMode}>
          <option value="targeted">Adjust this edit</option>
          <option value="rebuild_story">Rebuild the story from the footage</option>
        </select>
        <p className="mt-2 text-xs leading-relaxed text-[#666862]">{revisionMode === "rebuild_story" ? "Reconsiders the source dialogue and your original brief. Clip order and spoken selections are unlocked; other protections stay active." : "Describe a specific change and the parts you want to keep."} This sends a new AI editing request only when you submit. Use the rating card below to teach future edits.</p>
        <label className="mt-4 block text-sm font-bold text-[#20211F]" htmlFor="revision-note">What should the editor change?</label>
        <Textarea
          className="mt-2 min-h-28"
          id="revision-note"
          maxLength={1200}
          onChange={(event) => setNote(event.target.value)}
          placeholder={revisionMode === "rebuild_story" ? "For example: tell the story in the brief. Start with the problem, keep the explanation together, and finish with the result. Preserve complete sentences." : "For example: shorten the pause after ‘…’ to half a second. Keep the rest of the story."}
          value={note}
        />
        {recipe === "talking_head" ? (
          <fieldset className="mt-5 border-t border-[#D7D9D3] pt-5">
            <legend className="pr-2 text-sm font-bold text-[#20211F]">Optional caption correction</legend>
            <p className="mt-2 text-xs leading-relaxed text-[#666862]">
              This changes only the matching on-screen words. Capitalization and trailing punctuation do not need to match.
            </p>
            <label className="mt-3 block text-xs text-[#666862]" htmlFor="caption-original">Current on-screen caption text</label>
            <Input id="caption-original" maxLength={300} onChange={(event) => setOriginalText(event.target.value)} placeholder="Incorrect name or phrase" value={originalText} />
            <label className="mt-3 block text-xs text-[#666862]" htmlFor="caption-replacement">Replace with</label>
            <Input id="caption-replacement" maxLength={300} onChange={(event) => setReplacementText(event.target.value)} placeholder="Correct text" value={replacementText} />
          </fieldset>
        ) : null}
        {error ? <p className="mt-4 text-xs text-[#A23B2A]" role="alert">{error}</p> : null}
        <Button className="mt-5 h-12 w-full" disabled={submitting !== undefined} type="submit" variant="outline">
          {submitting === "revision" ? <LoaderCircleIcon aria-hidden="true" className="animate-spin" /> : <SendIcon aria-hidden="true" />}
          Create revised preview
        </Button>
      </form>
      <EditFeedbackCard editRunId={run.id} initialFeedback={initialFeedback} jobId={jobId} key={run.id} onSaved={onUpdated} version={run.version} />
    </div>
  );
}
