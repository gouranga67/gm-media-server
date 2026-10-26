"use client";
import { useEffect, useState } from "react";
import { getPilotReadiness, type PilotReadiness } from "@/lib/media-api";
import { StudioNav } from "./studio-nav";
export function PilotChecklist() {
  const [report, setReport] = useState<PilotReadiness>();
  const [error, setError] = useState("");
  const [done, setDone] = useState<readonly string[]>([]);
  useEffect(() => {
    let active = true;
    getPilotReadiness()
      .then((value) => {
        if (active) setReport(value);
      })
      .catch((e: unknown) => {
        if (active)
          setError(e instanceof Error ? e.message : "Readiness is unavailable");
      });
    return () => {
      active = false;
    };
  }, []);
  return (
    <main className="min-h-dvh bg-[#F7F7F5] px-4 py-5 text-[#20211F]">
      <div className="mx-auto max-w-4xl">
        <StudioNav current="/studio/pilot" />
        <h1 className="mt-8 text-3xl font-black text-[#173F5F]">
          Pilot acceptance
        </h1>
        <p className="mt-3 text-sm leading-6 text-[#666862]">
          Source tests and a successful render cannot judge a finished reel. Use
          this checklist after deployment with real footage and a fresh tester.
          Checkmarks last for this page visit; they are not a record of system
          verification.
        </p>
        {error ? (
          <p
            role="alert"
            className="my-4 rounded bg-[#FFF0EC] p-3 text-sm text-[#A23B2A]"
          >
            {error}
          </p>
        ) : null}
        {report ? (
          <div className="mt-6 space-y-5">
            <section className="rounded-lg border border-[#D7D9D3] bg-white p-5">
              <h2 className="font-bold text-[#173F5F]">Deployment scope</h2>
              <p className="mt-2 text-sm">{report.deployment_scope}</p>
              <p className="mt-3 text-xs text-[#666862]">
                New schema:{" "}
                {report.schema_ready ? "present" : "deployment required"} ·
                Private owner:{" "}
                {report.configured_private_owner
                  ? "configured"
                  : "not configured"}{" "}
                · Failed previews in seven days:{" "}
                {report.failed_previews_last_7_days}
              </p>
            </section>
            <section className="rounded-lg border border-[#D7D9D3] bg-white p-5">
              <h2 className="mb-3 font-bold text-[#173F5F]">
                Human and live checks · {done.length}/
                {report.remaining_acceptance.length}
              </h2>
              {report.remaining_acceptance.map((item) => (
                <label
                  className="flex min-h-14 items-start gap-3 border-t border-[#E7E8E4] py-4 text-sm"
                  key={item}
                >
                  <input
                    className="mt-1 size-4 shrink-0 accent-[#173F5F]"
                    type="checkbox"
                    checked={done.includes(item)}
                    onChange={(e) => {
                      const checked = e.currentTarget.checked;
                      setDone((previous) =>
                        checked
                          ? [...previous, item]
                          : previous.filter((v) => v !== item),
                      );
                    }}
                  />
                  <span>{item}</span>
                </label>
              ))}
            </section>
            <section className="rounded-lg border border-[#D7D9D3] bg-white p-5">
              <h2 className="font-bold text-[#173F5F]">Tool availability</h2>
              <dl className="mt-3 grid gap-3 sm:grid-cols-2">
                {Object.entries(report.tools).map(([name, enabled]) => (
                  <div
                    className="flex justify-between gap-3 border-b border-[#E7E8E4] py-2 text-xs"
                    key={name}
                  >
                    <dt>{name.replaceAll("_", " ")}</dt>
                    <dd
                      className={`font-bold ${enabled ? "text-[#215B43]" : "text-[#666862]"}`}
                    >
                      {enabled ? "Enabled" : "Gated"}
                    </dd>
                  </div>
                ))}
              </dl>
              <p className="mt-3 text-xs leading-5 text-[#666862]">
                Automatic person segmentation and tracking are gated pending
                local-model quality and resource checks. This appliance provides
                a shared private studio, not isolated public customer
                workspaces.
              </p>
            </section>
          </div>
        ) : null}
      </div>
    </main>
  );
}
