#!/usr/bin/env node
// DOM interaction checks with fake HTTP and upload transport; no live jobs or media.
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { afterEach, beforeEach, test } from "node:test";
import { Window } from "happy-dom";

const require = createRequire(import.meta.url);
const repo = path.resolve(import.meta.dirname, "..");
const dom = new Window({ url: "http://localhost/jobs/new" });
for (const name of ["window", "document", "navigator", "HTMLElement", "HTMLInputElement", "HTMLTextAreaElement", "File"]) {
  Object.defineProperty(globalThis, name, { configurable: true, value: name === "window" ? dom : dom[name] });
}
const { Event } = dom;
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const React = require("react");
const { act } = React;
const { createRoot } = require("react-dom/client");
const ts = require("typescript");
const Module = require("node:module");
const originalLoad = Module._load;
let lessonProposed = false;
let calls = [], transfers = [], navigation = [], readyEvents = 0, analysisStatus = "ready", root, managedAssets = [], batchFailure = false, conceptHistory = [], renderConceptFailure = false, conceptCounter = 0, organizationHistory = [], organizationFailure = false;
const serverId = "11111111-1111-4111-8111-111111111111";
const jobId = "22222222-2222-4222-8222-222222222222";
const serverAsset = {
  id: serverId, project_id: "33333333-3333-4333-8333-333333333333", project_name: "Talking footage",
  source_name: "talking.mp4", mime_type: "video/mp4", byte_size: 100, sha256: "fixture-checksum",
  duration_seconds: 10, thumbnail_available: false, created_at: "2026-01-01T00:00:00Z",
};
Module._load = function (request, parent, isMain) {
  if (request === "next/navigation") return { useRouter: () => ({ push: (url) => navigation.push(url) }) };
  if (request === "next/link") return { __esModule: true, default: ({ children, ...props }) => React.createElement("a", props, children) };
  if (request === "@/lib/resumable-upload") return {
    startResumableUpload: async (file, asset, callbacks) => {
      const transfer = { file, asset, callbacks, pauses: 0, resumes: 0 };
      transfers.push(transfer);
      return { abort: async () => { transfer.pauses += 1; }, start: () => { transfer.resumes += 1; } };
    },
  };
  if (request.startsWith("@/")) request = path.join(repo, "apps/web", request.slice(2));
  return originalLoad.call(this, request, parent, isMain);
};
for (const extension of [".ts", ".tsx"]) Module._extensions[extension] = (module, filename) => {
  const { outputText, diagnostics } = ts.transpileModule(fs.readFileSync(filename, "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022,
      jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true }, fileName: filename, reportDiagnostics: true,
  });
  const errors = diagnostics.filter((diagnostic) => diagnostic.category === ts.DiagnosticCategory.Error);
  assert.equal(errors.length, 0, errors.map((diagnostic) => ts.flattenDiagnosticMessageText(diagnostic.messageText, "\n")).join("\n"));
  module._compile(outputText, filename);
};
const { NewJobForm } = require(path.join(repo, "apps/web/app/_components/new-job-form.tsx"));
const { ConceptDesk } = require(path.join(repo, "apps/web/app/_components/concept-desk.tsx"));
const { MediaLibrary } = require(path.join(repo, "apps/web/app/_components/media-library.tsx"));
const { LearningLabPanel } = require(path.join(repo, "apps/web/app/_components/learning-lab.tsx"));
const { PreciseClipEditor } = require(path.join(repo, "apps/web/app/_components/precise-clip-editor.tsx"));
const { FinishingWorkspace } = require(path.join(repo, "apps/web/app/_components/finishing-workspace.tsx"));
const { SourceKnowledge } = require(path.join(repo, "apps/web/app/_components/source-knowledge.tsx"));
const { SourceRanges } = require(path.join(repo, "apps/web/app/_components/source-ranges.tsx"));
const { LibraryUpload } = require(path.join(repo, "apps/web/app/_components/library-upload.tsx"));

