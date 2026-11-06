"use client";

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown> : {};
}

function strings(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
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

export function EditingReceipt({ receipt }: { receipt: unknown }) {
  const data = record(receipt);
  if (data.version !== 1) return null;
  const contract = record(data.planning_contract);
  const audio = record(data.audio_processing);
  const changes = [...strings(data.local_repairs).map(item => item.replaceAll("_", " ")),
    ...strings(data.local_story_changes)];
  return (
    <details className="rounded-md border border-[#BFE3FF] bg-white p-5 text-sm text-[#173F5F]">
      <summary className="cursor-pointer font-bold">How this edit was made</summary>
      <div className="mt-3 space-y-3 leading-relaxed">
        <p>{SOURCES[String(data.plan_source)] ?? "The original planning route was not recorded."}</p>
        {PACING[String(contract.audio_pacing)] && <p>Audio direction: {PACING[String(contract.audio_pacing)]}.
          {contract.creative_quotas === false && " Zooms, transitions and effects were optional."}</p>}
        {changes.length > 0 ? <><p className="font-bold">Recorded local plan changes</p>
          <ul className="list-disc space-y-1 pl-5">{changes.map((change, index) => <li key={`${index}-${change}`}>{change}</li>)}</ul></>
          : <p>No local plan repairs or story trims were recorded for this render.</p>}
        <p>Local audio processing: {Number(audio.balanced_sources) || 0} sources balanced · {Number(audio.compressed_sources) || 0} compressed · {Number(audio.denoised_sources) || 0} denoised.</p>
        <p className="text-[#666862]">Technical checks do not judge the story or humour. Review the finished video and sound before exporting.</p>
      </div>
    </details>
  );
}
