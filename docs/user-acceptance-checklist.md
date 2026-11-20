# GM Studio hands on test checklist

Updated: 2026-11-03 (Australia/Brisbane).

Use this checklist to judge whether the deployed tools make useful reels. A successful render alone is not a pass: listen, watch and compare against the raw footage. Build `84b96419` is deployed; the [combined technical checkpoint](phase-reports/combined-acceptance-2026-11-02.md) records 536 passing backend tests, eight source gates, eight read-only live checks and a zero-AI NVENC fixture. The container-based core suite and hands-on acceptance remain pending. Start with the eight checks below; the later tables are a reference, not a requirement to test every control in one sitting.

## Start with these eight checks

1. Make a normal product reel from familiar footage. Check story, complete words, colour, captions, music and the ending.
2. Combine server talking footage with new B-roll and a review image from your computer. Check that all selections survive and the correct pictures support the speech.
3. Ask for one coherent story across several related recordings. Check that it uses useful contributions from more than one file without mixing product claims.
4. Make a slow, warm edit. Check that it does not inherit fast cuts or forced comic effects.
5. Generate fresh blooper ideas from known outtakes. Inspect the cited raw passages before selecting a concept. Check that the actual mistake and reaction make sense together.
6. Shorten a pause, correct a caption and boost one quiet phrase with the explicit local controls. Confirm the changes happen only where requested.
7. Add a readable review-card picture layer and move captions out of its way for that interval. Check the downloaded file too.
8. Approve/export one good edit and download it on your phone. Check the beginning, middle and end, then reopen it from Jobs.

## Prepare a small reusable test set

Keep one excellent existing edit as the baseline. Use fresh test jobs for changes so the baseline stays available. Gather a few talking clips, related alternate takes, genuine outtakes, silent product B-roll, a readable review image, one genuine transparent PNG, one HDR phone clip and a quiet/noisy speech clip. Green-screen tests need footage actually filmed against a green or blue background.

Work through one render at a time. Reuse the same small set rather than repeatedly uploading your whole library. Natural-language planning/revisions, concept generation, auto-sort and lesson trials use model requests. Explicit local finishing, precise edits, exact re-renders and delivery variants use local processing without another editor-model request. They still consume CPU/GPU time.

For every problem, record the job link, preview version, exact reel timestamp, brief, expected result and actual result. Identify whether you watched the web preview or a downloaded export. A useful report is: “Version 3, 0:08–0:10: I asked to boost this phrase, but its volume did not change.”

## Brief-first form and compatibility

| ID | Test | Pass when |
| --- | --- | --- |
| R1 | Select media, write a brief, leave Advanced alone | No recipe selection is required. After analysis, the assembly and reason appear before Start editing. |
| R2 | Add a brief starter, edit it, then apply a saved profile | The visible text is editable; no upload/model request starts from the shortcut. A profile changes presentation defaults, not purpose or assembly. |
| R3 | “Use montage-style cutaways, but keep my whole explanation” with talking video, product B-roll and a review photo | It retains a speech spine and can use the supporting pictures without requiring High impact pacing. |
| R4 | “Make a slow, warm visual montage” with photos and silent scenes | The interpretation uses visual assembly and calm pacing. Actual playback matches the mood. |
| R5 | “Do not make an ad; explain the product” and a separate blooper request | The first stays a story; the second uses blooper guidance without sales requirements. Filenames and project titles do not change the intent. |
| R6 | Inspect an explicit conflict, change Advanced, then Apply | The conflict blocks Start editing before a model call. Changing a field alone sends nothing; Apply updates the interpretation. Starting fixes the engine for retries/revisions. |
| R7 | Submit insufficient media: one still, a very short silent video, or separate audio narration | A useful compatibility message appears. No invented/duplicated filler or paid planning request is used to hide the limit. |
| R8 | Reopen an excellent old job, exact re-render it and inspect a new library concept job | Old engines, timing and approved plans remain intact. New concepts resolve once before their ordinary planning request. Compare real playback and usage. |

