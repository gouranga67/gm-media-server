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
for (const name of ["window", "document", "navigator", "HTMLElement", "HTMLInputElement", "HTMLTextAreaElement", "File", "FormData", "MutationObserver", "Node", "NodeFilter", "CustomEvent", "Event", "HTMLSelectElement", "HTMLButtonElement"]) {
  Object.defineProperty(globalThis, name, { configurable: true, value: name === "window" ? dom : dom[name] });
}
globalThis.getComputedStyle = dom.getComputedStyle.bind(dom);
const { Event } = dom;
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const React = require("react");
const { act } = React;
const { createRoot } = require("react-dom/client");
const ts = require("typescript");
const Module = require("node:module");
const originalLoad = Module._load;
let lessonProposed = false, labFixture = null;
let assemblySettings, assemblyError, assemblyLocked, profiles, previewFixture;
let revisionFailure = false;
function assemblyPreview() { return {ready: !assemblyError, locked: assemblyLocked, error:assemblyError, settings:assemblySettings, decision:assemblyError ? null : {recipe:assemblySettings.assembly_mode === "auto" ? "talking_head" : assemblySettings.assembly_mode,edit_style:assemblySettings.edit_style,purpose:assemblySettings.reel_intent === "auto" ? "story" : assemblySettings.reel_intent,label:"Speech with supporting pictures",reason:"Keep recorded speech continuous.",hosted_model_calls:0}}; }
let publishingFixture, alternativeFailure, durationFixture, durationFailure;
let subtitleFixture, subtitleFailure = false;
let folderList = [], folderMembers = new Map(), folderFailure = false;
let creativeImportAttempts = new Map();
URL.createObjectURL = () => "blob:synthetic-preview";
URL.revokeObjectURL = () => {};
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
const { CreativeBatchImport } = require(path.join(repo, "apps/web/app/_components/creative-batch-import.tsx"));
const { CreativeAssetsManager } = require(path.join(repo, "apps/web/app/_components/creative-assets-manager.tsx"));
const { PublishingPanel } = require(path.join(repo, "apps/web/app/_components/publishing-panel.tsx"));
const { AlternativeVersions } = require(path.join(repo, "apps/web/app/_components/alternative-versions.tsx"));
const { MetaConnectResult } = require(path.join(repo, "apps/web/app/_components/meta-connect-result.tsx"));
const { JobDurationSettings } = require(path.join(repo, "apps/web/app/_components/job-duration-settings.tsx"));
const { JobPreview } = require(path.join(repo, "apps/web/app/_components/job-preview.tsx"));
const { JobReviewControls } = require(path.join(repo, "apps/web/app/_components/job-review-controls.tsx"));
const { EditProgress } = require(path.join(repo, "apps/web/app/_components/edit-progress.tsx"));
const { RenderQualityCard } = require(path.join(repo, "apps/web/app/_components/render-quality-card.tsx"));
const { TreatmentTimeline } = require(path.join(repo, "apps/web/app/_components/treatment-timeline.tsx"));
const { AssemblyReadiness } = require(path.join(repo, "apps/web/app/_components/assembly-readiness.tsx"));
const { NewJobForm } = require(path.join(repo, "apps/web/app/_components/new-job-form.tsx"));
const { ConceptDesk } = require(path.join(repo, "apps/web/app/_components/concept-desk.tsx"));
const { MediaLibrary } = require(path.join(repo, "apps/web/app/_components/media-library.tsx"));
const { LearningLabPanel } = require(path.join(repo, "apps/web/app/_components/learning-lab.tsx"));
const { PreciseClipEditor } = require(path.join(repo, "apps/web/app/_components/precise-clip-editor.tsx"));
const { FinishingWorkspace } = require(path.join(repo, "apps/web/app/_components/finishing-workspace.tsx"));
const { AudioCleanupControls } = require(path.join(repo, "apps/web/app/_components/audio-cleanup-controls.tsx"));
const { VisualFinishingControls } = require(path.join(repo, "apps/web/app/_components/visual-finishing-controls.tsx"));
const { SourceKnowledge } = require(path.join(repo, "apps/web/app/_components/source-knowledge.tsx"));
const { SourceRanges } = require(path.join(repo, "apps/web/app/_components/source-ranges.tsx"));
const { SubtitleEditor } = require(path.join(repo, "apps/web/app/_components/subtitle-editor.tsx"));
const { splitSubtitle, mergeSubtitles } = require(path.join(repo, "apps/web/lib/subtitle-editing.ts"));
const { LibraryUpload } = require(path.join(repo, "apps/web/app/_components/library-upload.tsx"));

