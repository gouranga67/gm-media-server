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
let calls = [], transfers = [], navigation = [], readyEvents = 0, analysisStatus = "ready", root;
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
const { LibraryUpload } = require(path.join(repo, "apps/web/app/_components/library-upload.tsx"));

globalThis.fetch = async (url, options = {}) => {
  const route = String(url).replace("/api/media/", "");
  const body = options.body ? JSON.parse(options.body) : undefined;
  calls.push({ route, method: options.method ?? "GET", body });
  let payload;
  if (route === "projects") payload = { ...body, id: body.id };
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
  calls = []; transfers = []; navigation = []; readyEvents = 0; analysisStatus = "ready";
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
