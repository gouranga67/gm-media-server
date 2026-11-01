type QualityCheck = {
  readonly code: string;
  readonly label: string;
  readonly status: string;
  readonly detail: string;
};

type QualityFinding = {
  readonly code: string;
  readonly title: string;
  readonly detail: string;
  readonly severity: string;
  readonly start_seconds?: number;
  readonly end_seconds?: number;
  readonly clip_index?: number;
};

type QualityReview = {
  readonly version: string;
  readonly status: string;
  readonly checks: readonly QualityCheck[];
  readonly findings: readonly QualityFinding[];
  readonly finding_count: number;
};

type StoryBeat = {
  readonly clip_index: number;
  readonly role: string;
  readonly text: string;
  readonly start_seconds: number;
  readonly end_seconds: number;
  readonly source_in: number;
  readonly source_out: number;
  readonly word_timed: boolean;
};

function isStoryBeat(value: unknown): value is StoryBeat {
  if (!value || typeof value !== "object") return false;
  const beat = value as Record<string, unknown>;
  return ["clip_index", "start_seconds", "end_seconds", "source_in", "source_out"].every(
    (key) => typeof beat[key] === "number" && Number.isFinite(beat[key]),
  ) && typeof beat.role === "string" && typeof beat.text === "string" && typeof beat.word_timed === "boolean";
}

