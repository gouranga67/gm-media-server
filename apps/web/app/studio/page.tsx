import Link from "next/link";
import { StudioNav } from "@/app/_components/studio-nav";
import { RuntimePerformance } from "@/app/_components/runtime-performance";

export const metadata = { title: "Studio tools" };
const tools = [
  ["Source knowledge", "Product names, aliases and human source annotations.", "/studio/knowledge"],
  ["Brand & presets", "Reusable caption styles and publishing choices.", "/settings"],
  ["Learning", "Review feedback, evaluate proposed editing preferences and keep changes reversible.", "/learning"],
  ["Usage", "Measured model requests and tokens.", "/usage"],
  ["System & backup", "Appliance health, encrypted backup and recovery status.", "/system"],
  ["People", "Manage who can edit or review in this private studio.", "/access"],
  ["Operations", "Queue, capacity and retention controls.", "/operations"],
  ["Guided setup", "Check the studio before inviting a tester.", "/welcome"],
] as const;
export default function StudioPage() {
  return <main className="min-h-dvh bg-[#F7F7F5] px-4 py-5 text-[#20211F]"><div className="mx-auto max-w-5xl">
    <StudioNav current="/studio" /><h1 className="mt-8 text-3xl font-black text-[#173F5F]">Your studio</h1>
    <p className="mt-3 text-sm text-[#666862]">Manage the knowledge, preferences and services behind your edits.</p>
    <section aria-label="Studio tools" className="my-6 grid gap-3 sm:grid-cols-2">{tools.map(([title, description, href]) => <Link className="rounded-lg border border-[#D7D9D3] bg-white p-5 hover:border-[#174D73]" href={href} key={href}><h2 className="font-bold text-[#173F5F]">{title} →</h2><p className="mt-2 text-sm leading-6 text-[#666862]">{description}</p></Link>)}</section>
    <RuntimePerformance />
  </div></main>;
}
