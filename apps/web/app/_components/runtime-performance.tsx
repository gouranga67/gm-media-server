"use client";
import { useEffect, useState } from "react";
import {
  getRuntimePerformance,
  type RuntimePerformanceReport,
} from "@/lib/media-api";

export function RuntimePerformance() {
  const [report, setReport] = useState<RuntimePerformanceReport>();
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    getRuntimePerformance()
      .then((value) => {
        if (active) setReport(value);
      })
      .catch(() => {
        if (active)
          setError(
            "Timing measurements are unavailable. System health has more detail.",
          );
      });
    return () => {
      active = false;
    };
  }, []);
  return (
    <section className="rounded-lg border border-[#D7D9D3] bg-white p-5">
      <h2 className="font-bold text-[#173F5F]">Recent processing times</h2>
      <p className="mt-2 text-xs leading-5 text-[#666862]">
        Local worker samples. These show task time, excluding queue waits and
        hosted usage billing.
      </p>
      {error ? (
        <p role="status" className="mt-3 text-sm text-[#A23B2A]">
          {error}
        </p>
      ) : !report ? (
        <p className="mt-3 text-sm">Loading measurements…</p>
      ) : Object.keys(report.stages).length === 0 ? (
        <p className="mt-3 text-sm text-[#666862]">
          Measurements appear after the updated worker processes a task.
        </p>
      ) : (
        <div className="mt-4 overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr>
                <th className="py-2">Task</th>
                <th>Samples</th>
                <th>Median</th>
                <th>95th percentile</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(report.stages).map(([stage, value]) => (
                <tr className="border-t border-[#E7E8E4]" key={stage}>
                  <th className="py-3 font-medium">
                    {stage.replaceAll("_", " ")}
                  </th>
                  <td>{value.samples}</td>
                  <td>{value.median_seconds.toFixed(1)}s</td>
                  <td>{value.p95_seconds.toFixed(1)}s</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
