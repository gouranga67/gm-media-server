import Link from "next/link";

import type { EditRun } from "@/lib/media-api";

export function JobPromptHistory({
  originalPrompt,
  versions,
  activeVersion,
}: {
  readonly originalPrompt: string;
  readonly versions: readonly EditRun[];
  readonly activeVersion?: number;
}) {
  const orderedVersions = [...versions].sort((left, right) => left.version - right.version);
  return (
    <section aria-labelledby="original-prompt-heading" className="rounded-md border border-[#D7D9D3] bg-white p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="font-mono text-xs font-bold tracking-wide text-[#173F5F] uppercase" id="original-prompt-heading">Original prompt</h2>
        <Link className="text-xs font-bold text-[#173F5F] underline underline-offset-4" href="/prompts">All prompt history</Link>
      </div>
      <p className="mt-3 whitespace-pre-wrap break-words text-sm leading-relaxed text-[#20211F]">
        {originalPrompt.trim() || "No original text prompt was supplied for this job."}
      </p>
      {orderedVersions.length > 0 ? (
        <details className="mt-5 border-t border-[#D7D9D3] pt-4">
          <summary className="cursor-pointer text-sm font-bold text-[#173F5F] focus-visible:outline-2 focus-visible:outline-offset-4">
            Revision history · {orderedVersions.length} {orderedVersions.length === 1 ? "version" : "versions"}
          </summary>
          <p className="mt-2 text-xs leading-relaxed text-[#666862]">Your submitted requests, including failed attempts. Local edits and re-renders may have no new text prompt.</p>
          <ol className="mt-4 space-y-3">
            {orderedVersions.map((version) => (
              <li className="rounded-md bg-[#F7F7F5] p-3" key={version.id}>
                <div className="flex flex-wrap items-center gap-x-2 gap-y-1 font-mono text-[10px] text-[#53646F]">
                  <span className="font-bold text-[#173F5F]">Version {version.version}{version.version === activeVersion ? " · current" : ""}</span>
                  <span>{version.status.replaceAll("_", " ")}</span>
                  <time dateTime={version.created_at}>{new Date(version.created_at).toLocaleString()}</time>
                </div>
                <p className="mt-2 whitespace-pre-wrap break-words text-sm leading-relaxed text-[#20211F]">
                  {version.revision_note?.trim()
                    || (version.provider === "submitted"
                      ? "An exact edit plan was submitted; no new text prompt was recorded."
                      : version.version === 1
                        ? "Initial preview using the original prompt above."
                        : "No new text prompt was recorded for this version.")}
                </p>
                {version.caption_corrections.length > 0 ? (
                  <ul className="mt-2 space-y-1 text-xs leading-relaxed text-[#53646F]">
                    {version.caption_corrections.map((correction, index) => (
                      <li className="break-words" key={index}>Caption: “{correction.original_text}” → “{correction.replacement_text}”</li>
                    ))}
                  </ul>
                ) : null}
              </li>
            ))}
          </ol>
        </details>
      ) : null}
    </section>
  );
}