## Story and source selection

| ID | Test | Pass when |
| --- | --- | --- |
| S1 | Familiar product explanation with a short brief | The actual product is introduced, supported information stays connected, and the ending makes sense. |
| S2 | Good footage with little direction | The editor finds a coherent supported story without inventing claims or narration. |
| S3 | Several related recordings | Complementary recordings contribute where useful; alternate takes are compared rather than all repeated. |
| S4 | Several unrelated recordings | It avoids misleading connections and explains a narrower choice instead of forcing every file into one story. |
| S5 | Normal footage containing false starts and bloopers | The ordinary edit favours usable takes and avoids readiness chatter and long empty waits. |
| S6 | Slow, warm brief with restrained effects | Pacing and sound support the requested feeling; it is not padded to reach the target duration. |
| S7 | High-impact edit with effects enabled | Picture/sound changes support real beats, dialogue remains intelligible, and no speaking take becomes mismatched silent B-roll. |
| S8 | Two products with different claims | Names, demonstrations, reviews and benefits stay attached to their actual product. |

## Bloopers and concepts

| ID | Test | Pass when |
| --- | --- | --- |
| B1 | Generate fresh ideas from known recorded stumbles | Each offered gag has an intelligible setup, an actual incident clue and a real reaction/recovery where present. Review the linked raw ranges: a short stumble should not require watching a whole pitch or full product list. Generate fresh ideas after the incident-focus update; saved ideas retain their old passages. |
| B2 | Material containing only repeated clean takes | It declines automatic blooper generation rather than treating repetition alone as a joke. Purely visual comedy still needs manual review. |
| B3 | Short complete gag | It stays short instead of adding explanation, silence or unrelated reactions to reach five seconds or the target length. |
| B4 | ASR text split across a sentence | The edit does not start on a disconnected continuation or end on an accidental fragment after the comic beat. |
| B5 | Select and render a concept | The preview follows the selected recorded story; it does not substitute a conventional ad or manufacture laughter. |
| B6 | Reopen saved ideas | Reopening does not generate another request. Previously created jobs remain accessible. An older weak idea may be refused for a new job. |
| B7 | Review a blooper job | The screen identifies bloopers and gives outtake guidance, without sales-payoff checkboxes or a required call to action. |

## Library and uploads

The [folder-first library increment](phase-reports/library-folders-2026-11-03.md) is implemented in source and needs deployment. Existing collections become flat folders; nested folders and assisted filing are later work. Check the five deployment-acceptance steps in that report before reorganising a large batch.

| ID | Test | Pass when |
| --- | --- | --- |
| L1 | Upload a mixed batch directly to Library | Files become available without creating editing jobs. Processing and failures are visible. |
| L2 | Use server footage plus device uploads in one job | Selections persist across source switches and each original is attached once. |
| L3 | Pause/resume an upload or briefly interrupt the connection | The existing transfer resumes; it does not register another original or job. Keep the original file available until Ready. |
| L4 | Filter talking footage, B-roll, photos, audio and collections | Each view shows the expected sources; a photo category is distinct from a video footage role. |
| L5 | Rename, tag, favourite and categorise a source | Details persist and appear when choosing media for a new job. The original recording remains unchanged. |
| L6 | Auto-sort a small mixed batch | Suggestions describe the actual content and preserve manual work. Review folder choices; names-only Apply leaves memberships unchanged. Explicitly opt in to filing, confirm existing/new folders and reopen the saved result. |
| L7 | Speech search, scene search and recognised review text | Results point to relevant sources/ranges. Check the raw media; similarity or OCR alone is not proof. |
| L8 | Add a product name and aliases in Studio knowledge | Its real mentions are consistently identified without transferring unrelated claims to it. |
| L9 | Mark a source range Avoid | Fresh concepts/plans avoid that range. An older frozen edit remains available. |
| L10 | Move one disposable test source to Trash, then restore it | It disappears from new-job selection, restores correctly and does not break an existing edit. Trash does not reclaim its file storage. |
| L11 | Review exact duplicates | The chosen canonical record persists. If testing storage cleanup, use only an intentionally duplicated test file and confirm referenced edits still play. |
| L12 | Create a folder and add several selected videos/photos | Submission is explicit, membership persists and the originals still appear in All media. One item can belong to several folders. |
| L13 | Remove a member, rename a folder, then remove the test folder | Only the intended grouping changes; media, other memberships and existing edits remain. Removing a folder requires confirmation. |
| L14 | Change folder, filters and Grid/List, leave and return | The browsing location and display return without replaying selection. Search results remain inside the selected folder. |
| L15 | Find reel ideas from a folder | A fresh concept brief opens with that folder selected. Opening the page makes no generation request. |

