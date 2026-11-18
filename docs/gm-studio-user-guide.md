# GM Studio User Guide

**In the app:** Open **Guide** in the main navigation for a concise first-edit walkthrough, brief examples, review checklist and delivery-file explanation. This document remains the detailed operating reference.

Status: Living guide
Updated: 2026-11-17
Audience: First-time creators and experienced editors using GM Studio

GM Studio turns selected source media into a source-led reel. You provide the footage and the outcome you want; the system analyses the available material, plans an edit, renders a preview and keeps you in control of approval and delivery. It does not invent recorded speech or silently replace explicit instructions with generic editing preferences.

This guide is maintained alongside the product. Options marked **Current** are available in the application now. Options marked **Planned redesign** describe the streamlined workflow being introduced and should not be treated as available until their implementation is complete.

## The editing journey

```text
CREATE                  PROCESS                 REVIEW                  DELIVER
Choose media         →  Analyse sources     →  Watch the preview    →  Download or publish
Describe the result     Plan the edit           Approve or revise       Create variants
Set hard constraints    Render a preview        Make quick fixes        Save preferences
```

**Current:** Create is a three-step wizard: **Choose media**, **Give direction**, then **Review & create**. Only the current step is shown. The final review summarises selected files, the interpreted brief, output format, duration, editing style and processing choices before the job is created.

At every stage, GM Studio should make three things clear: the current status, the next recommended action and where to change something.

## Start a new edit

### Choose media

Select existing media from the server library, upload new files from the current device, or combine both in one job. Selecting a library item attaches the existing original; it does not create another copy or upload it again.

**Current:** **From this device** and **Server library** are separate tabs, so the large library does not sit underneath the upload box. Existing media appears as a thumbnail grid instead of a long filename list. Search and the Recent, Video, Photos and Audio choices stay visible. Less common role, project and folder filters are grouped under **More filters**. Selected originals remain selected when you search, filter or change pages and can be reviewed from the selected-media panel.

After you create a job with new files, the **Upload handoff** shows one overall transfer and the state of each file. Keep the page open while bytes are still being sent. As soon as every transfer finishes, **Continue to editing** becomes available; you do not need to wait on that screen for server finalisation, source analysis or automatic interpretation. Those checks continue safely inside the queued edit, and rendering starts only after the sources are ready.

Choose footage that contains the complete story you want to tell. Include relevant supporting pictures or B-roll when you want the editor to cut away from the speaker. A file label helps organise the library but is not proof that a scene contains a particular person, product or action.

### Choose how pictures combine

**Current:** Composition is chosen alongside the source media, before the job starts:

- **Automatic:** Use the normal source-led workflow and let GM Studio choose an appropriate assembly.
- **Standard edit:** Use cuts, framing and supporting pictures without chroma keying.
- **Green screen:** Assign one presenter video as the foreground and a different photo or video as the full-frame background.

For green screen, the presenter source supplies both the keyed picture and the recorded speech. The background is a silent visual layer and is not treated as dialogue footage or B-roll. Both sources may come from the current device, the server Library or one from each. GM Studio saves and validates these roles before editing starts, then preserves them through preview and final export.

Use a reasonably even green background and avoid clothing or important objects close to the same green. The first preview uses conservative defaults. During review, open **Green-screen composition** to choose a green, blue or custom key colour and adjust background removal, edge softness and reflected-colour spill.

For an uneven or non-standard screen, pause the main preview on a representative frame and choose **Pick colour from current frame**. Tap an evenly lit screen area away from the presenter, shadows, glare and reflected spill. The sampler averages a small patch around the tap so one noisy pixel does not dominate the result. You can also position the sample with the arrow keys and press Enter. **Use this colour** only prepares the key setting; no job data is saved and no render starts until you select **Create composition preview**. If the browser cannot read the frame, use the green/blue presets or manual colour picker.

**Create composition preview** keeps the current cut, speech, captions, music and effects and makes a new local version with zero AI tokens. Source roles remain fixed after editing begins.

### Quality-test a green-screen edit

Use one short presenter clip with visible hair, hands and some movement. Choose a background with enough detail to reveal missed green edges, but avoid a very busy pattern for the first test.

1. Create the job in **Green screen** mode and assign both roles before submission.
2. Watch the first preview without tuning it. Note the exact moments where edges, shadows or reflected green look wrong.
3. If necessary, sample an evenly lit part of the screen, then adjust similarity in small steps. Increase edge blend only enough to soften chatter; excessive blend can erase hair and fingers. Add spill suppression only when reflected green is visible on skin, hair or clothing.
4. Create a composition preview and watch it at normal speed, paused on difficult edges, and full-screen on a phone.
5. Confirm that the background fills the frame, the presenter remains sharp, speech and captions stay synchronized, and no background audio has been introduced.
6. Open **Studio → Pilot acceptance**, choose the green-screen quality check and record the exact preview as Pass or Fail with the device and moments inspected.

