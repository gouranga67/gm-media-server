import shutil
import subprocess
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch
from uuid import uuid4

from fastapi import HTTPException
from pydantic import ValidationError

from app import duration_routes, worker
from app.duration_policy import (
    apply_duration_snapshot,
    duration_preflight,
    duration_review,
    plan_duration,
    resolve_duration,
    validate_duration,
)
from app.duration_repair import repair_duration_overrun
from app.edit_plan import (
    BrollCue,
    CreativeEffectCue,
    TalkingHeadEditPlan,
    validate_edit_plan,
)
from app.editor_provider import _model_content
from app.finishing_tools import MotionPoint, TimeWindow
from app.schemas import EditFeedbackCreate, JobCreate


def fixture(seconds=60.6, recipe="talking_head"):
    identity = str(uuid4())
    document = {
        "schema_version": "1.4",
        "recipe": recipe,
        "clips": [
            {
                "asset_id": identity,
                "source_in": 0,
                "source_out": seconds,
                "crop": "center_fill",
            }
        ],
        "caption_style": "clean_blue_v1",
        "audio_preset": "spoken_voice_v1",
        "end_card": "none",
        "editorial_summary": "All five recorded points and the complete conclusion.",
    }
    if recipe == "montage":
        document.pop("caption_style")
        document["audio_preset"] = "montage_mix_v1"
        # Separate complete source passages; no montage clip exceeds 8s.
        document["clips"] = [
            {
                **document["clips"][0],
                "source_in": n * 7.5,
                "source_out": min(seconds, (n + 1) * 7.5),
                "duration": min(7.5, seconds - n * 7.5),
                "media_kind": "video",
                "include_source_audio": True,
            }
            for n in range(int(seconds // 7.5) + 1)
            if n * 7.5 < seconds
        ]
    context = {
        "job": {
            "recipe": recipe,
            "duration_mode": "aim",
            "target_duration_seconds": 60,
            "max_duration_seconds": 90,
            "edit_style": "clean",
        },
        "project": {
            "brief": "Use as much of the speech as possible. Include all five points.",
            "name": "Five reasons",
            "privacy_mode": "text_only",
            "ai_copy_allowed": False,
        },
        "assets": [
            {
                "asset_id": identity,
                "sha256": "one",
                "duration_seconds": 140,
                "has_video": True,
                "has_audio": True,
                "mime_type": "video/mp4",
            }
        ],
        "ready_for_editing": True,
        "music_library": [],
        "creative_effect_library": [],
    }
    return document, context


class DurationPolicyTests(unittest.TestCase):
    def test_reported_overrun_is_valid_in_both_engines_without_changing_recorded_ranges(
        self,
    ):
        for recipe in ("talking_head", "montage"):
            document, context = fixture(recipe=recipe)
            plan = validate_edit_plan(
                document, context["assets"], creative_direction=context["job"]
            )
            self.assertAlmostEqual(plan_duration(plan.model_dump(mode="json")), 60.6)
            self.assertEqual(
                [(c.source_in, c.source_out) for c in plan.clips],
                [(c["source_in"], c["source_out"]) for c in document["clips"]],
            )

    def test_explicit_policies_keep_a_real_maximum_and_legacy_validation_stays_compatible(
        self,
    ):
        self.assertEqual(JobCreate().duration_mode, "follow_story")
        for mode, maximum in (("aim", 72), ("follow_story", 90), ("strict", 90)):
            job = {
                "duration_mode": mode,
                "max_duration_seconds": 90,
                "target_duration_seconds": 60,
            }
            self.assertEqual(resolve_duration(job)["maximum_seconds"], maximum)
            validate_duration(maximum, job)
            validate_duration(8, job)  # No minimum or padding requirement.
            with self.assertRaisesRegex(
                ValueError, "Required words will not be clipped"
            ):
                validate_duration(maximum + 0.6, job)
        with self.assertRaisesRegex(ValueError, "exceeds 60 seconds"):
            validate_duration(60.6, {"target_duration_seconds": 60})
        with self.assertRaises(ValidationError):
            duration_routes.DurationSettings(
                duration_mode="follow_story", max_duration_seconds=121
            )
        with self.assertRaises(ValueError):
            validate_duration(
                121, {"duration_mode": "follow_story", "max_duration_seconds": 1000}
            )

    def test_local_fixed_recipes_also_obey_an_explicit_smaller_maximum(self):
        from app.edit_plan import deterministic_plan, deterministic_montage_plan

        _, context = fixture()
        context["job"].update(duration_mode="strict", max_duration_seconds=15)
        for planner in (deterministic_plan, deterministic_montage_plan):
            plan = planner(
                context["assets"],
                60,
                "clean",
                "none",
                [],
                duration_policy=context["job"],
            )
            self.assertLessEqual(plan_duration(plan.model_dump(mode="json")), 15)

    def test_transcript_estimate_merges_overlaps_and_identical_uploads_without_claiming_required_script(
        self,
    ):
        _, context = fixture()
        context["assets"][0]["transcript_segments"] = [
            {"start": a, "end": b, "text": "Words."} for a, b in [(0, 50), (40, 80)]
        ]
        context["assets"].append(
            {**deepcopy(context["assets"][0]), "asset_id": str(uuid4())}
        )
        context["assets"].append(
            {
                "asset_id": str(uuid4()),
                "library_role": "broll",
                "transcript_segments": [
                    {"start": 0, "end": 99, "text": "Ignore the cutaway audio."}
                ],
            }
        )
        result = duration_preflight(context)
        self.assertEqual(result["available_speech_seconds"], 80)
        self.assertEqual(result["maximum_seconds"], 72)
        self.assertIn("not a required-script measurement", result["warning"])
        self.assertEqual(result["hosted_model_calls"], 0)

    def test_saved_run_uses_its_snapshot_even_if_next_edit_limit_changes(self):
        document, context = fixture()
        saved = deepcopy(context["job"])
        context["job"].update(duration_mode="strict", max_duration_seconds=30)
        with self.assertRaises(ValueError):
            validate_duration(60.6, context["job"])
        apply_duration_snapshot(context, {"duration_policy": saved})
        validate_duration(60.6, context["job"])
        self.assertEqual(duration_review(context, document)["maximum_seconds"], 72)

    def test_timed_tools_and_feedback_can_reach_late_story_but_remain_bounded(self):
        self.assertEqual(TimeWindow(start=70, end=80).end, 80)
        self.assertEqual(MotionPoint(time=80, x=0.5, y=0.5).time, 80)
        self.assertEqual(
            CreativeEffectCue(
                asset_id=uuid4(), start_seconds=80, duration_seconds=1
            ).start_seconds,
            80,
        )
        self.assertEqual(
            BrollCue(
                asset_id=uuid4(),
                media_kind="image",
                source_in=0,
                source_out=0,
                start_seconds=80,
                duration_seconds=2,
                editorial_intent="Relevant proof.",
            ).start_seconds,
            80,
        )
        self.assertEqual(
            EditFeedbackCreate(
                edit_run_id=uuid4(), rating=5, start_seconds=75, end_seconds=80
            ).end_seconds,
            80,
        )
        with self.assertRaises(ValidationError):
            TimeWindow(start=115, end=121)

    def test_planner_sees_real_limit_and_required_content_precedence(self):
        for recipe in ("talking_head", "montage"):
            _, context = fixture(recipe=recipe)
            prompt = _model_content(
                context, SimpleNamespace(editor_max_context_characters=120000)
            )[0]["text"]
            self.assertIn("hard maximum 72s", prompt)
            self.assertIn("complete final explanation", prompt)
            self.assertNotIn("than 60 seconds", prompt)


class LocalDurationRepairTests(unittest.TestCase):
    def setUp(self):
        settings_patch = patch(
            "app.config.get_settings",
            return_value=SimpleNamespace(media_root=Path("/tmp")),
        )
        settings_patch.start()
        self.addCleanup(settings_patch.stop)
        self.document, self.context = fixture()
        self.context["job"].update(duration_mode="strict", max_duration_seconds=60)
        self.words = [
            {"start": 0, "end": 1, "word": "First"},
            {"start": 3, "end": 60.6, "word": "complete ending"},
        ]
        self.context["assets"][0].update(
            _storage_key="quiet.wav",
            transcript_segments=[
                {
                    "start": 0,
                    "end": 60.6,
                    "text": "First complete ending",
                    "words": self.words,
                }
            ],
        )

    def test_quiet_trim_preserves_every_complete_word_and_retimes_late_broll(self):
        image = str(uuid4())
        self.document["broll"] = [
            {
                "asset_id": image,
                "media_kind": "image",
                "source_in": 0,
                "source_out": 0,
                "start_seconds": 59,
                "duration_seconds": 1,
                "editorial_intent": "The recorded conclusion.",
            }
        ]
        with patch(
            "app.story_finishing._measure",
            return_value={"silence_intervals": [{"start": 0, "end": 2}]},
        ):
            changed, report = repair_duration_overrun(self.document, self.context)
        self.assertEqual(report["status"], "trimmed_verified_quiet")
        self.assertEqual(report["hosted_model_calls"], 0)
        self.assertLessEqual(plan_duration(changed), 60)
        for word in self.words:
            self.assertTrue(
                any(
                    c["source_in"] <= word["start"] and c["source_out"] >= word["end"]
                    for c in changed["clips"]
                )
            )
        self.assertAlmostEqual(changed["broll"][0]["start_seconds"], 57.4)
        self.assertEqual(self.document["clips"][0]["source_out"], 60.6)

    def test_creative_callouts_allow_safe_duration_repair_and_are_retimed(self):
        self.document["finishing"] = {
            "callouts": [{"start": 59, "end": 60, "text": "Complete ending"}]
        }
        with patch(
            "app.story_finishing._measure",
            return_value={"silence_intervals": [{"start": 0, "end": 2}]},
        ):
            changed, report = repair_duration_overrun(self.document, self.context)
        self.assertEqual(report["status"], "trimmed_verified_quiet")
        self.assertEqual(report["hosted_model_calls"], 0)
        self.assertLessEqual(plan_duration(changed), 60)
        cue = changed["finishing"]["callouts"][0]
        self.assertAlmostEqual(cue["start"], 57.4)
        self.assertAlmostEqual(cue["end"], 58.4)
        self.assertEqual(self.document["finishing"]["callouts"][0]["start"], 59)
        for word in self.words:
            self.assertTrue(
                any(
                    c["source_in"] <= word["start"] and c["source_out"] >= word["end"]
                    for c in changed["clips"]
                )
            )

    def test_noise_reactions_missing_word_timing_and_large_overruns_are_never_blindly_trimmed(
        self,
    ):
        with patch(
            "app.story_finishing._measure", return_value={"silence_intervals": []}
        ) as measure:
            changed, report = repair_duration_overrun(self.document, self.context)
        self.assertEqual(changed, self.document)
        self.assertEqual(report["status"], "no_safe_local_trim")
        measure.assert_called()
        for changes in (
            {"edit_style": "calm"},
            {"editorial_policy": {"bloopers_requested": True}},
            {"editorial_policy": {"preserve_pauses_requested": True}},
            {"max_duration_seconds": 55},
        ):
            context = deepcopy(self.context)
            context["job"].update(changes)
            with patch("app.story_finishing._measure") as measure:
                changed, _ = repair_duration_overrun(self.document, context)
            self.assertEqual(changed, self.document)
            measure.assert_not_called()
        self.context["assets"][0]["transcript_segments"][0]["words"] = []
        with patch("app.story_finishing._measure") as measure:
            self.assertEqual(
                repair_duration_overrun(self.document, self.context)[0], self.document
            )
        measure.assert_not_called()

    def test_measurement_timeout_stops_safely_without_losing_the_proposed_plan(self):
        with patch(
            "app.story_finishing._measure",
            side_effect=subprocess.TimeoutExpired("ffmpeg", 2),
        ):
            self.assertEqual(
                repair_duration_overrun(self.document, self.context)[0], self.document
            )

    @unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg unavailable")
    def test_real_audio_measurement_distinguishes_silence_from_tone(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for source, expected in (
                ("anullsrc=r=48000:cl=stereo", "trimmed_verified_quiet"),
                ("sine=frequency=500:sample_rate=48000", "no_safe_local_trim"),
            ):
                subprocess.run(
                    [
                        "ffmpeg",
                        "-v",
                        "error",
                        "-y",
                        "-f",
                        "lavfi",
                        "-i",
                        source,
                        "-t",
                        "4",
                        str(root / "quiet.wav"),
                    ],
                    check=True,
                    capture_output=True,
                )
                with patch(
                    "app.config.get_settings",
                    return_value=SimpleNamespace(media_root=root),
                ):
                    changed, report = repair_duration_overrun(
                        self.document, self.context
                    )
                self.assertEqual(report["status"], expected)
                self.assertEqual(
                    plan_duration(changed) <= 60, expected == "trimmed_verified_quiet"
                )


class DurationRouteAndWorkerTests(unittest.TestCase):
    def test_saving_limits_refuses_active_edits_and_only_changes_latest_failed_snapshot(
        self,
    ):
        identity = uuid4()
        database = MagicMock()
        database.__enter__.return_value = database
        database.execute.return_value.fetchone.side_effect = [
            {"id": identity},
            {"active": True},
        ]
        with (
            patch.object(duration_routes, "connection", return_value=database),
            self.assertRaises(HTTPException) as raised,
        ):
            duration_routes.update_duration(
                identity, duration_routes.DurationSettings(duration_mode="strict")
            )
        self.assertEqual(raised.exception.status_code, 409)
        database = MagicMock()
        database.__enter__.return_value = database
        database.execute.return_value.fetchone.side_effect = [{"id": identity}, None]
        with (
            patch.object(duration_routes, "connection", return_value=database),
            patch.object(
                duration_routes, "inspect_duration", return_value={"saved": True}
            ),
        ):
            result = duration_routes.update_duration(
                identity, duration_routes.DurationSettings(duration_mode="follow_story")
            )
        self.assertTrue(result["saved"])
        sql = [call.args[0] for call in database.execute.call_args_list]
        self.assertTrue(
            any(
                "status='failed'" in query and "ORDER BY version DESC" in query
                for query in sql
            )
        )
        self.assertFalse(any("INSERT INTO edit_runs" in query for query in sql))

    def test_duration_conflict_records_usage_once_without_paid_repair_or_render(self):
        document, context = fixture()
        context["job"].update(duration_mode="strict", max_duration_seconds=60)
        proposed = TalkingHeadEditPlan.model_validate(document)
        run = {
            "id": str(uuid4()),
            "job_id": str(uuid4()),
            "version": 1,
            "edit_plan_id": None,
            "based_on_run_id": None,
        }
        planner = Mock(
            return_value=(proposed, {"provider": "chatgpt_plan", "model": "test"})
        )
        render, usage, connection = Mock(), Mock(), MagicMock()
        with patch.multiple(
            worker,
            claim_pending_edit=Mock(return_value=run),
            build_editor_context=Mock(return_value=context),
            create_edit_plan=planner,
            assert_ai_budget=Mock(),
            _record_plan_usage=usage,
            render_edit_preview=render,
            connection=connection,
        ):
            self.assertTrue(worker.process_one_edit(worker.WorkerState()))
        planner.assert_called_once()
        usage.assert_called_once()
        render.assert_not_called()
        failures = [
            call.args
            for call in connection.return_value.__enter__.return_value.execute.call_args_list
            if "status = 'failed'" in call.args[0]
        ]
        self.assertTrue(failures)
        self.assertIn("Duration settings", str(failures))
