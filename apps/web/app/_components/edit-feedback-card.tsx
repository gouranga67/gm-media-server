"use client";

import { useState } from "react";
import { CheckIcon, LoaderCircleIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  saveEditFeedback,
  type EditFeedback,
  type FeedbackTag,
} from "@/lib/media-api";

const RATINGS = [
  [1, "Poor"], [2, "Needs work"], [3, "Good"], [4, "Great"], [5, "Excellent"],
] as const;

const TAGS: readonly { readonly value: FeedbackTag; readonly label: string; readonly kind: "strength" | "improve" }[] = [
  { value: "strong_hook", label: "Strong hook", kind: "strength" },
  { value: "clear_story", label: "Clear story", kind: "strength" },
  { value: "clean_captions", label: "Clean captions", kind: "strength" },
  { value: "balanced_audio", label: "Balanced audio", kind: "strength" },
  { value: "good_visuals", label: "Good visuals", kind: "strength" },
  { value: "good_colour", label: "Good colour", kind: "strength" },
  { value: "strong_ending", label: "Strong ending", kind: "strength" },
  { value: "effects_worked", label: "Effects worked", kind: "strength" },
  { value: "meme_worked", label: "Meme landed", kind: "strength" },
  { value: "weak_hook", label: "Hook needs work", kind: "improve" },
  { value: "confusing_story", label: "Story unclear", kind: "improve" },
  { value: "pacing_too_slow", label: "Too slow", kind: "improve" },
  { value: "pacing_too_fast", label: "Too fast", kind: "improve" },
  { value: "caption_issue", label: "Caption issue", kind: "improve" },
  { value: "audio_issue", label: "Audio issue", kind: "improve" },
  { value: "visual_issue", label: "Visual issue", kind: "improve" },
  { value: "colour_issue", label: "Colour issue", kind: "improve" },
  { value: "weak_ending", label: "Ending needs work", kind: "improve" },
  { value: "effects_too_much", label: "Too many effects", kind: "improve" },
  { value: "effects_too_loud", label: "Effects too loud", kind: "improve" },
  { value: "effect_timing_issue", label: "Effect timing issue", kind: "improve" },
  { value: "meme_forced", label: "Meme felt forced", kind: "improve" },
];

const OPPOSITES: Partial<Record<FeedbackTag, FeedbackTag>> = {
  strong_hook: "weak_hook", weak_hook: "strong_hook",
  clear_story: "confusing_story", confusing_story: "clear_story",
  pacing_too_slow: "pacing_too_fast", pacing_too_fast: "pacing_too_slow",
  clean_captions: "caption_issue", caption_issue: "clean_captions",
  balanced_audio: "audio_issue", audio_issue: "balanced_audio",
  good_visuals: "visual_issue", visual_issue: "good_visuals",
  good_colour: "colour_issue", colour_issue: "good_colour",
  strong_ending: "weak_ending", weak_ending: "strong_ending",
  effects_worked: "effects_too_much", effects_too_much: "effects_worked",
  meme_worked: "meme_forced", meme_forced: "meme_worked",
};

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : "Feedback could not be saved";
}