let intakeItems = [];
globalThis.fetch = async (url, options = {}) => {
  const route = String(url).replace("/api/media/", "");
  const body = options.body instanceof File ? options.body : options.body ? JSON.parse(options.body) : undefined;
  calls.push({ route, method: options.method ?? "GET", body });
  let payload;
  if (/^jobs\/[^/]+\/edits\/[^/]+\/subtitles(?:\/apply)?$/.test(route)) {
    if (subtitleFailure && options.method === "PUT") return { ok:false,status:409,json:async()=>({detail:"These subtitles changed in another tab. Reload before saving your draft."}) };
    if (options.method === "PUT") subtitleFixture = { ...subtitleFixture, revision: subtitleFixture.revision + 1, cues: body.cues, saved: true };
    payload = options.method === "POST" ? { id:"caption-render",version:3,status:"pending" } : structuredClone(subtitleFixture);
  }
  else if (route.startsWith("creative-assets/import?")) {
    const filename = new URLSearchParams(route.split("?")[1]).get("filename");
    const attempts = (creativeImportAttempts.get(filename) ?? 0) + 1; creativeImportAttempts.set(filename, attempts);
    if (filename === "existing.ogg") return { ok: false, status: 409, json: async () => ({ detail: "this exact creative file is already in the library" }) };
    if (filename === "retry.ogg" && attempts === 1) return { ok: false, status: 422, json: async () => ({ detail: "Synthetic import failure" }) };
    payload = { kind: "sound_effect", asset: { id: crypto.randomUUID() } };
  }
  else if (route === "creative-assets?active=false" || route === "music-tracks?active=true" || route === "music-tracks?active=false" || route === "music-tracks?active=all") payload = [];
  else if (route === "publishing/status") payload = publishingFixture.config;
  else if (route === "publishing/connections") payload = publishingFixture.accounts;
  else if (route.startsWith("publishing/drafts?") || (route === "publishing/drafts" && (options.method ?? "GET") === "GET")) payload = publishingFixture.draft ? [publishingFixture.draft] : [];
  else if (route === "publishing/drafts") { publishingFixture.draft = {id:body.id,final_export_id:body.final_export_id,job_id:jobId,version:4,revision:1,caption:"",posts:[],caption_request:null};payload=publishingFixture.draft; }
  else if (/^publishing\/drafts\/[^/]+\/publish$/.test(route)) {
    if(publishingFixture.failPublish) return {ok:false,status:409,json:async()=>({detail:"The export changed. Review it before posting."})};
    publishingFixture.draft.posts=body.connection_ids.map((id,index)=>({id:`post-${index}`,connection_id:id,platform:index?"facebook":"instagram",account_name:"Studio",status:"queued",publish_at:body.publish_at??new Date().toISOString(),permalink:null,error:null,remote_container_id:null}));payload=publishingFixture.draft;
  }
  else if (/^publishing\/drafts\/[^/]+\/captions$/.test(route)) { publishingFixture.draft.caption_request={id:body.id,status:"ready",options:[{label:"Concise",text:"A reviewed source story."},{label:"Story",text:"A family recipe story."},{label:"Question",text:"What would you choose?"}],total_tokens:100,error:null};payload=publishingFixture.draft.caption_request; }
  else if (/^publishing\/drafts\/[^/?]+$/.test(route)) { if(options.method==="PATCH"){publishingFixture.draft.caption=body.caption;publishingFixture.draft.revision+=1;}payload=publishingFixture.draft; }
  else if (route === "publishing/meta/complete") payload={connected:2};
  else if (route === "learning/lab") payload = labFixture ?? { lessons: lessonProposed ? [{ id:serverId,recipe:"talking_head",edit_style:"high_impact",status:"proposed",directive:"Keep complete clean speech.",training_job_ids:[jobId,"training-b","training-c"],evaluation:{held_out_jobs:0,can_promote:false,rating_delta:null,regressions:0} }] : [],trials:[],jobs:[] };
  else if (route === "learning/lab/propose") { lessonProposed=true;payload={matched_proposals:1,hosted_model_calls:0}; }
  else if (/^learning\/lab\/lessons\/[^/]+\/trial$/.test(route)) payload={id:"trial",status:"pending",version:2};
  else if (/^learning\/lab\/lessons\/[^/]+\/evaluate$/.test(route)) payload={can_promote:false};
  else if (/^learning\/lab\/lessons\/[^/]+\/status$/.test(route)) {labFixture.lessons[0].status=body.action==="promote"?"promoted":"rolled_back";payload={status:labFixture.lessons[0].status};}
  else if (route === "library/knowledge") payload = { products: [], evidence_version: "1.0" };
  else if (/^library\/products\//.test(route)) payload = { ...body, id: route.split("/").at(-1) };
  else if (route.endsWith("/ranges") && route.startsWith("library/assets/")) payload = [];
  else if (route.includes("/ranges/") && route.startsWith("library/assets/")) payload = body;
  else if (route === `jobs/${jobId}/review`) payload=previewFixture;
  else if (route === `jobs/${jobId}/revisions`) {
    if (revisionFailure) return {ok:false,status:422,json:async()=>({detail:"That quote occurs more than once. Add in clip N; no new edit was queued."})};
    payload = { id: "revision", version: 3, status: "pending" };
  }
  else if (route === `jobs/${jobId}/alternatives`) {
    if (alternativeFailure) return {ok:false,status:409,json:async()=>({detail:"This alternative could not be queued. Your original is unchanged."})};
    payload={id:"alternative",version:3,status:"pending"};
  }
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
  else if (route.startsWith("library/browse?")) {
    const p = new URLSearchParams(route.split("?")[1]);
    const q = (p.get("query") || "").toLowerCase(), view=p.get("view"), ids=p.getAll("match_ids");
    let items = managedAssets.filter(a => (view === "trash" ? a.library_status === "archived" : a.library_status === "active")
      && (!["talking","broll","unsorted"].includes(view) || a.mime_type.startsWith("video/") && a.media_role === (view === "unsorted" ? "auto" : view))
      && (!["image","audio"].includes(view) || a.mime_type.startsWith(view+"/"))
      && (p.get("category") === "all" || (a.media_category || "auto") === p.get("category"))
      && (p.get("favorite") !== "true" || a.favorite)
      && (p.get("unfiled") !== "true" || !a.collection_count)
      && (!p.get("collection_id") || folderMembers.get(p.get("collection_id"))?.has(a.id))
      && (!q || [a.display_name,a.source_name,a.project_name,a.notes,...a.tags].some(v=>v?.toLowerCase().includes(q)) || ids.includes(a.id)));
    const candidateIds=new Set(items.map(a=>a.id));
    items=items.filter(a=>p.get("copies")==="true" || view==="trash" || !a.canonical_asset_id || a.canonical_asset_id===a.id || !candidateIds.has(a.canonical_asset_id));
    items.sort((a,b)=>p.get("sort")==="name"?a.display_name.localeCompare(b.display_name):p.get("sort")==="largest"?b.byte_size-a.byte_size:Date.parse(b.created_at)-Date.parse(a.created_at)||a.id.localeCompare(b.id));
    const offset=Number(p.get("offset")),limit=Number(p.get("limit"));
    payload={items:items.slice(offset,offset+limit),total:items.length,summary:{active:managedAssets.filter(a=>a.library_status==="active").length,trash:managedAssets.filter(a=>a.library_status==="archived").length,stored_bytes:10000}};
  }
  else if (route.startsWith("library/intake/status?")) payload=new URLSearchParams(route.split("?")[1]).getAll("asset_ids").map(id=>({id,intake_status:analysisStatus === "failed" ? "failed" : "ready",error:"local analysis failed"}));
  else if (route.startsWith("library/intake?")) {
    const p=new URLSearchParams(route.split("?")[1]), q=(p.get("query")||"").toLowerCase();
    const items=intakeItems.filter(a=>a.display_name.toLowerCase().includes(q));
    payload={items:items.slice(Number(p.get("offset")),Number(p.get("offset"))+60),total:items.length,inbox_count:intakeItems.length};
  }
  else if (route === "library/intake/review") { intakeItems=intakeItems.filter(a=>!body.asset_ids.includes(a.id));payload={updated:body.asset_ids.length}; }
  else if (route.startsWith("library/assets?")) {
    const params = new URLSearchParams(route.split("?")[1]);
    payload = params.get("offset") === "0" ? managedAssets.filter((asset) => !params.get("collection_id") || folderMembers.get(params.get("collection_id"))?.has(asset.id)) : [];
  }
  else if (route === "library/collections") {
    if (options.method === "POST") { const folder={id:crypto.randomUUID(),...body,asset_count:0}; folderList.push(folder); folderMembers.set(folder.id,new Set()); payload=folder; }
    else payload=folderList.map(folder=>({...folder,asset_count:managedAssets.filter(asset=>asset.library_status==="active" && folderMembers.get(folder.id)?.has(asset.id)).length}));
  }
  else if (/^library\/collections\/[^/]+\/assets\/batch$/.test(route)) {
    if(folderFailure) return {ok:false,status:409,json:async()=>({detail:"Refresh this folder; no changes were made"})};
    const id=route.split("/")[2], members=folderMembers.get(id) ?? new Set();
    for(const asset of body.asset_ids) {if(body.action==="add")members.add(asset);else members.delete(asset);}
    folderMembers.set(id,members);
    for(const asset of managedAssets) asset.collection_count=[...folderMembers.values()].filter(ids=>ids.has(asset.id)).length;
    payload={updated:body.asset_ids.length};
  }
  else if (/^library\/collections\/[^/?]+$/.test(route)) {
    const id=route.split("/")[2], folder=folderList.find(item=>item.id===id);
    if(options.method==="PATCH") {Object.assign(folder,body);payload=folder;}
    if(options.method==="DELETE") {
      folderList=folderList.filter(item=>item.id!==id);folderMembers.delete(id);
      for(const asset of managedAssets)asset.collection_count=[...folderMembers.values()].filter(ids=>ids.has(asset.id)).length;
      payload=undefined;
    }
  }
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
  else if (/^library\/assets\/[^/?]+$/.test(route)) payload = { asset: managedAssets.find((item) => item.id === route.split("/").at(-1)), collections: folderList.filter(folder=>folderMembers.get(folder.id)?.has(route.split("/").at(-1))), evidence: [], visual_frames: [] };
  else if (route === "projects") payload = { ...body, id: body.id };
  else if (/^projects\/[^/]+\/jobs$/.test(route)) { assemblySettings={assembly_mode:body.assembly_mode ?? body.recipe,pacing_mode:body.pacing_mode ?? "manual",edit_style:body.edit_style,reel_intent:body.reel_intent}; payload = { ...body, id: jobId }; }
  else if (route === `jobs/${jobId}/duration`) {
    if (options.method === "PUT") {
      if (durationFailure) return {ok:false,status:409,json:async()=>({detail:"Wait for the current edit attempt to finish."})};
      durationFixture={...durationFixture,settings:body};
    }
    payload=durationFixture;
  }
  else if (route === `jobs/${jobId}/assembly`) {
    if (options.method === "PUT") {
      if (assemblyLocked) return {ok:false,status:409,json:async () => ({detail:"Assembly is frozen after planning starts."})};
      assemblySettings=body; assemblyError=null;
    }
    payload=assemblyPreview();
  }
  else if (route === "creative-profiles") payload=profiles;
  else if (/^projects\/[^/]+\/assets$/.test(route)) payload = { ...body, project_id: route.split("/")[1], status: "registered" };
  else if (/^assets\/[^/]+\/analysis$/.test(route)) payload = { status: analysisStatus, error: analysisStatus === "failed" ? "Analysis fixture failed" : null };
  else if (/^assets\/[^/?]+$/.test(route)) payload = { id: route.split("/")[1], status: "ready" };
  else if (route.startsWith("assets/library")) payload = [serverAsset];
  else if (route === `jobs/${jobId}/assets`) payload = { job_id: jobId, attached_count: body.asset_ids.length };
  else if (route === `jobs/${jobId}/preview`) { payload = { id: "preview", status: "pending" }; if (previewFixture) previewFixture.latest_run=payload; }
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
  subtitleFailure=false;
  const subtitleCues=[{id:"cue-0000",start:.1,end:2.5,text:"Costa Royal!",position:null,hidden:false},{id:"cue-0001",start:3.2,end:5.8,text:"Our favourite cream.",position:null,hidden:false}];
  subtitleFixture={run_id:serverId,version:2,base_hash:"a".repeat(64),revision:0,cues:subtitleCues,baseline:subtitleCues,position:"lower_safe",duration:6,saved:false,applied_run_id:null,hosted_model_calls:0};
  folderList=[];folderMembers=new Map();folderFailure=false;
  creativeImportAttempts = new Map();
  alternativeFailure=false;
  durationFailure=false;
  revisionFailure=false;
  durationFixture={settings:{duration_mode:"aim",target_duration_seconds:60,max_duration_seconds:90},assessment:{mode:"aim",preferred_seconds:60,maximum_seconds:72,available_speech_seconds:85,warning:"About 85s of speech includes possible repeated takes; this is not a required-script measurement."}};
  publishingFixture={config:{configured:true,redirect_uri:"https://studio.example.invalid/publishing/connect"},accounts:[{id:serverId,platform:"instagram",display_name:"Studio",active:true,token_expires_at:null}],draft:null,failPublish:false};
  managedAssets = [
    { ...serverAsset, id: "talk", source_name: "VID_0001.mp4", display_name: "Product introduction", media_role: "talking", job_references: 2 },
    { ...serverAsset, id: "broll", source_name: "VID_0002.mp4", display_name: "Cream close-up", media_role: "broll", job_references: 0 },
    { ...serverAsset, id: "unsorted", source_name: "VID_0003.mp4", display_name: "VID_0003.mp4", media_role: "auto", job_references: 0 },
  ].map((item) => ({ notes: "", tags: [], favorite: false, library_status: "active", collection_count: 0, visual_status: "ready", updated_at: item.created_at, ...item }));
  lessonProposed=false;labFixture=null;
  assemblySettings={assembly_mode:"auto",pacing_mode:"auto",edit_style:"energetic",reel_intent:"auto"}; assemblyError=null; assemblyLocked=false; profiles=[]; previewFixture=null;
  intakeItems = [];
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
async function click(element) { assert.ok(element); await waitFor(() => !element.disabled); await act(async () => { element.click(); await tick(); }); }
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
  assert.equal(posts("/jobs")[0].body.duration_mode,"follow_story");
  assert.equal(posts("/jobs")[0].body.max_duration_seconds,90);
  assert.deepEqual(posts(`/jobs/${jobId}/assets`)[0].body.asset_ids, [serverId]);
  const uploadRequests = posts("/assets").filter((call) => call.route.startsWith("projects/"));
  assert.equal(uploadRequests.length, 1);
  assert.equal(uploadRequests[0].body.job_id, jobId);
  assert.equal(uploadRequests[0].body.source_name, "close-up.mp4");
  assert.equal(posts("/preview").length, 0);
  await act(async () => transfers[0].callbacks.onSuccess());
  await waitFor(() => button("Start editing") && !button("Start editing").disabled);
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

test("blooper purpose is separate from format and waits for explicit job submission", async () => {
  await act(async () => root.render(React.createElement(NewJobForm)));
  await waitFor(() => document.getElementById("reel-intent"));
  await chooseOption("#reel-intent", "bloopers");
  assert.match(document.body.textContent, /No sales payoff or call to action is required/);
  assert.equal(posts("/jobs").length, 0);
  await click(document.querySelector(`input[aria-label="Use ${serverAsset.source_name}"]`));
  await type("#project-name", "Soap ad outtakes");
  await type("#project-brief", "Keep the lost line and real reaction.");
  await act(async () => document.querySelector("form").dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })));
  await waitFor(() => posts("/jobs").length === 1);
  assert.equal(posts("/jobs")[0].body.reel_intent, "bloopers");
  assert.equal(posts("/jobs")[0].body.recipe, "talking_head");
  assert.equal(posts("/preview").length, 0);
});
async function mountBrowser() {
  await act(async () => root.render(React.createElement(MediaLibrary)));
  await waitFor(() => !button("Browse all media").disabled);
  await click(button("Browse all media"));
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
  await click(button("Trash"));
  await waitFor(()=>document.querySelector('input[aria-label="Select Product introduction"]'));
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
  assert.deepEqual(posts("/assets")[0].body.library_intake, { display_name: "Lotion texture 001", media_role: "broll" });
  assert.equal(posts("library/assets/batch").length, 0, "Metadata is saved at registration, without waiting for browser analysis polling");
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

test("saved concept retrieval coverage shows focus and sampling limits without starting work", async () => {
  const session=conceptSession();
  session.coverage.retrieval={focus_applied:true,focus_matching_sources_available:8,
    focus_matching_sources_considered:3,focus_matching_passages_included:2,
    speech_passages_available:40,speech_sources_without_passages:1,sampling_limited:true};
  conceptHistory=[session];
  await mountConcepts();
  await waitFor(()=>document.querySelector('[aria-label="Source retrieval coverage"]'));
  const text=document.querySelector('[aria-label="Source retrieval coverage"]').textContent;
  assert.match(text,/3 of 8 sources matching your direction/);
  assert.match(text,/6 of 40 eligible recorded passages/);
  assert.match(text,/bounded sample/);
  assert.match(text,/do not verify pictured products/);
  assert.match(text,/cannot supply a recorded script/);
  assert.equal(posts("concepts").length,0);
  assert.equal(calls.some(call=>call.route.endsWith("/render")),false);
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

test("modern blooper options explain complete attempt and response bundles without starting work",async()=>{
  const session=conceptSession(crypto.randomUUID(),"","bloopers");
  Object.assign(session.coverage,{blooper_contract_version:2,complete_incident_bundles:3});
  for(const concept of session.concepts)concept.blooper_review={version:2,incident_count:1,recorded_setup_and_response:true};
  conceptHistory=[session];
  await mountConcepts();
  await waitFor(()=>document.body.textContent.includes('3 complete attempt/response bundles'));
  assert.match(document.body.textContent,/attempted line and real response kept together/);
  assert.match(document.body.textContent,/transcript clues can be wrong/);
  const preview=[...document.querySelectorAll('a')].find(e=>e.href.includes('#t=0,6'));
  assert.ok(preview);
  assert.equal(posts('concepts').length,0);
  assert.equal(calls.some(c=>c.route.endsWith('/render')),false);
});

test("photos can be categorized and filtered without assigning a video footage role", async () => {
  managedAssets.push({ ...managedAssets[0],id:"review-photo",mime_type:"image/png",display_name:"r3.png",source_name:"r3.png",media_role:"auto" });
  await mountBrowser();
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
  await mountBrowser();
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
  await mountBrowser();
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
test("voice cleanup runs only on explicit click and retains the saved finishing configuration",async()=>{
 await act(async()=>root.render(React.createElement(AudioCleanupControls,{jobId,version:2,onUpdated:()=>{readyEvents+=1;}})));
 assert.equal(posts(`jobs/${jobId}/revisions`).length,0);
 await click(button("Clean up & balance audio"));
 await waitFor(()=>readyEvents===1);
 const body=posts(`jobs/${jobId}/revisions`)[0].body;
 assert.equal(body.base_version,2);assert.equal(body.note,"");
 assert.equal(body.finishing_settings.voice_cleanup,"auto");
 assert.deepEqual(body.finishing_settings.voice_cleanup_profiles,[]);
 assert.deepEqual(body.finishing_settings.audio_joins,[]);
 assert.deepEqual(body.finishing_settings.layers,[]);
});
test("visual options do no work before explicit apply and preserve unrelated finishing",async()=>{
 await act(async()=>root.render(React.createElement(VisualFinishingControls,{jobId,version:2,onUpdated:()=>{readyEvents+=1;}})));
 const checks=[...document.querySelectorAll('input[type="checkbox"]')];
 assert.equal(checks.length,3);
 assert.ok(checks.every(e=>!e.checked));
 await click(checks[0]);await click(checks[2]);
 assert.equal(posts(`jobs/${jobId}/revisions`).length,0);
 await act(async()=>document.querySelector('form').dispatchEvent(new Event('submit',{bubbles:true,cancelable:true})));
 await waitFor(()=>readyEvents===1);
 const body=posts(`jobs/${jobId}/revisions`)[0].body;
 assert.equal(body.base_version,2);assert.equal(body.note,"");
 assert.equal(body.finishing_settings.smart_framing,"face");
 assert.equal(body.finishing_settings.safe_overlays,true);
 assert.equal(body.finishing_settings.shot_match,false);
 assert.deepEqual(body.finishing_settings.visual_profiles,[]);
 assert.deepEqual(body.finishing_settings.audio_joins,[]);
});
test("visual finishing explains declined shots and refuses stale versions",async()=>{
 await act(async()=>root.render(React.createElement(VisualFinishingControls,{jobId,version:1,
  report:{smart_framing:"face",profiles:[{clip_index:0,points:[],note:"Group shot; existing framing retained."}]},onUpdated:()=>{readyEvents+=1;}})));
 assert.ok(document.body.textContent.includes("Group shot"));
 await act(async()=>document.querySelector('form').dispatchEvent(new Event('submit',{bubbles:true,cancelable:true})));
 await waitFor(()=>document.querySelector('[role="alert"]'));
 assert.ok(document.body.textContent.includes("A newer edit is available"));
 assert.equal(posts(`jobs/${jobId}/revisions`).length,0);
});
test("voice cleanup explains source decisions and can be disabled without a model request",async()=>{
 await act(async()=>root.render(React.createElement(AudioCleanupControls,{jobId,version:2,
   report:{mode:"auto",profiles:[{asset_id:serverId,status:"measured",note:"No cleanup needed in the inspected passage."}]},onUpdated:()=>{readyEvents+=1;}})));
 assert.ok(document.body.textContent.includes("No cleanup needed"));
 assert.equal(posts(`jobs/${jobId}/revisions`).length,0);
 await click(button("Turn off automatic cleanup"));
 await waitFor(()=>readyEvents===1);
 assert.equal(posts(`jobs/${jobId}/revisions`)[0].body.finishing_settings.voice_cleanup,"off");
});
test("voice cleanup refuses to apply to a stale version",async()=>{
 await act(async()=>root.render(React.createElement(AudioCleanupControls,{jobId,version:1,onUpdated:()=>{readyEvents+=1;}})));
 await click(button("Clean up & balance audio"));
 await waitFor(()=>document.querySelector('[role="alert"]'));
 assert.ok(document.body.textContent.includes("A newer edit is available"));
 assert.equal(posts(`jobs/${jobId}/revisions`).length,0);
 assert.equal(readyEvents,0);
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

function learningFixture() {
  return {lessons:[{id:serverId,recipe:"talking_head",edit_style:"clean",status:"proposed",directive:"Keep complete clean speech.",training_job_ids:[],
    trial_options:[{job_id:jobId,eligible:true,reason:null},{job_id:"overlap",eligible:false,reason:"Footage overlaps another trial."}],
    evaluation:{held_out_jobs:1,can_promote:false,rating_delta:1,regressions:0,excluded_comparisons:0,overlapping_comparisons:0,token_delta:-300,costed_comparisons:1}}],
    trials:[],jobs:[{id:jobId,name:"Independent footage",recipe:"talking_head",edit_style:"clean",version:1},
      {id:"overlap",name:"Reuploaded footage",recipe:"talking_head",edit_style:"clean",version:1}]};
}

test("learning eligibility blocks reused footage and refresh never starts an experiment",async()=>{
  labFixture=learningFixture();
  await act(async()=>root.render(React.createElement(LearningLabPanel)));
  await waitFor(()=>document.body.textContent.includes("Independent footage"));
  const select=document.querySelector('select');
  assert.equal([...select.options].find(option=>option.value==="overlap").disabled,true);
  assert.equal(posts("trial").length,0);
  await act(async()=>{select.value=jobId;select.dispatchEvent(new Event("change",{bubbles:true}));});
  const originalConfirm=window.confirm;
  try {
    window.confirm=()=>false;
    await click(button("Create trial preview · uses model tokens"));
    assert.equal(posts("trial").length,0);
    window.confirm=()=>true;
    await click(button("Create trial preview · uses model tokens"));
    assert.equal(posts("trial").length,1);
    assert.deepEqual(posts("trial")[0].body,{job_id:jobId,base_version:1});
    await click(button("Refresh comparisons"));
    assert.equal(posts("trial").length,1);
    assert.equal(calls.filter(call=>call.route==="learning/lab").length,3);
  } finally {window.confirm=originalConfirm;}
});

test("learning compares exact versions with costs and saves only reviewed explicit ratings",async()=>{
  labFixture=learningFixture();
  labFixture.trials=[{id:"trial",job_id:jobId,version:2,baseline_version:1,status:"ready",evaluation_lesson_id:serverId,project_name:"Independent footage",
    baseline_available:true,candidate_available:true,baseline_usage:{total_tokens:1000,requests:1,model_latency_ms:2000},
    candidate_usage:{total_tokens:700,requests:2,model_latency_ms:1500},comparison:{baseline_rating:4,candidate_rating:5,note:"Clearer story."},executable_changed:false}];
  await act(async()=>root.render(React.createElement(LearningLabPanel)));
  await waitFor(()=>document.querySelectorAll('video').length===2);
  const videos=[...document.querySelectorAll('video')];
  assert.equal(videos[0].getAttribute("src").endsWith("version=1"),true);
  assert.equal(videos[1].getAttribute("src").endsWith("version=2"),true);
  assert.ok(videos.every(video=>video.getAttribute("preload")==="none"&&!video.hasAttribute("autoplay")));
  assert.equal(document.body.textContent.includes("700 tokens · 2 model request(s)"),true);
  assert.equal(document.body.textContent.includes("Saved comparison: baseline 4/5 · trial 5/5"),true);
  assert.equal(document.body.textContent.includes("executable edit was unchanged"),true);
  assert.equal(button("Save playback comparison").disabled,true);
  await type('textarea',"Better timing, same words.");
  assert.equal(posts("evaluate").length,0);
  await click(document.querySelector('input[type="checkbox"]'));
  await click(button("Save playback comparison"));
  assert.equal(posts("evaluate").length,1);
  assert.deepEqual(posts("evaluate")[0].body,{candidate_run_id:"trial",baseline_rating:4,candidate_rating:5,note:"Better timing, same words."});
  assert.equal(button("Promote passed lesson").disabled,true);
  await click(button("Retire proposed lesson"));
  assert.equal(posts("status").at(-1).body.action,"rollback");
  assert.equal(posts("trial").length,0);
});

test("learning cannot score an expired comparison preview",async()=>{
  labFixture=learningFixture();
  labFixture.trials=[{id:"trial",job_id:jobId,version:2,baseline_version:1,status:"ready",evaluation_lesson_id:serverId,project_name:"Expired pair",baseline_available:false,candidate_available:true}];
  await act(async()=>root.render(React.createElement(LearningLabPanel)));
  await waitFor(()=>document.body.textContent.includes("One is unavailable"));
  assert.equal(document.querySelectorAll('video').length,0);
  assert.equal(document.querySelectorAll('textarea').length,0);
  assert.equal(calls.some(call=>call.method==="POST"),false);
});


test("brief starters are visible editable instructions and never submit or change technical settings", async () => {
  await act(async () => root.render(React.createElement(NewJobForm)));
  await waitFor(() => document.getElementById("assembly-mode"));
  const headings=[...document.querySelectorAll("h2")].map((element) => element.textContent);
  assert.ok(headings.indexOf("Source media") < headings.indexOf("Describe your edit"));
  assert.equal(document.querySelector('input[name="recipe"]'),null);
  await type("#project-brief","Keep my existing thought.");
  await click(button("Recorded bloopers"));
  await click(button("Recorded bloopers"));
  assert.match(document.getElementById("project-brief").value,/Keep my existing thought/);
  assert.equal(document.getElementById("project-brief").value.match(/Make a bloopers reel/g).length,1);
  assert.equal(document.getElementById("assembly-mode").value,"auto");
  assert.equal(document.getElementById("reel-intent").value,"auto");
  assert.equal(posts("projects").length,0);
  assert.equal(posts("/jobs").length,0);
  assert.equal(posts("/preview").length,0);
});

test("negated montage brief is accepted in automatic mode and waits for interpretation before editing", async () => {
  assemblyError="No usable recorded video speech was found.";
  await act(async () => root.render(React.createElement(NewJobForm)));
  await waitFor(() => document.querySelector(`input[aria-label="Use ${serverAsset.source_name}"]`));
  await click(document.querySelector(`input[aria-label="Use ${serverAsset.source_name}"]`));
  await type("#project-name","Keep my explanation");
  await type("#project-brief","Do not make a montage. Keep my whole explanation.");
  await act(async () => document.querySelector("form").dispatchEvent(new Event("submit", {bubbles:true,cancelable:true})));
  await waitFor(() => document.body.textContent.includes("No usable recorded"));
  assert.equal(posts("/jobs")[0].body.assembly_mode,"auto");
  assert.equal(posts("/jobs")[0].body.pacing_mode,"auto");
  assert.equal(button("Start editing").disabled,true);
  assert.equal(posts("/preview").length,0);
  await chooseOption("#ready-assembly","montage");
  await chooseOption("#ready-pacing","calm");
  assert.equal(calls.filter((call) => call.method === "PUT").length,0);
  await click(button("Apply overrides"));
  await waitFor(() => !button("Start editing").disabled);
  assert.equal(calls.filter((call) => call.method === "PUT").length,1);
  assert.equal(document.getElementById("assembly-mode").value,"montage");
  assert.equal(document.querySelector('input[name="edit-style"][value="calm"]').checked,true);
  assert.equal(posts("/preview").length,0);
});

test("saved presentation profile never changes explicit assembly or purpose", async () => {
  profiles=[{id:serverId,name:"Montage defaults",recipe:"montage",target_duration_seconds:30,edit_style:"calm",music_mode:"none",target_platform:"all_social",output_aspect:"vertical",reasoning_effort:"medium",brand_kit_id:null,publishing_preset:"custom"}];
  await act(async () => root.render(React.createElement(NewJobForm)));
  await waitFor(() => document.getElementById("creative-profile"));
  await chooseOption("#assembly-mode","talking_head");
  await chooseOption("#reel-intent","bloopers");
  await chooseOption("#creative-profile",serverId);
  assert.equal(document.getElementById("assembly-mode").value,"talking_head");
  assert.equal(document.getElementById("reel-intent").value,"bloopers");
  assert.equal(document.querySelector('input[name="edit-style"][value="auto"]').checked,true);
  assert.equal(posts("/jobs").length,0);
});

test("stale advanced overrides report a freeze without starting a duplicate preview", async () => {
  let ready=false;
  const onReady=(value) => {ready=value;};
  await act(async () => root.render(React.createElement(AssemblyReadiness,{jobId,onReady})));
  await waitFor(() => ready);
  await chooseOption("#ready-pacing","calm");
  assert.equal(ready,false);
  assemblyLocked=true;
  await click(button("Apply overrides"));
  await waitFor(() => document.body.textContent.includes("frozen after planning"));
  assert.equal(ready,false);
  assert.equal(posts("/preview").length,0);
  assert.equal(posts("/jobs").length,0);
});


test("reopening an unstarted draft shows its interpretation and requires an explicit start", async () => {
  previewFixture={job:{id:jobId,recipe:"talking_head",status:"queued",output_aspect:"vertical"},latest_run:null,final_export:null,delivery_variants:[],versions:[],original_prompt:"A synthetic draft.",events:[]};
  await act(async () => root.render(React.createElement(JobPreview,{jobId})));
  await waitFor(() => document.body.textContent.includes("This edit has not started yet"));
  await waitFor(() => button("Start editing") && !button("Start editing").disabled);
  assert.equal(document.body.textContent.includes("Planning your edit"),false);
  assert.equal(posts("/preview").length,0);
  assert.equal(posts("/jobs").length,0);
  await click(button("Start editing"));
  await waitFor(() => document.body.textContent.includes("Your edit is queued"));
  assert.equal(posts("/preview").length,1);
  assert.equal(posts("/jobs").length,0);
});

test("progress distinguishes the queue from planning and rendering without estimating completion", async () => {
  const timestamp = new Date(Date.now()-30_000).toISOString();
  for (const [status,title,stage] of [["pending","Your edit is queued","Queued"],["planning","Planning your edit","Planning"],["rendering","Rendering your preview","Rendering"]]) {
    await act(async () => root.render(React.createElement(EditProgress,{run:{status,updated_at:timestamp,started_at:timestamp},checkedAt:Date.now(),connectionError:false})));
    assert.equal(document.querySelector("h1").textContent,title);
    assert.equal(document.querySelector('[aria-current="step"]').textContent.includes(stage),true);
    assert.equal(document.querySelectorAll('ol[aria-label="Edit progress"] li').length,4);
    assert.equal(document.body.textContent.includes("Worker checked in"),status!=="pending");
    assert.equal(document.querySelector('[role="progressbar"]'),null);
  }
  assert.equal(posts("/preview").length,0);
});

test("progress distinguishes a stale worker heartbeat from a lost status connection", async () => {
  const run={status:"planning",started_at:new Date(Date.now()-300_000).toISOString(),updated_at:new Date(Date.now()-180_000).toISOString()};
  await act(async () => root.render(React.createElement(EditProgress,{run,checkedAt:Date.now(),connectionError:false})));
  assert.equal(document.body.textContent.includes("worker has not checked in"),true);
  assert.equal(document.body.textContent.includes("does not confirm the edit has stopped"),true);
  await act(async () => root.render(React.createElement(EditProgress,{run,checkedAt:Date.now()-40_000,connectionError:true})));
  assert.equal(document.body.textContent.includes("Cannot refresh status"),true);
  assert.equal(document.body.textContent.includes("worker has not checked in"),false);
});

test("story review distinguishes recorded script coverage, automatic cleanup and human judgement", async () => {
  const review={version:"1.0",status:"passed",checks:[],findings:[],finding_count:0};
  await act(async () => root.render(React.createElement(RenderQualityCard,{review,storyContract:{status:"checked",central_point:"Explain the recorded result."},storyFinishing:{status:"attention",measured_clips:2,speech_clip_count:4,changes:["Shortened a measured quiet gap."],findings:["One passage could not be inspected."]}})));
  assert.equal(document.body.textContent.includes("2 of 4 speech passages measured"),true);
  assert.equal(document.body.textContent.includes("Shortened a measured quiet gap."),true);
  assert.equal(document.body.textContent.includes("not whether its meaning"),true);
  assert.equal(document.body.textContent.includes("Worth reviewing"),true);
  assert.equal(calls.length,0);
  await act(async () => root.render(React.createElement(RenderQualityCard,{review})));
  assert.equal(document.body.textContent.includes("Story selection and cleanup"),false);
});

test("recorded story outline shows actual passages and timing without model work", async () => {
  const review={version:"1.0",status:"passed",checks:[],findings:[],finding_count:0};
  const beat={clip_index:0,role:"context",text:"Our family made this cream.",start_seconds:0,end_seconds:3.25,source_in:12,source_out:15.25,word_timed:true};
  await act(async()=>root.render(React.createElement(RenderQualityCard,{review,storySequence:{outline:[null,{},beat],findings:["Check the setup before the source change."]}})));
  assert.equal(document.body.textContent.includes("Recorded story outline"),true);
  assert.equal(document.body.textContent.includes("Our family made this cream."),true);
  assert.equal(document.body.textContent.includes("Clip 1 · 0.0–3.3s · context"),true);
  assert.equal(document.body.textContent.includes("Source 12.0–15.3s · word-timed transcript"),true);
  assert.equal(document.body.textContent.includes("do not prove that the story or joke works"),true);
  assert.equal(document.body.textContent.includes("Worth reviewing"),true);
  assert.equal(document.querySelectorAll('ol li').length,1);
  assert.equal(calls.length,0);
});


test("treatment review filters saved cues and seeks only after an explicit jump", async () => {
  const seeks=[];
  const framing={kind:"framing",label:"Camera anchor",start:2.5,end:4,detail:"A planned move, not tracking.",clip_index:0};
  const captions={kind:"captions",label:"Upper captions",start:5,end:7,detail:"Saved caption region."};
  await act(async()=>root.render(React.createElement(TreatmentTimeline,{report:{events:[null,{},framing,captions,{...framing,start:NaN}],event_count:2},onSeek:seconds=>seeks.push(seconds)})));
  assert.equal(document.querySelectorAll('ol li').length,2);
  assert.deepEqual(seeks,[]);
  assert.equal(calls.length,0);
  const filter=document.querySelector('select[aria-label="Treatment kind"]');
  await act(async()=>{filter.value="captions";filter.dispatchEvent(new window.Event("change",{bubbles:true}));});
  assert.equal(document.querySelectorAll('ol li').length,1);
  assert.equal(document.body.textContent.includes("Upper captions"),true);
  assert.deepEqual(seeks,[]);
  await click(button("5.0–7.0s · Jump in preview"));
  assert.deepEqual(seeks,[5]);
  assert.equal(calls.length,0);
  await act(async()=>root.render(React.createElement(TreatmentTimeline,{report:{events:[framing]}})));
  assert.equal(document.querySelectorAll('ol li').length,1);
  assert.equal(document.body.textContent.includes("Camera anchor"),true);
  assert.equal(document.querySelector('select').value,"all");
  assert.equal(document.querySelectorAll('button').length,0);
});

test("legacy previews need no treatment report", async () => {
  await act(async()=>root.render(React.createElement(TreatmentTimeline,{report:undefined})));
  assert.equal(document.body.textContent,"");
  assert.equal(calls.length,0);
});

test("review recognises generated graphics and removes them only on request", async () => {
  let updates=0;
  const run={id:"ready",version:2,status:"ready",caption_settings:{},manifest:{
    finishing:{local_tools:{callouts:[{text:"A recorded label"}],pointers:[]}},
  }};
  await act(async()=>root.render(React.createElement(JobReviewControls,{jobId,run,finalExport:null,
    outputAspect:"vertical",recipe:"talking_head",targetDuration:30,deliveryVariants:[],editorialTimeline:[],
    initialCoverTime:0,initialFeedback:null,onUpdated:()=>{updates+=1;}})));
  assert.equal(document.body.textContent.includes("1 text labels/pointers"),true);
  assert.equal(document.body.textContent.includes("uses no library sound/graphic cues"),false);
  assert.equal(posts("revisions").length,0);
  await click(button("Remove sounds & graphics · zero AI"));
  assert.equal(posts("revisions").length,1);
  assert.equal(posts("revisions")[0].body.effects_enabled,false);
  assert.equal(updates,1);
});

test("quoted revision sends the displayed version only on submit and preserves rejected input",async()=>{
  let updates=0;revisionFailure=true;
  const run={id:"ready",version:2,status:"ready",caption_settings:{},manifest:{}};
  await act(async()=>root.render(React.createElement(JobReviewControls,{jobId,run,finalExport:null,outputAspect:"vertical",recipe:"talking_head",
    targetDuration:30,deliveryVariants:[],editorialTimeline:[],initialCoverTime:0,initialFeedback:null,onUpdated:()=>updates++})));
  const note='Make "cream works" louder by 3 dB';
  await type('#revision-note',note);
  assert.equal(posts("revisions").length,0);
  await act(async()=>document.querySelector('#revision-note').closest('form').dispatchEvent(new Event('submit',{bubbles:true,cancelable:true})));
  await waitFor(()=>document.body.textContent.includes('That quote occurs more than once'));
  assert.equal(document.querySelector('#revision-note').value,note);
  assert.equal(updates,0);assert.equal(posts("revisions")[0].body.base_version,2);
  revisionFailure=false;
  await act(async()=>document.querySelector('#revision-note').closest('form').dispatchEvent(new Event('submit',{bubbles:true,cancelable:true})));
  await waitFor(()=>updates===1);
  assert.equal(document.querySelector('#revision-note').value,"");
});

test("grounded receipt names the recorded phrase and seeks without another edit request",async()=>{
  const seeks=[];
  const run={id:"ready",version:3,status:"ready",caption_settings:{},manifest:{revision_report:{changed:true,changes:[],execution:{route:"local",scope:"phrase_pause",
    summary:"Removed measured quiet audio only.",target:{clip_index:0,phrase:"cream works.",start_seconds:.7,end_seconds:1.5,retained_pause_seconds:.5}}}}};
  await act(async()=>root.render(React.createElement(JobReviewControls,{jobId,run,finalExport:null,outputAspect:"vertical",recipe:"talking_head",
    targetDuration:30,deliveryVariants:[],editorialTimeline:[],initialCoverTime:0,initialFeedback:null,onUpdated:()=>{},onSeek:seconds=>seeks.push(seconds)})));
  assert.ok(document.body.textContent.includes('Matched recorded words: “cream works.”'));
  assert.ok(document.body.textContent.includes('Retained pause: 0.50s'));
  await click(button('Listen at 0.7s'));
  assert.deepEqual(seeks,[.7]);assert.equal(posts('revisions').length,0);
  run.manifest.revision_report.execution.target={phrase:'Legacy malformed target',clip_index:0,start_seconds:null};
  await act(async()=>root.render(React.createElement(JobReviewControls,{jobId,run,finalExport:null,outputAspect:"vertical",recipe:"talking_head",
    targetDuration:30,deliveryVariants:[],editorialTimeline:[],initialCoverTime:0,initialFeedback:null,onUpdated:()=>{},onSeek:seconds=>seeks.push(seconds)})));
  assert.equal([...document.querySelectorAll('button')].some(e=>e.textContent.startsWith('Listen at')),false);
  assert.deepEqual(seeks,[.7]);assert.equal(posts('revisions').length,0);
});

test("publishing opens without side effects and posts only the saved caption after an explicit click", async () => {
  await act(async()=>root.render(React.createElement(PublishingPanel,{exportId:serverId,version:4})));
  assert.equal(calls.filter(c=>c.route.startsWith("publishing/")).length,0);
  await click(button("Prepare a post"));
  await waitFor(()=>document.body.textContent.includes("Instagram · Studio"));
  assert.equal(calls.some(c=>c.route.startsWith("publishing/")&&c.method!=="GET"),false);
  assert.equal(button("Generate 3 caption options").disabled,true);
  await type('textarea',"My exact reviewed caption");
  const account=[...document.querySelectorAll('input[type="checkbox"]')].find(e=>e.parentElement.textContent.includes("Instagram"));
  await click(account);
  assert.equal(posts(`publishing/drafts/${publishingFixture.draft?.id}/publish`).length,0);
  await click(button("Save posting draft"));
  await waitFor(()=>document.body.textContent.includes("Posting draft saved"));
  assert.equal(publishingFixture.draft.caption,"My exact reviewed caption");
  assert.equal(calls.some(c=>c.route.endsWith("/publish")),false);
  await click(button("Post now"));
  await waitFor(()=>document.body.textContent.includes("This caption and export are frozen"));
  const approval=calls.find(c=>c.route.endsWith("/publish"));
  assert.equal(approval.body.revision,2);assert.deepEqual(approval.body.connection_ids,[serverId]);
  assert.equal(calls.some(c=>c.route.endsWith("/captions")),false);
});

test("caption choices require opt-in, stay editable and never trigger publication", async () => {
  await act(async()=>root.render(React.createElement(PublishingPanel,{exportId:serverId,version:4})));
  await click(button("Prepare a post"));await waitFor(()=>document.body.textContent.includes("Instagram · Studio"));
  await click([...document.querySelectorAll('input[type="checkbox"]')].find(e=>e.parentElement.textContent.includes("AI-written")));
  await click(button("Generate 3 caption options"));
  await waitFor(()=>document.body.textContent.includes("A reviewed source story."));
  await click([...document.querySelectorAll("button")].find(e=>e.textContent.includes("A reviewed source story.")));
  assert.equal(document.querySelector("textarea").value,"A reviewed source story.");
  assert.equal(publishingFixture.draft.caption,"");
  assert.equal(calls.some(c=>c.route.endsWith("/publish")),false);
});

test("rejected publication preserves the editable caption and does not automatically retry", async () => {
  publishingFixture.failPublish=true;
  await act(async()=>root.render(React.createElement(PublishingPanel,{exportId:serverId,version:4})));
  await click(button("Prepare a post"));await waitFor(()=>document.body.textContent.includes("Instagram · Studio"));
  await type('textarea',"Keep this caption");
  await click([...document.querySelectorAll('input[type="checkbox"]')].find(e=>e.parentElement.textContent.includes("Instagram")));
  await click(button("Post now"));await waitFor(()=>document.body.textContent.includes("The export changed"));
  assert.equal(document.querySelector("textarea").value,"Keep this caption");
  assert.equal(calls.filter(c=>c.route.endsWith("/publish")).length,1);
});

test("Meta callback exchanges the code once under StrictMode and removes it from the address", async () => {
  window.history.replaceState(null,"","/publishing/connect?code=private-code&state=private-state");
  await act(async()=>root.render(React.createElement(React.StrictMode,null,React.createElement(MetaConnectResult))));
  await waitFor(()=>document.body.textContent.includes("2 publishing accounts connected"));
  assert.equal(posts("publishing/meta/complete").length,1);
  assert.equal(window.location.search,"");
  assert.equal(document.body.textContent.includes("private-code"),false);
});

function savedVersions() {
  return [1,2].map(version=>({id:`saved-${version}`,version,status:"ready",preview_available:true,manifest:{},caption_corrections:[]}));
}

test("creative alternative options are explicit and preserve the selected kind and direction", async()=>{
  const versions=savedVersions();let updates=0;
  await act(async()=>root.render(React.createElement(AlternativeVersions,{jobId,run:versions[1],versions,onUpdated:()=>updates++})));
  assert.equal(posts("/alternatives").length,0);
  await click(button("Make another version"));
  assert.equal(posts("/alternatives").length,0);
  await click([...document.querySelectorAll('input[type="radio"]')].find(e=>e.parentElement.textContent.includes("Find a different story")));
  await type("textarea","Explore the family recipe origin.");
  assert.equal(posts("/alternatives").length,0);
  await click(button("Create one alternative preview"));
  assert.equal(updates,1);
  const request=posts("/alternatives")[0].body;
  assert.equal(request.kind,"different_story");assert.equal(request.base_version,2);
  assert.equal(request.direction,"Explore the family recipe origin.");
  assert.match(request.request_id,/^[0-9a-f-]{36}$/);
  assert.equal(calls.some(c=>c.route.includes("approval")||c.route.includes("publishing")),false);
});

test("an alternative request failure retains input and reuses its ID rather than queuing twice", async()=>{
  const versions=savedVersions();alternativeFailure=true;
  await act(async()=>root.render(React.createElement(AlternativeVersions,{jobId,run:versions[1],versions,onUpdated:()=>{}})));
  await click(button("Make another version"));await type("textarea","Try another opening.");
  await click(button("Create one alternative preview"));
  assert.match(document.body.textContent,/original is unchanged/);
  assert.equal(document.querySelector("textarea").value,"Try another opening.");
  assert.equal(posts("/alternatives").length,1);
  await click(button("Create one alternative preview"));
  assert.equal(posts("/alternatives")[0].body.request_id,posts("/alternatives")[1].body.request_id);
});

test("saved versions remain playable while an alternative is processing, with restore disabled", async()=>{
  const versions=savedVersions();const run={id:"running",version:3,status:"planning",manifest:{}};
  await act(async()=>root.render(React.createElement(AlternativeVersions,{jobId,run,versions,onUpdated:()=>{}})));
  assert.equal([...document.querySelectorAll("button")].some(e=>e.textContent==="Make another version"),false);
  assert.equal(button("Use version 1 as current · zero AI").disabled,true);
  await chooseOption("select","2");
  assert.match(document.querySelector("video").src,/version=2/);
  assert.match(document.querySelector("a").href,/download=true&version=2/);
  assert.equal(calls.length,0);
});

test("similar alternatives show an honest report and an earlier edit can be restored explicitly", async()=>{
  const versions=savedVersions();versions[1].manifest={revision_report:{alternative:{kind:"different_story",status:"similar",notice:"Still close to version 1. No automatic novelty retry was made.",compared_versions:[1]}}};
  await act(async()=>root.render(React.createElement(AlternativeVersions,{jobId,run:versions[1],versions,onUpdated:()=>{}})));
  assert.match(document.body.textContent,/Still similar to an earlier edit/);
  assert.equal(calls.length,0);
  await click(button("Use version 1 as current · zero AI"));
  assert.equal(posts("/revisions")[0].body.restore_version,1);
  assert.equal(posts("/revisions")[0].body.note,"");
  assert.equal(posts("/alternatives").length,0);
});


test("duration settings load on demand and save explicitly without retrying a job", async()=>{
  let updates=0;
  await act(async()=>root.render(React.createElement(JobDurationSettings,{jobId,failed:true,onUpdated:()=>{updates++;}})));
  assert.equal(calls.length,0);
  await click(button("Duration settings"));
  await waitFor(()=>document.querySelector('select[id$="-mode"]'));
  assert.match(document.body.textContent,/72 seconds for this edit/);
  assert.match(document.body.textContent,/not a required-script measurement/);
  await chooseOption('select[id$="-mode"]',"strict");
  await type('input[id$="-maximum"]',"60");
  assert.equal(calls.filter(c=>c.method==="PUT").length,0);
  await click(button("Save duration settings"));
  await waitFor(()=>updates===1);
  const saved=calls.find(c=>c.method==="PUT");
  assert.equal(saved.body.duration_mode,"strict"); assert.equal(saved.body.max_duration_seconds,60);
  assert.match(document.body.textContent,/Press Try again/);
  assert.equal(posts("/preview").length,0); assert.equal(posts("/jobs").length,0);
});

test("a failed duration save retains the requested settings and shows the error", async()=>{
  await act(async()=>root.render(React.createElement(JobDurationSettings,{jobId,failed:true,onUpdated:()=>assert.fail("must not refresh after failed save")})));
  await click(button("Duration settings"));
  await waitFor(()=>document.querySelector('select[id$="-mode"]'));
  await chooseOption('select[id$="-mode"]',"follow_story");
  await type('input[id$="-maximum"]',"120");
  durationFailure=true;
  await click(button("Save duration settings"));
  await waitFor(()=>document.body.textContent.includes("Wait for the current edit attempt"));
  assert.equal(document.querySelector('input[id$="-maximum"]').value,"120");
  assert.equal(document.querySelector('select[id$="-mode"]').value,"follow_story");
  assert.equal(posts("/preview").length,0);
});


test("batch creative import is explicit, skips duplicates, and retries only failed files", async () => {
  let loaded = 0;
  await act(async () => root.render(React.createElement(CreativeBatchImport, { onImported: async () => { loaded++; } })));
  await selectFiles('input[aria-label="Batch files"]', ["good.ogg", "existing.ogg", "retry.ogg"].map(name => new File(["synthetic sound"], name, { type: "audio/ogg" })));
  assert.equal(creativeImportAttempts.size, 0);
  for (const name of ["good.ogg", "existing.ogg", "retry.ogg"]) await type(`input[aria-label="Source for ${name}"]`, "https://example.org/sound-pack");
  await type('input[name="license_name"]', "CC0-1.0");
  await click(document.querySelector('input[name="commercial_use_confirmed"]'));
  await act(async () => document.querySelector("form").dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })));
  await waitFor(() => document.body.textContent.includes("1 imported · 1 already in library · 1 failed"));
  assert.equal(loaded, 1);
  assert.equal(creativeImportAttempts.get("good.ogg"), 1);
  assert.equal(creativeImportAttempts.get("existing.ogg"), 1);
  await act(async () => document.querySelector("form").dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })));
  await waitFor(() => document.body.textContent.includes("1 imported · 0 already in library · 0 failed"));
  assert.equal(creativeImportAttempts.get("retry.ogg"), 2);
  assert.equal(creativeImportAttempts.get("good.ogg"), 1);
  assert.equal(creativeImportAttempts.get("existing.ogg"), 1);
  assert.equal(loaded, 2);
});

test("creative import validates all source pages before sending any files", async () => {
  await act(async () => root.render(React.createElement(CreativeBatchImport, { onImported: async () => {} })));
  await selectFiles('input[aria-label="Batch files"]', [new File(["fixture"], "sound.ogg", { type: "audio/ogg" })]);
  await act(async () => document.querySelector("form").dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })));
  assert.equal(creativeImportAttempts.size, 0);
  assert.match(document.body.textContent, /every file a title and its HTTPS source/);
});