globalThis.fetch = async (url, options = {}) => {
  const route = String(url).replace("/api/media/", "");
  const body = options.body ? JSON.parse(options.body) : undefined;
  calls.push({ route, method: options.method ?? "GET", body });
  let payload;
  if (route === "learning/lab") payload = { lessons: lessonProposed ? [{ id:serverId,recipe:"talking_head",edit_style:"high_impact",status:"proposed",directive:"Keep complete clean speech.",training_job_ids:[jobId,"training-b","training-c"],evaluation:{held_out_jobs:0,can_promote:false,rating_delta:null,regressions:0} }] : [],trials:[],jobs:[] };
  else if (route === "learning/lab/propose") { lessonProposed=true;payload={matched_proposals:1,hosted_model_calls:0}; }
  else if (route === "library/knowledge") payload = { products: [], evidence_version: "1.0" };
  else if (/^library\/products\//.test(route)) payload = { ...body, id: route.split("/").at(-1) };
  else if (route.endsWith("/ranges") && route.startsWith("library/assets/")) payload = [];
  else if (route.includes("/ranges/") && route.startsWith("library/assets/")) payload = body;
  else if (route === `jobs/${jobId}/revisions`) payload = { id: "revision", version: 3, status: "pending" };
  else if (route === `jobs/${jobId}/finishing-tools`) payload = { version: 2, settings: { motions:[],colours:[],audio_regions:[],caption_regions:[],layers:[],music_start_seconds:0,voice_denoise:false,audio_joins:[] }, sources:[{ asset_id:serverId,name:"Review image",media_kind:"image",duration_seconds:0 }] };
  else if (route === "concepts/library-status") payload = { unique_sources: 3, catalogued_sources: 3, spoken_sources: 2, visually_indexed_sources: 3, still_processing: 0 };
  else if (route === "concepts" && (options.method ?? "GET") === "GET") payload = conceptHistory;
  else if (route === "concepts") {
    const created = conceptSession(body.id, body.focus, body.reel_kind);
    conceptHistory.unshift(created);
    conceptCounter += 1;
    payload = { ...created, status: "pending" };
  }
  else if (/^concepts\/[^/]+\/render$/.test(route)) {
    if (renderConceptFailure) return { ok: false, status: 409, json: async () => ({ detail: "Some footage was moved to Trash" }) };
    const session = conceptHistory.find((item) => item.id === route.split("/")[1]);
    for (const id of body.concept_ids) if (!session.jobs.some((job) => job.concept_id === id)) session.jobs.push({ concept_id: id, job_id: crypto.randomUUID() });
    payload = { jobs: session.jobs.filter((job) => body.concept_ids.includes(job.concept_id)) };
  }
  else if (/^concepts\/[^/?]+$/.test(route)) payload = conceptHistory.find((item) => item.id === route.split("/")[1]);
  else if (route === "library/organization" && (options.method ?? "GET") === "GET") payload = organizationHistory;
  else if (route === "library/organization") {
    const session = { id: body.id,asset_ids:body.asset_ids,status:"ready",total_tokens:500,error:null,applied_asset_ids:[],created_at:"2026-01-01T00:00:00Z",
      suggestions:body.asset_ids.map((id) => { const item = managedAssets.find((asset) => asset.id === id); return {
        asset_id:id,previous_name:item.display_name,display_name:item.mime_type.startsWith("image/") ? "Image of customer review" : "Talking about soap",
        mime_type:item.mime_type,media_role:item.mime_type.startsWith("image/") ? "auto" : "talking",media_category:"review",tags:["review"],confidence:"supported",reason:"Supported by the supplied preview or recorded words.",
      }; }) };
    organizationHistory.unshift(session); payload={ ...session,status:"pending" };
  }
  else if (/^library\/organization\/[^/]+\/apply$/.test(route)) {
    if (organizationFailure) return { ok:false,status:409,json:async () => ({ detail:"Library details changed; no files were changed" }) };
    const session=organizationHistory.find((item) => item.id === route.split("/")[2]);
    for (const suggestion of body.suggestions) {
      Object.assign(managedAssets.find((item) => item.id === suggestion.asset_id),suggestion);
      session.applied_asset_ids.push(suggestion.asset_id);
    }
    payload={updated:body.suggestions.length,applied_asset_ids:session.applied_asset_ids};
  }
  else if (/^library\/organization\/[^/?]+$/.test(route)) payload=organizationHistory.find((item) => item.id === route.split("/")[2]);
  else if (route.startsWith("library/assets?")) {
    const params = new URLSearchParams(route.split("?")[1]);
    payload = params.get("offset") === "0" ? managedAssets : [];
  }
  else if (route === "library/collections") payload = [];
  else if (route.startsWith("catalog/search?")) payload = { results: [{ asset_id: "broll", segment_kind: "visual", text: "Cream on the shelf", rank: 1 }] };
  else if (route === "library/assets/batch") {
    if (batchFailure) return { ok: false, status: 409, json: async () => ({ detail: "Refresh the library before changing these files" }) };
    for (const [index, id] of body.asset_ids.entries()) {
      const asset = managedAssets.find((item) => item.id === id);
      if (!asset) continue;
      if (body.action === "rename") asset.display_name = body.asset_ids.length === 1 ? body.name_prefix : `${body.name_prefix} ${String(index + 1).padStart(3, "0")}`;
      if (body.action === "role") asset.media_role = body.media_role;
      if (body.action === "category") asset.media_category = body.media_category;
      if (body.action === "trash" || body.action === "restore") asset.library_status = body.action === "trash" ? "archived" : "active";
    }
    payload = { updated: body.asset_ids.length, action: body.action };
  }
  else if (/^library\/assets\/[^/?]+$/.test(route)) payload = { asset: managedAssets.find((item) => item.id === route.split("/").at(-1)), collections: [], evidence: [], visual_frames: [] };
  else if (route === "projects") payload = { ...body, id: body.id };
  else if (/^projects\/[^/]+\/jobs$/.test(route)) payload = { ...body, id: jobId };
  else if (/^projects\/[^/]+\/assets$/.test(route)) payload = { ...body, project_id: route.split("/")[1], status: "registered" };
  else if (/^assets\/[^/]+\/analysis$/.test(route)) payload = { status: analysisStatus, error: analysisStatus === "failed" ? "Analysis fixture failed" : null };
  else if (/^assets\/[^/?]+$/.test(route)) payload = { id: route.split("/")[1], status: "ready" };
  else if (route.startsWith("assets/library")) payload = [serverAsset];
  else if (route === `jobs/${jobId}/assets`) payload = { job_id: jobId, attached_count: body.asset_ids.length };
  else if (route === `jobs/${jobId}/preview`) payload = { id: "preview", status: "queued" };
  else if (route === "catalog/visual/status") payload = { assets_pending: 0, assets_failed: 0, assets_ready: 1, frames_total: 1 };
  else if (["system", "client-diagnostics"].includes(route)) payload = {};
  else if (["music-tracks", "creative-assets?active=true", "editor/models", "creative-profiles", "brand-kits"].includes(route)) payload = [];
  else throw new Error(`Unexpected fixture request: ${route}`);
  return { ok: true, status: 200, json: async () => payload };
};

beforeEach(() => {
  window.history.replaceState(null, "", "/jobs/new");
  calls = []; transfers = []; navigation = []; readyEvents = 0; analysisStatus = "ready"; batchFailure = false; conceptHistory = []; renderConceptFailure = false; conceptCounter = 0;
  organizationHistory = []; organizationFailure = false;
  managedAssets = [
    { ...serverAsset, id: "talk", source_name: "VID_0001.mp4", display_name: "Product introduction", media_role: "talking", job_references: 2 },
    { ...serverAsset, id: "broll", source_name: "VID_0002.mp4", display_name: "Cream close-up", media_role: "broll", job_references: 0 },
    { ...serverAsset, id: "unsorted", source_name: "VID_0003.mp4", display_name: "VID_0003.mp4", media_role: "auto", job_references: 0 },
  ].map((item) => ({ notes: "", tags: [], favorite: false, library_status: "active", collection_count: 0, visual_status: "ready", updated_at: item.created_at, ...item }));
  lessonProposed=false;
  window.sessionStorage.clear();
  document.body.innerHTML = '<div id="root"></div>';
  root = createRoot(document.getElementById("root"));
});
afterEach(async () => { await act(async () => root.unmount()); await dom.happyDOM.abort(); });
const tick = () => new Promise((resolve) => setTimeout(resolve, 10));
async function waitFor(predicate) {
  for (let i = 0; i < 100; i += 1) { if (predicate()) return; await act(async () => { await tick(); }); }
  assert.ok(predicate(), "UI did not reach the expected state");
}
async function mountLibrary() {
  await act(async () => root.render(React.createElement(LibraryUpload, { onReady: async () => { readyEvents += 1; } })));
}
function button(label) {
  const found = [...document.querySelectorAll("button")].find((item) => item.textContent.trim() === label);
  assert.ok(found, `Missing button: ${label}`); return found;
}
async function click(element) { assert.ok(element); await act(async () => element.click()); }
async function selectFiles(selector, files) {
  const input = document.querySelector(selector);
  assert.ok(input, `File picker unavailable alongside server selection: ${selector}`);
  Object.defineProperty(input, "files", { configurable: true, value: files });
  await act(async () => input.dispatchEvent(new Event("change", { bubbles: true })));
}
async function type(selector, value) {
  const input = document.querySelector(selector);
  Object.getOwnPropertyDescriptor(input instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype, "value").set.call(input, value);
  await act(async () => input.dispatchEvent(new Event("input", { bubbles: true })));
}
const clip = (name = "close-up.mp4") => new File(["synthetic upload fixture"], name, { type: "video/mp4" });
const posts = (suffix) => calls.filter((call) => call.method === "POST"
  && (call.route === suffix.replace(/^\//, "") || call.route.endsWith(suffix)));

test("one job combines selected server footage and a device upload, with an explicit edit start", async () => {
  await act(async () => root.render(React.createElement(NewJobForm)));
  await waitFor(() => document.querySelector(`input[aria-label="Use ${serverAsset.source_name}"]`));
  await click(document.querySelector(`input[aria-label="Use ${serverAsset.source_name}"]`));
  await selectFiles('input[aria-label="Add files from this device"]', [clip()]);
  assert.match(document.body.textContent, /1 from server \+ 1 from this device/);
  await type("#project-name", "Mixed source reel");
  await type("#project-brief", "Keep my voice and show product close-ups.");
  await act(async () => document.querySelector("form").dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })));
  await waitFor(() => transfers.length === 1);
  assert.equal(posts("projects").length, 1);
  assert.equal(posts("/jobs").length, 1);
  assert.deepEqual(posts(`/jobs/${jobId}/assets`)[0].body.asset_ids, [serverId]);
  const uploadRequests = posts("/assets").filter((call) => call.route.startsWith("projects/"));
  assert.equal(uploadRequests.length, 1);
  assert.equal(uploadRequests[0].body.job_id, jobId);
  assert.equal(uploadRequests[0].body.source_name, "close-up.mp4");
  assert.equal(posts("/preview").length, 0);
  await act(async () => transfers[0].callbacks.onSuccess());
  await waitFor(() => document.body.textContent.includes("Start editing"));
  await click(button("Start editing"));
  assert.equal(posts("/preview").length, 1);
  assert.deepEqual(navigation, [`/jobs/${jobId}`]);
});

test("library upload waits for submission, creates no job, resumes, and refreshes after analysis", async () => {
  await mountLibrary();
  await type('input:not([type="file"])', "Product close-ups");
  await selectFiles('input[type="file"]', [clip()]);
  assert.equal(calls.length, 0, "Selecting files must not automatically submit them");
  await click(button("Upload 1 file to library"));
  await waitFor(() => transfers.length === 1);
  assert.equal(posts("projects").length, 1);
  assert.equal(posts("projects")[0].body.name, "Product close-ups");
  assert.equal(posts("/assets")[0].body.job_id, null);
  await click(document.querySelector('button[aria-label="Pause close-up.mp4"]'));
  assert.equal(transfers[0].pauses, 1);
  await click(document.querySelector('button[aria-label="Resume close-up.mp4"]'));
  assert.equal(transfers[0].resumes, 1);
  await act(async () => transfers[0].callbacks.onSuccess());
  await waitFor(() => readyEvents === 1);
  assert.match(document.body.textContent, /Ready in your library/);
  await selectFiles('input[type="file"]', [clip("second-close-up.mp4")]);
  await click(button("Upload 1 file to library"));
  await waitFor(() => transfers.length === 2);
  assert.equal(posts("projects").length, 1, "More files use the same batch project");
  assert.equal(posts("/jobs").length, 0);
  assert.equal(posts("/preview").length, 0);
});

test("checking failed analysis never uploads or registers the original twice", async () => {
  await mountLibrary(); analysisStatus = "failed";
  await selectFiles('input[type="file"]', [clip()]);
  await click(button("Upload 1 file to library"));
  await waitFor(() => transfers.length === 1);
  await act(async () => transfers[0].callbacks.onSuccess());
  await waitFor(() => document.body.textContent.includes("Original saved; analysis needs attention"));
  assert.equal(readyEvents, 0);
  analysisStatus = "ready";
  await click(document.querySelector('button[aria-label="Check status of close-up.mp4"]'));
  await waitFor(() => readyEvents === 1);
  assert.equal(posts("/assets").length, 1);
  assert.equal(transfers.length, 1);
});

test("network errors resume the existing transfer instead of registering another original", async () => {
  await mountLibrary();
  await selectFiles('input[type="file"]', [clip()]);
  await click(button("Upload 1 file to library"));
  await waitFor(() => transfers.length === 1);
  await act(async () => transfers[0].callbacks.onError(new Error("Connection lost")));
  await click(document.querySelector('button[aria-label="Resume close-up.mp4"]'));
  assert.equal(transfers[0].resumes, 1);
  assert.equal(posts("/assets").length, 1);
});

test("invalid and empty files are rejected before any server mutation", async () => {
  await mountLibrary();
  await selectFiles('input[type="file"]', [new File(["text"], "notes.txt", { type: "text/plain" }), new File([], "empty.mp4", { type: "video/mp4" })]);
  assert.match(document.body.textContent, /supported video, photo, or audio/);
  assert.match(document.body.textContent, /empty.mp4 is empty/);
  assert.equal(calls.length, 0);
  assert.equal(button("Upload to library").disabled, true);
});

async function chooseOption(selector, value) {
  const select = document.querySelector(selector);
  assert.ok(select, `Missing select: ${selector}`);
  await act(async () => { select.value = value; select.dispatchEvent(new Event("change", { bubbles: true })); });
}
async function mountBrowser() {
  await act(async () => root.render(React.createElement(MediaLibrary)));
  await waitFor(() => document.querySelector('input[aria-label="Select Product introduction"]'));
}

test("library separates B-roll and talking footage, preserves search, and keeps uploads collapsed", async () => {
  await mountBrowser();
  assert.equal(document.getElementById("library-import").hidden, true);
  await click(button("B-roll"));
  assert.ok(document.querySelector('input[aria-label="Select Cream close-up"]'));
  assert.equal(document.querySelector('input[aria-label="Select Product introduction"]'), null);
  await click(button("Unsorted"));
  assert.ok(document.querySelector('input[aria-label="Select VID_0003.mp4"]'));
  await click(button("All media"));
  await type('input[type="search"]', "shelf");
  await waitFor(() => document.body.textContent.includes("Cream on the shelf"));
  assert.equal(document.querySelector('input[aria-label="Select Product introduction"]'), null);
  await click(button("Add media"));
  assert.equal(document.getElementById("library-import").hidden, false);
});

test("batch names preserve original filenames and role changes move only the displayed selection", async () => {
  await mountBrowser();
  await click(button("Unsorted"));
  await click(document.querySelector('input[aria-label="Select displayed files"]'));
  await chooseOption('select[aria-label="Label selected videos"]', "broll");
  await waitFor(() => managedAssets.find((item) => item.id === "unsorted").media_role === "broll");
  assert.deepEqual(posts("library/assets/batch").at(-1).body.asset_ids, ["unsorted"]);
  await waitFor(() => !document.querySelector('[aria-label="Selected media actions"]'));
  await click(button("B-roll"));
  await click(document.querySelector('input[aria-label="Select displayed files"]'));
  await click(button("Rename batch"));
  await type('input[placeholder="e.g. Cream close-up"]', "Cream texture");
  await act(async () => document.querySelector('section[aria-label="Selected media actions"] form').dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })));
  await waitFor(() => document.body.textContent.includes("Cream texture 002"));
  assert.equal(managedAssets.find((item) => item.id === "talk").display_name, "Product introduction");
  assert.ok(managedAssets.every((item) => item.source_name.startsWith("VID_")));
  await click(button("All media"));
  await click(document.querySelector('button[aria-label="Rename Product introduction"]'));
  await type('input[placeholder="e.g. Cream close-up"]', "New product intro");
  await click(button("Save names"));
  await waitFor(() => document.body.textContent.includes("New product intro"));
});