export function EditFeedbackCard({
  jobId,
  editRunId,
  version,
  initialFeedback,
  onSaved,
}: {
  readonly jobId: string;
  readonly editRunId: string;
  readonly version: number;
  readonly initialFeedback: EditFeedback | null;
  readonly onSaved: () => void;
}) {
  const [rating, setRating] = useState(initialFeedback?.rating ?? 0);
  const [tags, setTags] = useState<readonly FeedbackTag[]>(initialFeedback?.tags ?? []);
  const [note, setNote] = useState(initialFeedback?.note ?? "");
  const [scope, setScope] = useState<NonNullable<EditFeedback["scope"]>>(initialFeedback?.scope ?? "edit");
  const [start, setStart] = useState(initialFeedback?.start_seconds?.toString() ?? "");
  const [end, setEnd] = useState(initialFeedback?.end_seconds?.toString() ?? "");
  const [wouldUseAgain, setWouldUseAgain] = useState(initialFeedback?.would_use_again ?? false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(Boolean(initialFeedback));
  const [error, setError] = useState<string>();

  const toggleTag = (tag: FeedbackTag) => {
    setSaved(false);
    setError(undefined);
    setTags((current) => {
      if (current.includes(tag)) return current.filter((item) => item !== tag);
      const opposite = OPPOSITES[tag];
      const compatible = opposite ? current.filter((item) => item !== opposite) : current;
      return [...compatible, tag];
    });
  };

  const submit = async () => {
    if (rating === 0) {
      setError("Choose an overall rating first.");
      return;
    }
    setSaving(true);
    setError(undefined);
    try {
      await saveEditFeedback(jobId, {
        editRunId,
        rating,
        tags,
        note: note.trim(),
        wouldUseAgain, scope, startSeconds: start === "" ? undefined : Number(start), endSeconds: end === "" ? undefined : Number(end),
      });
      setSaved(true);
      onSaved();
    } catch (saveError) {
      setError(errorMessage(saveError));
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="rounded-md border border-[#BFD2DE] bg-white p-5">
      <p className="font-mono text-xs font-bold tracking-wide text-[#174D73] uppercase">Teach future edits</p>
      <h2 className="mt-2 text-xl font-bold text-[#173F5F]">How did version {version} turn out?</h2>
      <p className="mt-2 text-sm leading-relaxed text-[#666862]">
        Your rating stays on this server. Repeated feedback becomes a cautious preference after at least three examples.
      </p>

      <div aria-label="Overall edit rating" className="mt-4 grid grid-cols-5 gap-1" role="group">
        {RATINGS.map(([value, label]) => (
          <button
            aria-pressed={rating === value}
            className={`min-h-14 rounded-md border px-1 py-2 text-[10px] font-bold ${rating === value ? "border-[#173F5F] bg-[#173F5F] text-white" : "border-[#D7D9D3] bg-white text-[#53646F] hover:border-[#7A9AAE]"}`}
            key={value}
            onClick={() => { setRating(value); setSaved(false); setError(undefined); }}
            type="button"
          >
            <span className="block text-base">{value}</span>{label}
          </button>
        ))}
      </div>

      {(["strength", "improve"] as const).map((kind) => (
        <div className="mt-4" key={kind}>
          <p className="text-xs font-bold text-[#173F5F]">{kind === "strength" ? "WHAT WORKED" : "WHAT SHOULD IMPROVE"}</p>
          {kind === "strength" ? <p className="mt-1 text-xs text-[#666862]">Choose all that apply.</p> : null}
          <div className="mt-2 flex flex-wrap gap-2">
            {TAGS.filter((tag) => tag.kind === kind).map((tag) => (
              <button
                aria-pressed={tags.includes(tag.value)}
                className={`rounded-full border px-3 py-2 text-xs ${tags.includes(tag.value) ? (kind === "strength" ? "border-[#73B894] bg-[#E4F1E9] text-[#245E43]" : "border-[#D69A8D] bg-[#FFF0EC] text-[#8D3023]") : "border-[#D7D9D3] bg-white text-[#53646F]"}`}
                key={tag.value}
                onClick={() => toggleTag(tag.value)}
                type="button"
              >
                {tag.label}
              </button>
            ))}
          </div>
        </div>
      ))}

      <label className="mt-4 block text-xs font-bold text-[#173F5F]" htmlFor={`feedback-note-${editRunId}`}>OPTIONAL NOTE</label>
      <Textarea
        className="mt-2 min-h-20"
        id={`feedback-note-${editRunId}`}
        maxLength={1200}
        onChange={(event) => { setNote(event.target.value); setSaved(false); }}
        placeholder="What should the editor remember next time?"
        value={note}
      />
      <details className="mt-4"><summary className="min-h-11 cursor-pointer content-center text-xs font-bold text-[#173F5F]">Focus feedback on a topic or moment</summary><div className="grid gap-3 py-3 sm:grid-cols-3"><label className="text-xs">Topic<select className="mt-1 min-h-11 w-full rounded border border-[#C7CBD0] bg-white px-2" value={scope} onChange={(e) => { setScope(e.currentTarget.value as typeof scope); setSaved(false); }}>{["edit","story","pacing","captions","audio","colour","effects"].map((value) => <option key={value} value={value}>{value}</option>)}</select></label><label className="text-xs">Start seconds · optional<input className="mt-1 min-h-11 w-full rounded border border-[#C7CBD0] px-2" min={0} max={60} step="0.1" type="number" value={start} onChange={(e) => { setStart(e.currentTarget.value); setSaved(false); }} /></label><label className="text-xs">End seconds · optional<input className="mt-1 min-h-11 w-full rounded border border-[#C7CBD0] px-2" min={0} max={60} step="0.1" type="number" value={end} onChange={(e) => { setEnd(e.currentTarget.value); setSaved(false); }} /></label></div></details>
      <label className="mt-4 flex items-center gap-3 rounded-md bg-[#EFF6FA] p-3 text-sm text-[#173F5F]">
        <input checked={wouldUseAgain} onChange={(event) => { setWouldUseAgain(event.target.checked); setSaved(false); }} type="checkbox" />
        I would publish or use this edit
      </label>
      {error ? <p className="mt-3 text-xs text-[#A23B2A]" role="alert">{error}</p> : null}
      <Button className={`mt-4 h-12 w-full ${saved ? "" : "bg-[#173F5F] text-white hover:bg-[#245674]"}`} disabled={saving} onClick={() => void submit()} type="button" variant={saved ? "outline" : "default"}>
        {saving ? <LoaderCircleIcon aria-hidden="true" className="animate-spin" /> : saved ? <CheckIcon aria-hidden="true" /> : null}
        {saved ? "Feedback saved" : "Save feedback"}
      </Button>
    </section>
  );
}