test("a local callout queues only after submit and preserves the inspected settings", async () => {
  await act(async () => root.render(React.createElement(FinishingWorkspace, { jobId, version: 2, clips: [{ duration: 3, source_in: 0, source_out: 3 }], onUpdated: () => {} })));
  await click(document.querySelector("summary"));
  await waitFor(() => document.querySelector("select"));
  await chooseOption("select", "callout");
  await type('input[placeholder="A short label or 2 / 5"]', "A real reaction");
  assert.equal(posts(`jobs/${jobId}/revisions`).length, 0);
  await act(async () => document.querySelector("form").dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })));
  const request = posts(`jobs/${jobId}/revisions`).at(-1).body;
  assert.equal(request.base_version, 2);
  assert.equal(request.note, "");
  assert.equal(request.finishing_settings.callouts[0].text, "A real reaction");
  assert.deepEqual(request.finishing_settings.layers, []);
  assert.deepEqual(request.finishing_settings.motions, []);
});


test("AI music approval is explicit per file and is never sent for effects", async () => {
  await act(async () => root.render(React.createElement(CreativeBatchImport, { onImported: async () => {} })));
  await selectFiles('input[aria-label="Batch files"]', [new File(["fixture"], "approved.mp3", { type: "audio/mpeg" })]);
  await type('input[aria-label="Source for approved.mp3"]', "https://pixabay.com/music/example-123/");
  await type('input[name="license_name"]', "Pixabay Content License");
  assert.equal(document.querySelector('input[aria-label="Approve AI-generated music for approved.mp3"]').checked, false);
  await click(document.querySelector('input[aria-label="Approve AI-generated music for approved.mp3"]'));
  assert.equal(creativeImportAttempts.size, 0);
  await act(async () => document.querySelector("form").dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })));
  await waitFor(() => creativeImportAttempts.get("approved.mp3") === 1);
  const query = new URLSearchParams(calls.find(c => c.route.startsWith("creative-assets/import?")).route.split("?")[1]);
  assert.equal(query.get("ai_generated_music"), "true");
  await chooseOption('select', "sound_effect");
  await selectFiles('input[aria-label="Batch files"]', [new File(["fixture"], "effect.ogg", { type: "audio/ogg" })]);
  await type('input[aria-label="Source for effect.ogg"]', "https://example.org/pack");
  assert.equal(document.querySelector('input[aria-label="Approve AI-generated music for effect.ogg"]'), null);
  await act(async () => document.querySelector("form").dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })));
  await waitFor(() => creativeImportAttempts.get("effect.ogg") === 1);
  const effect = new URLSearchParams(calls.filter(c => c.route.startsWith("creative-assets/import?")).at(-1).route.split("?")[1]);
  assert.equal(effect.get("ai_generated_music"), "false");
});

