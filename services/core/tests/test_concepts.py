import json
import unittest
from contextlib import contextmanager
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import UUID, uuid4

from fastapi import HTTPException
from pydantic import ValidationError

from app.concept_inventory import (MAX_INVENTORY_CHARACTERS, balanced_sources, compact_inventory,
                                   concept_brief, public_inventory, validate_concepts)
from app.concept_provider import generate_concepts
from app.concept_schemas import ConceptRequestCreate, ConceptSelection
from app.concepts import process_one_concept, render_selected_concepts, request_concepts
from app.config import Settings
from app.editor_provider import _request_plan
from app.concept_schemas import ConceptProposals


def asset(index, project="group", role="auto"):
    return {"id": uuid4(), "project_id": project, "sha256": f"{index:064x}", "display_name": f"Cream source {index}",
            "source_name": f"camera-{index}.mp4", "project_name": project, "media_role": role,
            "mime_type": "video/mp4", "manifest": {"derived": {"thumbnail": "private/thumb.jpg"}},
            "storage_key": "private/original", "notes": "", "tags": [], "job_uses": 0}


def fixture():
    rows = [asset(1), asset(2)]
    segments = [{"id": index, "asset_id": row["id"], "start_seconds": n * 5,
                 "end_seconds": (n + 1) * 5, "text": text}
                for row in rows for index, n, text in ((1 if row is rows[0] else 3, 0, "Here is the product we are demonstrating today."),
                                                      (2 if row is rows[0] else 4, 1, "This is the complete explanation and supported result."))]
    payload = ConceptRequestCreate(id=uuid4())
    inventory = compact_inventory(rows, segments, payload)
    doc = {"concepts": [dict(title="A useful demonstration", angle="Show the product and its result.",
                             script=[dict(evidence_id=1, role="hook"), dict(evidence_id=2, role="ending")], visuals=[]),
                        dict(title="A second explanation", angle="A different recorded explanation.",
                             script=[dict(evidence_id=3, role="hook"), dict(evidence_id=4, role="ending")], visuals=[])]}
    concepts = validate_concepts(doc, inventory, payload.id)
    session = dict(id=payload.id, status="ready", concepts=concepts, inventory=inventory,
                   audience="", privacy_mode="hybrid", model="test-model")
    return payload, inventory, doc, session


