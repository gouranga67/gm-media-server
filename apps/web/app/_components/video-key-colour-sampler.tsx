"use client";

import { useEffect, useRef, useState, type KeyboardEvent, type PointerEvent } from "react";
import { CheckIcon, PipetteIcon, RefreshCwIcon, XIcon } from "lucide-react";

import { Button } from "@/components/ui/button";

const MAX_FRAME_WIDTH = 960;
const SAMPLE_RADIUS = 2;

type Point = { readonly x: number; readonly y: number };
type Frame = { readonly width: number; readonly height: number; readonly time: number };

function channelHex(value: number) {
  return Math.max(0, Math.min(255, Math.round(value))).toString(16).padStart(2, "0");
}

export function rgbaSampleToHex(data: Uint8ClampedArray) {
  let red = 0;
  let green = 0;
  let blue = 0;
  let pixels = 0;
  for (let index = 0; index + 3 < data.length; index += 4) {
    if (data[index + 3] < 16) continue;
    red += data[index];
    green += data[index + 1];
    blue += data[index + 2];
    pixels += 1;
  }
  if (!pixels) return undefined;
  return `#${channelHex(red / pixels)}${channelHex(green / pixels)}${channelHex(blue / pixels)}`.toUpperCase();
}

function formatTime(seconds: number) {
  if (!Number.isFinite(seconds) || seconds < 0) return "current frame";
  const whole = Math.floor(seconds);
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}

