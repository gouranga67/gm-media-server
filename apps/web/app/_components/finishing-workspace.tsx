"use client";
import { useEffect, useState, type FormEvent } from "react";
import {
  getFinishingTools,
  requestRevision,
  requestLocalRepair,
  type FinishingInspection,
  type FinishingTools,
  type EditorialClip,
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
  | "join";
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
  const [inspection, setInspection] = useState<FinishingInspection>();
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
            <label className="block text-xs font-bold">
              Tool
              <select
                className={control}
                value={tool}
                onChange={(e) => setTool(e.currentTarget.value as Tool)}
              >
                <option value="motion">Targeted camera move</option>
                <option value="audio">Phrase audio level</option>
                <option value="captions">Timed caption placement</option>
                <option value="colour">Selected clip colour</option>
                <option value="layer">Picture layer / green screen</option>
                <option value="music">Music excerpt</option>
                <option value="join">Independent audio / picture join</option>
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
            {tool === "audio" || tool === "captions" || tool === "layer" ? (
              <div className="grid grid-cols-2 gap-3">
                <label className="text-xs">
                  Reel start seconds
                  <input
                    className={control}
                    min={0}
                    max={60}
                    step="0.01"
                    type="number"
                    required
                    value={start}
                    onChange={(e) => setStart(e.currentTarget.value)}
                  />
                </label>
                <label className="text-xs">
                  Reel end seconds
                  <input
                    className={control}
                    min={0.01}
                    max={60}
                    step="0.01"
                    type="number"
                    required
                    value={end}
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
            {tool === "motion" || tool === "layer" ? (
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
                ((tool === "audio" ||
                  tool === "captions" ||
                  tool === "layer") &&
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
              {regions?.motions.length ?? 0} camera moves ·{" "}
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