test("Trash requires an explicit click and confirmation, preserves used originals, and can restore", async () => {
  await mountBrowser();
  await click(document.querySelector('input[aria-label="Select Product introduction"]'));
  await click(button("Move to Trash"));
  assert.equal(posts("library/assets/batch").length, 0);
  assert.match(document.body.textContent, /1 are used by existing jobs/);
  await click(button("Confirm move to Trash"));
  await waitFor(() => !document.querySelector('input[aria-label="Select Product introduction"]'));
  assert.equal(managedAssets.find((item) => item.id === "talk").job_references, 2);
  await click(button("Trash (1)"));
  await click(document.querySelector('input[aria-label="Select Product introduction"]'));
  await click(button("Restore selected"));
  await waitFor(() => managedAssets.find((item) => item.id === "talk").library_status === "active");
  assert.equal(calls.some((call) => call.method === "DELETE"), false);
});

test("failed bulk actions retain the selection and display the server error", async () => {
  await mountBrowser(); batchFailure = true;
  await click(document.querySelector('input[aria-label="Select Product introduction"]'));
  await click(button("Move to Trash"));
  await click(button("Confirm move to Trash"));
  await waitFor(() => document.querySelector('[role="alert"]')?.textContent.includes("Refresh the library"));
  assert.equal(document.querySelector('input[aria-label="Select Product introduction"]').checked, true);
  assert.equal(managedAssets[0].library_status, "active");
});

