import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";
import {
  ArrowRightIcon,
  CheckCircle2Icon,
  ClipboardCheckIcon,
  DownloadIcon,
  FileTextIcon,
  LibraryIcon,
  PlayCircleIcon,
  SearchIcon,
  FolderOpenIcon,
  SlidersHorizontalIcon,
  SparklesIcon,
  UploadCloudIcon,
} from "lucide-react";

import { StudioNav } from "@/app/_components/studio-nav";

export const metadata: Metadata = {
  title: "Guide",
  description: "Learn how to create, review, revise, and export an edit in GM Studio.",
};

const workflow = [
  {
    title: "Choose media",
    description: "Upload from this device, select existing library media, or combine both. Continue as soon as file transfer finishes; analysis continues in the queued edit.",
    icon: UploadCloudIcon,
  },
  {
    title: "Give direction",
    description: "Describe the outcome. A script, numbered points, or scene order becomes the editing contract.",
    icon: FileTextIcon,
  },
  {
    title: "Review the preview",
    description: "Watch once with sound, then approve, ask for a story change, or make a deterministic local fix.",
    icon: PlayCircleIcon,
  },
  {
    title: "Export",
    description: "Approval creates the full-quality MP4, captions, cover image, post copy, and provenance package.",
    icon: DownloadIcon,
  },
] as const;

const briefExamples = [
  {
    label: "Simple direction",
    copy: "Make a warm 30-second Instagram Reel. Keep the explanation together and finish on the result.",
  },
  {
    label: "Ordered points",
    copy: "Use these points in order: 1. the problem, 2. how we solved it, 3. the result, 4. the invitation.",
  },
  {
    label: "Exact script",
    copy: "Use this script exactly:\n[Paste the recorded wording here in the order it should appear.]",
  },
] as const;

function SectionTitle({ eyebrow, title, children }: { readonly eyebrow: string; readonly title: string; readonly children: ReactNode }) {
  return (
    <div className="max-w-3xl">
      <p className="font-mono text-[10px] font-bold tracking-widest text-[#174D73] uppercase">{eyebrow}</p>
      <h2 className="mt-2 text-2xl font-black tracking-tight text-[#173F5F]">{title}</h2>
      <div className="mt-3 text-sm leading-6 text-[#666862]">{children}</div>
    </div>
  );
}

