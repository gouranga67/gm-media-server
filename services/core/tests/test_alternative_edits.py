import json
import unittest
from contextlib import contextmanager
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

from fastapi import HTTPException
from pydantic import ValidationError

from app import editing
from app.alternative_edits import (
    alternative_instruction,
    assess_alternative,
    compact_history,
    prepare_alternative,
)
from app.editor_provider import _model_content, _public_context
from app.take_quality import editing_policy
from app.schemas import AlternativeCreate


def cut(identity="one", start=0, end=4, **extra):
    return {"asset_id": identity, "source_in": start, "source_out": end, **extra}


class AlternativeEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.assets = [
            {
                "asset_id": "one",
                "sha256": "first",
                "transcript_segments": [
                    {
                        "start": 0,
                        "end": 4,
                        "text": "This cream started with our family recipe.",
                    },
                    {
                        "start": 10,
                        "end": 14,
                        "text": "Customers describe how the texture feels.",
                    },
                ],
            },
            {"asset_id": "copy", "sha256": "first"},
            {
                "asset_id": "two",
                "sha256": "second",
                "transcript_segments": [
                    {
                        "start": 0,
                        "end": 4,
                        "text": "This cream started with our family recipe.",
                    }
                ],
            },
        ]
        self.before = {"clips": [cut()]}
        self.rows = [{"id": "reference", "version": 1, "document": self.before}]

    def assess(self, current, kind="different_story", rows=None):
        return assess_alternative(kind, current, rows or self.rows, self.assets)

    def test_music_prose_and_tiny_handles_do_not_count_as_an_alternative(self):
        for kind in ("different_cut", "different_story"):
            for document in (
                {
                    **self.before,
                    "music_track_id": "new",
                    "editorial_summary": "Entirely new!",
                },
                {"clips": [cut(start=0.01, end=3.99)]},
            ):
                with self.subTest(kind=kind, document=document):
                    self.assertEqual(self.assess(document, kind)["status"], "similar")

    def test_splitting_a_clip_or_uploading_identical_bytes_cannot_fake_novelty(self):
        for document in (
            {"clips": [cut(end=2), cut(start=2)]},
            {"clips": [cut("copy")]},
        ):
            self.assertEqual(self.assess(document)["status"], "similar")
            self.assertEqual(
                self.assess(document)["comparisons"][0]["source_overlap"], 1
            )

    def test_reordering_the_middle_is_a_different_cut_even_with_the_same_opening(self):
        before = {
            "clips": [cut(start=0, end=2), cut(start=2, end=4), cut(start=10, end=12)]
        }
        after = {"clips": [before["clips"][0], before["clips"][2], before["clips"][1]]}
        result = self.assess(
            after, "different_cut", [{"version": 1, "document": before}]
        )
        self.assertEqual(result["status"], "different_cut")

    def test_another_take_of_same_script_is_not_a_different_story(self):
        result = self.assess({"clips": [cut("two")]})
        self.assertEqual(result["status"], "similar")
        self.assertEqual(result["comparisons"][0]["speech_similarity"], 1)

    def test_visual_treatment_counts_for_a_cut_but_not_for_a_story(self):
        new = {"clips": [cut(visual_preset="punch_in")]}
        self.assertEqual(self.assess(new, "different_cut")["status"], "different_cut")
        self.assertEqual(self.assess(new, "different_story")["status"], "similar")

    def test_different_recorded_passage_is_reported_without_claiming_semantic_quality(
        self,
    ):
        result = self.assess({"clips": [cut(start=10, end=14)]})
        self.assertEqual(result["status"], "different_selections")
        self.assertEqual(result["semantic_judgement"], "human_review_required")
        self.assertEqual(result["hosted_model_calls"], 0)

    def test_comparison_checks_other_versions_not_only_the_reference(self):
        alternate = {"clips": [cut(start=10, end=14)]}
        rows = self.rows + [{"version": 2, "document": alternate}]
        result = self.assess(alternate, rows=rows)
        self.assertEqual(result["status"], "similar")
        self.assertEqual(result["closest_version"], 2)

    def test_history_is_bounded_and_context_unlocks_only_an_explicit_new_story(self):
        original = deepcopy(self.rows)
        history = compact_history(self.rows * 30, self.assets)
        self.assertLessEqual(len(history), 8)
        self.assertLess(len(json.dumps(history)), 6000)
        for kind in ("different_cut", "different_story"):
            context = {
                "job": {"recipe": "talking_head", "_selected_story_contract": {}},
                "project": {"privacy_mode": "transcript_only"},
                "assets": self.assets,
                "selected_concept": {"script": ["recorded"]},
                "revision": {"mode": "targeted", "previous_plan": self.before},
            }
            prepare_alternative(context, {"alternative_kind": kind}, self.rows)
            self.assertEqual("selected_concept" in context, kind == "different_cut")
            prompt = _model_content(
                context, SimpleNamespace(editor_max_context_characters=120000)
            )[0]["text"]
            self.assertIn("successful option to keep", prompt)
            self.assertNotIn("rejected draft", prompt)
            public = _public_context(context, 120000)
            self.assertNotIn("_alternative_history", public)
            self.assertEqual(public["alternative"]["earlier_edits"], history[:1])
        self.assertEqual(self.rows, original)

    def test_alternative_default_does_not_accidentally_request_bloopers(self):
        for kind in ("different_cut", "different_story"):
            instruction = alternative_instruction(kind)
            self.assertLess(len(alternative_instruction(kind, "x" * 600)), 1200)
            self.assertFalse(
                editing_policy({"brief": "Product introduction " + instruction})[
                    "bloopers_requested"
                ]
            )


