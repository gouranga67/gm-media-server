"use client";

import Link from "next/link";
import { StudioNav } from "./studio-nav";
import { useEffect, useState, type ReactNode } from "react";
import { AlertTriangleIcon, CheckCircle2Icon, CpuIcon, DatabaseBackupIcon, HardDriveIcon, LoaderCircleIcon, ServerIcon, ThermometerIcon } from "lucide-react";

import { getApplianceHealth, type ApplianceHealth as HealthData } from "@/lib/media-api";

function formatBytes(value: number) {
  const units = ["B", "KB", "MB", "GB", "TB"];
  let amount = value;
  let index = 0;
  while (amount >= 1024 && index < units.length - 1) { amount /= 1024; index += 1; }
  return `${new Intl.NumberFormat(undefined, { maximumFractionDigits: amount >= 10 ? 1 : 2 }).format(amount)} ${units[index]}`;
}

function Metric({ icon, label, value, note, attention = false }: { readonly icon: ReactNode; readonly label: string; readonly value: string; readonly note: string; readonly attention?: boolean }) {
  return <article className={`rounded-md border p-4 ${attention ? "border-[#D8B4AA] bg-[#FFF7F4]" : "border-[#D7D9D3] bg-white"}`}><div className="flex items-center justify-between gap-3"><p className="font-mono text-[9px] font-bold tracking-wide text-[#666862] uppercase">{label}</p><span className={attention ? "text-[#A23B2A]" : "text-[#174D73]"}>{icon}</span></div><p className="mt-3 text-2xl font-bold tracking-tight text-[#173F5F]">{value}</p><p className="mt-1 text-xs text-[#666862]">{note}</p></article>;
}

