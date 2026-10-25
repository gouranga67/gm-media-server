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

export function RenderQualityCard({ review }: { readonly review: unknown }) {
  if (!review || typeof review !== "object" || !("version" in review)) return null;
  const report = review as QualityReview;
  if (!Array.isArray(report.checks) || !Array.isArray(report.findings)) return null;
  const label = report.status === "passed" ? "Checks completed" : report.status === "attention" ? "Worth reviewing" : "Checks incomplete";
  const badge = report.status === "passed" ? "bg-[#E4F1E9] text-[#245E43]" : "bg-[#FFF6DC] text-[#775C08]";

  return (
    <section aria-label="Local quality review" className="rounded-md border border-[#BFD2DE] bg-white p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-bold text-[#173F5F]">Local quality review</h2>
          <p className="mt-1 text-xs text-[#666862]">Finished video and timing checks · zero AI tokens</p>
        </div>
        <span className={`rounded-full px-3 py-1 text-xs font-bold ${badge}`}>{label}</span>
      </div>
      <p className="mt-3 text-sm leading-relaxed text-[#53646F]">
        This report keeps your edit intact. Listen and watch before changing a pause, dark shot, or delivery choice.
        Story quality and humour still need your judgement.
      </p>
      {report.findings.length ? (
        <ul className="mt-4 space-y-3">
          {report.findings.map((finding, index) => (
            <li className="rounded-md bg-[#F5F8FA] p-3" key={`${finding.code}-${index}`}>
              <p className="text-sm font-bold text-[#173F5F]">{finding.title}</p>
              {typeof finding.start_seconds === "number" ? (
                <p className="mt-1 font-mono text-[10px] text-[#53646F]">
                  {finding.start_seconds.toFixed(1)}s{typeof finding.end_seconds === "number" ? `–${finding.end_seconds.toFixed(1)}s` : ""}
                  {typeof finding.clip_index === "number" ? ` · clip ${finding.clip_index + 1}` : ""}
                </p>
              ) : null}
              <p className="mt-1 text-xs leading-relaxed text-[#53646F]">{finding.detail}</p>
            </li>
          ))}
        </ul>
      ) : <p className="mt-4 text-sm text-[#245E43]">{report.status === "passed" ? "No issues flagged by these checks." : "No issues flagged so far; some measurements are unavailable."}</p>}
      {report.finding_count > report.findings.length ? <p className="mt-2 text-xs text-[#666862]">Showing {report.findings.length} of {report.finding_count} review hints.</p> : null}
      <details className="mt-4 border-t border-[#D7D9D3] pt-3">
        <summary className="cursor-pointer text-xs font-bold text-[#173F5F]">What was checked</summary>
        <ul className="mt-3 space-y-3">
          {report.checks.map((check) => (
            <li key={check.code}>
              <p className="text-xs font-bold text-[#173F5F]">{check.label} · {check.status.replaceAll("_", " ")}</p>
              <p className="mt-1 text-xs leading-relaxed text-[#53646F]">{check.detail}</p>
            </li>
          ))}
        </ul>
      </details>
    </section>
  );
}