class AlternativeRequestTests(unittest.TestCase):
    def setUp(self):
        self.job_id, self.reference = uuid4(), uuid4()
        self.payload = AlternativeCreate(
            request_id=uuid4(), base_version=2, kind="different_cut"
        )
        self.context = {
            "ready_for_editing": True,
            "assets": [],
            "project": {"privacy_mode": "transcript_only"},
        }
        self.prior = {
            "id": self.reference,
            "version": 2,
            "caption_corrections": [],
            "caption_settings": {"position": "upper"},
            "effects_enabled": False,
            "broll_enabled": False,
        }
        self.existing = None
        self.database = Mock()
        self.database.execute.side_effect = self.query

    def query(self, sql, params=()):
        if "alternative_request_id=%s" in sql:
            return Mock(fetchone=lambda: self.existing)
        if "SELECT id FROM jobs" in sql:
            return Mock(fetchone=lambda: {"id": self.job_id})
        if "SELECT 1 FROM edit_runs" in sql:
            return Mock(fetchone=lambda: None)
        if "SELECT * FROM edit_runs" in sql:
            return Mock(fetchone=lambda: self.prior)
        if "COALESCE(max(version)" in sql:
            return Mock(fetchone=lambda: {"version": 4})
        if "INSERT INTO edit_runs" in sql:
            return Mock(
                fetchone=lambda: {"id": uuid4(), "version": 4, "status": "pending"}
            )
        return Mock(fetchone=lambda: None)

    def call(self):
        @contextmanager
        def connection():
            yield self.database

        with patch.multiple(
            editing,
            _context_or_http=Mock(return_value=self.context),
            connection=connection,
            assert_job_capacity=Mock(),
        ):
            return editing.request_alternative(self.job_id, self.payload)

    def test_creates_new_version_preserving_reference_and_removal_controls(self):
        self.assertEqual(self.call()["version"], 4)
        inserts = [
            call
            for call in self.database.execute.call_args_list
            if "INSERT INTO edit_runs" in call.args[0]
        ]
        self.assertEqual(len(inserts), 1)
        values = inserts[0].args[1]
        self.assertEqual(values[2], self.reference)
        self.assertIs(values[6], False)
        self.assertIs(values[10], False)
        self.assertEqual(values[-3:-1], ("different_cut", self.payload.request_id))
        self.assertFalse(
            any(
                "UPDATE edit_plans" in call.args[0] or "DELETE" in call.args[0]
                for call in self.database.execute.call_args_list
            )
        )

    def test_replayed_request_returns_same_version_and_changed_payload_is_rejected(
        self,
    ):
        self.existing = {
            "id": uuid4(),
            "alternative_kind": "different_cut",
            "base_version": 2,
            "revision_note": alternative_instruction("different_cut"),
            "status": "pending",
        }
        self.assertEqual(self.call()["id"], self.existing["id"])
        self.payload.kind = "different_story"
        with self.assertRaises(HTTPException) as failure:
            self.call()
        self.assertEqual(failure.exception.status_code, 409)
        self.assertFalse(
            any(
                "INSERT" in call.args[0]
                for call in self.database.execute.call_args_list
            )
        )

    def test_local_only_request_does_not_silently_return_same_deterministic_edit(self):
        self.context["project"]["privacy_mode"] = "local_only"
        with self.assertRaises(HTTPException) as failure:
            self.call()
        self.assertEqual(failure.exception.status_code, 409)
        self.database.execute.assert_not_called()

    def test_invalid_inputs_cannot_queue_an_unscoped_or_unknown_alternative(self):
        for extra in (
            {"kind": "random"},
            {"direction": "x" * 601},
            {"base_version": 0},
        ):
            with self.assertRaises(ValidationError):
                AlternativeCreate.model_validate({**self.payload.model_dump(), **extra})


