"use client";
import { useEffect, useState, type FormEvent } from "react";
import {
  getFinishingTools,
  requestRevision,
  requestLocalRepair,
  type FinishingInspection,
  type FinishingTools,
  type EditorialClip,
  type VisualEffectIntensity,
  type VisualEffectPosition,
  type VisualEffectPreset,
} from "@/lib/media-api";
const control =
  "mt-1 min-h-11 w-full rounded-md border border-[#C7CBD0] bg-white px-3 text-sm text-[#20211F]";
type Tool =
  | "motion"
  | "audio"
  | "captions"
  | "colour"
  | "layer"
  | "music"
  | "join"
  | "callout"
  | "visual_beat"
  | "pointer"
  | "music_pause";
type TaskGroup = "story" | "picture" | "layers" | "sound";
const taskGroups: readonly {
  readonly id: TaskGroup;
  readonly label: string;
  readonly summary: string;
  readonly tools: readonly Tool[];
}[] = [
  { id: "story", label: "Story & timing", summary: "Audio-picture joins", tools: ["join"] },
  { id: "picture", label: "Picture", summary: "Framing, movement, colour", tools: ["motion", "colour"] },
  { id: "layers", label: "Layers & graphics", summary: "Pictures, callouts, effects", tools: ["layer", "callout", "visual_beat", "pointer"] },
  { id: "sound", label: "Sound & captions", summary: "Voice, music, subtitles", tools: ["audio", "captions", "music", "music_pause"] },
];
const toolLabels: Readonly<Record<Tool, string>> = {
  motion: "Targeted camera move",
  audio: "Phrase audio level",
  captions: "Timed caption placement",
  colour: "Selected clip colour",
  layer: "Picture layer / green screen",
  music: "Music excerpt",
  join: "Independent audio / picture join",
  callout: "Text callout / list counter",
  visual_beat: "Visual effect / animation",
  pointer: "Arrow / circle pointer",
  music_pause: "Pause music, keep speech",
};
type EffectEligibility = {
  readonly status: "ready" | "review" | "blocked";
  readonly label: string;
  readonly reason: string;
};
const effectGalleryGroups = [
  { label: "Accent", categories: ["accent", "layout", "pointer"] },
  { label: "Social", categories: ["social"] },
  { label: "Text", categories: ["typography"] },
  { label: "Camera", categories: ["camera"] },
  { label: "Transition", categories: ["transition"] },
] as const;
const sourceBackedTextEffects: readonly VisualEffectPreset[] = [
  "letter_dive",
  "comment_drop",
  "post_wall",
  "sketch_words",
];
function effectChecklist(preset: VisualEffectPreset): readonly string[] {
  if (preset === "paper_tear") return [
    "The cut still reads clearly.",
    "Story audio stays continuous across the tear.",
    "The playful treatment suits the moment.",
  ];
  if (preset === "rack_focus" || preset === "dolly_zoom") return [
    "The intended subject stays visible.",
    "No crop edge, blur or movement distracts from the story.",
    "The camera treatment supports the beat rather than overpowering it.",
  ];
  if (preset === "live_cursor") return [
    "The pointer lands on the real target.",
    "The click pulse does not imply an action that did not happen.",
    "Captions and important picture details remain clear.",
  ];
  if (sourceBackedTextEffects.includes(preset) || preset === "voice_note") return [
    "Every word or implication is supported by the source.",
    "Dialogue captions remain easy to read.",
    "The treatment does not invent a sender, audience or reaction.",
  ];
  return [
    "The effect marks a genuinely important beat.",
    "The complete frame and main subject remain readable.",
    "Dialogue captions stay clear above the treatment.",
  ];
}
export function FinishingWorkspace({
  jobId,
  version,
  clips,
  onUpdated,
}: {
  readonly jobId: string;
  readonly version: number;
  readonly clips: readonly EditorialClip[];
  readonly onUpdated: () => void;
}) {
  const [open, setOpen] = useState(false);
  return (
    <details
      className="rounded-md border border-[#D7D9D3] bg-white p-4"
      id="finishing-workspace"
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary className="min-h-11 cursor-pointer content-center text-sm font-bold text-[#173F5F]">
        Finishing tools · local preview
      </summary>
      {open ? (
        <FinishingForm
          key={version}
          jobId={jobId}
          version={version}
          clips={clips}
          onUpdated={onUpdated}
        />
      ) : (
        <p className="mt-2 text-xs leading-5 text-[#666862]">
          Targeted camera movement, audio, captions, colour and picture layers.
          Existing versions stay available.
        </p>
      )}
    </details>
  );
}
function FinishingForm({
  jobId,
  version,
  clips,
  onUpdated,
}: {
  readonly jobId: string;
  readonly version: number;
  readonly clips: readonly EditorialClip[];
  readonly onUpdated: () => void;
}) {
  const [callout, setCallout] = useState("");
  const [calloutStyle, setCalloutStyle] = useState<
    "label" | "thought" | "counter" | "headline" | "comment"
  >("headline");
  const [visualBeat, setVisualBeat] = useState<VisualEffectPreset>("impact_frame");
  const [visualBeatIntensity, setVisualBeatIntensity] = useState<VisualEffectIntensity>("standard");
  const [visualBeatPosition, setVisualBeatPosition] = useState<VisualEffectPosition>("center");
  const [cursorStartX, setCursorStartX] = useState("0.25");
  const [cursorStartY, setCursorStartY] = useState("0.4");
  const [cursorEndX, setCursorEndX] = useState("0.75");
  const [cursorEndY, setCursorEndY] = useState("0.4");
  const [cursorClick, setCursorClick] = useState(true);
  const [letterText, setLetterText] = useState("");
  const [commentText, setCommentText] = useState("");
  const [postTexts, setPostTexts] = useState(["", "", ""]);
  const [sketchText, setSketchText] = useState("");
  const [focusStartX, setFocusStartX] = useState("0.35");
  const [focusStartY, setFocusStartY] = useState("0.35");
  const [focusEndX, setFocusEndX] = useState("0.65");
  const [focusEndY, setFocusEndY] = useState("0.55");
  const [tearBoundaryIndex, setTearBoundaryIndex] = useState(1);
  const [tearDirection, setTearDirection] = useState<"left" | "right">("left");
  const [dollyClipIndex, setDollyClipIndex] = useState(0);
  const [dollyDirection, setDollyDirection] = useState<"push_in" | "pull_out">("push_in");
  const [dollyAnchorX, setDollyAnchorX] = useState("0.5");
  const [dollyAnchorY, setDollyAnchorY] = useState("0.5");
  const [pointerShape, setPointerShape] = useState<"arrow" | "circle">(
    "circle",
  );
  const [pointerDirection, setPointerDirection] = useState<
    "left" | "right" | "up" | "down"
  >("right");
  const [inspection, setInspection] = useState<FinishingInspection>();
  const [taskGroup, setTaskGroup] = useState<TaskGroup>("picture");
  const [tool, setTool] = useState<Tool>("motion");
  const [clipIndex, setClipIndex] = useState(0);
  const [start, setStart] = useState("0");
  const [end, setEnd] = useState("2");
  const [gain, setGain] = useState("3");
  const [position, setPosition] = useState<
    "lower_safe" | "middle" | "upper" | "hidden"
  >("upper");
  const [zoom, setZoom] = useState("1.15");
  const [anchorX, setAnchorX] = useState("0.5");
  const [anchorY, setAnchorY] = useState("0.5");
  const [saturation, setSaturation] = useState("1");
  const [gamma, setGamma] = useState("1");
  const [lead, setLead] = useState("0.25");
  const [tail, setTail] = useState("0");
  const [sourceId, setSourceId] = useState("");
  const [sourceIn, setSourceIn] = useState("0");
  const [width, setWidth] = useState("0.4");
  const [shape, setShape] = useState<"rectangle" | "circle">("rectangle");
  const [animation, setAnimation] = useState<"none" | "fade" | "slide_up">(
    "fade",
  );
  const [keyColor, setKeyColor] = useState("");
  const [rate, setRate] = useState("1");
  const [freeze, setFreeze] = useState(false);
  const [musicStart, setMusicStart] = useState("0");
  const [denoise, setDenoise] = useState(false);
  const [restore, setRestore] = useState(String(Math.max(1, version - 1)));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const effectDefinition = inspection?.effect_registry.effects.find(
    (effect) => effect.preset === visualBeat,
  );
  const intensityParameter = effectDefinition?.parameters.find(
    (parameter) => parameter.key === "intensity",
  );
  const positionParameter = effectDefinition?.parameters.find(
    (parameter) => parameter.key === "position",
  );
  const cursorParameters = effectDefinition?.parameters.filter(
    (parameter) => parameter.type === "number",
  ) ?? [];
  const focusParameters = effectDefinition?.parameters.filter(
    (parameter) => parameter.key.startsWith("focus_") && parameter.type === "number",
  ) ?? [];
  const clipBoundaries = clips.slice(0, -1).flatMap((clip, index) => {
    const incoming = clips[index + 1];
    return incoming?.transition === "cut" && incoming.duration >= 0.4 ? [{
      boundaryIndex: index + 1,
      at: clips.slice(0, index + 1).reduce((total, item) => total + item.duration, 0),
      outgoing: clip.source_name,
      incoming: incoming.source_name,
      incomingDuration: incoming.duration,
    }] : [];
  });
  const dollyClips = clips.flatMap((clip, index) => {
    const at = clips.slice(0, index).reduce((total, item) => total + item.duration, 0);
    const endAt = at + clip.duration;
    const settings = inspection?.settings;
    const hasCameraConflict = clip.visual_preset !== "standard"
      || settings?.motions.some((motion) => motion.clip_index === index)
      || (settings?.smart_framing === "face" && settings.visual_profiles?.some((profile) => profile.clip_index === index))
      || settings?.product_profiles?.some((profile) => profile.clip_index === index);
    const hasLayerConflict = settings?.layers.some((layer) => layer.start < endAt && layer.end > at);
    return clip.media_kind === "video" && clip.duration >= 1 && clip.duration <= 8 && !hasCameraConflict && !hasLayerConflict
      ? [{ clipIndex: index, at, endAt, name: clip.source_name, duration: clip.duration }]
      : [];
  });
  function effectEligibility(preset: VisualEffectPreset): EffectEligibility {
    if (preset === "paper_tear") return clipBoundaries.length
      ? { status: "ready", label: "Ready", reason: `${clipBoundaries.length} ordinary cut${clipBoundaries.length === 1 ? "" : "s"} available.` }
      : { status: "blocked", label: "Unavailable", reason: "Needs two clips joined by an ordinary cut and at least 0.4 seconds in the incoming clip." };
    if (preset === "dolly_zoom") return dollyClips.length
      ? { status: "ready", label: "Ready", reason: `${dollyClips.length} stable video clip${dollyClips.length === 1 ? "" : "s"} available.` }
      : { status: "blocked", label: "Unavailable", reason: "Needs a complete 1–8 second video clip without another camera move, tracked crop or picture layer." };
    if (preset === "rack_focus") return {
      status: "review", label: "Check shot", reason: "You must confirm the shot is stable and choose two clear focus targets.",
    };
    if (preset === "live_cursor") return {
      status: "review", label: "Place target", reason: "You must place the start and end points; the server does not track the target.",
    };
    if (sourceBackedTextEffects.includes(preset)) return {
      status: "review", label: "Check wording", reason: "You must supply wording that is genuinely supported by the footage.",
    };
    if (preset === "voice_note") return {
      status: "review", label: "Check speech", reason: "Confirm the chosen range contains the recorded speech this card represents.",
    };
    return { status: "ready", label: "Ready", reason: "This effect can be configured for the current cut." };
  }
  function selectEffect(preset: VisualEffectPreset) {
    const definition = inspection?.effect_registry.effects.find(
      (effect) => effect.preset === preset,
    );
    setVisualBeat(preset);
    setVisualBeatIntensity(
      (definition?.parameters.find((parameter) => parameter.key === "intensity")
        ?.default ?? "standard") as VisualEffectIntensity,
    );
    setVisualBeatPosition(
      (definition?.parameters.find((parameter) => parameter.key === "position")
        ?.default ?? "center") as VisualEffectPosition,
    );
    const value = (key: string, fallback: number) =>
      definition?.parameters.find((parameter) => parameter.key === key)?.default ?? fallback;
    setCursorStartX(String(value("cursor_start_x", 0.25)));
    setCursorStartY(String(value("cursor_start_y", 0.4)));
    setCursorEndX(String(value("cursor_end_x", 0.75)));
    setCursorEndY(String(value("cursor_end_y", 0.4)));
    setCursorClick(Boolean(value("click", 1)));
    setLetterText(String(
      definition?.parameters.find((parameter) => parameter.key === "letter_text")?.default ?? "",
    ));
    setCommentText(String(
      definition?.parameters.find((parameter) => parameter.key === "comment_text")?.default ?? "",
    ));
    const postDefaults = definition?.parameters.find((parameter) => parameter.key === "post_texts")?.default;
    setPostTexts(Array.isArray(postDefaults) ? [postDefaults[0] ?? "", postDefaults[1] ?? "", postDefaults[2] ?? ""] : ["", "", ""]);
    setSketchText(String(
      definition?.parameters.find((parameter) => parameter.key === "sketch_text")?.default ?? "",
    ));
    setFocusStartX(String(value("focus_start_x", 0.35)));
    setFocusStartY(String(value("focus_start_y", 0.35)));
    setFocusEndX(String(value("focus_end_x", 0.65)));
    setFocusEndY(String(value("focus_end_y", 0.55)));
    setTearDirection(
      (definition?.parameters.find((parameter) => parameter.key === "tear_direction")?.default ?? "left") as "left" | "right",
    );
    setDollyDirection(
      (definition?.parameters.find((parameter) => parameter.key === "dolly_direction")?.default ?? "push_in") as "push_in" | "pull_out",
    );
    setDollyAnchorX(String(value("dolly_anchor_x", 0.5)));
    setDollyAnchorY(String(value("dolly_anchor_y", 0.5)));
    const duration = definition?.default_duration_seconds ?? (preset === "impact_frame" ? 0.2 : 2);
    if (preset === "paper_tear" && clipBoundaries[0]) {
      setTearBoundaryIndex(clipBoundaries[0].boundaryIndex);
      setStart(String(Number(clipBoundaries[0].at.toFixed(3))));
      setEnd(String(Number((clipBoundaries[0].at + Math.min(duration, clipBoundaries[0].incomingDuration)).toFixed(3))));
    } else if (preset === "dolly_zoom" && dollyClips[0]) {
      setDollyClipIndex(dollyClips[0].clipIndex);
      setStart(String(Number(dollyClips[0].at.toFixed(3))));
      setEnd(String(Number(dollyClips[0].endAt.toFixed(3))));
    } else {
      setEnd(String(Number(start) + duration));
    }
  }
  useEffect(() => {
    let active = true;
    getFinishingTools(jobId)
      .then((value) => {
        if (active) {
          setInspection(value);
          setMusicStart(String(value.settings.music_start_seconds));
          setDenoise(value.settings.voice_denoise);
          setSourceId(value.sources[0]?.asset_id ?? "");
        }
      })
      .catch((e: unknown) => {
        if (active)
          setError(
            e instanceof Error ? e.message : "Tools could not be loaded",
          );
      });
    return () => {
      active = false;
    };
  }, [jobId]);
  async function apply(settings: FinishingTools) {
    setBusy(true);
    setError("");
    try {
      await requestRevision(jobId, {
        note: "",
        captionCorrections: [],
        baseVersion: version,
        finishingSettings: settings,
      });
      onUpdated();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not apply tools");
    } finally {
      setBusy(false);
    }
  }
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!inspection) return;
    let next: FinishingTools = {
      ...inspection.settings,
      voice_denoise: denoise,
    };
    if (tool === "join")
      next = {
        ...next,
        audio_joins: [
          ...(next.audio_joins ?? []).filter((j) => j.clip_index !== clipIndex),
          {
            clip_index: clipIndex,
            lead_seconds: Number(lead),
            tail_seconds: Number(tail),
          },
        ],
      };
    if (tool === "motion")
      next = {
        ...next,
        motions: [
          ...next.motions.filter((m) => m.clip_index !== clipIndex),
          {
            clip_index: clipIndex,
            points: [
              { time: 0, zoom: 1, x: Number(anchorX), y: Number(anchorY) },
              {
                time: Math.max(0.1, (clips[clipIndex]?.duration ?? 1) - 0.01),
                zoom: Number(zoom),
                x: Number(anchorX),
                y: Number(anchorY),
              },
            ],
          },
        ],
      };
    if (tool === "colour")
      next = {
        ...next,
        colours: [
          ...next.colours.filter((c) => c.clip_index !== clipIndex),
          {
            clip_index: clipIndex,
            saturation: Number(saturation),
            gamma: Number(gamma),
          },
        ],
      };
    if (tool === "audio")
      next = {
        ...next,
        audio_regions: [
          ...next.audio_regions.filter(
            (r) => r.start !== Number(start) || r.end !== Number(end),
          ),
          { start: Number(start), end: Number(end), gain_db: Number(gain) },
        ],
      };
    if (tool === "captions")
      next = {
        ...next,
        caption_regions: [
          ...next.caption_regions.filter(
            (r) => r.start !== Number(start) || r.end !== Number(end),
          ),
          { start: Number(start), end: Number(end), position },
        ],
      };
    if (tool === "music")
      next = { ...next, music_start_seconds: Number(musicStart) };
    if (tool === "layer") {
      const source = inspection.sources.find((s) => s.asset_id === sourceId);
      if (!source) return;
      next = {
        ...next,
        layers: [
          ...next.layers,
          {
            asset_id: sourceId,
            media_kind: source.media_kind,
            source_in: source.media_kind === "image" ? 0 : Number(sourceIn),
            start: Number(start),
            end: Number(end),
            width: Number(width),
            x: Number(anchorX),
            y: Number(anchorY),
            shape,
            animation,
            chroma_color: keyColor || null,
            playback_rate: source.media_kind === "image" ? 1 : Number(rate),
            freeze: source.media_kind === "video" && freeze,
          },
        ],
      };
    }
    const window = { start: Number(start), end: Number(end) };
    const outside = (r: { start: number; end: number }) =>
      r.end <= window.start || r.start >= window.end;
    if (tool === "callout")
      next = {
        ...next,
        callouts: [
          ...(next.callouts ?? []).filter(outside),
          {
            ...window,
            text: callout,
            style: calloutStyle,
            position: "upper",
            animation: "pop",
          },
        ],
      };
    if (tool === "pointer")
      next = {
        ...next,
        pointers: [
          ...(next.pointers ?? []).filter(outside),
          {
            ...window,
            x: Number(anchorX),
            y: Number(anchorY),
            size: 0.14,
            shape: pointerShape,
            direction: pointerDirection,
          },
        ],
      };
    if (tool === "visual_beat") {
      const effect: NonNullable<FinishingTools["visual_beats"]>[number] = {
        ...window,
        preset: visualBeat,
        intensity: visualBeatIntensity,
        ...(positionParameter ? { position: visualBeatPosition } : {}),
        ...(visualBeat === "live_cursor"
          ? {
              cursor_start_x: Number(cursorStartX),
              cursor_start_y: Number(cursorStartY),
              cursor_end_x: Number(cursorEndX),
              cursor_end_y: Number(cursorEndY),
              click: cursorClick,
            }
          : {}),
        ...(visualBeat === "letter_dive" ? { letter_text: letterText.trim() } : {}),
        ...(visualBeat === "comment_drop" ? { comment_text: commentText.trim() } : {}),
        ...(visualBeat === "post_wall" ? { post_texts: postTexts.map((text) => text.trim()).filter(Boolean) } : {}),
        ...(visualBeat === "sketch_words" ? { sketch_text: sketchText.trim() } : {}),
        ...(visualBeat === "rack_focus"
          ? {
              focus_start_x: Number(focusStartX),
              focus_start_y: Number(focusStartY),
              focus_end_x: Number(focusEndX),
              focus_end_y: Number(focusEndY),
            }
          : {}),
        ...(visualBeat === "paper_tear"
          ? { boundary_index: tearBoundaryIndex, tear_direction: tearDirection }
          : {}),
        ...(visualBeat === "dolly_zoom"
          ? {
              dolly_clip_index: dollyClipIndex,
              dolly_direction: dollyDirection,
              dolly_anchor_x: Number(dollyAnchorX),
              dolly_anchor_y: Number(dollyAnchorY),
            }
          : {}),
      };
      next = {
        ...next,
        visual_beats: [
          ...(next.visual_beats ?? []).filter(outside),
          effect,
        ],
      };
    }
    if (tool === "music_pause")
      next = {
        ...next,
        music_regions: [
          ...(next.music_regions ?? []).filter(outside),
          { ...window, gain_db: -60 },
        ],
      };
    await apply(next);
  }
  async function restoreVersion() {
    setBusy(true);
    setError("");
    try {
      await requestRevision(jobId, {
        note: "",
        captionCorrections: [],
        baseVersion: version,
        restoreVersion: Number(restore),
      });
      onUpdated();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not restore version");
    } finally {
      setBusy(false);
    }
  }
  const regions = inspection?.settings;
  return (
    <div className="space-y-4 pt-4">
      <p className="text-xs leading-5 text-[#666862]">
        Changes create a new preview using this cut and zero additional model
        tokens. Times below refer to the finished reel, except source in. New
        layers are silent; the story audio continues.
      </p>
      {error ? (
        <p
          role="alert"
          className="rounded-md bg-[#FFF0EC] p-3 text-sm text-[#A23B2A]"
        >
          {error}
        </p>
      ) : null}
      {!inspection ? (
        <p>Loading tools…</p>
      ) : inspection.version !== version ? (
        <p className="text-sm text-[#A23B2A]">
          A newer preview is available. Refresh this page before editing.
        </p>
      ) : (
        <>
          <form className="space-y-4" onSubmit={submit}>
            <fieldset>
              <legend className="text-xs font-bold text-[#173F5F]">What do you want to adjust?</legend>
              <div className="mt-2 grid grid-cols-2 gap-2">
                {taskGroups.map((group) => (
                  <button
                    aria-pressed={taskGroup === group.id}
                    className={`min-h-16 rounded-md border p-3 text-left ${taskGroup === group.id ? "border-[#173F5F] bg-[#EFF6FA]" : "border-[#D7D9D3] bg-white"}`}
                    key={group.id}
                    onClick={() => {
                      setTaskGroup(group.id);
                      const first = group.tools[0];
                      setTool(first);
                      if (first === "visual_beat") selectEffect(visualBeat);
                    }}
                    type="button"
                  >
                    <span className="block text-xs font-bold text-[#173F5F]">{group.label}</span>
                    <span className="mt-1 block text-[11px] leading-4 text-[#666862]">{group.summary}</span>
                  </button>
                ))}
              </div>
            </fieldset>
            <label className="block text-xs font-bold">
              Adjustment
              <select
                className={control}
                value={tool}
                onChange={(e) => {
                  const selected = e.currentTarget.value as Tool;
                  setTool(selected);
                  const parent = taskGroups.find((group) => group.tools.includes(selected));
                  if (parent) setTaskGroup(parent.id);
                  if (selected === "visual_beat") selectEffect(visualBeat);
                }}
              >
                {taskGroups.map((group) => (
                  <optgroup key={group.id} label={group.label}>
                    {group.tools.map((value) => <option key={value} value={value}>{toolLabels[value]}</option>)}
                  </optgroup>
                ))}
              </select>
            </label>
            {tool === "motion" || tool === "colour" || tool === "join" ? (
              <label className="block text-xs">
                Clip
                <select
                  className={control}
                  value={clipIndex}
                  onChange={(e) => setClipIndex(Number(e.currentTarget.value))}
                >
                  {clips.map((clip, i) => (
                    <option value={i} key={clip.clip_id || i}>
                      {i + 1}. {clip.source_name}
                    </option>
                  ))}
                </select>
              </label>
            ) : null}
            {[
              "audio",
              "captions",
              "layer",
              "callout",
              "pointer",
              "music_pause",
              "visual_beat",
            ].includes(tool) ? (
              <div className="grid grid-cols-2 gap-3">
                <label className="text-xs">
                  Reel start seconds
                  <input
                    className={control}
                    min={0}
                    max={120}
                    step="0.01"
                    type="number"
                    required
                    value={start}
                    readOnly={tool === "visual_beat" && (visualBeat === "paper_tear" || visualBeat === "dolly_zoom")}
                    onChange={(e) => setStart(e.currentTarget.value)}
                  />
                </label>
                <label className="text-xs">
                  Reel end seconds
                  <input
                    className={control}
                    min={0.01}
                    max={120}
                    step="0.01"
                    type="number"
                    required
                    value={end}
                    readOnly={tool === "visual_beat" && visualBeat === "dolly_zoom"}
                    onChange={(e) => setEnd(e.currentTarget.value)}
                  />
                </label>
              </div>
            ) : null}
            {tool === "join" ? (
              <div className="space-y-3">
                <p className="text-xs leading-5 text-[#666862]">
                  Start this clip&apos;s recorded audio before its picture
                  (J-cut), or let it continue after the picture changes (L-cut).
                  Existing speech at the neighbouring boundary must stay clear.
                  Captions follow the audible source range. Clear these joins
                  before trimming the timeline.
                </p>
                <div className="grid grid-cols-2 gap-3">
                  <label className="text-xs">
                    Audio lead seconds
                    <input
                      className={control}
                      min={0}
                      max={1}
                      step="0.05"
                      type="number"
                      value={lead}
                      onChange={(e) => setLead(e.currentTarget.value)}
                    />
                  </label>
                  <label className="text-xs">
                    Audio tail seconds
                    <input
                      className={control}
                      min={0}
                      max={1}
                      step="0.05"
                      type="number"
                      value={tail}
                      onChange={(e) => setTail(e.currentTarget.value)}
                    />
                  </label>
                </div>
              </div>
            ) : null}
            {tool === "motion" ? (
              <label className="block text-xs">
                Ending zoom · 1.0–1.35
                <input
                  className={control}
                  min={1}
                  max={1.35}
                  step="0.01"
                  required
                  type="number"
                  value={zoom}
                  onChange={(e) => setZoom(e.currentTarget.value)}
                />
              </label>
            ) : null}
            {tool === "motion" || tool === "layer" || tool === "pointer" ? (
              <div className="grid grid-cols-2 gap-3">
                <label className="text-xs">
                  Horizontal anchor · 0 left / 1 right
                  <input
                    className={control}
                    min={0}
                    max={1}
                    step="0.05"
                    required
                    type="number"
                    value={anchorX}
                    onChange={(e) => setAnchorX(e.currentTarget.value)}
                  />
                </label>
                <label className="text-xs">
                  Vertical anchor · 0 top / 1 bottom
                  <input
                    className={control}
                    min={0}
                    max={1}
                    step="0.05"
                    required
                    type="number"
                    value={anchorY}
                    onChange={(e) => setAnchorY(e.currentTarget.value)}
                  />
                </label>
              </div>
            ) : null}
            {tool === "audio" ? (
              <label className="block text-xs">
                Voice adjustment · dB
                <input
                  className={control}
                  min={-12}
                  max={12}
                  step="0.5"
                  required
                  type="number"
                  value={gain}
                  onChange={(e) => setGain(e.currentTarget.value)}
                />
              </label>
            ) : null}
            {tool === "captions" ? (
              <label className="block text-xs">
                Caption position
                <select
                  className={control}
                  value={position}
                  onChange={(e) =>
                    setPosition(e.currentTarget.value as typeof position)
                  }
                >
                  <option value="lower_safe">Lower safe area</option>
                  <option value="middle">Middle</option>
                  <option value="upper">Upper</option>
                  <option value="hidden">Hide during this range</option>
                </select>
              </label>
            ) : null}
            {tool === "callout" ? (
              <div className="space-y-3">
                <label className="block text-xs">
                  Callout text
                  <input
                    className={control}
                    maxLength={64}
                    required
                    value={callout}
                    onChange={(e) => setCallout(e.target.value)}
                    placeholder="A short label or 2 / 5"
                  />
                </label>
                <label className="block text-xs">
                  Style
                  <select
                    className={control}
                    value={calloutStyle}
                    onChange={(e) =>
                      setCalloutStyle(e.target.value as typeof calloutStyle)
                    }
                  >
                    <option value="label">Label</option>
                    <option value="headline">Bold headline</option>
                    <option value="comment">Comment card</option>
                    <option value="thought">Thought</option>
                    <option value="counter">Counter</option>
                  </select>
                </label>
                <p className="text-xs text-[#666862]">
                  Appears in the upper safe area. Keep factual labels faithful
                  to the footage; no subtitle commands. Maximum eight seconds.
                </p>
              </div>
            ) : null}
            {tool === "visual_beat" ? (
              <div className="space-y-3">
                <section
                  aria-labelledby="effect-gallery-heading"
                  className="space-y-4 rounded-md border border-[#D7D9D3] bg-[#F7F7F5] p-3"
                >
                  <div>
                    <h3 id="effect-gallery-heading" className="text-sm font-bold text-[#173F5F]">
                      Effect gallery
                    </h3>
                    <p className="mt-1 text-xs leading-5 text-[#666862]">
                      Browse freely. Choosing a card only changes these controls; no preview is created until you submit.
                    </p>
                  </div>
                  {effectGalleryGroups.map((group) => {
                    const effects = inspection.effect_registry.effects.filter((effect) =>
                      group.categories.some((category) => category === effect.category),
                    );
                    return effects.length ? (
                      <div className="space-y-2" key={group.label}>
                        <h4 className="text-[11px] font-bold uppercase tracking-[0.12em] text-[#666862]">
                          {group.label}
                        </h4>
                        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                          {effects.map((effect) => {
                            const eligibility = effectEligibility(effect.preset);
                            const selected = effect.preset === visualBeat;
                            const statusClass = eligibility.status === "ready"
                              ? "bg-[#E8F4ED] text-[#286A49]"
                              : eligibility.status === "review"
                                ? "bg-[#FFF6D8] text-[#6F5710]"
                                : "bg-[#FFF0EC] text-[#A23B2A]";
                            return (
                              <button
                                aria-pressed={selected}
                                className={`min-h-11 rounded-md border p-3 text-left focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#173F5F] ${selected ? "border-[#173F5F] bg-[#BFE3FF]" : "border-[#D7D9D3] bg-white"}`}
                                data-effect-card={effect.preset}
                                key={effect.preset}
                                onClick={() => selectEffect(effect.preset)}
                                type="button"
                              >
                                <span className="flex items-start justify-between gap-2">
                                  <span className="text-sm font-bold text-[#20211F]">{effect.label}</span>
                                  <span className={`shrink-0 rounded px-2 py-1 text-[10px] font-bold ${statusClass}`}>
                                    {eligibility.label}
                                  </span>
                                </span>
                                <span className="mt-2 block text-xs leading-5 text-[#666862]">
                                  {effect.summary}
                                </span>
                                <span className="mt-2 block text-[11px] leading-4 text-[#20211F]">
                                  {eligibility.reason}
                                </span>
                              </button>
                            );
                          })}
                        </div>
                      </div>
                    ) : null;
                  })}
                </section>
                <label className="block text-xs">
                  Quick selector
                  <select
                    className={control}
                    value={visualBeat}
                    onChange={(e) => selectEffect(e.currentTarget.value as VisualEffectPreset)}
                  >
                    {inspection.effect_registry.effects.map((effect) => (
                      <option value={effect.preset} key={effect.preset}>
                        {effect.label}
                      </option>
                    ))}
                  </select>
                </label>
                {effectDefinition ? (
                  <section className="space-y-3 rounded-md border border-[#D7D9D3] bg-white p-3" aria-label={`${effectDefinition.label} guidance`}>
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <h3 className="text-sm font-bold text-[#173F5F]">{effectDefinition.label}</h3>
                        <p className="mt-1 text-xs leading-5 text-[#666862]">
                          {effectDefinition.summary} Use for {effectDefinition.minimum_duration_seconds}–{effectDefinition.maximum_duration_seconds} seconds.
                        </p>
                      </div>
                      <span className="shrink-0 rounded bg-[#F7F7F5] px-2 py-1 text-[10px] font-bold text-[#666862]">
                        Registry v{inspection.effect_registry.version}
                      </span>
                    </div>
                    <dl className="grid gap-2 text-xs sm:grid-cols-2">
                      <div className="rounded-md bg-[#E8F4ED] p-2">
                        <dt className="font-bold text-[#286A49]">Best for</dt>
                        <dd className="mt-1 leading-5 text-[#20211F]">{effectDefinition.best_for}</dd>
                      </div>
                      <div className="rounded-md bg-[#FFF6D8] p-2">
                        <dt className="font-bold text-[#6F5710]">Avoid when</dt>
                        <dd className="mt-1 leading-5 text-[#20211F]">{effectDefinition.avoid_when}</dd>
                      </div>
                    </dl>
                    <div className="rounded-md bg-[#F7F7F5] p-2 text-xs">
                      <p className="font-bold text-[#20211F]">After preview, check</p>
                      <ul className="mt-1 list-disc space-y-1 pl-4 leading-5 text-[#666862]">
                        {effectChecklist(visualBeat).map((item) => <li key={item}>{item}</li>)}
                      </ul>
                    </div>
                    <p className="text-xs leading-5 text-[#666862]">
                      Recorded speech keeps its timing and dialogue captions stay above the effect.
                    </p>
                  </section>
                ) : null}
                <div className="grid grid-cols-2 gap-3">
                  {intensityParameter ? (
                    <label className="text-xs">
                      {intensityParameter.label}
                      <select className={control} value={visualBeatIntensity} onChange={(e) => setVisualBeatIntensity(e.currentTarget.value as VisualEffectIntensity)}>
                        {intensityParameter.values?.map((value) => <option value={value} key={value}>{value}</option>)}
                      </select>
                    </label>
                  ) : null}
                  {positionParameter ? (
                    <label className="text-xs">
                      {positionParameter.label}
                      <select className={control} value={visualBeatPosition} onChange={(e) => setVisualBeatPosition(e.currentTarget.value as VisualEffectPosition)}>
                        {positionParameter.values?.map((value) => <option value={value} key={value}>{value}</option>)}
                      </select>
                    </label>
                  ) : null}
                </div>
                {visualBeat === "live_cursor" ? (
                  <div className="space-y-3 rounded-md border border-[#D7D9D3] p-3">
                    <p className="text-xs leading-5 text-[#666862]">
                      Coordinates are fractions of the frame. The first point moves to the second; this does not track an object automatically.
                    </p>
                    <div className="grid grid-cols-2 gap-3">
                      {cursorParameters.map((parameter) => {
                        const state = parameter.key === "cursor_start_x"
                          ? [cursorStartX, setCursorStartX] as const
                          : parameter.key === "cursor_start_y"
                            ? [cursorStartY, setCursorStartY] as const
                            : parameter.key === "cursor_end_x"
                              ? [cursorEndX, setCursorEndX] as const
                              : parameter.key === "cursor_end_y"
                                ? [cursorEndY, setCursorEndY] as const
                                : undefined;
                        return state ? (
                          <label className="text-xs" key={parameter.key}>
                            {parameter.label}
                            <input className={control} min={parameter.minimum} max={parameter.maximum} step="0.01" type="number" required value={state[0]} onChange={(event) => state[1](event.currentTarget.value)} />
                          </label>
                        ) : null;
                      })}
                    </div>
                    <label className="flex min-h-11 items-center gap-2 text-xs">
                      <input type="checkbox" checked={cursorClick} onChange={(event) => setCursorClick(event.currentTarget.checked)} />
                      Show a click pulse at the destination
                    </label>
                  </div>
                ) : null}
                {visualBeat === "rack_focus" ? (
                  <div className="space-y-3 rounded-md border border-[#D7D9D3] p-3">
                    <p className="text-xs leading-5 text-[#666862]">
                      Coordinates are fractions of the frame. A sharp window moves from the first point to the second while the surrounding picture softens. This is a simulated focus pull: it does not detect depth or track a subject, so use a stable shot with clear targets.
                    </p>
                    <div className="grid grid-cols-2 gap-3">
                      {focusParameters.map((parameter) => {
                        const state = parameter.key === "focus_start_x"
                          ? [focusStartX, setFocusStartX] as const
                          : parameter.key === "focus_start_y"
                            ? [focusStartY, setFocusStartY] as const
                            : parameter.key === "focus_end_x"
                              ? [focusEndX, setFocusEndX] as const
                              : parameter.key === "focus_end_y"
                                ? [focusEndY, setFocusEndY] as const
                                : undefined;
                        return state ? (
                          <label className="text-xs" key={parameter.key}>
                            {parameter.label}
                            <input className={control} min={parameter.minimum} max={parameter.maximum} step="0.01" type="number" required value={state[0]} onChange={(event) => state[1](event.currentTarget.value)} />
                          </label>
                        ) : null;
                      })}
                    </div>
                  </div>
                ) : null}
                {visualBeat === "paper_tear" ? (
                  <div className="space-y-3 rounded-md border border-[#D7D9D3] p-3">
                    <p className="text-xs leading-5 text-[#666862]">
                      Paper Tear starts exactly at a saved cut. It freezes the final outgoing frame into staggered strips and reveals the real incoming clip underneath. Recorded audio continues unchanged. Changing the cut later removes this transition for safety.
                    </p>
                    {clipBoundaries.length ? (
                      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                        <label className="text-xs">
                          Clip boundary
                          <select
                            className={control}
                            value={tearBoundaryIndex}
                            onChange={(event) => {
                              const boundaryIndex = Number(event.currentTarget.value);
                              const boundary = clipBoundaries.find((item) => item.boundaryIndex === boundaryIndex);
                              setTearBoundaryIndex(boundaryIndex);
                              if (boundary) {
                                const duration = Math.min(effectDefinition?.default_duration_seconds ?? 0.7, boundary.incomingDuration);
                                setStart(String(Number(boundary.at.toFixed(3))));
                                setEnd(String(Number((boundary.at + duration).toFixed(3))));
                              }
                            }}
                          >
                            {clipBoundaries.map((boundary) => (
                              <option value={boundary.boundaryIndex} key={boundary.boundaryIndex}>
                                After clip {boundary.boundaryIndex} · {boundary.outgoing} → {boundary.incoming} · {boundary.at.toFixed(2)}s
                              </option>
                            ))}
                          </select>
                        </label>
                        <label className="text-xs">
                          Pull direction
                          <select className={control} value={tearDirection} onChange={(event) => setTearDirection(event.currentTarget.value as "left" | "right")}>
                            <option value="left">Pull outgoing picture left</option>
                            <option value="right">Pull outgoing picture right</option>
                          </select>
                        </label>
                      </div>
                    ) : (
                      <p className="text-xs font-bold text-[#A23B2A]">Paper Tear needs two clips joined by an ordinary cut, with at least 0.4 seconds in the incoming clip.</p>
                    )}
                  </div>
                ) : null}
                {visualBeat === "dolly_zoom" ? (
                  <div className="space-y-3 rounded-md border border-[#D7D9D3] p-3">
                    <p className="text-xs leading-5 text-[#666862]">
                      This is a crop-and-scale illusion over one complete stable video clip. It cannot reproduce real camera parallax, reconstruct depth or lock a subject automatically. Choose an anchor that remains visible throughout the shot; later timeline changes remove the effect for safety.
                    </p>
                    {dollyClips.length ? (
                      <div className="grid grid-cols-2 gap-3">
                        <label className="col-span-2 text-xs">
                          Stable video clip
                          <select className={control} value={dollyClipIndex} onChange={(event) => {
                            const clipIndex = Number(event.currentTarget.value);
                            const selected = dollyClips.find((item) => item.clipIndex === clipIndex);
                            setDollyClipIndex(clipIndex);
                            if (selected) {
                              setStart(String(Number(selected.at.toFixed(3))));
                              setEnd(String(Number(selected.endAt.toFixed(3))));
                            }
                          }}>
                            {dollyClips.map((clip) => <option value={clip.clipIndex} key={clip.clipIndex}>Clip {clip.clipIndex + 1} · {clip.name} · {clip.duration.toFixed(2)}s</option>)}
                          </select>
                        </label>
                        <label className="text-xs">
                          Move
                          <select className={control} value={dollyDirection} onChange={(event) => setDollyDirection(event.currentTarget.value as "push_in" | "pull_out")}>
                            <option value="push_in">Push in</option>
                            <option value="pull_out">Pull out</option>
                          </select>
                        </label>
                        <span />
                        <label className="text-xs">
                          Horizontal anchor
                          <input className={control} min={0.3} max={0.7} step="0.01" type="number" required value={dollyAnchorX} onChange={(event) => setDollyAnchorX(event.currentTarget.value)} />
                        </label>
                        <label className="text-xs">
                          Vertical anchor
                          <input className={control} min={0.25} max={0.75} step="0.01" type="number" required value={dollyAnchorY} onChange={(event) => setDollyAnchorY(event.currentTarget.value)} />
                        </label>
                      </div>
                    ) : (
                      <p className="text-xs font-bold text-[#A23B2A]">Dolly Zoom needs a 1–8 second video clip without another camera move, tracked crop or overlapping picture layer.</p>
                    )}
                  </div>
                ) : null}
                {visualBeat === "letter_dive" ? (
                  <label className="block text-xs">
                    Short source-backed text
                    <input
                      className={control}
                      type="text"
                      required
                      minLength={1}
                      maxLength={effectDefinition?.parameters.find((parameter) => parameter.key === "letter_text")?.maximum_length ?? 18}
                      value={letterText}
                      onChange={(event) => setLetterText(event.currentTarget.value)}
                      placeholder="A word from the footage"
                    />
                    <span className="mt-1 block leading-5 text-[#666862]">
                      Use a genuine word or short phrase from the footage. Letters drop in individually; dialogue captions remain above it.
                    </span>
                  </label>
                ) : null}
                {visualBeat === "comment_drop" ? (
                  <label className="block text-xs">
                    Short source-backed comment
                    <input
                      className={control}
                      type="text"
                      required
                      minLength={1}
                      maxLength={effectDefinition?.parameters.find((parameter) => parameter.key === "comment_text")?.maximum_length ?? 48}
                      value={commentText}
                      onChange={(event) => setCommentText(event.currentTarget.value)}
                      placeholder="A comment supported by the footage"
                    />
                    <span className="mt-1 block leading-5 text-[#666862]">
                      Uses the existing caption-aware comment card. Strength changes its entrance; it never replaces dialogue captions.
                    </span>
                  </label>
                ) : null}
                {visualBeat === "voice_note" ? (
                  <p className="rounded-md border border-[#D7D9D3] p-3 text-xs leading-5 text-[#666862]">
                    Draws a voice-message card with a play icon, animated waveform, progress marker and the real window duration. It uses the existing recorded speech, does not generate audio or identify a sender, and moves away from active dialogue captions.
                  </p>
                ) : null}
                {visualBeat === "post_wall" ? (
                  <fieldset className="space-y-3 rounded-md border border-[#D7D9D3] p-3">
                    <legend className="px-1 text-xs font-bold">Source-backed idea cards</legend>
                    {postTexts.map((text, index) => (
                      <label className="block text-xs" key={index}>
                        Card {index + 1}{index === 2 ? " · optional" : ""}
                        <input
                          className={control}
                          type="text"
                          required={index < 2}
                          minLength={index < 2 ? 1 : undefined}
                          maxLength={effectDefinition?.parameters.find((parameter) => parameter.key === "post_texts")?.item_maximum_length ?? 42}
                          value={text}
                          onChange={(event) => {
                            const nextValue = event.currentTarget.value;
                            setPostTexts((current) => current.map((value, itemIndex) => itemIndex === index ? nextValue : value));
                          }}
                          placeholder="A phrase supported by the footage"
                        />
                      </label>
                    ))}
                    <p className="text-xs leading-5 text-[#666862]">
                      Builds a staggered wall of two or three cards. Use real phrases or faithful summaries only; no usernames, likes, shares or invented social posts.
                    </p>
                  </fieldset>
                ) : null}
                {visualBeat === "sketch_words" ? (
                  <label className="block text-xs">
                    One to three source-backed words
                    <input
                      className={control}
                      type="text"
                      required
                      minLength={1}
                      maxLength={effectDefinition?.parameters.find((parameter) => parameter.key === "sketch_text")?.maximum_length ?? 24}
                      value={sketchText}
                      onChange={(event) => setSketchText(event.currentTarget.value)}
                      placeholder="Words supported by the footage"
                    />
                    <span className="mt-1 block leading-5 text-[#666862]">
                      Words draw on separately with marker-like lettering and accent strokes. Use genuine wording only; dialogue captions remain above the sketch.
                    </span>
                  </label>
                ) : null}
              </div>
            ) : null}
            {tool === "pointer" ? (
              <div className="grid grid-cols-2 gap-3">
                <label className="text-xs">
                  Shape
                  <select
                    className={control}
                    value={pointerShape}
                    onChange={(e) =>
                      setPointerShape(e.target.value as typeof pointerShape)
                    }
                  >
                    <option value="circle">Circle</option>
                    <option value="arrow">Arrow</option>
                  </select>
                </label>
                <label className="text-xs">
                  Direction
                  <select
                    className={control}
                    value={pointerDirection}
                    onChange={(e) =>
                      setPointerDirection(
                        e.target.value as typeof pointerDirection,
                      )
                    }
                  >
                    {["right", "left", "up", "down"].map((value) => (
                      <option key={value} value={value}>
                        {value}
                      </option>
                    ))}
                  </select>
                </label>
                <p className="col-span-2 text-xs text-[#666862]">
                  Fixed position in the frame; this pointer does not follow
                  moving objects. Maximum eight seconds.
                </p>
              </div>
            ) : null}
            {tool === "music_pause" ? (
              <p className="text-xs text-[#666862]">
                Fades the selected music down for this interval, then restores
                it. Dialogue keeps playing normally. Requires a music track;
                maximum eight seconds.
              </p>
            ) : null}
            {tool === "colour" ? (
              <div className="grid grid-cols-2 gap-3">
                <label className="text-xs">
                  Saturation
                  <input
                    className={control}
                    min={0.5}
                    max={1.5}
                    step="0.05"
                    required
                    type="number"
                    value={saturation}
                    onChange={(e) => setSaturation(e.currentTarget.value)}
                  />
                </label>
                <label className="text-xs">
                  Gamma
                  <input
                    className={control}
                    min={0.8}
                    max={1.2}
                    step="0.05"
                    required
                    type="number"
                    value={gamma}
                    onChange={(e) => setGamma(e.currentTarget.value)}
                  />
                </label>
              </div>
            ) : null}
            {tool === "music" ? (
              <label className="block text-xs">
                Start inside selected track · seconds
                <input
                  className={control}
                  min={0}
                  step="0.1"
                  required
                  type="number"
                  value={musicStart}
                  onChange={(e) => setMusicStart(e.currentTarget.value)}
                />
                <span className="mt-2 block leading-5 text-[#666862]">
                  Uses the job&apos;s licensed track and current mix. Short
                  tracks loop; this does not select or enable new music.
                </span>
              </label>
            ) : null}
            {tool === "layer" ? (
              <div className="space-y-3">
                <label className="block text-xs">
                  Attached source
                  <select
                    className={control}
                    value={sourceId}
                    required
                    onChange={(e) => setSourceId(e.currentTarget.value)}
                  >
                    {inspection.sources.map((s) => (
                      <option value={s.asset_id} key={s.asset_id}>
                        {s.name} · {s.media_kind}
                      </option>
                    ))}
                  </select>
                </label>
                <div className="grid grid-cols-2 gap-3">
                  <label className="text-xs">
                    Source in seconds
                    <input
                      className={control}
                      min={0}
                      step="0.01"
                      required
                      type="number"
                      value={sourceIn}
                      onChange={(e) => setSourceIn(e.currentTarget.value)}
                    />
                  </label>
                  <label className="text-xs">
                    Width · fraction of frame
                    <input
                      className={control}
                      min={0.1}
                      max={1}
                      step="0.05"
                      required
                      type="number"
                      value={width}
                      onChange={(e) => setWidth(e.currentTarget.value)}
                    />
                  </label>
                  <label className="text-xs">
                    Shape
                    <select
                      className={control}
                      value={shape}
                      onChange={(e) =>
                        setShape(e.currentTarget.value as typeof shape)
                      }
                    >
                      <option value="rectangle">Contained rectangle</option>
                      <option value="circle">Circle crop</option>
                    </select>
                  </label>
                  <label className="text-xs">
                    Entrance
                    <select
                      className={control}
                      value={animation}
                      onChange={(e) =>
                        setAnimation(e.currentTarget.value as typeof animation)
                      }
                    >
                      <option value="fade">Fade</option>
                      <option value="slide_up">Slide up</option>
                      <option value="none">Cut</option>
                    </select>
                  </label>
                  <label className="text-xs">
                    Remove background colour
                    <select
                      className={control}
                      value={keyColor}
                      onChange={(e) => setKeyColor(e.currentTarget.value)}
                    >
                      <option value="">Keep source background</option>
                      <option value="#00FF00">Green screen</option>
                      <option value="#0000FF">Blue screen</option>
                    </select>
                  </label>
                  <label className="text-xs">
                    Video playback rate
                    <input
                      className={control}
                      min={0.25}
                      max={4}
                      step="0.25"
                      type="number"
                      value={rate}
                      onChange={(e) => setRate(e.currentTarget.value)}
                    />
                  </label>
                </div>
                <label className="flex min-h-11 items-center gap-2 text-xs">
                  <input
                    type="checkbox"
                    checked={freeze}
                    onChange={(e) => setFreeze(e.currentTarget.checked)}
                  />
                  Freeze the selected video frame
                </label>
                <p className="text-xs leading-5 text-[#666862]">
                  Green screen requires a real flat-colour background. Automatic
                  person cutout and subject tracking remain unavailable. Keep
                  important text clear of the picture and caption areas.
                </p>
              </div>
            ) : null}
            <label className="flex min-h-11 items-center gap-2 text-xs">
              <input
                type="checkbox"
                checked={denoise}
                onChange={(e) => setDenoise(e.currentTarget.checked)}
              />
              Gentle voice noise reduction
            </label>
            <button
              className="min-h-11 w-full rounded-md bg-[#173F5F] px-3 text-sm font-bold text-white disabled:opacity-50"
              disabled={
                busy ||
                (tool === "visual_beat" && visualBeat === "paper_tear" && clipBoundaries.length === 0) ||
                (tool === "visual_beat" && visualBeat === "dolly_zoom" && dollyClips.length === 0) ||
                ((tool === "audio" ||
                  tool === "captions" ||
                  tool === "layer" ||
                  ["callout", "pointer", "music_pause", "visual_beat"].includes(tool)) &&
                  Number(end) <= Number(start))
              }
            >
              {busy ? "Creating preview…" : "Create preview with this tool"}
            </button>
          </form>
          <details className="border-t border-[#D7D9D3] pt-2">
            <summary className="min-h-11 cursor-pointer content-center text-xs font-bold">
              One-pass local repair
            </summary>
            <p className="my-3 text-xs leading-5 text-[#666862]">
              Choose one repair for this version, then review the result. No
              background retry loop or additional model request. Tightening
              measured speech gaps can shorten a comic pause.
            </p>
            <div className="flex flex-wrap gap-2">
              {(["tighten_pauses", "denoise"] as const).map((kind) => (
                <button
                  className="min-h-11 rounded border border-[#C7CBD0] px-3 text-xs"
                  disabled={busy}
                  key={kind}
                  onClick={() => {
                    setBusy(true);
                    setError("");
                    void requestLocalRepair(jobId, version, kind)
                      .then(onUpdated)
                      .catch((e: unknown) =>
                        setError(
                          e instanceof Error ? e.message : "Repair failed",
                        ),
                      )
                      .finally(() => setBusy(false));
                  }}
                  type="button"
                >
                  {kind === "denoise"
                    ? "Reduce voice noise"
                    : "Tighten measured gaps"}
                </button>
              ))}
            </div>
          </details>
          <details className="border-t border-[#D7D9D3] pt-2">
            <summary className="min-h-11 cursor-pointer content-center text-xs font-bold">
              Active finishing &amp; version recovery
            </summary>
            <p className="my-3 text-xs text-[#666862]">
              {(regions?.callouts?.length ?? 0) +
                (regions?.pointers?.length ?? 0) + (regions?.visual_beats?.length ?? 0)}{" "}
              visual accents · {regions?.music_regions?.length ?? 0} music
              pauses · {regions?.motions.length ?? 0} camera moves ·{" "}
              {regions?.audio_regions.length ?? 0} audio ranges ·{" "}
              {regions?.caption_regions.length ?? 0} caption ranges ·{" "}
              {regions?.layers.length ?? 0} picture layers
            </p>
            <div className="flex flex-wrap items-end gap-3">
              <button
                className="min-h-11 rounded-md border border-[#D7D9D3] px-3 text-xs"
                disabled={busy}
                type="button"
                onClick={() => {
                  if (
                    window.confirm(
                      "Clear all local finishing tools in a new preview? The cut and previous versions stay available.",
                    )
                  )
                    void apply({
                      motions: [],
                      colours: [],
                      audio_regions: [],
                      caption_regions: [],
                      layers: [],
                      music_start_seconds: 0,
                      voice_denoise: false,
                      audio_joins: [],
                    });
                }}
              >
                Clear local finishing
              </button>
              <label className="text-xs">
                Restore ready version
                <input
                  className={control}
                  min={1}
                  max={version}
                  step={1}
                  type="number"
                  value={restore}
                  onChange={(e) => setRestore(e.currentTarget.value)}
                />
              </label>
              <button
                className="min-h-11 rounded-md border border-[#D7D9D3] px-3 text-xs"
                disabled={busy}
                onClick={() => void restoreVersion()}
                type="button"
              >
                Restore as new preview
              </button>
            </div>
          </details>
        </>
      )}
    </div>
  );
}