## Revisions and precise editing

Use one good test reel for this group. Precise controls refer to source time; finishing windows refer to reel time. Review each resulting version rather than stacking many uninspected changes.

| ID | Test | Pass when |
| --- | --- | --- |
| E1 | Type revision feedback without submitting | Nothing starts automatically; text remains available. |
| E1a | After deploying the camera timing fix, open **Shed life 1** and choose **Re-render exact edit**, then export | The speaking shot following the soap-cutting cutaway remains in sync through its punch-in. The story, source ranges and cutaway stay the same; no new AI usage is added. Inspect both preview and final MP4. |
| E2 | Submit one clear natural-language change | The requested content or structure actually changes, with unrelated strengths preserved where possible. A rewritten summary alone is not enough. |
| E2a | Ask to raise only the final quiet speech clip, keeping its words and picture | That same clip becomes louder relative to neighbouring dialogue; the change report lists its gain. The agent must not substitute a different closing take as a volume fix. |
| E2b | Trim a dangling word at the end of a phrase | The excluded word stays excluded after rendering; protective word handles do not bring its beginning back. Check the exact range change and listen to the join. |
| E3 | Use the story-rebuild revision option | It can replace/reorder unlocked material rather than mechanically repeating the rejected draft. |
| E4 | Trim at word boundaries | Complete words remain audible and synchronized; source seconds are not confused with reel seconds. |
| E5 | Split, move or remove a clip | The intended passage changes, remaining audio is continuous and retained overlays follow the content. |
| E6 | Tighten one long pause | Waiting shrinks without clipping words or removing the intended reaction. |
| E7 | Correct caption wording | Matching on-screen text changes; the recorded speech and unrelated captions remain intact. |
| E8 | Try a cut, dip and picture dissolve | The chosen picture transition is visible without shortening dialogue or producing black flashes. |
| E9 | Restore a previous ready version | A new preview reproduces that version; previous versions and approved deliveries remain accessible. |
| E10 | Submit from an old browser tab after making a newer version | Stale edits are refused with a refresh instruction rather than silently applied to the wrong cut. |
| E11 | Try a local hook audition on an ordinary story | It changes the opening using actual recorded speech and preserves intelligibility. This control is intentionally absent for bloopers. |

Replacement-take selection is currently exposed through the typed agent/API tool rather than a dedicated form picker. Test it when using that tool: choose another attached take and verify its source identity, dialogue, duration and captions. A missing visible replacement picker is not evidence that the underlying tool failed.

## Finishing tools

Open **Finishing tools · local preview** on a ready job. These tools require explicit submission; having them available does not mean the initial planner automatically uses all of them.

