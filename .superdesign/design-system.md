# GM Studio design system

## Product character

GM Studio is a private media-production appliance reached from a phone over Tailscale. The interface should feel calm, dependable, and operational: a compact studio console rather than a consumer social app. It must explain what the Lenovo server is doing without exposing infrastructure jargon in the primary flow.

The product edits only media supplied by the user. Agents may plan cuts, pacing, captions, crops, layouts, and written copy when explicitly allowed. They never generate replacement video, images, voices, music, or synthetic people. Show this promise in plain language near job creation.

## Visual direction

Use a technical minimalist paper-and-harbor palette with flat surfaces and hairline structure.

- Page: warm paper `#F7F7F5`.
- Main ink and primary action: deep harbor blue `#173F5F`.
- Main text: charcoal `#20211F`.
- Secondary text: muted graphite `#666862` with accessible contrast.
- Rules and inactive borders: `#D7D9D3`.
- Card surface: `#FFFFFF` or the page color where hierarchy remains clear.
- Selected/progress accent: pale sky `#BFE3FF`, normally paired with harbor-blue text.
- Healthy/online status: restrained green `#3A8F63`, used only as a semantic status dot or small indicator.
- Attention/progress accent: coral `#FF8C69`.
- Secondary status accent: gold `#F4D35E`.
- Error: the existing destructive token.

Use existing CSS variables where possible, extending them locally for the paper and harbor-blue direction. Do not fetch remote fonts. Use the existing system sans stack for body and headings and the existing system mono stack for compact labels, file sizes, timestamps, and server status. Headings are firm and compact, with restrained tracking. Avoid all gradients, shadows, glass effects, glow, and decorative imagery.

## Geometry and spacing

- Phone reference viewport: 390 × 844 px, while remaining responsive from 320 px upward.
- Use a single-column application shell with 16 px side padding and safe-area padding at the top and bottom.
- Structure sections with 1 px rules, rectangular blocks, and a 2 px to 8 px corner radius. Keep controls slightly softer than structural panels.
- Use an 8 px base spacing rhythm. Section gaps are 24 to 32 px. Related controls are 8 to 12 px apart.
- Minimum touch target is 44 × 44 px.
- Keep the primary action in a sticky bottom action area so it remains reachable with one hand.
- Use dense information sparingly. Operational details such as file size, progress, and connection status use compact mono labels.

## Application shell

The phone shell has a compact top bar with the text identity `GM Studio`, a private-online status badge, and an optional storage-health line. Do not invent a logo or use an image mark. The content scrolls behind a stable top identity and ends above a sticky bottom submission bar.

The job creation route is `/jobs/new`. It is a focused form, not a dashboard. Use a clear heading, a short source-only explanation, and numbered or strongly separated sections that follow the order in which someone acts after filming.

## Components

### Status badge

Compact pill or squared badge with a status dot and text such as `Private · Online`. The small green dot indicates a healthy private connection; surrounding text and controls use harbor blue. Do not imply public internet exposure.

### Recipe cards

Recipe choices are full-width tap targets with name, outcome, and format. `Talking-head Reel` is selected and available, described as `15–60 sec · 9:16`. Future recipes such as `Montage` and `Photo Post` may appear as disabled rows with a restrained `Later` label. Disabled options should remain legible and obviously unavailable.

### Text fields

Labels remain visible above inputs. Provide concrete examples in placeholders without replacing labels. The brief should help a person specify audience, key message, pacing, and any must-keep moments. Error text appears directly below the affected field.

### Privacy mode

Show three selectable cards or a compact radio group:

- `Hybrid`: local files; approved text reasoning may use a configured cloud model.
- `Text only`: local files; transcript and text metadata may be sent for reasoning.
- `Local only`: files and reasoning stay on this server.

Describe each choice in one short sentence. Keep the actual selected state obvious through border, background, and radio state, not color alone.

### Source media picker

Use a large touch-friendly file picker labelled `Add source media`. State supported video, photo, and audio and `Up to 20 GB per file`. It may have a hairline/dashed outline, but should remain consistent with the technical grid. Never display stock or generated thumbnails in an empty picker.

### Upload queue

Each file row includes filename, type/size, current status, and progress. Show a simple horizontal progress bar for active uploads. Actions such as pause, resume, retry, and remove need accessible labels and 44 px targets. Ready files use a check mark and `Ready`. Copy should reassure the user that an interrupted phone upload will continue when the browser reconnects.

### AI-written copy option

This is a separate explicit opt-in. Label it `Allow AI-written caption copy` and leave it off by default. Supporting text must say this affects text only; uploaded visuals and audio remain the only media used in the edit.

### Primary action

The sticky primary button reads `Create job & upload`. The action area may summarize the number and total size of selected files. Disabled, busy, upload, success, and failure states must be distinguishable in text as well as visually.

## Interaction and accessibility

- All controls use semantic form elements and visible focus rings.
- Labels and status must not rely on color alone.
- Use native mobile file selection with multiple media files accepted.
- Preserve form state if upload preparation fails.
- Uploads are resumable and show truthful byte progress.
- Respect reduced-motion preferences. Use only short, functional transitions for progress or expanded detail.
- Maintain WCAG AA contrast for essential text and controls.
- Avoid exposing internal service names, ports, database terms, or container details in the task flow. A later system page can explain the stack.

## Content voice

Use short, direct sentences. Prefer `Add source media`, `Brief`, `Privacy`, `Ready`, and `Try again`. Explain agent behavior concretely: `Agents plan the edit. Your uploaded footage, photos, and audio are the only media used.`
