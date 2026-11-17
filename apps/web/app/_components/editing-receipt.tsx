"use client";

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown> : {};
}

function strings(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function records(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.map(record).filter((item) => Object.keys(item).length > 0) : [];
}

const SOURCES: Record<string, string> = {
  model_plan: "AI planned this edit from the selected sources and brief.",
  saved_plan: "This render reused a saved edit plan.",
  local_controls: "Local editing controls updated this edit.",
};
const PACING: Record<string, string> = {
  connected_passages: "Complete conversations and useful natural sound",
  tight_dialogue: "Tighter dialogue with complete phrases",
  music_led: "Music and pictures, with complete speech where useful",
};
const INSTRUCTION_HANDLING: Record<string, string> = {
  supplied_script: "The supplied script and its order were treated as authoritative.",
  ordered_scenes: "Every supplied scene was kept in the requested order.",
  ordered_points: "Every supplied point was kept in the requested order.",
  creative_brief: "The brief guided the edit while the AI chose source-backed structure.",
};

export function EditingReceipt({ receipt }: { receipt: unknown }) {
  const data = record(receipt);
  if (data.version !== 1 && data.version !== 2) return null;
  const contract = record(data.planning_contract);
  const briefReview = record(data.brief_contract_review);
  const audio = record(data.audio_processing);
  const effectReceipt = record(data.effect_decisions);
  const effectItems = records(effectReceipt.items);
  const effectGroups = (["selected", "rejected", "skipped"] as const).map((decision) => ({
    decision,
    items: effectItems.filter((item) => item.decision === decision),
  })).filter((group) => group.items.length > 0);
  const changes = [...strings(data.local_repairs).map(item => item.replaceAll("_", " ")),
    ...strings(data.local_story_changes)];
  return (
    <details className="rounded-md border border-[#BFE3FF] bg-white p-5 text-sm text-[#173F5F]">
      <summary className="cursor-pointer font-bold">How this edit was made</summary>
      <div className="mt-3 space-y-3 leading-relaxed">
        <p>{SOURCES[String(data.plan_source)] ?? "The original planning route was not recorded."}</p>
        {INSTRUCTION_HANDLING[String(contract.instruction_mode)] ? (
          <p>Instruction handling: {INSTRUCTION_HANDLING[String(contract.instruction_mode)]}</p>
        ) : null}
        {briefReview.status === "checked" ? (
          <p className="rounded-md border border-[#9CCDB1] bg-[#E8F4ED] p-3 text-xs font-bold text-[#315B40]">
            Transcript check passed: the selected speech preserves the supplied script or ordered points.
          </p>
        ) : briefReview.status === "attention" ? (
          <p className="rounded-md border border-[#E6D8A8] bg-[#FFF8DE] p-3 text-xs leading-5 text-[#6B5510]">
            Some scene meaning could not be verified from transcript evidence. Check the preview against your brief before approval.
          </p>
        ) : null}
        {PACING[String(contract.audio_pacing)] && <p>Audio direction: {PACING[String(contract.audio_pacing)]}.
          {contract.creative_quotas === false && " Zooms, transitions and effects were optional."}</p>}
        {data.version === 2 && effectItems.length > 0 ? (
          <details className="rounded-md border border-[#D7D9D3] bg-[#F7F7F5] p-3">
            <summary className="min-h-11 cursor-pointer content-center font-bold">
              Effect decisions · {effectItems.filter((item) => item.decision === "selected").length} selected · {effectItems.filter((item) => item.decision === "rejected").length} rejected · {effectItems.filter((item) => item.decision === "skipped").length} skipped
            </summary>
            <div className="mt-3 space-y-4">
              {effectGroups.map((group) => (
                <section aria-label={`${group.decision} effects`} className="space-y-2" key={group.decision}>
                  <h4 className="text-xs font-bold uppercase tracking-[0.12em] text-[#666862]">{group.decision}</h4>
                  <ul className="space-y-2">
                    {group.items.map((item, index) => {
                      const evidence = strings(item.evidence);
                      const tone = group.decision === "selected"
                        ? "border-[#9CCDB1] bg-[#E8F4ED]"
                        : group.decision === "rejected"
                          ? "border-[#F0B6A9] bg-[#FFF0EC]"
                          : "border-[#D7D9D3] bg-white";
                      return (
                        <li className={`rounded-md border p-3 ${tone}`} key={`${String(item.preset)}-${index}`}>
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <span className="font-bold text-[#20211F]">{String(item.label || item.preset)}</span>
                            <span className="rounded bg-white px-2 py-1 text-[10px] font-bold uppercase text-[#666862]">
                              {String(item.eligibility || "unrecorded").replaceAll("_", " ")}
                            </span>
                          </div>
                          <p className="mt-1 text-xs leading-5 text-[#53646F]">{String(item.reason || "No reason was recorded.")}</p>
                          {evidence.length ? <p className="mt-1 text-xs font-bold text-[#173F5F]">{evidence.join(" · ")}</p> : null}
                        </li>
                      );
                    })}
                  </ul>
                </section>
              ))}
              <p className="text-xs leading-5 text-[#666862]">{String(effectReceipt.note || "This receipt records the saved plan, not a quality score.")}</p>
            </div>
          </details>
        ) : null}
        {changes.length > 0 ? <><p className="font-bold">Recorded local plan changes</p>
          <ul className="list-disc space-y-1 pl-5">{changes.map((change, index) => <li key={`${index}-${change}`}>{change}</li>)}</ul></>
          : <p>No local plan repairs or story trims were recorded for this render.</p>}
        <p>Local audio processing: {Number(audio.balanced_sources) || 0} sources balanced · {Number(audio.compressed_sources) || 0} compressed · {Number(audio.denoised_sources) || 0} denoised.</p>
        <p className="text-[#666862]">Technical checks do not judge the story or humour. Review the finished video and sound before exporting.</p>
      </div>
    </details>
  );
}