export function RenderQualityCard({
  review,
  storyContract,
  storyFinishing,
  storySequence,
}: {
  readonly review: unknown;
  readonly storyContract?: unknown;
  readonly storyFinishing?: unknown;
  readonly storySequence?: unknown;
}) {
  if (!review || typeof review !== "object" || !("version" in review))
    return null;
  const report = review as QualityReview;
  const contract =
    storyContract && typeof storyContract === "object"
      ? (storyContract as { status?: string; central_point?: string })
      : undefined;
  const cleanup =
    storyFinishing && typeof storyFinishing === "object"
      ? (storyFinishing as {
          status?: string;
          changes?: readonly string[];
          findings?: readonly string[];
          measured_clips?: number;
          speech_clip_count?: number;
        })
      : undefined;
  const sequence = storySequence && typeof storySequence === "object"
    ? storySequence as { findings?: readonly string[]; outline?: readonly unknown[] } : undefined;
  const sequenceFindings = Array.isArray(sequence?.findings)
    ? sequence.findings.filter((line) => typeof line === "string") : [];
  const outline = Array.isArray(sequence?.outline) ? sequence.outline.filter(isStoryBeat).slice(0, 48) : [];
  const changes = Array.isArray(cleanup?.changes)
    ? cleanup.changes.filter((line) => typeof line === "string")
    : [];
  const findings = Array.isArray(cleanup?.findings)
    ? cleanup.findings.filter((line) => typeof line === "string")
    : [];
  if (!Array.isArray(report.checks) || !Array.isArray(report.findings))
    return null;
  const needsReview =
    report.status === "attention" ||
    findings.length > 0 ||
    sequenceFindings.length > 0 ||
    contract?.status === "attention";
  const label = needsReview
    ? "Worth reviewing"
    : report.status === "passed"
      ? "Checks completed"
      : "Checks incomplete";
  const badge =
    report.status === "passed" && !needsReview
      ? "bg-[#E4F1E9] text-[#245E43]"
      : "bg-[#FFF6DC] text-[#775C08]";

  return (
    <section
      aria-label="Local quality review"
      className="rounded-md border border-[#BFD2DE] bg-white p-5"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-bold text-[#173F5F]">
            Local quality review
          </h2>
          <p className="mt-1 text-xs text-[#666862]">
            Finished video and timing checks · zero AI tokens
          </p>
        </div>
        <span className={`rounded-full px-3 py-1 text-xs font-bold ${badge}`}>
          {label}
        </span>
      </div>
      <p className="mt-3 text-sm leading-relaxed text-[#53646F]">
        This report keeps your edit intact. Listen and watch before changing a
        pause, dark shot, or delivery choice. Story quality and humour still
        need your judgement.
      </p>
      {outline.length ? <details className="mt-4 border-t border-[#D7D9D3] pt-3">
        <summary className="min-h-11 cursor-pointer text-sm font-bold text-[#173F5F]">Recorded story outline</summary>
        <p className="mt-2 text-xs text-[#53646F]">These are the selected source passages. Roles describe the edit plan; they do not prove that the story or joke works.</p>
        <ol className="mt-3 space-y-3 text-xs text-[#53646F]">{outline.map((beat) => <li key={beat.clip_index}>
          <p className="font-bold">Clip {beat.clip_index + 1} · {beat.start_seconds.toFixed(1)}–{beat.end_seconds.toFixed(1)}s · {beat.role}</p>
          <p className="mt-1">{beat.text || "Picture-only passage or speech without usable transcript timing."}</p>
          <p className="mt-1">Source {beat.source_in.toFixed(1)}–{beat.source_out.toFixed(1)}s · {beat.word_timed ? "word-timed transcript" : "limited transcript evidence"}</p>
        </li>)}</ol>
        {sequenceFindings.length ? <ul className="mt-3 space-y-2 text-xs text-[#A23B2A]">{sequenceFindings.map((finding, index) => <li key={index}>{finding}</li>)}</ul> : null}
      </details> : null}
      {contract?.status === "checked" ||
      (cleanup && cleanup.status !== "not_applicable") ? (
        <details className="mt-4 border-t border-[#D7D9D3] pt-3">
          <summary className="min-h-11 cursor-pointer text-sm font-bold text-[#173F5F]">
            Story selection and cleanup
          </summary>
          {contract?.status === "checked" ? (
            <div className="mt-2 text-xs leading-relaxed text-[#53646F]">
              <p className="font-bold">
                Selected recorded passages and their order checked.
              </p>
                <p className="mt-1">{typeof contract.central_point === "string" ? contract.central_point : ""}</p>
              <p className="mt-1">
                This checks the selected script, not whether its meaning,
                delivery or ending works for a viewer.
              </p>
            </div>
          ) : null}
          {cleanup && cleanup.status !== "not_applicable" ? (
            <p className="mt-3 text-xs text-[#53646F]">
              Local cleanup · {cleanup.measured_clips ?? 0}
              {typeof cleanup.speech_clip_count === "number"
                ? ` of ${cleanup.speech_clip_count}`
                : ""}{" "}
              speech passages measured · zero additional AI calls
            </p>
          ) : null}
          {changes.length ? (
            <ul className="mt-2 space-y-2 text-xs text-[#53646F]">
              {changes.map((line, index) => (
                <li key={index}>{line}</li>
              ))}
            </ul>
          ) : cleanup?.status === "checked" ? (
            <p className="mt-2 text-xs text-[#53646F]">
              No automatic cleanup changes were needed by these checks.
            </p>
          ) : null}
          {findings.length ? (
            <ul className="mt-2 space-y-2 text-xs text-[#A23B2A]">
              {findings.map((line, index) => (
                <li key={index}>{line}</li>
              ))}
            </ul>
          ) : null}
        </details>
      ) : null}
      {report.findings.length ? (
        <ul className="mt-4 space-y-3">
          {report.findings.map((finding, index) => (
            <li
              className="rounded-md bg-[#F5F8FA] p-3"
              key={`${finding.code}-${index}`}
            >
              <p className="text-sm font-bold text-[#173F5F]">
                {finding.title}
              </p>
              {typeof finding.start_seconds === "number" ? (
                <p className="mt-1 font-mono text-[10px] text-[#53646F]">
                  {finding.start_seconds.toFixed(1)}s
                  {typeof finding.end_seconds === "number"
                    ? `–${finding.end_seconds.toFixed(1)}s`
                    : ""}
                  {typeof finding.clip_index === "number"
                    ? ` · clip ${finding.clip_index + 1}`
                    : ""}
                </p>
              ) : null}
              <p className="mt-1 text-xs leading-relaxed text-[#53646F]">
                {finding.detail}
              </p>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-4 text-sm text-[#245E43]">
          {report.status === "passed"
            ? "No issues flagged by the video measurements."
            : "No issues flagged so far; some measurements are unavailable."}
        </p>
      )}
      {report.finding_count > report.findings.length ? (
        <p className="mt-2 text-xs text-[#666862]">
          Showing {report.findings.length} of {report.finding_count} review
          hints.
        </p>
      ) : null}
      <details className="mt-4 border-t border-[#D7D9D3] pt-3">
        <summary className="cursor-pointer text-xs font-bold text-[#173F5F]">
          What was checked
        </summary>
        <ul className="mt-3 space-y-3">
          {report.checks.map((check) => (
            <li key={check.code}>
              <p className="text-xs font-bold text-[#173F5F]">
                {check.label} · {check.status.replaceAll("_", " ")}
              </p>
              <p className="mt-1 text-xs leading-relaxed text-[#53646F]">
                {check.detail}
              </p>
            </li>
          ))}
        </ul>
      </details>
    </section>
  );
}
