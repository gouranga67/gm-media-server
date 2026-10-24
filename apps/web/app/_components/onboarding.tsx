"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { CheckCircle2Icon, CircleIcon, LoaderCircleIcon } from "lucide-react";
import { getStudioOverview, saveStudioSettings, type StudioOverview } from "@/lib/media-api";
import { StudioNav } from "./studio-nav";

const steps = [
  ["private_access", "Private access", "Tailscale identity protects the studio.", "/access"],
  ["editor_connected", "AI editor", "Your ChatGPT plan can create edit decisions.", "/usage"],
  ["backup_monitoring", "Recovery", "USB and off-site backup monitoring is available.", "/system"],
  ["brand_ready", "Brand", "Create a caption look for repeatable output.", "/settings"],
  ["library_ready", "Media library", "Upload or catalogue reusable source media.", "/library"],
  ["first_delivery", "First delivery", "Approve and export one complete edit.", "/jobs/new"],
] as const;

export function Onboarding() {
  const [overview, setOverview] = useState<StudioOverview>(); const [error, setError] = useState<string>(); const [saving, setSaving] = useState(false);
  useEffect(() => { getStudioOverview().then(setOverview).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Setup status is unavailable")); }, []);
  async function finish() { if (!overview) return; setSaving(true); try { const current = overview.settings; const saved = await saveStudioSettings({ studio_name: current.studio_name, onboarding_completed: true, daily_ai_token_limit: current.daily_ai_token_limit, monthly_ai_token_limit: current.monthly_ai_token_limit, max_active_jobs: current.max_active_jobs, preview_retention_days: current.preview_retention_days, delivery_retention_days: current.delivery_retention_days }); setOverview({ ...overview, settings: { ...overview.settings, onboarding_completed: saved.onboarding_completed } }); } catch (reason) { setError(reason instanceof Error ? reason.message : "Could not save setup"); } finally { setSaving(false); } }
  const complete = overview ? Object.values(overview.readiness).filter(Boolean).length : 0;
  return <main className="min-h-dvh bg-[#F7F7F5] px-4 py-[max(1.25rem,env(safe-area-inset-top))] text-[#20211F] sm:px-6"><div className="mx-auto max-w-3xl"><header className="border-b border-[#D7D9D3] pb-5"><StudioNav /><p className="mt-8 font-mono text-[10px] font-bold tracking-widest text-[#174D73] uppercase">Guided setup</p><h1 className="mt-2 text-3xl font-black text-[#173F5F]">Make the studio yours</h1><p className="mt-3 text-sm leading-6 text-[#666862]">These checks explain the whole appliance. Existing work already counts.</p></header>{!overview && !error ? <div className="flex min-h-80 items-center justify-center"><LoaderCircleIcon className="size-8 animate-spin text-[#173F5F]" /></div> : null}{error ? <p className="mt-6 rounded-md bg-[#FFF0EC] p-4 text-sm text-[#A23B2A]">{error}</p> : null}{overview ? <div className="py-6"><div className="mb-5 rounded-md border border-[#A9C9DC] bg-[#EFF6FA] p-4"><div className="flex justify-between text-sm font-bold text-[#173F5F]"><span>Studio readiness</span><span>{complete}/{steps.length}</span></div><div className="mt-3 h-2 overflow-hidden rounded-full bg-white"><div className="h-full bg-[#307455]" style={{ width: `${complete / steps.length * 100}%` }} /></div></div><div className="grid gap-3">{steps.map(([key, title, description, href], index) => { const done = overview.readiness[key]; return <Link className="flex items-center gap-4 rounded-md border border-[#D7D9D3] bg-white p-4 hover:border-[#8AB5CE]" href={href} key={key}><span className={`flex size-9 shrink-0 items-center justify-center rounded-full ${done ? "bg-[#E4F1E9] text-[#307455]" : "bg-[#F1F2EF] text-[#788078]"}`}>{done ? <CheckCircle2Icon className="size-5" /> : <CircleIcon className="size-5" />}</span><div className="min-w-0"><p className="font-bold text-[#173F5F]">{index + 1}. {title}</p><p className="mt-1 text-xs text-[#666862]">{description}</p></div><span className="ml-auto text-[#174D73]">→</span></Link>; })}</div><div className="mt-6 rounded-md border border-[#D7D9D3] bg-white p-5"><p className="font-bold text-[#173F5F]">Ready to use GM Studio?</p><p className="mt-2 text-xs leading-5 text-[#666862]">You can finish onboarding even if you plan to add a brand or more media later. The checklist remains available here.</p><button className="mt-4 min-h-11 w-full rounded-md bg-[#173F5F] px-5 text-sm font-bold text-white disabled:opacity-50" disabled={saving} onClick={() => void finish()}>{saving ? "Saving…" : overview.settings.onboarding_completed ? "Setup completed" : "Finish setup"}</button></div></div> : null}</div></main>;
}