class ConceptInventoryTests(unittest.TestCase):
    def test_discovery_deduplicates_and_spreads_budget_across_upload_groups(self):
        rows = [asset(index) for index in range(10)] + [asset(11, "late group")]
        rows.insert(1, {**rows[0], "id": uuid4()})
        chosen = balanced_sources(rows, "", 4)
        self.assertEqual(len(chosen), 4)
        self.assertEqual(len({row["sha256"] for row in chosen}), 4)
        self.assertIn("late group", {row["project_name"] for row in chosen})

    def test_public_inventory_excludes_original_paths_and_checksums(self):
        _, inventory, _, _ = fixture()
        serialized = json.dumps(public_inventory(inventory))
        self.assertNotIn("private/original", serialized)
        self.assertNotIn("private/thumb", serialized)
        self.assertNotIn("sha256", serialized)
        self.assertIn("supported result", serialized)

    def test_large_inventory_keeps_bounded_speech_coverage_from_late_sources(self):
        rows = [asset(index, f"group-{index}") for index in range(60)]
        segments = [dict(id=source * 100 + n, asset_id=row["id"], start_seconds=n * 3, end_seconds=n * 3 + 3,
                         text=f"This is the complete recorded explanation {n} from source {source}. " * 4)
                    for source, row in enumerate(rows) for n in range(36)]
        inventory = compact_inventory(rows, segments, ConceptRequestCreate(id=uuid4()))
        self.assertLessEqual(len(json.dumps(public_inventory(inventory), ensure_ascii=False)), MAX_INVENTORY_CHARACTERS)
        self.assertEqual(len({item["asset_id"] for item in inventory["evidence"]}), 60)
        self.assertTrue(any(item["start"] >= 100 for item in inventory["evidence"]))

    def test_recent_concepts_share_the_same_text_budget_and_no_new_model_call(self):
        row = asset(1)
        payload = ConceptRequestCreate(id=uuid4())
        recent = [{"title": "A previous story", "speech_evidence_ids": [1,2]}]
        inventory = compact_inventory([row], [], payload, recent=recent)
        self.assertEqual(public_inventory(inventory)["recent_concepts"], recent)
        self.assertLess(len(json.dumps(public_inventory(inventory))), MAX_INVENTORY_CHARACTERS)

    def test_long_library_metadata_leaves_room_for_recorded_speech(self):
        rows = [{**asset(index), "display_name": "x" * 160, "project_name": "p" * 160,
                 "notes": "n" * 400, "tags": ["t" * 60] * 3} for index in range(60)]
        segments = [dict(id=index, asset_id=row["id"], start_seconds=0, end_seconds=5,
                         text="This is a complete recorded explanation of the product.")
                    for index, row in enumerate(rows)]
        inventory = compact_inventory(rows, segments, ConceptRequestCreate(id=uuid4(), focus="f" * 1200, audience="a" * 600))
        self.assertLessEqual(len(json.dumps(public_inventory(inventory), ensure_ascii=False)), MAX_INVENTORY_CHARACTERS)
        self.assertGreaterEqual(len(inventory["evidence"]), 2)

    def test_broll_labels_do_not_become_spoken_script(self):
        row = asset(1, role="broll")
        inventory = compact_inventory([row], [dict(id=1, asset_id=row["id"], start_seconds=0,end_seconds=5,text="This person is saying a complete sentence.")], ConceptRequestCreate(id=uuid4()))
        self.assertEqual(inventory["evidence"], [])

    def test_concepts_display_exact_recorded_words_and_stable_ids(self):
        payload, inventory, doc, session = fixture()
        concepts = validate_concepts(doc, inventory, payload.id)
        self.assertEqual(concepts, session["concepts"])
        self.assertEqual(concepts[0]["script"][0]["text"], inventory["evidence"][0]["text"])
        self.assertEqual(concepts[0]["estimated_seconds"], 10)
        self.assertIn(inventory["evidence"][0]["text"], concept_brief(concepts[0]))
        self.assertNotIn("storage_key", concept_brief(concepts[0]))

    def test_unknown_citations_visuals_duplicates_and_excessive_scripts_are_rejected(self):
        payload, inventory, doc, _ = fixture()
        mutations = [lambda d: d["concepts"][0]["script"][0].update(evidence_id=999),
                     lambda d: d["concepts"][0]["script"][1].update(evidence_id=1),
                     lambda d: d["concepts"][0]["visuals"].append(dict(asset_id=str(uuid4()), reason="Unknown source")),
                     lambda d: d["concepts"].append(deepcopy(d["concepts"][0]))]
        for mutate in mutations:
            bad = deepcopy(doc); mutate(bad)
            with self.assertRaises(ValueError):
                validate_concepts(bad, inventory, payload.id)

    def test_selection_rejects_more_than_two_and_duplicate_ids(self):
        id = uuid4()
        for ids in ([], [id,id], [uuid4(),uuid4(),uuid4()]):
            with self.assertRaises(ValidationError):
                ConceptSelection(concept_ids=ids)

    def test_privacy_controls_preview_sharing_without_a_second_model_request(self):
        _, inventory, _, _ = fixture()
        settings = Settings(database_url="postgresql://example.invalid/test", upload_hook_secret="x" * 32)
        for privacy in ("text_only", "hybrid"):
            with patch("app.concept_provider.usable_chatgpt_credentials", return_value={"access_token":"fixture"}), \
                 patch("app.concept_provider._request_plan", return_value=({"concepts": []}, {"total_tokens": 123})) as request, \
                 patch("app.editor_visual_context.high_impact_visuals", return_value=[{"type":"input_image","image_url":"fixture-image"}]) as visuals:
                generate_concepts(inventory, privacy, settings)
                request.assert_called_once()
                task = request.call_args.kwargs["structured_task"]
                self.assertNotIn("private/", json.dumps(task))
                self.assertEqual(visuals.call_count, 1 if privacy == "hybrid" else 0)