export default function GuidePage() {
  return (
    <main className="min-h-dvh bg-[#F7F7F5] px-4 pt-[max(1rem,env(safe-area-inset-top))] pb-[max(3rem,env(safe-area-inset-bottom))] text-[#20211F] sm:px-6">
      <div className="mx-auto max-w-6xl">
        <header className="border-b border-[#D7D9D3] pb-6">
          <StudioNav current="/guide" />
          <div className="mt-8 grid gap-6 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-end">
            <div className="max-w-3xl">
              <p className="font-mono text-[10px] font-bold tracking-widest text-[#174D73] uppercase">Start here</p>
              <h1 className="mt-2 text-3xl font-black tracking-tight text-[#173F5F] sm:text-4xl">Make your first edit without learning an editing program</h1>
              <p className="mt-4 max-w-2xl text-sm leading-6 text-[#666862]">
                You choose the source material and describe the result. GM Studio builds a reviewable preview, while keeping scripts, required points, and your manual choices under your control.
              </p>
            </div>
            <div className="flex flex-col gap-2 sm:flex-row lg:flex-col">
              <Link className="inline-flex min-h-12 items-center justify-center gap-2 rounded-md bg-[#173F5F] px-5 text-sm font-bold text-white" href="/jobs/new">
                Start a new edit <ArrowRightIcon aria-hidden="true" className="size-4" />
              </Link>
              <Link className="inline-flex min-h-12 items-center justify-center gap-2 rounded-md border border-[#A9C0D0] bg-white px-5 text-sm font-bold text-[#173F5F]" href="/library">
                <LibraryIcon aria-hidden="true" className="size-4" /> Browse media
              </Link>
            </div>
          </div>
        </header>

        <section className="scroll-mt-6 py-10" id="first-edit">
          <SectionTitle eyebrow="The 60-second guide" title="One job, four decisions">
            <p>You do not need to configure every option. For a normal first edit, complete these four steps and leave the optional sections closed.</p>
          </SectionTitle>
          <ol className="mt-6 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            {workflow.map(({ title, description, icon: Icon }, index) => (
              <li className="rounded-md border border-[#D7D9D3] bg-white p-5" key={title}>
                <div className="flex items-center justify-between">
                  <Icon aria-hidden="true" className="size-5 text-[#174D73]" />
                  <span className="font-mono text-[10px] font-bold text-[#666862]">0{index + 1}</span>
                </div>
                <h3 className="mt-5 font-bold text-[#173F5F]">{title}</h3>
                <p className="mt-2 text-xs leading-5 text-[#666862]">{description}</p>
              </li>
            ))}
          </ol>
        </section>

        <section className="border-t border-[#D7D9D3] py-10" id="library">
          <SectionTitle eyebrow="Your media library" title="Search first; organise only when it helps">
            <p>The Library is a visual workspace, not a filing requirement. Search recorded words or scenes, scan thumbnails, then select the sources you want.</p>
          </SectionTitle>
          <div className="mt-6 grid gap-3 md:grid-cols-3">
            {[
              [SearchIcon, "Find anything", "Use the large search box for filenames, spoken words, or indexed scene descriptions."],
              [FolderOpenIcon, "Browse visually", "Use media-type tabs and the thumbnail gallery. Folders group sources without copying them."],
              [SlidersHorizontalIcon, "Act on a selection", "Tick one or more items. Start a new edit immediately, or open Organize for folders, labels, names, and Trash."],
            ].map(([Icon, title, description]) => {
              const LibraryGuideIcon = Icon as typeof SearchIcon;
              return <article className="rounded-md border border-[#D7D9D3] bg-white p-5" key={title as string}><LibraryGuideIcon aria-hidden="true" className="size-5 text-[#174D73]" /><h3 className="mt-4 font-bold text-[#173F5F]">{title as string}</h3><p className="mt-2 text-xs leading-5 text-[#666862]">{description as string}</p></article>;
            })}
          </div>
          <p className="mt-4 text-xs leading-5 text-[#666862]">Open <strong>Filters</strong> only for category, favourites, repeated uploads, sort order, or AI-assisted auto-sort. Open a thumbnail to preview it and edit detailed metadata.</p>
          <div className="mt-4 rounded-md border border-[#BFD2DE] bg-[#EFF6FA] p-5 text-sm leading-6 text-[#53646F]">
            For green screen, choose <strong>Green screen</strong> while selecting media, then assign one presenter video and one background photo or video. You can mix a device upload with Library media. The presenter supplies the recorded speech; the background remains a silent visual layer.
          </div>
        </section>

        <section className="border-t border-[#D7D9D3] py-10" id="briefs">
          <SectionTitle eyebrow="Writing the brief" title="Say what must happen before describing the style">
            <p>GM Studio reads your brief as a contract. Put required wording and order first. Add tone, pacing, music, and effects afterwards.</p>
          </SectionTitle>
          <div className="mt-6 grid gap-4 lg:grid-cols-[0.9fr_1.1fr]">
            <article className="rounded-md border border-[#BFD2DE] bg-[#EFF6FA] p-5">
              <h3 className="font-bold text-[#173F5F]">Priority order</h3>
              <ol className="mt-4 space-y-3 text-sm text-[#53646F]">
                {["Exact script or required recorded words", "Numbered points or requested scene order", "The outcome and intended audience", "Optional treatment such as pacing, music, captions and effects"].map((item, index) => (
                  <li className="flex gap-3" key={item}><span className="font-mono text-xs font-bold text-[#174D73]">{index + 1}</span><span>{item}</span></li>
                ))}
              </ol>
              <p className="mt-5 border-t border-[#C9DDE8] pt-4 text-xs leading-5 text-[#53646F]">
                If the recording or duration cannot support a required script or point, GM Studio should report the conflict instead of silently inventing or removing content.
              </p>
            </article>
            <div className="space-y-3">
              {briefExamples.map((example) => (
                <article className="rounded-md border border-[#D7D9D3] bg-white p-4" key={example.label}>
                  <p className="font-mono text-[10px] font-bold tracking-wide text-[#174D73] uppercase">{example.label}</p>
                  <p className="mt-2 whitespace-pre-line text-sm leading-6 text-[#20211F]">{example.copy}</p>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section className="border-t border-[#D7D9D3] py-10" id="decisions">
          <SectionTitle eyebrow="Who decides?" title="Let the AI handle presentation; keep meaning with the human">
            <p>Automatic choices reduce form-filling, but they must never outrank an explicit instruction or a manual setting.</p>
          </SectionTitle>
          <div className="mt-6 grid gap-4 md:grid-cols-2">
            <DecisionCard icon="ai" title="GM Studio can decide" items={[
              "Which complete recorded passages best satisfy the brief",
              "A sensible duration when you choose Follow the story",
              "Framing, pacing, captions, transitions, music and effects",
              "The platform preset when the brief names one clear destination",
              "Whether an optional effect helps; selected effects are not quotas",
            ]} />
            <DecisionCard icon="human" title="You remain responsible for" items={[
              "Selecting the correct private source material",
              "The exact script, required claims, names, prices and dates",
              "Whether visual scenes match the intended meaning",
              "Final quality, rights, factual accuracy and permission to publish",
              "Approving the version that becomes the full-quality export",
            ]} />
          </div>
        </section>

        <section className="border-t border-[#D7D9D3] py-10" id="processing">
          <SectionTitle eyebrow="While the edit is building" title="You can close the page and come back later">
            <p>The processing screen reports saved server milestones rather than a made-up percentage or finish time. The job continues on the server even when this page is closed.</p>
          </SectionTitle>
          <ol className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
            {["Upload complete", "Source checks", "Building edit", "Preview ready"].map((milestone, index) => (
              <li className="border-t-4 border-[#173F5F] pt-3 text-xs font-bold text-[#173F5F]" key={milestone}>
                <span className="mr-2 font-mono text-[10px] text-[#666862]">0{index + 1}</span>
                {milestone}
              </li>
            ))}
          </ol>
          <div className="mt-6 rounded-md border border-[#BFD2DE] bg-[#EFF6FA] p-5 text-sm leading-6 text-[#53646F]">
            Use <strong>Jobs</strong> to return to the edit. Open <strong>Live status &amp; technical details</strong> only when you want elapsed time, worker check-ins, or the event timeline. Connection and stale-worker warnings appear automatically when they matter.
          </div>
        </section>

        <section className="scroll-mt-6 border-t border-[#D7D9D3] py-10" id="review">
          <SectionTitle eyebrow="Reviewing a preview" title="Watch once, then choose one path">
            <p>The first screen is intentionally a decision point. Detailed controls stay closed until you ask for them.</p>
          </SectionTitle>
          <div className="mt-6 grid gap-3 md:grid-cols-3">
            <ReviewCard emphasized title="Approve & export">Use when the story, words, captions, audio and visuals are ready. This starts the final-quality render.</ReviewCard>
            <ReviewCard title="Ask editor for story change">Describe one specific correction and say what must remain unchanged. Rebuild the story only when the structure is wrong.</ReviewCard>
            <ReviewCard title="Make a small local fix">Choose Story & timing, Picture, Layers & graphics, or Sound & captions. Processing starts only when you explicitly create a new preview.</ReviewCard>
          </div>
          <p className="mt-4 rounded-md border border-[#D7D9D3] bg-white p-4 text-sm leading-6 text-[#53646F]">
            <strong>What this preview uses</strong> summarises the applied treatment. Green-screen jobs also show <strong>Green-screen composition</strong>, where you can choose a preset, enter a colour, or pause the preview and sample an evenly lit part of the screen. Sampling only prepares the setting; adjust background removal, edge softness and colour spill, then explicitly create a zero-AI local preview.
          </p>
          <div className="mt-4 rounded-md border border-[#BFD2DE] bg-[#EFF6FA] p-5 text-sm leading-6 text-[#53646F]">
            <h3 className="font-bold text-[#173F5F]">Find a treatment on the edit map</h3>
            <p className="mt-2">Open <strong>Small local fixes</strong>, then <strong>Edit map</strong>. The Story, Picture, Layers, Sound and Captions rows share one time scale, so you can see where the current version changes without reading a long event list.</p>
            <p className="mt-2">Select a mark to inspect its saved timing and explanation. <strong>Preview</strong> moves the existing player to that moment; <strong>Open…</strong> takes you to the relevant editor. Inspecting and filtering the map never changes the edit, renders a preview or calls AI.</p>
          </div>
          <div className="mt-4 rounded-md border border-[#D7D9D3] bg-white p-5 text-sm leading-6 text-[#53646F]">
            <h3 className="font-bold text-[#173F5F]">Changing the picture between two clips</h3>
            <p className="mt-2">Open <strong>Small local fixes</strong>, then <strong>Transitions between clips</strong>. Choose a named clip boundary and use <strong>Preview</strong> to start playback one second before it.</p>
            <ul className="mt-3 space-y-2">
              <li><strong>Cut</strong> changes picture immediately and usually suits continuous speech.</li>
              <li><strong>Short dissolve</strong> briefly blends the pictures without moving or shortening speech.</li>
              <li><strong>Dip to black</strong> marks a clear change in time, place or topic.</li>
            </ul>
            <p className="mt-3">Selecting an option does no work. <strong>Create transition preview</strong> changes only that boundary and creates a zero-AI local preview. Special effects such as Paper Tear stay in <strong>Layers &amp; graphics</strong>.</p>
          </div>
          <div className="mt-4 rounded-md border border-[#D7D9D3] bg-white p-5">
            <h3 className="font-bold text-[#173F5F]">Before approving, check these five things</h3>
            <ol className="mt-4 grid gap-3 text-sm text-[#53646F] sm:grid-cols-2 lg:grid-cols-5">
              {["The opening makes sense", "Required words and order are present", "Speech joins sound natural", "Captions are correct and readable", "The ending feels complete"].map((item, index) => <li className="flex gap-2" key={item}><span className="font-mono text-xs font-bold text-[#174D73]">{index + 1}</span>{item}</li>)}
            </ol>
          </div>
        </section>

        <section className="border-t border-[#D7D9D3] py-10" id="settings">
          <SectionTitle eyebrow="Finding settings" title="Options appear where they affect the workflow">
            <p>Most users can keep the defaults. Open a section only when the job actually needs a different choice.</p>
          </SectionTitle>
          <div className="mt-6 overflow-hidden rounded-md border border-[#D7D9D3] bg-white">
            {[
              ["Before editing", "Media, brief, platform, shape, duration, pacing, privacy and model effort"],
              ["While reviewing", "Transitions, subtitles, clip order, pauses, framing, audio balance, colour, green-screen key tuning and effect removal"],
              ["At approval", "Cover frame and the decision to start the full-quality export"],
              ["After delivery", "Downloads, publishing, alternate local formats and reusable creative profiles"],
            ].map(([stage, options]) => <div className="grid gap-1 border-b border-[#E7E8E4] p-4 last:border-0 sm:grid-cols-[10rem_1fr]" key={stage}><strong className="text-sm text-[#173F5F]">{stage}</strong><span className="text-sm leading-6 text-[#666862]">{options}</span></div>)}
          </div>
        </section>

        <section className="border-t border-[#D7D9D3] py-10" id="delivery">
          <SectionTitle eyebrow="Delivery files" title="Download only what you need">
            <p>The complete package is safest for archiving. Individual files are available when you are posting immediately.</p>
          </SectionTitle>
          <dl className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {[
              ["Final MP4", "The full-resolution finished video."],
              ["Captions", "Timed subtitle text for platforms or accessibility."],
              ["Cover image", "The selected still frame for a thumbnail or post cover."],
              ["Post copy", "Suggested accompanying text when available."],
              ["Provenance", "A record of source-led editing, checks and processing."],
              ["Complete package", "A ZIP containing the delivery files together."],
            ].map(([term, description]) => <div className="rounded-md border border-[#D7D9D3] bg-white p-4" key={term}><dt className="font-bold text-[#173F5F]">{term}</dt><dd className="mt-2 text-xs leading-5 text-[#666862]">{description}</dd></div>)}
          </dl>
        </section>

        <section className="rounded-md border border-[#BFD2DE] bg-[#EFF6FA] p-6 sm:flex sm:items-center sm:justify-between sm:gap-6">
          <div><h2 className="text-xl font-bold text-[#173F5F]">Ready for a first edit?</h2><p className="mt-2 text-sm text-[#53646F]">Choose a small set of media and write one clear outcome. The defaults will handle the rest.</p></div>
          <Link className="mt-4 inline-flex min-h-12 w-full items-center justify-center gap-2 rounded-md bg-[#173F5F] px-5 text-sm font-bold text-white sm:mt-0 sm:w-auto" href="/jobs/new">Create an edit <ArrowRightIcon aria-hidden="true" className="size-4" /></Link>
        </section>
      </div>
    </main>
  );
}

function DecisionCard({ icon, title, items }: { readonly icon: "ai" | "human"; readonly title: string; readonly items: readonly string[] }) {
  const Icon = icon === "ai" ? SparklesIcon : ClipboardCheckIcon;
  return (
    <article className={`rounded-md border bg-white p-5 ${icon === "ai" ? "border-[#BFD2DE]" : "border-[#D7D9D3]"}`}>
      <div className="flex items-center gap-2"><Icon aria-hidden="true" className="size-5 text-[#174D73]" /><h3 className="font-bold text-[#173F5F]">{title}</h3></div>
      <ul className="mt-4 space-y-3 text-sm text-[#53646F]">
        {items.map((item) => <li className="flex gap-2" key={item}><CheckCircle2Icon aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-[#307455]" />{item}</li>)}
      </ul>
    </article>
  );
}

function ReviewCard({ title, emphasized = false, children }: { readonly title: string; readonly emphasized?: boolean; readonly children: ReactNode }) {
  return (
    <article className={`rounded-md bg-white p-5 ${emphasized ? "border-2 border-[#173F5F]" : "border border-[#D7D9D3]"}`}>
      <h3 className="font-bold text-[#173F5F]">{title}</h3>
      <p className="mt-2 text-xs leading-5 text-[#666862]">{children}</p>
    </article>
  );
}