| ID | Test | Pass when |
| --- | --- | --- |
| F1 | Targeted camera move on one clip | The move occurs at the chosen time and keeps the intended face/product visible without unwanted jumps. |
| F2 | Phrase audio level over a short reel interval | The phrase is audibly louder/quieter, neighbouring speech stays stable and loud changes do not clip. |
| F3 | Gentle voice denoising | Background noise improves without making the voice metallic or swallowing words. |
| F4 | Timed captions: lower, middle, upper, then hidden | Placement changes only during the specified windows; words stay synchronized. Compare with actual social-app controls on a phone. |
| F5 | Selected-clip colour adjustment on normal and HDR footage | The selected shot changes as requested, skin/highlights look plausible and no new washed-out or clipped appearance appears. |
| F6 | Review image as a contained picture layer | The whole intended card remains readable, with no accidental fill-crop or caption collision. |
| F7 | Picture-in-picture, circle crop, opacity and entrance animation | Size/position/timing match the settings. A circle intentionally crops; a rectangle contains the image. |
| F8 | Genuine transparent PNG | Actual transparency reveals the underlying video. A checkerboard baked into the image is not transparency. |
| F9 | Prepared green/blue-screen chroma keying | The chosen screen colour disappears with acceptable edges. This mode is labelled as requiring a real solid screen. |
| F9b | Replace background beta with white, timber or ordinary room wall | The review page creates a bounded two-second original/result/mask comparison using the chosen background. Inspect hair, hands, held items, holes and flicker. The edit, original and final export remain unchanged; a usable sample is not yet production approval. |
| F10 | Retime or freeze a silent picture layer | Its visual timing changes without speeding, slowing or desynchronizing the main speech. |
| F11 | Selected music and excerpt start | The chosen track is audible from the requested part, speech remains clear and the ending fades appropriately. |
| F12 | Independent audio/picture join at a quiet boundary | One clip's recorded audio can lead or trail its picture without cutting a word, overlapping unrelated speech or moving captions to the wrong audio. |
| F13 | One-pass local pause repair | It creates one new preview with no model request and no repeated background repair cycle. Compare the comic timing before/after. |
| F14 | Clear local finishing or restore a saved version | The test changes can be reversed and the prior useful edit remains accessible. |

Automatic subject tracking, learned background removal, optical-flow slow motion and automatic shot matching are not shipped. Their absence is not a failed test of the current tools.

## Delivery and phone use

| ID | Test | Pass when |
| --- | --- | --- |
| D1 | Download the preview and approve/export one good version | Both files play; the final uses the approved cut and correct shape, captions, colours, music and effects. |
| D2 | Inspect the final package | Expected media, caption/credit/provenance files are present; source and licence information refer to the actual selected material. |
| D3 | Make a shorter or differently shaped delivery variant | The variant retains complete usable content; cropping and captions suit its shape and the original delivery stays available. No additional editor-model tokens are used. |
| D4 | Re-render exact edit | The cut stays the same while current local processing is used; no fresh editorial/model request occurs. |
| D5 | Open, play, scrub and download on a physical phone | Portrait/landscape layout works, buttons are reachable, playback is in sync and the downloaded file plays outside the browser. |
| D6 | Reopen Jobs, original prompt and revision history | The original brief and version history remain visible; preview-ready and final-delivered states are distinguishable. |

## Feedback and learning

| ID | Test | Pass when |
| --- | --- | --- |
| R1 | Save a rating, tags, topic and timestamped note | Values persist against the correct job/version; entering feedback does not start a render. |
| R2 | Propose lessons after repeated feedback on different ordinary jobs | Proposals are visible and remain inactive until evaluated/promoted. Revisions of one job do not count as independent training examples. |
| R3 | Try a lesson on genuinely fresh footage | It creates an explicit normal editor revision, preserves baseline and candidate, and records its model usage. Checksums overlapping training footage or prior trial footage are refused, including shared supporting pictures. Reencoded copies are not automatically recognised as the same recording. |
| R4 | Watch and rate three source-independent held-out comparisons | Explicit playback review binds each score to its exact versions and provenance. Promotion requires no lower candidate ratings and at least one improvement to an executable edit. A higher rating on an unchanged cut earns no positive credit; old scores without qualifying evidence need review. |
| R5 | Promote, then roll back an evaluated lesson | Future applicable jobs receive/remove the guidance; prior edits remain unchanged. |
| R6 | Make bloopers after ordinary clean-take feedback | Clean-take lessons do not override the outtake purpose. Blooper feedback is retained, but dedicated blooper learning is future work. |