class SelectionDatabase:
    def __init__(self, session):
        self.session = session
        self.jobs = {}
        self.writes = []
        self.missing = set()

    @contextmanager
    def connection(self):
        previous = deepcopy((self.jobs, self.writes))
        try: yield self
        except Exception:
            self.jobs, self.writes = previous
            raise

    def execute(self, sql, parameters=()):
        sql = " ".join(sql.split())
        if sql.startswith("SELECT * FROM reel_concept_requests"):
            self.result = self.session
        elif sql.startswith("SELECT concept_id,job_id"):
            self.result = [dict(concept_id=id, job_id=job) for id,job in self.jobs.items()]
        elif sql.startswith("SELECT a.id,a.sha256"):
            self.result = [dict(id=UUID(a["asset_id"]), sha256=a["sha256"]) for a in self.session["inventory"]["assets"] if a["asset_id"] not in self.missing]
        elif sql.startswith("INSERT"):
            self.writes.append((sql, parameters))
            if "INSERT INTO reel_concept_jobs" in sql: self.jobs[parameters[1]] = parameters[2]
            self.result = None
        else: raise AssertionError(sql)
        return self
    def fetchone(self): return self.result
    def fetchall(self): return self.result


class ConceptSelectionTests(unittest.TestCase):
    def setUp(self):
        _, _, _, self.session = fixture()
        self.db = SelectionDatabase(self.session)
        for name, value in (("connection", self.db.connection), ("assert_ai_budget", Mock()), ("assert_job_capacity", Mock()), ("get_settings", lambda: SimpleNamespace(chatgpt_model="configured-model"))):
            patcher = patch("app.concepts." + name, value); patcher.start(); self.addCleanup(patcher.stop)
        self.selection = ConceptSelection(concept_ids=[UUID(item["id"]) for item in self.session["concepts"]])

    def test_two_selected_concepts_create_two_jobs_once_and_only_attach_their_sources(self):
        first = render_selected_concepts(self.session["id"], self.selection, "editor@example.invalid")
        count = len(self.db.writes)
        second = render_selected_concepts(self.session["id"], self.selection, "editor@example.invalid")
        self.assertEqual(first, second)
        self.assertEqual(len(self.db.writes), count)
        self.assertEqual(len(first["jobs"]), 2)
        self.assertEqual(sum("INSERT INTO edit_runs" in sql for sql,_ in self.db.writes), 2)
        self.assertEqual(sum("INSERT INTO job_assets" in sql for sql,_ in self.db.writes), 2)
        for sql, args in self.db.writes:
            if "INSERT INTO projects" in sql:
                self.assertIn("recorded lines", args[2])

    def test_trashed_or_changed_source_rejects_entire_selection_without_creating_jobs(self):
        self.db.missing.add(self.session["inventory"]["assets"][0]["asset_id"])
        with self.assertRaises(HTTPException) as error:
            render_selected_concepts(self.session["id"], self.selection, "editor@example.invalid")
        self.assertEqual(error.exception.status_code, 409)
        self.assertFalse(self.db.writes)

    def test_capacity_failure_during_second_job_rolls_back_both(self):
        with patch("app.concepts.assert_job_capacity", side_effect=[None, HTTPException(status_code=429,detail="wait")]):
            with self.assertRaises(HTTPException):
                render_selected_concepts(self.session["id"], self.selection, "editor@example.invalid")
        self.assertFalse(self.db.writes)
        self.assertFalse(self.db.jobs)

    def test_unselected_or_not_ready_concepts_cannot_start_jobs(self):
        with self.assertRaises(HTTPException):
            render_selected_concepts(self.session["id"], ConceptSelection(concept_ids=[uuid4()]), "editor@example.invalid")
        self.session["status"] = "generating"
        with self.assertRaises(HTTPException):
            render_selected_concepts(self.session["id"], self.selection, "editor@example.invalid")
        self.assertFalse(self.db.writes)


class ConceptWorkerTests(unittest.TestCase):
    def test_invalid_model_citations_record_usage_and_fail_without_automatic_model_retry(self):
        payload, inventory, doc, _ = fixture()
        doc["concepts"][0]["script"][0]["evidence_id"] = 999
        row = dict(id=payload.id, inventory=inventory, privacy_mode="text_only")
        database = Mock()
        database.execute.return_value.fetchone.side_effect = [row, None]
        @contextmanager
        def connection(): yield database
        state = SimpleNamespace(active_concept_request_id=None)
        with patch("app.concepts.connection", connection), patch("app.concepts.assert_ai_budget"), \
             patch("app.concepts.get_settings", return_value=SimpleNamespace(edit_lease_seconds=900)), \
             patch("app.concepts.generate_concepts", return_value=(doc, {"model":"fixture-model","usage":{"total_tokens":123}})) as provider, \
             patch("app.concepts._record_usage") as record:
            self.assertTrue(process_one_concept(state))
            self.assertFalse(process_one_concept(state))
            provider.assert_called_once()
            record.assert_called_once()
        self.assertIsNone(state.active_concept_request_id)
        self.assertTrue(any("status='failed'" in call.args[0] for call in database.execute.call_args_list))