test("uploads can be named and labelled as B-roll without creating an edit", async () => {
  await mountLibrary();
  await type('input[aria-label="Upload file name prefix"]', "Lotion texture");
  await chooseOption('select[aria-label="Upload footage role"]', "broll");
  await selectFiles('input[type="file"]', [clip()]);
  await click(button("Upload 1 file to library"));
  await waitFor(() => transfers.length === 1);
  await act(async () => transfers[0].callbacks.onSuccess());
  await waitFor(() => readyEvents === 1);
  const updates = posts("library/assets/batch").map((call) => call.body);
  assert.ok(updates.some((body) => body.action === "rename" && body.name_prefix === "Lotion texture 001"));
  assert.ok(updates.some((body) => body.action === "role" && body.media_role === "broll"));
  assert.equal(posts("/jobs").length, 0);
});

test("new-job picker shows readable names and filters footage roles without dropping selected sources", async () => {
  serverAsset.display_name = "Finished product close-up";
  serverAsset.media_role = "broll";
  try {
    await act(async () => root.render(React.createElement(NewJobForm)));
    await waitFor(() => document.body.textContent.includes("Finished product close-up"));
    await click(document.querySelector(`input[aria-label="Use ${serverAsset.source_name}"]`));
    await chooseOption('#library-purpose', 'talking');
    assert.equal(document.querySelector(`input[aria-label="Use ${serverAsset.source_name}"]`), null);
    assert.match(document.body.textContent, /1 from server \+ 0 from this device/);
    await chooseOption('#library-purpose', 'broll');
    assert.equal(document.querySelector(`input[aria-label="Use ${serverAsset.source_name}"]`).checked, true);
    await type('#library-search', 'Finished product');
    await waitFor(() => document.querySelector(`input[aria-label="Use ${serverAsset.source_name}"]`));
  } finally { delete serverAsset.display_name; delete serverAsset.media_role; }
});