A failed result is useful evidence. Record it before experimenting further so the affected version and settings remain identifiable.

## Find and organise media

**Current:** The main Library is a search-first gallery. The large search box is always available and can match display names, recorded words and indexed scene descriptions. Start typing from the folder home and GM Studio automatically opens the searchable **All media** view.

Use the Library in this order:

1. Search when you know what was said or pictured.
2. Use **All types**, **Videos**, **Photos**, **Audio**, **Talking footage**, **B-roll** or **Unsorted** to narrow the gallery.
3. Open **Filters** only when you need a category, favourite-only view, repeated uploads or a different sort order.
4. Open a thumbnail to preview the original and edit its name, notes, tags, category, footage role or folder membership.
5. Tick one or more thumbnails to open the selection tray. **Use in new edit** is the primary action; folder, category, rename, auto-sort and Trash actions are grouped under **Organize**.

The default grid is designed for visual scanning. Switch to **List** when filenames and detailed metadata matter more than pictures. Folders group related sources without copying them, and a source may belong to several folders. **Inbox** contains recent uploads that may still be undergoing local analysis. **Not in folders** is useful for cleaning up loose media.

Opening a thumbnail shows a focused preview panel. Watch or inspect the media first, then choose **Use this media in a new edit** when it is the source you need. Less common controls are grouped under **Edit name & labels**, **Find moments in this media**, **Folders**, and **File management**. This keeps destructive actions and technical catalogue evidence away from the main decision.

**Auto-sort** asks AI to suggest descriptive names, categories, footage roles and folders for a bounded set of files. Suggestions are reviewable and do not apply until you explicitly save them. Use manual labels when the intended role or subject is not evident from the source.

### Name the project

**Current:** A project name is optional. GM Studio suggests a short name from the first useful line of your brief, or from the selected media when the brief is empty. The suggested name is shown before submission and can always be replaced with your own, such as `Azura agency introduction` or `Spring product launch`.

### Describe the edit

The brief is the creative contract. Describe the result in ordinary language. It can be a broad request, an ordered list of points, an ordered scene plan or a complete script.

Examples:

```text
Make a short Instagram reel introducing our agency. Keep the explanation warm and credible. End on the client revenue result.
```

```text
- Introduce who we help
- Explain what makes the agency different
- End with the client result
```

```text
Scene 1: Introduce the founder
Scene 2: Explain the agency's speciality
Scene 3: Show client examples
Scene 4: End with the revenue result
```

```text
Use this script exactly:
Welcome to Azura Agency.
We help creators turn attention into revenue.
Talk to us today.
```

GM Studio interprets these forms differently:

| Brief type | What GM Studio preserves | What AI may decide |
| --- | --- | --- |
| Complete script | Recorded wording and order | Timing, framing, captions, music, effects and relevant supporting pictures |
| Ordered scenes | Every scene in order | The best source-backed shot and treatment inside each scene |
| Ordered dot points | Every point in order and its meaning | Exact source selection and presentation |
| General brief | Explicit requirements and exclusions | The most coherent source-backed structure |

If the recordings or maximum duration cannot support a supplied script or all required points, GM Studio should report the conflict. It must not silently remove content or invent words.

**Current:** New AI-planned edits also run a local transcript-backed contract check before rendering. When the transcript clearly contains a supplied script or ordered point, the proposed edit is rejected and corrected if it omits or reorders that material. Visual scene meaning and instructions that cannot be established from transcript evidence remain marked for human review rather than being reported as automatically verified.

### State what must remain true

Use **Must include** for facts, moments or recorded points that cannot be omitted. Put exclusions directly in the brief, for example `Do not use the backstage footage` or `No sales ending`.

Useful optional direction includes:

- Who the video is for
- What viewers should understand
- How viewers should feel
- How the video should end
- A required call to action
- Names or specialist terms that captions must spell correctly

Avoid using presentation settings to express story requirements. For example, `High impact` controls presentation; it does not mean that the editor may remove a required explanation.

## How instructions are prioritised

GM Studio uses the following order when instructions interact:

1. Rights, privacy and safety requirements
2. Recorded source truth
3. Explicit exclusions and material that must not be used
4. Supplied script, scene order or ordered points
5. Remaining brief and must-include direction
6. Complete understandable speech and story continuity
7. Optional music, effects and other creative treatment