function setupFolders() {
  folderList=[{id:serverId,name:"Creams",description:"Product story",asset_count:1},{id:jobId,name:"Campaign",description:"",asset_count:0}];
  folderMembers=new Map([[serverId,new Set(["talk"])],[jobId,new Set()]]);
  managedAssets[0].collection_count=1;
}
async function mountFolderHome() {
  await act(async()=>root.render(React.createElement(MediaLibrary)));
  await waitFor(()=>document.querySelector('button[aria-label="Open folder Creams"]'));
}
async function openCreams() {
  await waitFor(()=>document.querySelector('button[aria-label="Open folder Creams"]'));
  await click(document.querySelector('button[aria-label="Open folder Creams"]'));
  await waitFor(()=>document.querySelector('input[aria-label="Select Product introduction"]'));
}

test("library opens with folder cards and opening a folder scopes search without writing",async()=>{
  setupFolders(); await mountFolderHome();
  assert.equal(document.querySelector('input[aria-label="Select Product introduction"]'),null);
  await openCreams();
  assert.equal(document.querySelector('input[aria-label="Select Cream close-up"]'),null);
  await type('input[type="search"]',"shelf");
  await waitFor(()=>calls.some(call=>call.route.startsWith("catalog/search?")));
  assert.equal(document.querySelector('input[aria-label="Select Cream close-up"]'),null,"global search evidence must not escape a folder");
  assert.equal(calls.filter(call=>call.method!=="GET").length,0);
});