function conceptSession(id = crypto.randomUUID(), focus = "", reelKind = "story") {
  const session = { id, focus, reel_kind: reelKind, audience: "", privacy_mode: "hybrid", status: "ready", total_tokens: 1200,
    created_at: "2026-01-01T00:00:00Z", error: null, model: "fixture-model", jobs: [],
    coverage: { unique_sources_available: 3, sources_considered: 3, speech_passages: 6 },
    concepts: [1,2,3].map((index) => ({ id: `option-${index}`, title: `Recorded story ${index}`,
      angle: "A supported story from the existing footage.", estimated_seconds: 12, source_backed: true,
      asset_ids: [serverId], visuals: [{ asset_id: serverId, display_name: "Product detail", reason: "Shows this recorded demonstration.", mime_type: "video/mp4" }],
      script: [{ evidence_id: index * 2, asset_id: serverId, start: 0, end: 6, role: "hook", text: "These are the exact opening words from the recording.", display_name: "Product introduction", source_name: "talking.mp4" },
               { evidence_id: index * 2 + 1, asset_id: serverId, start: 6, end: 12, role: "ending", text: "Here is the supported ending already recorded.", display_name: "Product introduction", source_name: "talking.mp4" }] })) };
  if (reelKind === "bloopers") {
    session.coverage.possible_blooper_passages = 3;
    for (const concept of session.concepts) {
      concept.reel_kind = "bloopers";
      Object.assign(concept.script[0], { text: "I can't pronounce that! Start again.", blooper_candidate: true, blooper_signals: ["word_stumble", "retake_direction"] });
    }
  }
  return session;
}
async function mountConcepts() {
  await act(async () => root.render(React.createElement(ConceptDesk)));
  await waitFor(() => !button("Generate reel ideas").disabled);
}