AI may make low-risk, reversible creative decisions. You remain responsible for factual claims, permission to use the media, the intended audience, publication destination and final approval.

## Presentation options

**Current:** Presentation uses sensible defaults and is collapsed on the Create screen. The summary shows the active preset, shape, duration and pacing rule. Open **Optional presentation** only when the destination or treatment needs to differ from those defaults; leaving it closed does not disable any setting.

When the brief names exactly one supported destination—Instagram, TikTok, YouTube Short, LinkedIn or Facebook—GM Studio applies that publishing preset automatically. If you already changed a presentation control, your manual choice wins. Briefs naming several destinations keep the neutral custom setup so that one platform is not chosen arbitrarily.

### Duration

**Follow the story** asks for the shortest complete version up to the maximum. It does not pad the video to fill the available time.

**Aim for a duration** treats the selected duration as a preference while preserving complete required material.

**Strict duration** uses a hard limit. If the required script cannot fit, revise the script or increase the limit rather than expecting the editor to clip words or silently remove a point.

### Output shape

- **Vertical 9:16:** Reels, TikTok, Shorts and phone-first viewing
- **Landscape 16:9:** YouTube, websites, presentations and desktop viewing
- **Square 1:1:** Feed posts and platforms where square media is preferred

Choose the intended publishing destination when known. A publishing preset sets the recommended platform, shape and duration together; any individual adjustment you make afterwards takes precedence.

### Editing style

- **Follow my brief:** Uses explicit pacing from the brief and otherwise applies the saved presentation default
- **Clean:** Stable framing, restrained punch-ins and simple cuts
- **Energetic:** Faster pacing, emphasis punch-ins and occasional transitions
- **Calm:** Longer thoughts with subtle movement
- **High impact:** Frequent picture changes and accents where the footage supports them

An editing style never authorises changes to a supplied script or required scene order.

### Music

- **No music:** Voice and source sound only
- **Subtle:** Quiet rights-approved music beneath speech
- **Present:** More noticeable music with automatic speech ducking

Only approved local tracks are used. The editor should lower music around speech automatically, but you should listen to the preview before approval.

### Creative effects

Effects are optional presentation tools, not a quota. A selected effects level permits suitable effects; it does not require the editor to add one at every opportunity. Effects should be left out when they weaken speech, humour, readability or story clarity.

### Publishing preset and brand kit

A publishing preset supplies platform, shape and duration defaults. A brand kit supplies caption colours, type treatment and related presentation choices. Neither should override the current brief, supplied script or explicit exclusions.

## While GM Studio builds the preview

The processing screen shows four saved server milestones: **Upload complete**, **Source checks**, **Building edit**, and **Preview ready**. They are real states, not a percentage or a time estimate. You can safely close the page while a job is processing; the server continues working and the job remains available from **Jobs**.

Most users only need the current milestone and its short explanation. Open **Live status & technical details** when diagnosing a slow or interrupted job. It contains elapsed time, the latest server and worker check-ins, and the job timeline. Connection and stale-worker warnings appear automatically outside this section because they may need attention.

## Review a preview

Watch the complete preview with sound before approval. Check:

- The opening quickly establishes the subject
- Every required point or scene is present and in order
- Recorded words have not been clipped or changed
- Captions are correct and do not cover important content
- Music does not overpower speech
- Supporting pictures are relevant
- The ending completes the requested thought or action

**Current:** The main review decision appears directly after the video with three clear paths: **Approve and export**, **Ask editor for story change**, and **Make a small local fix**. A compact **What this preview uses** receipt shows clip, transition, supporting-visual, composition, sound/graphic, music and caption choices before the advanced controls.

Local finishing is organised by what you want to change rather than renderer terminology:

- **Story & timing:** Transitions, audio-picture joins and precise timeline work
- **Picture:** Framing, camera movement and colour
- **Layers & graphics:** Picture layers, callouts, pointers and visual effects
- **Sound & captions:** Voice levels, music placement and subtitle position

Choosing a group or control does not start processing. A new preview is created only when you use that control's explicit preview button. Quality reports, prompt history and technical details remain progressively disclosed. The optional future-edit rating is under **Teach future edits**, while the final-delivery view puts downloads first and keeps publishing and provenance details separate.

### Read the edit map

Open **Small local fixes**, then **Edit map**, for a compact view of where the current version uses story cuts and transitions, picture treatments, layers and graphics, sound, and captions. All rows share the same time scale. Use the category buttons to reduce clutter, then select a mark to read its saved name, timing and explanation.