class ConceptRequestTests(unittest.TestCase):
    def test_repeated_request_id_reuses_saved_session_without_new_inventory_or_model_work(self):
        payload, _, _, session = fixture()
        session.update(focus=payload.focus, collection_id=None)
        database = Mock(); database.execute.return_value.fetchone.return_value = session
        @contextmanager
        def connection(): yield database
        with patch("app.concepts.connection", connection), patch("app.concepts.load_inventory") as inventory:
            result = request_concepts(payload)
        self.assertEqual(result["id"], payload.id)
        self.assertNotIn("inventory", result)
        inventory.assert_not_called()
        self.assertFalse(any("INSERT" in call.args[0] for call in database.execute.call_args_list))

    def test_reusing_request_id_with_different_privacy_or_focus_is_rejected(self):
        payload, _, _, session = fixture()
        session.update(focus="A different scope", collection_id=None)
        database = Mock(); database.execute.return_value.fetchone.return_value = session
        @contextmanager
        def connection(): yield database
        with patch("app.concepts.connection", connection), patch("app.concepts.load_inventory") as inventory:
            with self.assertRaises(HTTPException) as error:
                request_concepts(payload)
        self.assertEqual(error.exception.status_code, 409)
        inventory.assert_not_called()

    def test_no_speech_ready_does_not_queue_a_model_call(self):
        payload = ConceptRequestCreate(id=uuid4())
        database = Mock()
        database.execute.return_value.fetchone.side_effect = [None, {"count":0}]
        @contextmanager
        def connection(): yield database
        with patch("app.concepts.connection", connection), patch("app.concepts.assert_ai_budget"), \
             patch("app.concepts.load_inventory", return_value=({"assets":[],"evidence":[]},{})):
            with self.assertRaises(HTTPException) as error:
                request_concepts(payload)
        self.assertEqual(error.exception.status_code, 409)
        self.assertFalse(any("INSERT" in call.args[0] for call in database.execute.call_args_list))


class ConceptTransportTests(unittest.TestCase):
    def test_structured_concept_transport_preserves_streaming_no_storage_and_exact_task_schema(self):
        _, _, document, _ = fixture()
        settings = Settings(database_url="postgresql://example.invalid/test", upload_hook_secret="x" * 32)
        events = [b'data: ' + json.dumps({"type":"response.output_text.delta", "delta":json.dumps(document)}).encode() + b'\n',
                  b'data: ' + json.dumps({"type":"response.completed", "response":{"id":"fixture-response", "model":"fixture-model", "usage":{"total_tokens":321}}}).encode() + b'\n']
        response = Mock(); response.__enter__ = Mock(return_value=events); response.__exit__ = Mock(return_value=False)
        task = dict(name="library_reel_concepts", instructions="Find recorded stories.",
                    content=[{"type":"input_text","text":"Only supplied transcript evidence."}], schema=ConceptProposals.model_json_schema())
        with patch("app.editor_provider.urllib.request.urlopen", return_value=response) as request, \
             patch("app.editor_provider._model_content", side_effect=AssertionError("Must not build another edit prompt")):
            actual, usage = _request_plan(endpoint="https://example.invalid/responses", token="fixture", model="fixture-model",
                                          reasoning_effort="medium", context={}, settings=settings, structured_task=task)
        body = json.loads(request.call_args.args[0].data)
        self.assertEqual(body["instructions"], task["instructions"])
        self.assertEqual(body["input"][0]["content"], task["content"])
        self.assertEqual(body["text"]["format"]["schema"], task["schema"])
        self.assertEqual(body["text"]["format"]["name"], "library_reel_concepts")
        self.assertFalse(body["store"])
        self.assertTrue(body["stream"])
        self.assertEqual(actual, document)
        self.assertEqual(usage["total_tokens"], 321)
        request.assert_called_once()

    def test_concept_schema_has_required_closed_objects_for_strict_structured_output(self):
        schema = ConceptProposals.model_json_schema()
        for definition in [schema, *schema["$defs"].values()]:
            if definition.get("type") == "object":
                self.assertFalse(definition["additionalProperties"])
                self.assertEqual(set(definition["required"]), set(definition["properties"]))
