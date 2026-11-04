"use client";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { getLearningComparisons, type LearningComparisonPage } from "@/lib/media-api";

const control = "min-h-11 rounded-md border border-[#C7CBD0] bg-white px-3 text-sm text-[#173F5F] disabled:opacity-50";
type Position = readonly (string | undefined)[];

export function LearningComparisonHistory({ lessonId, busy, refreshToken, renderTrial }: {
  readonly lessonId: string; readonly busy: boolean; readonly refreshToken: object;
  readonly renderTrial: (trial: LearningComparisonPage["items"][number]) => ReactNode;
}) {
  const [page, setPage] = useState<LearningComparisonPage>();
  const [positions, setPositions] = useState<Position>([undefined]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState<Position>();
  const current = useRef<Position>([undefined]);
  const sequence = useRef(0);
  const load = useCallback(async (target: Position) => {
    const request = ++sequence.current;
    setLoading(true); setError("");
    try {
      const result = await getLearningComparisons(lessonId, target.at(-1));
      if (request !== sequence.current) return;
      setPage(result); current.current = target; setPositions(target); setRetry(undefined);
    } catch (failure) {
      if (request !== sequence.current) return;
      setError(failure instanceof Error ? failure.message : "Comparison history could not be loaded."); setRetry(target);
    } finally { if (request === sequence.current) setLoading(false); }
  }, [lessonId]);
  useEffect(() => {
    void load(current.current);
    return () => { sequence.current += 1; };
  }, [load, refreshToken]);
  return <section aria-label="Full comparison history" className="mt-3 space-y-3 rounded-md border border-[#BFD2DE] bg-[#FAFAF8] p-3">
    <div className="flex flex-wrap items-center justify-between gap-2"><h4 className="text-sm font-bold text-[#173F5F]">Full comparison history</h4><button className={control} disabled={busy || loading} onClick={() => void load(current.current)} type="button">Refresh history page</button></div>
    <p className="text-xs leading-5 text-[#666862]">20 comparisons per page. Unsaved ratings and notes stay here while you change pages. Save each review explicitly before leaving Learning.</p>
    {error ? <div role="alert" className="rounded bg-[#FFF0EC] p-3 text-sm text-[#A23B2A]"><p>{error}</p><button className={`${control} mt-2`} disabled={busy || loading} onClick={() => void load(retry ?? current.current)} type="button">Retry history page</button></div> : null}
    {loading ? <p role="status" className="text-sm text-[#53646F]">Loading comparisons…</p> : null}
    {page ? <>
      <p role="status" className="text-xs text-[#53646F]">Page {positions.length} · {page.items.length} shown · {page.total} saved trials for this lesson</p>
      <fieldset disabled={busy || loading} className="min-w-0 space-y-3">{page.items.map(renderTrial)}</fieldset>
      {!page.items.length ? <p className="text-sm text-[#666862]">No comparisons on this page. Refresh the recent page if the history changed.</p> : null}
      <div className="flex flex-wrap gap-2"><button className={control} disabled={busy || loading || positions.length === 1} onClick={() => void load(positions.slice(0,-1))} type="button">Newer comparisons</button><button className={control} disabled={busy || loading || !page.next_before} onClick={() => { if (page.next_before) void load([...positions,page.next_before]); }} type="button">Older comparisons</button><button className={control} disabled={busy || loading || positions.length === 1} onClick={() => void load([undefined])} type="button">Most recent comparisons</button></div>
    </> : null}
  </section>;
}