test("bulk folder membership preserves originals, supports photos and removes only that grouping",async()=>{
  setupFolders(); managedAssets[1].mime_type="image/png";
  await mountBrowser();
  await click(document.querySelector('input[aria-label="Select Cream close-up"]'));
  await chooseOption('#folder-destination',serverId);
  assert.equal(posts(`library/collections/${serverId}/assets/batch`).length,0);
  await click(button("Add to folder"));
  await waitFor(()=>folderMembers.get(serverId).has("broll"));
  assert.equal(managedAssets[1].source_name,"VID_0002.mp4");
  assert.equal(managedAssets[1].library_status,"active");
  await click(button("Folders"));await openCreams();
  await click(document.querySelector('input[aria-label="Select Cream close-up"]'));
  await click(button("Remove from this folder"));
  await waitFor(()=>!folderMembers.get(serverId).has("broll"));
  assert.ok(folderMembers.get(serverId).has("talk"));
  assert.equal(managedAssets.length,3);
  assert.equal(posts("library/assets/batch").length,0);
  assert.equal(posts("projects").length,0);
});

test("failed folder action keeps selection and server error for retry",async()=>{
  setupFolders();await mountBrowser();
  await click(document.querySelector('input[aria-label="Select Cream close-up"]'));
  await chooseOption('#folder-destination',serverId);folderFailure=true;
  await click(button("Add to folder"));
  await waitFor(()=>document.querySelector('[role="alert"]')?.textContent.includes("Refresh this folder"));
  assert.equal(document.querySelector('input[aria-label="Select Cream close-up"]').checked,true);
  assert.equal(folderMembers.get(serverId).has("broll"),false);
});