test("concept discovery is explicit, shows recorded script and pictures, and renders only two selected options", async () => {
  await mountConcepts();
  assert.equal(posts("concepts").length, 0);
  assert.equal(calls.some((call) => call.route.endsWith("/render")), false);
  await click(button("Generate reel ideas"));
  await waitFor(() => document.querySelector('input[aria-label="Choose Recorded story 1"]'));
  assert.equal(conceptCounter, 1);
  assert.match(document.body.textContent, /exact opening words from the recording/);
  assert.match(document.body.textContent, /Supporting pictures/);
  assert.equal(calls.some((call) => call.route.endsWith("/render")), false);
  await click(document.querySelector('input[aria-label="Choose Recorded story 1"]'));
  await click(document.querySelector('input[aria-label="Choose Recorded story 2"]'));
  assert.equal(document.querySelector('input[aria-label="Choose Recorded story 3"]').disabled, true);
  await click(button("Create 2 previews"));
  await waitFor(() => [...document.querySelectorAll('a')].filter((item) => item.textContent === "Open edit").length === 2);
  const render = calls.filter((call) => call.route.endsWith('/render'));
  assert.equal(render.length, 1);
  assert.deepEqual(render[0].body.concept_ids, ["option-1", "option-2"]);
  assert.equal(conceptCounter, 1);
});

test("saved concepts reopen without a model call and a failed render retains the chosen option", async () => {
  conceptHistory = [conceptSession()];
  await mountConcepts();
  await waitFor(() => document.querySelector('input[aria-label="Choose Recorded story 1"]'));
  assert.equal(posts("concepts").length, 0);
  renderConceptFailure = true;
  await click(document.querySelector('input[aria-label="Choose Recorded story 1"]'));
  await click(button("Create 1 preview"));
  await waitFor(() => document.querySelector('[role="alert"]')?.textContent.includes("Trash"));
  assert.equal(document.querySelector('input[aria-label="Choose Recorded story 1"]').checked, true);
  assert.equal(posts("concepts").length, 0);
  assert.equal(conceptHistory[0].jobs.length, 0);
});

