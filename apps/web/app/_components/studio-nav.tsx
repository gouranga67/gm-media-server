import Link from "next/link";

const groups = [
  { label: "Home", href: "/", links: [] },
  { label: "Create", href: "/jobs/new", links: [["New edit", "/jobs/new"], ["Concepts & bloopers", "/concepts"]] },
  { label: "Library", href: "/library", links: [["Media", "/library"], ["Music & effects", "/creative"], ["Duplicates", "/library/duplicates"], ["Source knowledge", "/studio/knowledge"]] },
  { label: "Jobs", href: "/jobs", links: [["Edits", "/jobs"], ["Prompt history", "/prompts"]] },
  { label: "Studio", href: "/studio", links: [["Overview", "/studio"], ["Brand & presets", "/settings"], ["Learning", "/learning"], ["Usage", "/usage"], ["Operations", "/operations"], ["System & backup", "/system"], ["People", "/access"]] },
] as const;

export function StudioNav({ current = "/" }: { readonly current?: string }) {
  const active = groups.find((group) => group.href === current || group.links.some(([, href]) => href === current)) ?? (current.startsWith("/jobs/") ? groups[3] : undefined);
  return <div className="min-w-0">
    <nav aria-label="Studio navigation" className="flex flex-wrap items-center gap-x-4 gap-y-1">
      <Link className="mr-1 py-2 text-sm font-black tracking-tight text-[#173F5F]" href="/">GM Studio</Link>
      {groups.map((group) => <Link aria-current={current === group.href ? "page" : undefined} className={`min-h-11 content-center text-xs font-bold underline-offset-4 ${active === group ? "text-[#173F5F] underline" : "text-[#53646F] hover:underline"}`} href={group.href} key={group.href}>{group.label}</Link>)}
    </nav>
    {active && active.links.length > 0 ? <nav aria-label={`${active.label} tools`} className="flex flex-wrap gap-x-4 gap-y-1 border-t border-[#E7E8E4] pt-1">
      {active.links.map(([label, href]) => <Link aria-current={current === href ? "page" : undefined} className={`min-h-9 content-center text-xs underline-offset-4 ${current === href ? "font-bold text-[#173F5F] underline" : "text-[#53646F] hover:underline"}`} href={href} key={href}>{label}</Link>)}
    </nav> : null}
  </div>;
}