test("folder create and rename require submission; deleting grouping leaves sources and other folder intact",async()=>{
  setupFolders();await mountFolderHome();
  await click(button("New folder"));
  await type('input[placeholder="e.g. Castor oil cream"]',"Soap");
  assert.equal(posts("library/collections").length,0);
  await click(button("Create folder"));
  await waitFor(()=>folderList.some(folder=>folder.name==="Soap"));
  assert.equal(managedAssets.length,3);
  await click(button("Folders"));await openCreams();
  await click([...document.querySelectorAll("summary")].find(item=>item.textContent==="Folder options"));
  await click(button("Rename folder"));await type('input[placeholder="e.g. Castor oil cream"]',"Cream demonstrations");
  assert.equal(calls.some(call=>call.method==="PATCH"),false);
  await click(button("Save folder name"));
  await waitFor(()=>folderList[0].name==="Cream demonstrations");
  await click(button("Remove folder"));
  assert.equal(calls.some(call=>call.method==="DELETE"),false);
  await click(button("Confirm remove folder"));
  await waitFor(()=>!folderList.some(folder=>folder.id===serverId));
  assert.equal(managedAssets.length,3);
  assert.equal(managedAssets[0].job_references,2);
  assert.ok(folderList.some(folder=>folder.id===jobId));
  assert.equal(managedAssets[0].library_status,"active");
});