test("bloopers are an explicit mode with visible clues and no preview until selection", async () => {
  await mountConcepts();
  assert.equal(document.querySelector('select[aria-label="Reel type"]').value, "story");
  await chooseOption('select[aria-label="Reel type"]', 'bloopers');
  assert.equal(posts("concepts").length, 0);
  assert.match(document.body.textContent, /Purely visual gags.*may be missed/);
  await click(button("Find blooper reel ideas"));
  await waitFor(() => document.querySelector('input[aria-label="Choose Recorded story 1"]'));
  assert.equal(posts("concepts")[0].body.reel_kind, "bloopers");
  assert.match(document.body.textContent, /Possible outtake · word stumble, retake direction/);
  assert.match(document.body.textContent, /3 possible outtake passages/);
  assert.equal(calls.some((call) => call.route.endsWith('/render')), false);
  await click(document.querySelector('input[aria-label="Choose Recorded story 1"]'));
  await click(button("Create 1 preview"));
  await waitFor(() => [...document.querySelectorAll('a')].some((item) => item.textContent === "Open edit"));
  assert.deepEqual(calls.find((call) => call.route.endsWith('/render')).body.concept_ids, ["option-1"]);
});

test("a saved blooper session can honestly decline weak evidence without creating a job", async () => {
  const session = conceptSession(crypto.randomUUID(), "", "bloopers");
  session.concepts = [];
  conceptHistory = [session];
  await mountConcepts();
  await waitFor(() => document.body.textContent.includes("No worthwhile blooper reel was supported"));
  assert.equal(posts("concepts").length, 0);
  assert.equal(button("Create selected previews").disabled, true);
  assert.equal(calls.some((call) => call.route.endsWith('/render')), false);
});

test("photos can be categorized and filtered without assigning a video footage role", async () => {
  managedAssets.push({ ...managedAssets[0],id:"review-photo",mime_type:"image/png",display_name:"r3.png",source_name:"r3.png",media_role:"auto" });
  await act(async () => root.render(React.createElement(MediaLibrary)));
  await waitFor(() => document.querySelector('input[aria-label="Select r3.png"]'));
  await click(button("Photos"));
  await click(document.querySelector('input[aria-label="Select r3.png"]'));
  assert.equal(document.querySelector('select[aria-label="Label selected videos"]').disabled,true);
  await chooseOption('select[aria-label="Categorize selected files"]',"review");
  await waitFor(() => managedAssets.find((item) => item.id === "review-photo").media_category === "review");
  await chooseOption('select[aria-label="Filter media category"]',"product");
  assert.equal(document.querySelector('input[aria-label="Select r3.png"]'),null);
  await chooseOption('select[aria-label="Filter media category"]',"review");
  assert.ok(document.querySelector('input[aria-label="Select r3.png"]'));
});

test("auto-sort suggestions require explicit application and can be edited before saving", async () => {
  managedAssets.push({ ...managedAssets[0],id:"review-photo",mime_type:"image/png",display_name:"r3.png",source_name:"r3.png",media_role:"auto" });
  await act(async () => root.render(React.createElement(MediaLibrary)));
  await waitFor(() => document.querySelector('input[aria-label="Select r3.png"]'));
  await click(document.querySelector('input[aria-label="Select r3.png"]'));
  await click(button("Auto-sort selected"));
  await waitFor(() => document.querySelector('section[aria-label="Auto-sort library"]'));
  assert.equal(posts("library/organization").length,0);
  await click(button("Suggest names & categories"));
  await waitFor(() => document.querySelector('input[aria-label="Suggested name for r3.png"]'));
  assert.equal(managedAssets.find((item) => item.id === "review-photo").display_name,"r3.png");
  await type('input[aria-label="Suggested name for r3.png"]',"Customer review of cream");
  await click(button("Apply 1 selected suggestions"));
  await waitFor(() => document.querySelector('input[aria-label="Select Customer review of cream"]'));
  const photo=managedAssets.find((item) => item.id === "review-photo");
  assert.equal(photo.source_name,"r3.png");
  assert.equal(photo.media_category,"review");
  assert.equal(posts("library/organization").length,1);
  assert.equal(calls.some((call) => call.route === "projects"),false);
  await click(document.querySelector('button[aria-label="Close auto-sort"]'));
  await click(button("Auto-sort"));
  await waitFor(() => document.querySelector('select[aria-label="Saved auto-sort session"]'));
  await chooseOption('select[aria-label="Saved auto-sort session"]',organizationHistory[0].id);
  await waitFor(() => document.querySelector('input[aria-label="Apply suggestion for r3.png"]'));
  assert.equal(document.querySelector('input[aria-label="Apply suggestion for r3.png"]').disabled,true);
  assert.equal(posts("library/organization").length,1);
});

test("failed auto-sort application preserves the review and original names", async () => {
  await act(async () => root.render(React.createElement(MediaLibrary)));
  await waitFor(() => document.querySelector('input[aria-label="Select VID_0003.mp4"]'));
  await click(document.querySelector('input[aria-label="Select VID_0003.mp4"]'));
  await click(button("Auto-sort selected"));
  await click(button("Suggest names & categories"));
  await waitFor(() => document.querySelector('input[aria-label="Apply suggestion for VID_0003.mp4"]'));
  organizationFailure=true;
  await click(button("Apply 1 selected suggestions"));
  await waitFor(() => document.body.textContent.includes("Library details changed"));
  assert.equal(document.querySelector('input[aria-label="Apply suggestion for VID_0003.mp4"]').checked,true);
  assert.equal(managedAssets.find((item) => item.id === "unsorted").display_name,"VID_0003.mp4");
  assert.equal(posts("library/organization").length,1);
});


