import Link from "next/link";

export function StudioNav({ current }: { readonly current?: string }) {
  const links = [
    ["Home", "/"], ["New edit", "/jobs/new"], ["Jobs", "/jobs"], ["Library", "/library"],
    ["Brand", "/settings"], ["Usage", "/usage"], ["Operations", "/operations"], ["Access", "/access"],
  ] as const;
  return <nav aria-label="Studio navigation" className="flex flex-wrap items-center gap-x-4 gap-y-2">
    <Link className="mr-2 text-sm font-black tracking-tight text-[#173F5F]" href="/">GM Studio</Link>
    {links.map(([label, href]) => <Link aria-current={current === href ? "page" : undefined} className={`font-mono text-[10px] font-bold underline-offset-4 ${current === href ? "text-[#20211F] underline" : "text-[#53646F] hover:text-[#173F5F] hover:underline"}`} href={href} key={href}>{label}</Link>)}
  </nav>;
}
