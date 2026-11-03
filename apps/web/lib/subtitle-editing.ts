import type { SubtitleCue } from "./media-api";

export function splitSubtitle(cue: SubtitleCue, cursor: number): readonly SubtitleCue[] {
  const boundaries = Array.from(cue.text.matchAll(/\s+/g), (match) => match.index!);
  if (cursor <= 0 || cursor >= cue.text.length || !boundaries.length || cue.end - cue.start < .16) {
    throw new Error("Place the text cursor between words in a caption lasting at least 0.16 seconds.");
  }
  const point = boundaries.reduce((best, at) => Math.abs(at - cursor) < Math.abs(best - cursor) ? at : best);
  const left = cue.text.slice(0, point).trim(), right = cue.text.slice(point).trim();
  if (!left || !right) throw new Error("Place the cursor between two words, away from spaces at the beginning or end.");
  const at = Math.round(Math.max(cue.start + .08, Math.min(cue.end - .08,
    cue.start + (cue.end - cue.start) * left.split(/\s+/).length / cue.text.trim().split(/\s+/).length)) * 1000) / 1000;
  return [{ ...cue, end: at, text: left }, { ...cue, id: `cue-${crypto.randomUUID()}`, start: at, text: right }];
}
export function mergeSubtitles(left: SubtitleCue, right: SubtitleCue): SubtitleCue {
  if (left.hidden || right.hidden) throw new Error("Show both captions before merging them.");
  if (left.end > right.start + .001) throw new Error("These captions overlap. Keep them as separate lines.");
  const text = `${left.text.trim()} ${right.text.trim()}`;
  if (text.length > 600) throw new Error("The merged caption is too long; keep it as separate lines.");
  return { ...left, end: right.end, text };
}
export function replaceSubtitles(cues: readonly SubtitleCue[], search: string, replacement: string, all: boolean, from = 0): readonly SubtitleCue[] {
  if (!search.trim() || !replacement.trim()) throw new Error("Enter a phrase and replacement text. Use Hide to remove a caption.");
  const expression = new RegExp(search.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), all ? "gi" : "i");
  let replaced = false;
  return cues.map((cue, index) => {
    if (!all && (replaced || index < from)) return cue;
    const text = cue.text.replace(expression, () => { replaced = true; return replacement; });
    if (text.length > 600) throw new Error("A replacement would make a caption too long. Edit that line directly.");
    return text === cue.text ? cue : { ...cue, text };
  });
}