const toolClip = { clip_index:0,clip_id:"1234567890abcdef",asset_id:serverId,source_name:"Talking about soap",source_in:0,source_out:4,duration:4,words:[{text:"Soap",start:.2,end:.6}] };
test("precise edits wait for submit and carry the inspected version and clip handle",async()=>{
 await act(async()=>root.render(React.createElement(PreciseClipEditor,{jobId,version:2,clip:toolClip,onUpdated:()=>{readyEvents+=1;}})));
 await click(document.querySelector('button[aria-label="Start before Soap at 0.20 seconds"]'));
 assert.equal(posts(`jobs/${jobId}/revisions`).length,0);
 await act(async()=>document.querySelector('form').dispatchEvent(new Event('submit',{bubbles:true,cancelable:true})));
 await waitFor(()=>readyEvents===1);
 const body=posts(`jobs/${jobId}/revisions`)[0].body;
 assert.equal(body.base_version,2);assert.equal(body.clip_adjustments[0].clip_id,toolClip.clip_id);
 assert.equal(body.clip_adjustments[0].source_in,.12);assert.equal(body.note,"");
});
test("finishing choices make no request until explicit submission and preserve local-only revision",async()=>{
 await act(async()=>root.render(React.createElement(FinishingWorkspace,{jobId,version:2,clips:[toolClip],onUpdated:()=>{readyEvents+=1;}})));
 const details=document.querySelector('details');
 await act(async()=>{details.open=true;details.dispatchEvent(new Event('toggle'));});
 await waitFor(()=>document.querySelector('form'));
 assert.equal(posts(`jobs/${jobId}/revisions`).length,0);
 await act(async()=>document.querySelector('form').dispatchEvent(new Event('submit',{bubbles:true,cancelable:true})));
 await waitFor(()=>readyEvents===1);
 const body=posts(`jobs/${jobId}/revisions`)[0].body;
 assert.equal(body.base_version,2);assert.equal(body.note,"");
 assert.equal(body.finishing_settings.motions[0].points[1].zoom,1.15);
 assert.equal(body.finishing_settings.motions[0].points[1].time,3.99);
});
test("source dictionary saves names and aliases only after submit",async()=>{
 await act(async()=>root.render(React.createElement(SourceKnowledge)));
 await waitFor(()=>!button("Save product").disabled||document.body.textContent.includes("No products added"));
 const inputs=document.querySelectorAll('form input');
 await type('form input',"Castor oil");
 Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,"value").set.call(inputs[1],"castor, oil roller");
 await act(async()=>inputs[1].dispatchEvent(new Event('input',{bubbles:true})));
 assert.equal(calls.some(c=>c.method==="PUT"),false);
 await act(async()=>document.querySelector('form').dispatchEvent(new Event('submit',{bubbles:true,cancelable:true})));
 await waitFor(()=>calls.some(c=>c.method==="PUT"));
 assert.deepEqual(calls.find(c=>c.method==="PUT").body.aliases,["castor","oil roller"]);
});
test("source annotations are separate from the whole-file role and need confirmation by submission",async()=>{
 await act(async()=>root.render(React.createElement(SourceRanges,{assetId:serverId,duration:10})));
 await click(button("Mark source ranges"));
 await waitFor(()=>document.querySelector('form'));
 assert.equal(calls.some(c=>c.method==="PUT"),false);
 await act(async()=>document.querySelector('form').dispatchEvent(new Event('submit',{bubbles:true,cancelable:true})));
 await waitFor(()=>calls.some(c=>c.method==="PUT"));
 assert.equal(calls.find(c=>c.method==="PUT").body.role,"broll");
 assert.equal(calls.find(c=>c.method==="PUT").body.end_seconds,3);
});


test("lesson proposals stay inactive and cannot start a trial without an explicit selection",async()=>{
 await act(async()=>root.render(React.createElement(LearningLabPanel)));
 await waitFor(()=>document.body.textContent.includes("No repeated note pattern"));
 assert.equal(calls.some(c=>c.method==="POST"),false);
 await click(button("Propose lessons from saved notes"));
 await waitFor(()=>document.body.textContent.includes("Keep complete clean speech."));
 assert.equal(button("Promote passed lesson").disabled,true);
 assert.equal(button("Create trial preview · uses model tokens").disabled,true);
 assert.equal(calls.filter(c=>c.method==="POST").length,1);
 assert.equal(calls.some(c=>c.route.endsWith("/trial")),false);
});