test("folder, layout and filters return after leaving the library without replaying a selection",async()=>{
  setupFolders();await mountFolderHome();await openCreams();
  await click(document.querySelector('button[aria-label="List view"]'));
  await click(document.querySelector('input[aria-label="Select Product introduction"]'));
  await type('input[type="search"]',"Product");
  await act(async()=>root.unmount());root=createRoot(document.getElementById("root"));
  await act(async()=>root.render(React.createElement(MediaLibrary)));
  await waitFor(()=>document.querySelector('input[aria-label="Select Product introduction"]'));
  assert.equal(document.querySelector('input[type="search"]').value,"Product");
  assert.equal(document.querySelector('button[aria-label="List view"]').getAttribute("aria-pressed"),"true");
  assert.equal(document.querySelector('input[aria-label="Select Product introduction"]').checked,false);
  assert.match(document.querySelector('[aria-label="Library breadcrumb"]').textContent,/Creams/);
  assert.equal(calls.filter(call=>call.method!=="GET").length,0);
});

test("folder concept shortcut preselects scope without submitting AI or opening unrelated ideas",async()=>{
  setupFolders();await mountFolderHome();await openCreams();
  assert.equal(document.querySelector('a[href^="/concepts?collection="]').getAttribute("href"),`/concepts?collection=${serverId}`);
  await act(async()=>root.unmount());root=createRoot(document.getElementById("root"));
  window.history.replaceState(null,"",`/concepts?collection=${serverId}`);
  conceptHistory=[conceptSession()];
  await mountConcepts();
  assert.equal(document.querySelector('select[aria-label="Concept footage scope"]').value,serverId);
  assert.equal(document.querySelector('input[aria-label="Choose Recorded story 1"]'),null);
  assert.equal(posts("concepts").length,0);
});

test("missing folder shortcut asks for a scope instead of silently generating from the whole library",async()=>{
  window.history.replaceState(null,"",`/concepts?collection=${serverId}`);
  await act(async()=>root.render(React.createElement(ConceptDesk)));
  await waitFor(()=>document.querySelector('[role="alert"]')?.textContent.includes("folder is unavailable"));
  assert.equal(button("Generate reel ideas").disabled,true);
  assert.equal(posts("concepts").length,0);
  await chooseOption('select[aria-label="Concept footage scope"]',"");
  assert.equal(button("Generate reel ideas").disabled,false);
  assert.equal(posts("concepts").length,0);
});