Do the lesson trials last: they need additional model requests and genuinely fresh footage. Ten comments alone do not establish that a proposed rule improved output.

## System and shared studio checks

| ID | Test | Pass when |
| --- | --- | --- |
| O1 | Open System and Studio during normal work | Deployed build, job state, stage timings and queues are understandable. An older failed job warning is distinguishable from a current deployment failure. |
| O2 | Upload a small clip while another job renders | The interface/search stay usable and analysis/render work progresses without missing or duplicated jobs. |
| O3 | Check local/off-site backup status | Recent successful results are visible. Use the existing isolated restore verifier for recovery acceptance; do not overwrite the live library. |
| O4 | Test intended editor/viewer access with another user | Permitted actions work and disallowed actions are refused. The current product is one shared private studio, not isolated customer workspaces. |
| O5 | Test a failure/retry when it actually occurs | The reason is visible and retry acts on the intended job/version. A provider overload must not silently trigger repeated paid requests. |

Reboot-during-render recovery is a separate maintenance test using the existing drill. Schedule it when no valuable work is running; an ordinary user test session does not require another reboot.

## Record the results

Mark each test **Pass**, **Fail**, **Not tested** or **Not applicable**. For creative tests, record both technical success and whether you would publish the result. Fix story, word cuts, caption readability, colour and voice/music balance before judging whether more decorative effects would help.

| Test ID | Job and version | Timestamp | Expected versus actual | Result |
| --- | --- | --- | --- | --- |
| | | | | |

The automated commands and recovery lanes remain in the [technical testing plan](testing-plan.md).

Resume check: leave a newly saved job before pressing Start editing, then reopen it from Jobs. It should say the edit has not started, show its readiness/interpretation, and start only when you press the button.

Progress check: after pressing Start editing, the screen should show Queued, Planning, Rendering, then the ready preview. Queued may be brief, and an exact re-render can skip planning. Waiting/run elapsed time and worker check-ins should remain distinct. Disconnect the browser network briefly: it should report that status cannot refresh, preserve the last known stage, and resume updates when connected. A delayed worker check-in is an uncertainty notice, not a claim that the edit has failed. No percentage or completion time is promised.

Story consistency acceptance: generate fresh ordinary story ideas after deploying this increment. In each script, check that a condition such as “If your skin gets dry…” stays connected to its recorded recommendation. Choose one concept and verify that its opening, explanation and ending survive in the rendered order, without an unrelated spoken claim replacing them. A complete shorter story is acceptable. In Local quality review, expand Story selection and cleanup to inspect passage/order checks, measured audio coverage and exact cleanup changes; these are not an automatic story-quality score. Compare a normal story containing a genuine empty wait and quiet closing take, then a calm/intentional-reaction edit that should keep its pacing. Finally reopen an older excellent edit and make a targeted revision: its saved cut should remain accessible and explicit revisions should retain their existing freedom.

Publishing acceptance: follow [Meta publishing setup](meta-publishing-setup.md). Open a ready approved final export, prepare a draft and verify that choosing caption options, editing copy and saving do not publish. Confirm the export version, exact wording and named account before one explicit Post now action. Check the actual post on Instagram, then Facebook separately before combined posting. A scheduled-post test must show the correct device timezone and stay queued until due. An expired connection should request reconnection. After a lost response, use the existing remote-status check rather than submitting another post. Owner-only access and non-public media delivery remain in force; automated tests do not replace a first authorized real Meta post.

## Creative alternatives