The map is an inspection tool. Opening it, filtering it and selecting a mark never starts processing. **Preview** moves the existing player to that moment. **Open Story & timing**, **Open Picture**, **Open Layers & graphics** or **Open Sound & captions** takes you to the relevant editor; a new version is created only after that editor's explicit preview action. The collapsed text list underneath remains available when exact event names and timings are easier to use than the visual map.

### Change a transition

Open **Small local fixes**, then **Transitions between clips**. Choose the boundary by its outgoing and incoming clip names. **Preview** starts playback one second before that boundary so you can hear and see the change in context.

- **Cut:** Changes picture immediately and usually suits continuous speech or action.
- **Short dissolve:** Briefly blends the pictures for a gentler change. It does not overlap, move or shorten the recorded speech.
- **Dip to black:** Fades through black and is best for a clear change in time, place or topic.

Selecting a transition only prepares the change. GM Studio sends no job until you choose **Create transition preview**. That action changes one boundary, preserves clip order and words, creates a new local preview with zero AI editing calls, and keeps the current version available. Special transitions such as Paper Tear remain in **Layers & graphics** because they are expressive visual effects with separate eligibility checks.

### Request a revision

Describe the difference you want and what should stay unchanged. Precise instructions work best:

```text
Make the first five seconds faster. Keep the spoken wording and the rest of the edit unchanged.
```

```text
Remove the pause before the revenue example and lower the music under the final sentence.
```

```text
Keep every scene in the same order, but use fewer effects and calmer framing.
```

GM Studio should preserve unrelated strengths automatically. Use a story rebuild only when you want a materially different selection or structure.

### Correct captions

Use subtitle editing for spelling, punctuation and on-screen wording. Caption corrections retain the current cut and do not require a new story plan. Verify names, companies, product terms, prices and dates yourself.

### Use advanced editing

Advanced controls are appropriate when you need to:

- Reorder or remove individual clips
- Trim or split a precise source range
- Change per-clip framing or punch-ins
- Adjust a particular pause or audio level
- Remove or alter a specific effect
- Inspect the treatment timeline

Most first-time users should request a natural-language revision before changing individual clips.

## Approve and export

Approval freezes the selected version and starts its final-quality render. Before approving, confirm the version, captions, cover frame and delivery shape.

**Current:** A numeric cover time selects a frame by seconds into the edit.

**Planned redesign:** GM Studio will suggest visual cover thumbnails and allow selection from the video rather than requiring a number.

A preview download is not the same as the final export. The redesigned interface will label preview downloads explicitly and place final downloads in the Delivery stage.

## Deliver and reuse

After the final render, download the video or use an available publishing connection. Delivery tools may also create another shape or duration, download captions and package related assets.

Create a variant when the story remains valid but the destination changes. Request a revision when the story or content itself needs to change.

## Privacy, rights and AI use

**Current:** The active assembly choice, privacy mode and model effort are visible in the **Advanced editor controls** summary even when the section is closed. Open it when a job needs stricter privacy or an explicit processing choice; most ordinary edits can keep the defaults.

Privacy modes control what may be shared with the configured editor:

- **Hybrid:** Transcript text and selected low-resolution visual context may be shared
- **Text only:** Transcript, recognised text and metadata may be shared, but not images or original files
- **Local only:** Media-derived material remains on the server and editing uses supported local behaviour

Original files remain on the GM Studio server. Confirm that you have permission to use the selected media, music, likenesses and claims before publishing.

## Troubleshooting

### A required point is missing

Check that it appears clearly in the brief or Must include field and that the selected recordings contain it. If it is part of a list, format the list with bullets or numbers. Request a revision that identifies the missing point and asks to preserve the rest.

### The script was paraphrased or reordered

Label it explicitly with `Use this script exactly:` and place the script beneath that heading. Confirm that the selected recordings contain the words. If they do not, record the missing lines or allow a flexible adaptation.

### The result is too long

Ask for tighter pauses, repeated-take removal or a shorter introduction while naming the material that must remain. Do not use a strict limit that cannot contain the required script.

### The result is too busy

Request fewer effects, calmer framing or fewer picture changes. You can keep the script and clip order locked while changing presentation.

### Captions are wrong

Correct them in the subtitle editor. Add important names and spellings to the brief for future versions.

## Guide maintenance rules

Every user-facing change should update this guide in the same change set. When an option is renamed, moved or removed, update its instructions and status marker. Planned sections become Current only after the interface and behaviour are verified. New advanced controls require a plain-language purpose, guidance on when to use them and a warning when misuse could alter the story.
