"use client";

import { useState, type FormEvent, type ReactNode } from "react";
import {
  ArchiveIcon,
  CheckIcon,
  DownloadIcon,
  FileTextIcon,
  ImageIcon,
  LoaderCircleIcon,
  RefreshCwIcon,
  SendIcon,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  approveEdit,
  requestRevision,
  type EditRun,
  type FinalExport,
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
  onUpdated,
}: {
  readonly jobId: string;
  readonly run: EditRun;
  readonly finalExport: FinalExport | null;
  readonly onUpdated: () => void;
}) {
  const [note, setNote] = useState("");
  const [originalText, setOriginalText] = useState("");
  const [replacementText, setReplacementText] = useState("");
  const [submitting, setSubmitting] = useState<"revision" | "approval">();
  const [error, setError] = useState<string>();

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

  const approve = async () => {
    setSubmitting("approval");
    setError(undefined);
    try {
      await approveEdit(jobId, run.version);
      onUpdated();
    } catch (approvalError) {
      setError(message(approvalError));
    } finally {
      setSubmitting(undefined);
    }
  };

  if (finalExport?.status === "ready" && finalExport.files_available) {
    const root = `/api/media/jobs/${encodeURIComponent(jobId)}/final`;
    return (
      <section className="space-y-4 rounded-md border border-[#BFE3FF] bg-white p-5">
        <div>
          <p className="flex items-center gap-2 font-mono text-xs font-bold tracking-wide text-[#3A8F63] uppercase">
            <CheckIcon aria-hidden="true" className="size-4" /> Final delivery ready
          </p>
          <h2 className="mt-2 text-xl font-bold text-[#173F5F]">Download the finished reel</h2>
          <p className="mt-2 text-sm leading-relaxed text-[#666862]">
            Version {finalExport.version} · 1080 × 1920 · non-synthetic media only
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
          {finalExport.post_copy_available ? (
            <DownloadButton href={`${root}/post-copy`} icon={<FileTextIcon aria-hidden="true" />} label="Post copy" />
          ) : null}
        </div>
      </section>
    );
  }

  if (finalExport?.status === "pending" || finalExport?.status === "rendering") {
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
      {finalExport?.status === "failed" ? (
        <section className="rounded-md border border-[#E7C4BC] bg-white p-5">
          <p className="font-mono text-xs font-bold text-[#A23B2A] uppercase">Final export needs attention</p>
          <p className="mt-2 text-sm text-[#666862]">{finalExport.error}</p>
          <Button className="mt-4 h-12 w-full" disabled={submitting !== undefined} onClick={() => void approve()} variant="outline">
            <RefreshCwIcon aria-hidden="true" /> Retry final export
          </Button>
        </section>
      ) : null}

      <section className="rounded-md border border-[#D7D9D3] bg-white p-5">
        <p className="font-mono text-xs font-bold tracking-wide text-[#173F5F] uppercase">Approve version {run.version}</p>
        <h2 className="mt-2 text-xl font-bold text-[#173F5F]">Happy with this edit?</h2>
        <p className="mt-2 text-sm leading-relaxed text-[#666862]">
          Approval freezes this edit plan and starts the full-quality local render.
        </p>
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
        <fieldset className="mt-5 border-t border-[#D7D9D3] pt-5">
          <legend className="pr-2 text-sm font-bold text-[#20211F]">Optional caption correction</legend>
          <label className="mt-2 block text-xs text-[#666862]" htmlFor="caption-original">Current transcript text</label>
          <Input id="caption-original" maxLength={300} onChange={(event) => setOriginalText(event.target.value)} placeholder="Incorrect name or phrase" value={originalText} />
          <label className="mt-3 block text-xs text-[#666862]" htmlFor="caption-replacement">Replace with</label>
          <Input id="caption-replacement" maxLength={300} onChange={(event) => setReplacementText(event.target.value)} placeholder="Correct text" value={replacementText} />
        </fieldset>
        {error ? <p className="mt-4 text-xs text-[#A23B2A]" role="alert">{error}</p> : null}
        <Button className="mt-5 h-12 w-full" disabled={submitting !== undefined} type="submit" variant="outline">
          {submitting === "revision" ? <LoaderCircleIcon aria-hidden="true" className="animate-spin" /> : <SendIcon aria-hidden="true" />}
          Create revised preview
        </Button>
      </form>
    </div>
  );
}