export function ApplianceHealth() {
  const [health, setHealth] = useState<HealthData>();
  const [error, setError] = useState<string>();

  useEffect(() => {
    let cancelled = false;
    async function refresh() {
      try {
        const result = await getApplianceHealth();
        if (!cancelled) { setHealth(result); setError(undefined); }
      } catch (requestError) {
        if (!cancelled) setError(requestError instanceof Error ? requestError.message : "Appliance health is unavailable");
      }
    }
    void refresh();
    const timer = window.setInterval(() => void refresh(), 60_000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, []);

  const backupGood = health?.backup?.state === "ready" || health?.backup?.state === "running";
  const offsiteGood = health?.offsite_backup?.state === "ready" || health?.offsite_backup?.state === "running";
  const servicesGood = health?.services && health.services.running >= health.services.expected;
  return <main className="min-h-dvh bg-[#F7F7F5] px-4 pt-[max(1.25rem,env(safe-area-inset-top))] pb-[max(2rem,env(safe-area-inset-bottom))] text-[#20211F] [color-scheme:light] sm:px-6"><div className="mx-auto max-w-6xl"><header className="border-b border-[#D7D9D3] pb-5"><div className="flex flex-wrap items-center justify-between gap-4"><StudioNav current="/system" />{health ? <span className={`inline-flex items-center gap-2 rounded-full border px-3 py-2 font-mono text-[10px] font-bold ${health.status === "healthy" ? "border-[#B9D8C7] bg-[#E4F1E9] text-[#307455]" : "border-[#D8B4AA] bg-[#FFF7F4] text-[#A23B2A]"}`}>{health.status === "healthy" ? <CheckCircle2Icon className="size-3.5" /> : <AlertTriangleIcon className="size-3.5" />}{health.status.toUpperCase()}</span> : null}</div><p className="mt-6 font-mono text-[10px] font-bold tracking-widest text-[#174D73] uppercase">Appliance operations</p><h1 className="mt-2 text-3xl font-bold tracking-tight text-[#173F5F]">System health &amp; backup</h1><p className="mt-3 max-w-2xl text-sm leading-6 text-[#666862]">A read-only view of the Lenovo, editing queues, encrypted USB snapshots, and the OneDrive recovery copy. It refreshes every minute.</p></header>
  {!health && !error ? <div className="flex min-h-72 items-center justify-center"><LoaderCircleIcon className="size-8 animate-spin text-[#173F5F]" /></div> : null}{error ? <p className="mt-6 rounded-md border border-[#D8B4AA] bg-[#FFF7F4] p-4 text-sm text-[#A23B2A]">{error}</p> : null}{health ? <div className="space-y-6 py-6">{health.alerts.length ? <section className="rounded-md border border-[#D8B4AA] bg-[#FFF7F4] p-4"><p className="flex items-center gap-2 font-bold text-[#A23B2A]"><AlertTriangleIcon className="size-4" />Attention needed</p><ul className="mt-2 space-y-1 text-sm text-[#666862]">{health.alerts.map((alert) => <li key={alert}>• {alert}</li>)}</ul></section> : <section className="rounded-md border border-[#B9D8C7] bg-[#E4F1E9] p-4"><p className="flex items-center gap-2 font-bold text-[#307455]"><CheckCircle2Icon className="size-4" />All monitored systems look healthy</p></section>}
  <section className="grid grid-cols-2 gap-3 lg:grid-cols-4"><Metric icon={<HardDriveIcon className="size-4" />} label="Media disk" value={health.disk ? `${health.disk.used_percent}% used` : "Pending"} note={health.disk ? `${formatBytes(health.disk.available_bytes)} available` : "Waiting for host snapshot"} attention={Boolean(health.disk && (health.disk.used_percent >= 85 || health.disk.available_bytes < 50 * 1024 ** 3))} /><Metric icon={<ThermometerIcon className="size-4" />} label="GPU temperature" value={health.gpu?.temperature_celsius === null || health.gpu?.temperature_celsius === undefined ? "Unavailable" : `${health.gpu.temperature_celsius}°C`} note="NVIDIA host sensor" attention={Boolean(health.gpu?.temperature_celsius && health.gpu.temperature_celsius >= 83)} /><Metric icon={<ServerIcon className="size-4" />} label="Services" value={health.services ? `${health.services.running}/${health.services.expected}` : "Pending"} note="Core containers running" attention={health.services ? !servicesGood : false} /><Metric icon={<DatabaseBackupIcon className="size-4" />} label="Encrypted backup" value={health.backup?.state ?? "Pending"} note={health.backup?.age_hours === null || health.backup?.age_hours === undefined ? health.backup?.message ?? "Waiting for first backup" : `${health.backup.age_hours} hours old`} attention={health.backup ? !backupGood : false} /></section>
  <section className="grid gap-4 lg:grid-cols-2"><article className="rounded-md border border-[#D7D9D3] bg-white p-5"><div className="flex items-center gap-2"><CpuIcon className="size-4 text-[#174D73]" /><h2 className="font-bold text-[#173F5F]">Work queues</h2></div><div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3">{Object.entries(health.queues ?? {}).map(([name, count]) => <div className="rounded-md bg-[#F7F7F5] p-3" key={name}><p className="font-mono text-[8px] font-bold tracking-wide text-[#666862] uppercase">{name.replaceAll("_", " ")}</p><p className="mt-2 text-xl font-bold text-[#173F5F]">{count.toLocaleString()}</p></div>)}</div></article><article className="rounded-md border border-[#D7D9D3] bg-white p-5"><h2 className="font-bold text-[#173F5F]">Recovery posture</h2><dl className="mt-4 space-y-3 text-sm"><div className="flex justify-between gap-4 border-b border-[#E7E8E4] pb-3"><dt className="text-[#666862]">USB repository</dt><dd className="font-bold text-[#20211F]">{health.backup?.state ?? "not reported"}</dd></div><div className="flex justify-between gap-4 border-b border-[#E7E8E4] pb-3"><dt className="text-[#666862]">OneDrive copy</dt><dd className={`font-bold ${offsiteGood ? "text-[#20211F]" : "text-[#A23B2A]"}`}>{health.offsite_backup?.state?.replaceAll("_", " ") ?? "not reported"}</dd></div><div className="flex justify-between gap-4 border-b border-[#E7E8E4] pb-3"><dt className="text-[#666862]">Reboot recovery</dt><dd className={`font-bold ${health.reboot_recovery?.status === "passed" ? "text-[#20211F]" : "text-[#A23B2A]"}`}>{health.reboot_recovery?.status?.replaceAll("_", " ") ?? "not reported"}</dd></div><div className="flex justify-between gap-4 border-b border-[#E7E8E4] pb-3"><dt className="text-[#666862]">Internal disk SMART</dt><dd className="font-bold text-[#20211F]">{health.smart?.state ?? "not reported"}</dd></div><div className="flex justify-between gap-4"><dt className="text-[#666862]">Last snapshot</dt><dd className="text-right font-mono text-[10px] text-[#20211F]">{health.generated_at ? new Date(health.generated_at).toLocaleString() : "pending"}</dd></div></dl><p className="mt-5 rounded-md border border-dashed border-[#C7CBD0] bg-[#F7F7F5] p-3 text-xs leading-5 text-[#666862]"><strong className="text-[#173F5F]">Recovery rule:</strong> keep one current encrypted copy on the USB and another in OneDrive before permanently removing source media.</p></article></section></div> : null}</div></main>;
}