async function mountSubtitles() {
  await act(async()=>root.render(React.createElement(SubtitleEditor,{jobId,runId:serverId,version:2,videoUrl:"/fixture.mp4",onApplied:()=>readyEvents++})));
  await click(button("Edit subtitles"));
  await waitFor(()=>document.querySelector('textarea[aria-label="Subtitle 1"]'));
}
test("subtitle typing never saves or renders; explicit draft save survives reopening",async()=>{
  await mountSubtitles();
  await type('textarea[aria-label="Subtitle 1"]',"Castor oil!");
  assert.equal(calls.filter(call=>call.method!=="GET").length,0);
  await click(button("Save draft"));
  await waitFor(()=>subtitleFixture.saved);
  assert.equal(posts(`subtitles/apply`).length,0);
  assert.equal(subtitleFixture.cues[0].text,"Castor oil!");
  assert.equal(subtitleFixture.cues[0].start,.1);
  assert.equal(subtitleFixture.cues[0].end,2.5);
  await click(button("Close"));
  await act(async()=>root.unmount()); root=createRoot(document.getElementById("root"));
  await mountSubtitles();
  assert.equal(document.querySelector('textarea[aria-label="Subtitle 1"]').value,"Castor oil!");
});
test("apply subtitles saves unsaved edits then requests exactly one local preview",async()=>{
  await mountSubtitles();
  await type('textarea[aria-label="Subtitle 2"]',"A better cream.");
  await click(button("Apply subtitles"));
  await waitFor(()=>readyEvents===1);
  const writes=calls.filter(call=>call.method!=="GET");
  assert.deepEqual(writes.map(call=>call.method),["PUT","POST"]);
  assert.ok(writes[1].route.endsWith("/subtitles/apply"));
  assert.equal(writes[1].body.revision,1);
  assert.equal(writes[0].body.cues[1].text,"A better cream.");
});
test("find replace, hide, positioning and undo stay in the subtitle draft",async()=>{
  await mountSubtitles();
  await click([...document.querySelectorAll("summary")].find(item=>item.textContent==="Find, replace & move all"));
  await type('input[aria-label="Find subtitle text"]',"Royal");
  await type('input[aria-label="Replacement subtitle text"]',"oil");
  await click(button("Replace all"));
  assert.equal(document.querySelector('textarea[aria-label="Subtitle 1"]').value,"Costa oil!");
  const hide=document.querySelector('[aria-label="Timed subtitle transcript"] input[type="checkbox"]');
  await click(hide);
  await chooseOption('select[aria-label="Position subtitle 2"]',"upper");
  await click(button("Save draft"));
  assert.equal(subtitleFixture.cues[0].hidden,true);
  assert.equal(subtitleFixture.cues[1].position,"upper");
  assert.equal(subtitleFixture.cues[1].start,3.2);
  await click(button("Undo"));
  assert.equal(document.querySelector('select[aria-label="Position subtitle 2"]').value,"");
  assert.equal(calls.filter(call=>call.method==="POST").length,0);
});
test("subtitle conflict preserves unsaved text and never starts a render",async()=>{
  await mountSubtitles();subtitleFailure=true;
  await type('textarea[aria-label="Subtitle 1"]',"My unsaved correction");
  await click(button("Apply subtitles"));
  await waitFor(()=>document.querySelector('[role="alert"]')?.textContent.includes("another tab"));
  assert.equal(document.querySelector('textarea[aria-label="Subtitle 1"]').value,"My unsaved correction");
  assert.equal(calls.filter(call=>call.method==="POST").length,0);
});
test("subtitle split and merge preserve the full interval and words",()=>{
  const cue={id:"cue-0",start:1,end:3,text:"Really good cream",position:null,hidden:false};
  const parts=splitSubtitle(cue,6);
  assert.equal(parts[0].start,1);assert.equal(parts[1].end,3);
  assert.equal(parts[0].end,parts[1].start);
  assert.equal(parts.map(part=>part.text).join(" "),cue.text);
  assert.throws(()=>splitSubtitle({...cue,text:"  cream words"},1),/between two words/);
  const merged=mergeSubtitles(...parts);
  assert.equal(merged.start,cue.start);assert.equal(merged.end,cue.end);assert.equal(merged.text,cue.text);
});

test("standalone import registers folder and mixed-media labels before analysis", async () => {
  setupFolders();
  await act(async()=>root.render(React.createElement(LibraryUpload,{folders:folderList,destination:serverId,onReady:async()=>{readyEvents+=1;}})));
  await act(async()=>root.render(React.createElement(LibraryUpload,{folders:folderList,destination:"",onReady:async()=>{readyEvents+=1;}})));
  assert.equal(document.querySelector('select[aria-label="Upload destination folder"]').value,serverId,'Opening the Inbox preserves the chosen destination');
  await type('input[aria-label="Upload file name prefix"]','Cream proof');
  await chooseOption('select[aria-label="Upload footage role"]','broll');
  await selectFiles('input[type="file"]',[clip(),new File(['photo'],'review.png',{type:'image/png'})]);
  assert.equal(calls.length,0);
  await click(button('Upload 2 files to library'));
  await waitFor(()=>posts('/assets').length===2);
  const bodies=posts('/assets').map(c=>c.body);
  assert.deepEqual(bodies[0].library_intake,{display_name:'Cream proof 001',media_role:'broll',collection_id:serverId});
  assert.deepEqual(bodies[1].library_intake,{display_name:'Cream proof 002',media_role:'auto',collection_id:serverId});
  assert.ok(bodies.every(b=>b.job_id===null));
  assert.equal(posts('library/assets/batch').length,0);
  assert.equal(posts('/jobs').length,0);
});

test("large upload batches use two transfer slots, advance after errors, and group analysis checks",async()=>{
  await mountLibrary();
  await selectFiles('input[type="file"]',Array.from({length:5},(_,i)=>clip(`source-${i}.mp4`)));
  await click(button('Upload 5 files to library'));
  await waitFor(()=>transfers.length===2);
  assert.equal(posts('/assets').length,2);
  assert.match(document.body.textContent,/Waiting for an upload slot/);
  await act(async()=>transfers[0].callbacks.onError(new Error('Connection interrupted')));
  await waitFor(()=>transfers.length===3);
  await act(async()=>{transfers[1].callbacks.onSuccess();transfers[2].callbacks.onSuccess();});
  await waitFor(()=>transfers.length===5);
  await waitFor(()=>document.body.textContent.includes('Ready in your library'));
  assert.equal(calls.filter(c=>/^assets\/[^/]+\/analysis$/.test(c.route)).length,0);
  const registered=posts('/assets').length;
  await click(document.querySelector('button[aria-label="Resume source-0.mp4"]'));
  assert.match(document.body.textContent,/Waiting for an upload slot/);
  await click(document.querySelector('button[aria-label="Pause source-3.mp4"]'));
  await waitFor(()=>transfers[0].resumes===1);
  assert.equal(posts('/assets').length,registered,'Resume uses the original asset and transfer');
});

test("library pages request only 60 rows, and changing pages clears hidden selections",async()=>{
  const template=managedAssets[0];
  for(let i=0;i<130;i++)managedAssets.push({...template,id:`page-${String(i).padStart(3,'0')}`,display_name:`Product take ${i}`,created_at:'2024-01-01T00:00:00Z'});
  await mountBrowser();
  assert.equal(document.querySelectorAll('input[aria-label^="Select "]:not([aria-label="Select displayed files"])').length,60);
  await click(document.querySelector('input[aria-label="Select Product introduction"]'));
  await click(button('Next files'));
  await waitFor(()=>document.body.textContent.includes('61–120 of 133'));
  assert.equal(document.querySelector('[aria-label="Selected media actions"]'),null);
  assert.equal(document.querySelector('input[aria-label="Select Product introduction"]'),null);
  await click(button('Previous files'));
  await waitFor(()=>document.querySelector('input[aria-label="Select Product introduction"]'));
  assert.equal(document.querySelector('input[aria-label="Select Product introduction"]').checked,false);
  assert.ok(calls.some(c=>c.route.startsWith('library/browse?')&&new URLSearchParams(c.route.split('?')[1]).get('offset')==='60'));
  assert.equal(calls.filter(c=>c.route.startsWith('library/assets?')).length,0,'No full-library download');
  assert.equal(calls.filter(c=>c.method!=='GET').length,0);
  await type('input[type="search"]','Product');
  await waitFor(()=>document.body.textContent.includes('132 files'));
  const searches=calls.filter(c=>c.route.startsWith('catalog/search?')).length;
  await click(button('Next files'));
  await waitFor(()=>document.body.textContent.includes('61–120 of 132'));
  assert.equal(calls.filter(c=>c.route.startsWith('catalog/search?')).length,searches,'Paging reuses the bounded speech/visual query');
});

function setupIntake(){
  intakeItems=managedAssets.map((a,i)=>({...a,intake_status:i===0?'ready':i===1?'processing':'failed',error:i===2?'Local analysis failed':'',folders:[]}));
}
test("Inbox separates processing from reviewable imports, files explicitly, then marks reviewed",async()=>{
  setupFolders();setupIntake();await mountBrowser();await click(button('Inbox'));
  await waitFor(()=>document.querySelector('input[aria-label="Review Product introduction"]'));
  assert.equal(document.querySelector('input[aria-label="Review Cream close-up"]').disabled,true);
  assert.equal(document.querySelector('input[aria-label="Review VID_0003.mp4"]').disabled,true);
  await click(document.querySelector('input[aria-label="Review Product introduction"]'));
  await chooseOption('select[aria-label="File imports in folder"]',jobId);
  assert.equal(posts('library/intake/review').length,0);
  await click(button('Add imports to folder'));
  await waitFor(()=>folderMembers.get(jobId).has('talk'));
  assert.equal(posts('library/intake/review').length,0,'Filing does not silently mark reviewed');
  await waitFor(()=>document.querySelector('input[aria-label="Review Product introduction"]'));
  await click(document.querySelector('input[aria-label="Review Product introduction"]'));
  await click(button('Mark reviewed'));
  await waitFor(()=>!document.querySelector('input[aria-label="Review Product introduction"]'));
  assert.deepEqual(posts('library/intake/review')[0].body,{asset_ids:['talk'],action:'review'});
  assert.ok(managedAssets.some(a=>a.id==='talk'));
  assert.equal(posts('library/organization').length,0);
  assert.equal(posts('/jobs').length,0);
});

test("Inbox dismiss requires confirmation, never deletes and reopens without replaying selection",async()=>{
  setupIntake();await mountBrowser();await click(button('Inbox'));
  await waitFor(()=>document.querySelector('input[aria-label="Review Product introduction"]'));
  await click(document.querySelector('input[aria-label="Review Product introduction"]'));
  await click([...document.querySelectorAll('button')].find(b=>b.textContent==='Dismiss from Inbox'));
  assert.equal(posts('library/intake/review').length,0);
  await click(button('Confirm dismiss'));
  await waitFor(()=>intakeItems.length===2);
  assert.equal(posts('library/intake/review')[0].body.action,'dismiss');
  assert.equal(calls.filter(c=>c.method==='DELETE').length,0);
  await click(button('All media'));await waitFor(()=>document.querySelector('input[aria-label="Select Product introduction"]'));
  await click(button('Inbox'));await waitFor(()=>document.querySelector('input[aria-label="Review Cream close-up"]'));
  assert.equal(document.querySelector('[aria-label="Selected imports"]'),null);
  assert.equal(managedAssets.length,3);
});