export function VideoKeyColourSampler({
  getPreviewVideo,
  onSelect,
}: {
  readonly getPreviewVideo?: () => HTMLVideoElement | null;
  readonly onSelect: (colour: string) => void;
}) {
  const capturedFrame = useRef<HTMLCanvasElement | null>(null);
  const visibleCanvas = useRef<HTMLCanvasElement>(null);
  const [frame, setFrame] = useState<Frame>();
  const [marker, setMarker] = useState<Point>();
  const [sampledColour, setSampledColour] = useState<string>();
  const [error, setError] = useState("");

  useEffect(() => {
    const destination = visibleCanvas.current;
    const source = capturedFrame.current;
    if (!destination || !source || !frame) return;
    const context = destination.getContext("2d");
    if (!context) return;
    context.drawImage(source, 0, 0, frame.width, frame.height);
  }, [frame]);

  const capture = () => {
    setError("");
    const video = getPreviewVideo?.();
    if (!video) {
      setError("The preview video is not available. Use a preset or the manual colour picker instead.");
      return;
    }
    if (video.readyState < 2 || !video.videoWidth || !video.videoHeight) {
      setError("Play or scrub the preview until a frame is visible, then try again.");
      return;
    }
    video.pause();
    const scale = Math.min(1, MAX_FRAME_WIDTH / video.videoWidth);
    const width = Math.max(1, Math.round(video.videoWidth * scale));
    const height = Math.max(1, Math.round(video.videoHeight * scale));
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    try {
      const context = canvas.getContext("2d", { willReadFrequently: true });
      if (!context) throw new Error("Canvas capture is not supported.");
      context.drawImage(video, 0, 0, width, height);
      capturedFrame.current = canvas;
      setFrame({ width, height, time: video.currentTime });
      setMarker(undefined);
      setSampledColour(undefined);
    } catch {
      setError("This browser could not read the preview frame. Use a preset or the manual colour picker instead.");
    }
  };

  const sampleAt = (point: Point) => {
    const canvas = capturedFrame.current;
    if (!canvas) return;
    const x = Math.max(0, Math.min(canvas.width - 1, Math.round(point.x)));
    const y = Math.max(0, Math.min(canvas.height - 1, Math.round(point.y)));
    const left = Math.max(0, x - SAMPLE_RADIUS);
    const top = Math.max(0, y - SAMPLE_RADIUS);
    const width = Math.min(canvas.width - left, SAMPLE_RADIUS * 2 + 1);
    const height = Math.min(canvas.height - top, SAMPLE_RADIUS * 2 + 1);
    try {
      const context = canvas.getContext("2d", { willReadFrequently: true });
      const colour = context ? rgbaSampleToHex(context.getImageData(left, top, width, height).data) : undefined;
      if (!colour) throw new Error("No visible pixel was selected.");
      setMarker({ x, y });
      setSampledColour(colour);
      setError("");
    } catch {
      setError("That pixel could not be sampled. Try another area or use the manual colour picker.");
    }
  };

  const pointFromPointer = (event: PointerEvent<HTMLCanvasElement>) => {
    if (!frame) return;
    const bounds = event.currentTarget.getBoundingClientRect();
    if (!bounds.width || !bounds.height) return;
    sampleAt({
      x: ((event.clientX - bounds.left) / bounds.width) * frame.width,
      y: ((event.clientY - bounds.top) / bounds.height) * frame.height,
    });
  };

  const moveKeyboardMarker = (event: KeyboardEvent<HTMLCanvasElement>) => {
    if (!frame) return;
    const step = Math.max(1, Math.round(Math.min(frame.width, frame.height) * 0.02));
    const current = marker ?? { x: frame.width / 2, y: frame.height / 2 };
    const next = { ...current };
    if (event.key === "ArrowLeft") next.x -= step;
    else if (event.key === "ArrowRight") next.x += step;
    else if (event.key === "ArrowUp") next.y -= step;
    else if (event.key === "ArrowDown") next.y += step;
    else if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      sampleAt(current);
      return;
    } else return;
    event.preventDefault();
    const bounded = {
      x: Math.max(0, Math.min(frame.width - 1, next.x)),
      y: Math.max(0, Math.min(frame.height - 1, next.y)),
    };
    setMarker(bounded);
  };

  const close = () => {
    capturedFrame.current = null;
    setFrame(undefined);
    setMarker(undefined);
    setSampledColour(undefined);
    setError("");
  };

  if (!frame) {
    return (
      <div className="space-y-2">
        <Button className="h-11 w-full" onClick={capture} type="button" variant="outline">
          <PipetteIcon aria-hidden="true" /> Pick colour from current frame
        </Button>
        {error ? <p className="rounded-md bg-[#FFF0EC] p-3 text-xs leading-5 text-[#A23B2A]" role="alert">{error}</p> : null}
      </div>
    );
  }

  return (
    <section className="space-y-3 rounded-md border border-[#BFD2DE] bg-[#EFF6FA] p-3" aria-labelledby="colour-sampler-title">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-xs font-bold text-[#173F5F]" id="colour-sampler-title">Tap the screen colour</h3>
          <p className="mt-1 text-[11px] leading-5 text-[#53646F]">Preview paused at {formatTime(frame.time)}. Choose an evenly lit area away from the subject, shadows, glare and colour spill.</p>
        </div>
        <Button aria-label="Close colour sampler" className="size-11 shrink-0 p-0" onClick={close} type="button" variant="outline"><XIcon aria-hidden="true" /></Button>
      </div>
      <div className="relative mx-auto w-fit max-w-full overflow-hidden rounded-md border border-[#B7C0C7] bg-black">
        <canvas
          aria-label="Paused preview frame. Tap or click an evenly lit screen area to sample its colour. Arrow keys move the sample point and Enter selects it."
          className="block h-auto max-h-[28rem] max-w-full cursor-crosshair touch-none"
          height={frame.height}
          onKeyDown={moveKeyboardMarker}
          onPointerDown={pointFromPointer}
          ref={visibleCanvas}
          role="application"
          tabIndex={0}
          width={frame.width}
        />
        {marker ? <span aria-hidden="true" className="pointer-events-none absolute size-5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-white shadow-[0_0_0_2px_#173F5F]" style={{ left: `${(marker.x / frame.width) * 100}%`, top: `${(marker.y / frame.height) * 100}%` }} /> : null}
      </div>
      <p className="text-[10px] leading-4 text-[#666862]">Keyboard: use arrow keys to position the marker, then press Enter.</p>
      {sampledColour ? (
        <div className="flex items-center justify-between gap-3 rounded-md border border-[#D7D9D3] bg-white p-2">
          <div className="flex items-center gap-2">
            <span aria-hidden="true" className="size-8 rounded border border-[#B7C0C7]" style={{ backgroundColor: sampledColour }} />
            <div><p className="text-[9px] font-bold tracking-wide text-[#666862] uppercase">Selected colour</p><p className="font-mono text-xs font-bold text-[#173F5F]">{sampledColour}</p></div>
          </div>
          <Button className="h-11" onClick={capture} type="button" variant="ghost"><RefreshCwIcon aria-hidden="true" /> Resample</Button>
        </div>
      ) : <p className="rounded-md border border-dashed border-[#9FB7C7] bg-white p-3 text-center text-xs text-[#53646F]">Tap the paused frame to choose the colour to remove.</p>}
      {error ? <p className="rounded-md bg-[#FFF0EC] p-3 text-xs leading-5 text-[#A23B2A]" role="alert">{error}</p> : null}
      <div className="grid grid-cols-2 gap-2">
        <Button className="h-11" onClick={close} type="button" variant="outline">Cancel</Button>
        <Button className="h-11 bg-[#173F5F] text-white hover:bg-[#12344F]" disabled={!sampledColour} onClick={() => { if (sampledColour) { onSelect(sampledColour); close(); } }} type="button"><CheckIcon aria-hidden="true" /> Use this colour</Button>
      </div>
      <p className="text-center text-[10px] leading-4 text-[#666862]">This only prepares the key colour. Nothing saves or renders until you create the composition preview.</p>
    </section>
  );
}