class AlternativeWorkerTests(unittest.TestCase):
    def test_same_result_is_reported_without_an_automatic_novelty_model_retry(self):
        from app.edit_plan import TalkingHeadEditPlan
        from app import worker
        from unittest.mock import MagicMock

        identity = str(uuid4())
        document = TalkingHeadEditPlan(
            schema_version="1.3",
            recipe="talking_head",
            clips=[{**cut(identity), "crop": "center_fill"}],
            caption_style="clean_blue_v1",
            audio_preset="spoken_voice_v1",
            end_card="none",
            editorial_summary="Same supported story.",
        )
        reference = uuid4()
        run = {
            "id": uuid4(),
            "job_id": uuid4(),
            "version": 2,
            "edit_plan_id": None,
            "based_on_run_id": reference,
            "alternative_kind": "different_cut",
            "revision_note": alternative_instruction("different_cut"),
        }
        context = {
            "ready_for_editing": True,
            "project": {
                "name": "Cream",
                "brief": "Explain cream",
                "privacy_mode": "transcript_only",
                "ai_copy_allowed": False,
            },
            "job": {},
            "assets": [
                {
                    "asset_id": identity,
                    "duration_seconds": 10,
                    "has_video": True,
                    "has_audio": True,
                }
            ],
            "music_library": [],
            "creative_effect_library": [],
        }
        connection = MagicMock()
        database = connection.return_value.__enter__.return_value
        prior = {
            "id": reference,
            "version": 1,
            "document": document.model_dump(mode="json"),
            "caption_corrections": [],
        }
        database.execute.return_value.fetchall.return_value = [prior]
        database.execute.return_value.fetchone.return_value = prior
        planner = Mock(
            return_value=(document, {"provider": "chatgpt_plan", "model": "fixture"})
        )
        renderer = Mock(
            return_value={
                "outputs": {"preview": "fixture.mp4"},
                "manifest_path": "fixture.json",
            }
        )
        with patch.multiple(
            worker,
            claim_pending_edit=Mock(return_value=run),
            build_editor_context=Mock(return_value=context),
            create_edit_plan=planner,
            assert_ai_budget=Mock(),
            _record_plan_usage=Mock(),
            _persist_generated_plan=Mock(),
            render_edit_preview=renderer,
            connection=connection,
        ):
            self.assertTrue(worker.process_one_edit(worker.WorkerState()))
        planner.assert_called_once()
        renderer.assert_called_once()
        self.assertEqual(
            renderer.call_args.args[0]["revision_report"]["alternative"]["status"],
            "similar",
        )


if __name__ == "__main__":
    unittest.main()
