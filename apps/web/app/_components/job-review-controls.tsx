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
  type OutputAspect,
  type Recipe,
  type TargetDuration,
} from "@/lib/media-api";

function message(error: unknown) {
  return error instanceof Error ? error.message : "The review request could not be completed";
}

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
  initialCoverTime,
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
  readonly initialCoverTime: number;
  readonly onUpdated: () => void;
}) {
  const [note, setNote] = useState("");
  const [originalText, setOriginalText] = useState("");
  const [replacementText, setReplacementText] = useState("");
  const [submitting, setSubmitting] = useState<"revision" | "approval">();
  const [error, setError] = useState<string>();
  const [profileName, setProfileName] = useState("");
  const [profileSaved, setProfileSaved] = useState(false);
  const [variantAspect, setVariantAspect] = useState<OutputAspect>(outputAspect === "vertical" ? "square" : "vertical");
  const [variantDuration, setVariantDuration] = useState<TargetDuration>(targetDuration >= 30 ? 15 : targetDuration);
  const [toolSubmitting, setToolSubmitting] = useState<"profile" | "variant">();
  const [timelineSubmitting, setTimelineSubmitting] = useState<number>();
  const [lockedElements, setLockedElements] = useState<readonly string[]>([]);
  const [coverTime, setCoverTime] = useState(initialCoverTime);

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
        captionCorrections:
          cleanOriginal && cleanReplacement
            ? [{ original_text: cleanOriginal, replacement_text: cleanReplacement }]
            : [],
        lockedElements,
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

  const adjustClip = async (
    clip: EditorialClip,
    change: { readonly action: "keep" | "remove" | "move_up" | "move_down"; readonly visual_preset?: EditorialClip["visual_preset"]; readonly source_audio_gain_db?: number },
  ) => {
    setTimelineSubmitting(clip.clip_index);
    setError(undefined);
    try {
      await requestRevision(jobId, {
        note: "",
        captionCorrections: [],
        clipAdjustments: [{ clip_index: clip.clip_index, ...change }],
        lockedElements,
      });
      onUpdated();
    } catch (timelineError) {
      setError(message(timelineError));
    } finally {
      setTimelineSubmitting(undefined);
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

      <section className="rounded-md border border-[#D7D9D3] bg-white p-5">
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
                    <Button aria-label="Move clip earlier" disabled={timelineSubmitting !== undefined || clip.clip_index === 0} onClick={() => void adjustClip(clip, { action: "move_up" })} size="icon" type="button" variant="outline"><ArrowUpIcon /></Button>
                    <Button aria-label="Move clip later" disabled={timelineSubmitting !== undefined || clip.clip_index === editorialTimeline.length - 1} onClick={() => void adjustClip(clip, { action: "move_down" })} size="icon" type="button" variant="outline"><ArrowDownIcon /></Button>
                    <Button aria-label="Remove clip" disabled={timelineSubmitting !== undefined || editorialTimeline.length <= (recipe === "montage" ? 2 : 1)} onClick={() => void adjustClip(clip, { action: "remove" })} size="icon" type="button" variant="outline"><Trash2Icon /></Button>
                  </div>
                </div>
                {clip.transcript_excerpt ? <p className="mt-2 line-clamp-2 text-xs leading-relaxed text-[#666862]">“{clip.transcript_excerpt}”</p> : null}
                {clip.editorial_intent ? <p className="mt-2 text-xs leading-relaxed text-[#53646F]">{clip.editorial_intent}</p> : null}
                <div className="mt-3 grid grid-cols-2 gap-2">
                  <select
                    aria-label={`Framing for clip ${clip.clip_index + 1}`}
                    className="h-10 rounded-md border border-[#D7D9D3] bg-white px-2 text-xs"
                    disabled={timelineSubmitting !== undefined}
                    onChange={(event) => void adjustClip(clip, { action: "keep", visual_preset: event.currentTarget.value as EditorialClip["visual_preset"] })}
                    value={clip.visual_preset}
                  >
                    <option value="standard">Standard frame</option>
                    <option value="punch_in">Punch in</option>
                    {recipe === "talking_head" ? <option value="strong_punch_in">Strong punch in</option> : null}
                    {clip.duration >= 2 ? <option value="slow_push_in">Slow push in</option> : null}
                    {clip.duration >= 2 ? <option value="slow_pull_out">Slow pull out</option> : null}
                  </select>
                  {recipe === "montage" && clip.media_kind === "video" ? (
                    <select
                      aria-label={`Source volume for clip ${clip.clip_index + 1}`}
                      className="h-10 rounded-md border border-[#D7D9D3] bg-white px-2 text-xs"
                      disabled={timelineSubmitting !== undefined}
                      onChange={(event) => void adjustClip(clip, { action: "keep", source_audio_gain_db: Number(event.currentTarget.value) })}
                      value={clip.source_audio_gain_db}
                    >
                      <option value={-6}>Quiet source</option><option value={0}>Normal source</option><option value={4}>Louder source</option><option value={8}>Feature source</option>
                    </select>
                  ) : <span className="flex items-center px-2 text-xs text-[#666862]">{clip.media_kind}</span>}
                </div>
              </article>
            ))}
          </div>
        </div>
        <div className="mb-5 border-t border-[#D7D9D3] pt-4">
          <p className="font-mono text-xs font-bold text-[#173F5F] uppercase">Protect in AI revisions</p>
          <div className="mt-3 flex flex-wrap gap-2">
            {["clip order", "spoken phrases", "captions", "music"].map((item) => (
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
        <label className="mt-4 block text-sm font-bold text-[#20211F]" htmlFor="revision-note">Editing feedback</label>
        <Textarea
          className="mt-2 min-h-28"
          id="revision-note"
          maxLength={1200}
          onChange={(event) => setNote(event.target.value)}
          placeholder="For example: shorten the opening and reach the strongest point sooner."
          value={note}
        />
        {recipe === "talking_head" ? (
          <fieldset className="mt-5 border-t border-[#D7D9D3] pt-5">
            <legend className="pr-2 text-sm font-bold text-[#20211F]">Optional caption correction</legend>
            <label className="mt-2 block text-xs text-[#666862]" htmlFor="caption-original">Current transcript text</label>
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
    </div>
  );
}