| ID | Test | Pass when |
| --- | --- | --- |
| A1 | Open Make another version on a good completed edit | Opening options and changing the choice/direction create no job or model request. |
| A2 | Choose Different cut, same story, then Create one alternative preview | One new version appears; the core message remains coherent and its opening/takes/pacing/treatment provide a worthwhile alternative. Watch and compare both versions. |
| A3 | Choose Find a different story on footage with several recorded subjects/angles | The editor explores another supported recorded angle rather than changing music on the old script. A library concept's earlier script is unlocked, while factual/source restrictions remain. |
| A4 | Use a narrowly constrained recording without worthwhile alternatives | A repeated result is reported honestly as similar; the studio does not keep spending requests automatically. |
| A5 | While an alternative runs, open saved versions | Earlier retained previews play and download; restoring is disabled while another run is active. |
| A6 | Choose an earlier version as current after completion | A new version uses its saved plan with zero AI calls; existing approvals and exports remain recorded. |
| A7 | Compare request failure/retry and original controls | Direction text survives a failure, an uncertain retry reuses its request ID, and normal targeted revisions/exact re-render still work. |

Each explicitly generated alternative consumes an editing request and a local render. Analysis is reused; existing invalid-plan repair may add its bounded repair request. Similarity is a local heuristic over up to eight completed versions of this job, not a story-quality guarantee or a cross-job novelty check.

## Adaptive duration

| ID | Test | Pass when |
| --- | --- | --- |
| D1 | Create a new edit with Follow the story | The visible maximum defaults to 90s. The result can finish sooner and keeps the full recorded thought without padding. |
| D2 | Retry the previously failed 60.6s / 60s-preference job after deployment | The migrated flexible policy allows up to 72s. It no longer fails solely because it crossed 60s. Check all five points and the complete final explanation by listening. |
| D3 | Open Duration settings on that saved job | Changing fields does nothing until Save. Saving creates no edit; press Try again separately. No re-upload is needed. |
| D4 | Compare Aim for 60s with Strict maximum 60s | Aim permits up to 72s within the configured cap. Strict remains at 60s: measured empty waits may be trimmed, otherwise it asks for an increased cap, condensed version or split. No clipped words or accelerated voice. |
| D5 | Change a ready job's next-edit cap below the approved version's length | Exact re-render/export of the approved version still uses its saved policy. A new AI revision/alternative uses the new cap. |
| D6 | Make a story over 60s, within a chosen maximum up to 120s | Late captions, effects, B-roll, finishing windows and timestamped feedback work; actual duration and policy appear below playback. Check the final export too. |

The preflight speech estimate includes repeated takes and is not a verified measurement of the required script. Automatic splitting and semantic proof that every requested point survived are not implemented; use the brief, available duration settings and playback review.

## Creative toolkit

| ID | Test | Pass when |
| --- | --- | --- |
| FX1 | Open Library → Music & effects | The sounds/graphics appear with previews; searches and type filters find the expected assets. |
| FX2 | Select several licensed files | Nothing uploads until Import unfinished files is pressed. Each file has its own editable title/source link. |
| FX3 | Import one duplicate and retry an unfinished file | Completed imports stay in place, the duplicate is skipped, and only unfinished files are sent again. |
| FX4 | Edit one effect’s guidance | Mood, energy and use/avoid notes persist without re-uploading or changing its file. |
| FX5 | Make a fresh Social/Meme-heavy edit with a real reveal/reaction | Relevant accents appear at earned moments, speech stays clear and the story stays coherent. A sound and graphic can share one beat. Effects are not compulsory decoration. |
| FX6 | Add a short callout or list counter in Finishing tools | Only explicit submission creates a local preview; the words appear at the chosen reel time, clear of dialogue captions. |
| FX7 | Add a fixed arrow/circle | It points at the intended detail during its interval. It does not claim to follow moving objects. |
| FX8 | Add a one-second music pause on a reel with music | Music fades down and returns, speech continues normally, and the exported MP4 matches the preview. |

## Save the release results

After deployment, use **Studio → Pilot acceptance** to record these observations against the displayed build. Select the exact edit version or published result, describe what happened, confirm you checked it, then Save. Unlike the earlier page checkboxes, these records survive leaving the page. Record failures too. A new deployed build needs fresh checks; earlier records remain in history. The machine evidence section links to System, Operations and Publishing and distinguishes missing setup from completed real tests. Full instructions and read-only acceptance commands are in the Phase 31 section of [the technical testing plan](testing-plan.md).
