import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from app.edit_plan import (
    CreativeEffectCue,
    TalkingHeadEditPlan,
    edit_plan_duration,
    validate_edit_plan,
)
from app.story_contract import (
    check_story_contract,
    contract_for,
    selected_story_contract,
)
from app.story_finishing import finish_new_story
from app.story_passages import story_passages


def plan_for(identity, ranges):
    return TalkingHeadEditPlan.model_validate(
        {
            "schema_version": "1.4",
            "recipe": "talking_head",
            "clips": [
                {
                    "asset_id": identity,
                    "source_in": a,
                    "source_out": b,
                    "crop": "center_fill",
                }
                for a, b in ranges
            ],
            "caption_style": "clean_blue_v1",
            "audio_preset": "spoken_voice_v1",
            "end_card": "none",
            "editorial_summary": "Keep the recorded story.",
        }
    )


class StoryPassageTests(unittest.TestCase):
    def segment(self, text, words, identity="a", index=1):
        return {
            "id": index,
            "asset_id": identity,
            "start_seconds": words[0]["start"],
            "end_seconds": words[-1]["end"],
            "text": text,
            "words": words,
        }

    def test_word_timed_sentences_split_without_inventing_timestamps_and_drop_only_prefix_filler(
        self,
    ):
        words = [
            {"start": i, "end": i + 1, "text": text}
            for i, text in enumerate(
                [
                    "All",
                    "right,",
                    "This",
                    "cream",
                    "works.",
                    "If",
                    "your",
                    "skin",
                    "gets",
                    "dry,",
                ]
            )
        ]
        raw = self.segment("All right, This cream works. If your skin gets dry,", words)
        units = story_passages([raw])
        self.assertEqual(
            [(u["text"], u["start_seconds"], u["end_seconds"]) for u in units],
            [("This cream works.", 2, 5), ("If your skin gets dry,", 5, 10)],
        )
        self.assertEqual(len({u["id"] for u in units}), 2)
        self.assertTrue(all(-(2**53) < u["id"] < 0 for u in units))
        self.assertTrue(units[1]["needs_context"])
        self.assertEqual(
            raw["text"], "All right, This cream works. If your skin gets dry,"
        )
        self.assertEqual(units, story_passages([raw]))

    def test_continuation_joins_only_with_same_source_close_timing_and_preserves_provenance(
        self,
    ):
        first = {
            "id": 1,
            "asset_id": "a",
            "start_seconds": 0,
            "end_seconds": 2,
            "text": "If your skin gets dry,",
        }
        second = {
            "id": 2,
            "asset_id": "a",
            "start_seconds": 2.1,
            "end_seconds": 4,
            "text": "this is where to start.",
        }
        units = story_passages([first, second])
        self.assertEqual(len(units), 1)
        self.assertEqual(
            units[0]["text"], "If your skin gets dry, this is where to start."
        )
        self.assertEqual(units[0]["catalogue_ids"], [1, 2])
        self.assertEqual(len(story_passages([first, {**second, "asset_id": "b"}])), 2)
        self.assertEqual(
            len(
                story_passages(
                    [first, {**second, "start_seconds": 8, "end_seconds": 10}]
                )
            ),
            2,
        )

    def test_mismatched_or_missing_words_do_not_create_false_precision(self):
        raw = {
            "id": 1,
            "asset_id": "a",
            "start_seconds": 0,
            "end_seconds": 8,
            "text": "A complete claim. Another whole sentence.",
            "words": [{"start": 0, "end": 1, "text": "Wrong."}],
        }
        units = story_passages([raw])
        self.assertEqual(len(units), 1)
        self.assertEqual(units[0]["id"], 1)
        self.assertEqual(units[0]["end_seconds"], 8)
        self.assertEqual(units[0]["boundary_evidence"], "catalogue_only")


class StoryContractTests(unittest.TestCase):
    def setUp(self):
        self.identity = str(uuid4())
        self.assets = [
            {
                "asset_id": self.identity,
                "has_audio": True,
                "has_video": True,
                "duration_seconds": 12,
                "transcript_segments": [
                    {
                        "words": [
                            {"start": i, "end": i + 0.4, "text": w}
                            for i, w in enumerate(
                                [
                                    "The",
                                    "cream",
                                    "works.",
                                    "This",
                                    "explains",
                                    "why.",
                                    "Here",
                                    "is",
                                    "the",
                                    "result.",
                                ]
                            )
                        ]
                    }
                ],
            }
        ]
        self.script = [
            {
                "evidence_id": i + 1,
                "asset_id": self.identity,
                "start": a,
                "end": b,
                "text": text,
                "role": role,
            }
            for i, (a, b, text, role) in enumerate(
                [
                    (0, 2.4, "The cream works.", "hook"),
                    (3, 5.4, "This explains why.", "development"),
                    (6, 9.4, "Here is the result.", "ending"),
                ]
            )
        ]
        self.contract = {
            **contract_for("Explain why the cream works.", self.script),
            "beats": self.script,
        }

    def test_complete_story_allows_silence_cleanup_and_rejects_missing_ending_or_reordering(
        self,
    ):
        plan = plan_for(self.identity, [(0, 2.5), (3, 5.5), (6, 9.5)])
        report = check_story_contract(plan, self.contract, self.assets)
        self.assertEqual(report["status"], "checked")
        self.assertEqual(report["semantic_judgement"], "human_review_required")
        for ranges in [
            [(0, 2.5), (3, 5.5)],
            [(6, 9.5), (3, 5.5), (0, 2.5)],
            [(0, 1.5), (3, 5.5), (1.5, 2.5), (6, 9.5)],
        ]:
            with self.assertRaisesRegex(ValueError, "selected story contract"):
                check_story_contract(
                    plan_for(self.identity, ranges), self.contract, self.assets
                )

    def test_only_new_selected_concepts_activate_the_contract_not_legacy_or_bloopers(
        self,
    ):
        self.assertIsNone(
            selected_story_contract({"selected_concept": {"script": self.script}})
        )
        selected = {
            "script": self.script,
            "story_contract": contract_for("The point.", self.script),
            "reel_kind": "story",
        }
        self.assertIsNotNone(selected_story_contract({"selected_concept": selected}))
        self.assertIsNone(
            selected_story_contract(
                {"selected_concept": {**selected, "reel_kind": "bloopers"}}
            )
        )
        old = validate_edit_plan(
            plan_for(self.identity, [(0, 2.5)]).model_dump(mode="json"), self.assets
        )
        self.assertEqual(len(old.clips), 1)
        with self.assertRaisesRegex(ValueError, "selected story contract"):
            validate_edit_plan(
                old.model_dump(mode="json"),
                self.assets,
                creative_direction={"_selected_story_contract": self.contract},
            )

    def test_contract_rejects_unselected_spoken_claims_and_removed_negations(self):
        self.assets[0]["transcript_segments"][0]["words"].append(
            {"start": 10, "end": 10.4, "text": "Unselected."}
        )
        with self.assertRaisesRegex(ValueError, "outside the selected story"):
            check_story_contract(
                plan_for(self.identity, [(0, 2.5), (3, 5.5), (6, 9.5), (10, 10.5)]),
                self.contract,
                self.assets,
            )
        self.assets[0]["transcript_segments"][0]["words"][4]["text"] = "not"
        with self.assertRaisesRegex(ValueError, "selected story contract"):
            check_story_contract(
                plan_for(self.identity, [(0, 4), (4.5, 9.5)]),
                self.contract,
                self.assets,
            )

    def test_complete_legacy_concepts_still_run_without_a_new_constraint(self):
        plan = plan_for(self.identity, [(0, 2.5)])
        self.assertEqual(
            check_story_contract(plan, None, self.assets)["status"], "not_applicable"
        )


class StoryFinishingTests(unittest.TestCase):
    def setUp(self):
        self.identity = str(uuid4())
        self.asset = {
            "asset_id": self.identity,
            "has_audio": True,
            "has_video": True,
            "duration_seconds": 12,
            "_storage_key": "source.mp4",
            "transcript_segments": [
                {
                    "words": [
                        {"start": 0.1, "end": 1, "text": "Setup."},
                        {"start": 5, "end": 6, "text": "Result."},
                        {"start": 8, "end": 9, "text": "Ending."},
                    ]
                }
            ],
        }
        self.context = {
            "project": {"brief": "Make a useful story."},
            "job": {
                "editorial_policy": {"intent": "story"},
                "edit_style": "high_impact",
            },
            "assets": [self.asset],
        }
        self.settings = patch(
            "app.config.get_settings",
            return_value=SimpleNamespace(media_root=Path("/tmp")),
        )
        self.settings.start()
        self.addCleanup(self.settings.stop)

    def test_trim_requires_both_a_word_gap_and_measured_quiet_and_retimes_effects(self):
        plan = plan_for(self.identity, [(0, 6.2), (7.8, 9.2)])
        effect = {
            "asset_id": str(uuid4()),
            "start_seconds": 5,
            "duration_seconds": 0.3,
            "purpose": "payoff",
        }
        plan.effects = [CreativeEffectCue(**effect)]
        measured = {
            "silence_intervals": [{"start": 1.1, "end": 4.9}],
            "loudness": {"integrated_lufs": -18, "true_peak_dbfs": -5},
        }
        with patch("app.story_finishing._measure", return_value=measured):
            finished, report = finish_new_story(self.context, plan)
        self.assertLess(edit_plan_duration(finished), edit_plan_duration(plan) - 2)
        self.assertLess(finished.effects[0].start_seconds, 3)
        self.assertEqual(finished.clips[0].source_in, 0)
        self.assertGreaterEqual(finished.clips[1].source_out, 6)
        self.assertEqual(report["hosted_model_calls"], 0)
        with patch(
            "app.story_finishing._measure",
            return_value={**measured, "silence_intervals": []},
        ):
            untouched, _ = finish_new_story(self.context, plan)
        self.assertEqual(untouched.model_dump(), plan.model_dump())

    def test_quiet_speech_boost_uses_measured_passages_not_whole_file_stats(self):
        plan = plan_for(self.identity, [(0, 1.2), (7.8, 9.2)])
        with patch(
            "app.story_finishing._measure",
            side_effect=[
                {
                    "silence_intervals": [],
                    "loudness": {"integrated_lufs": -15, "true_peak_dbfs": -4},
                },
                {
                    "silence_intervals": [],
                    "loudness": {"integrated_lufs": -35, "true_peak_dbfs": -20},
                },
            ],
        ):
            finished, report = finish_new_story(self.context, plan)
        self.assertEqual(finished.clips[0].source_audio_gain_db, 0)
        self.assertEqual(finished.clips[1].source_audio_gain_db, 6)
        self.assertEqual(
            [(c.source_in, c.source_out) for c in finished.clips],
            [(0, 1.2), (7.8, 9.2)],
        )
        self.assertTrue(any("6 dB" in line for line in report["changes"]))

    def test_missing_measurement_holds_and_explicit_directions_are_preserved(self):
        plan = plan_for(self.identity, [(0, 6.2)])
        for override in [
            {"edit_style": "calm"},
            {"editorial_policy": {"intent": "bloopers", "bloopers_requested": True}},
            {
                "editorial_policy": {
                    "intent": "story",
                    "preserve_pauses_requested": True,
                }
            },
        ]:
            with patch("app.story_finishing._measure") as meter:
                result, _ = finish_new_story(
                    {**self.context, "job": {**self.context["job"], **override}}, plan
                )
            self.assertEqual(result.model_dump(), plan.model_dump())
            meter.assert_not_called()
        with patch("app.story_finishing._measure", side_effect=TimeoutError):
            result, report = finish_new_story(self.context, plan)
        self.assertEqual(result.model_dump(), plan.model_dump())
        self.assertTrue(report["findings"])
        plan.clips[0].editorial_intent = "Hold the genuine reaction."
        with patch(
            "app.story_finishing._measure",
            return_value={
                "silence_intervals": [{"start": 1.1, "end": 4.9}],
                "loudness": {},
            },
        ):
            result, _ = finish_new_story(self.context, plan)
        self.assertEqual(result.model_dump(), plan.model_dump())

    def test_disposable_opening_is_removed_but_explicit_opening_is_kept(self):
        self.asset["transcript_segments"][0]["words"] = [
            {"start": 0, "end": 0.2, "text": "All"},
            {"start": 0.2, "end": 0.4, "text": "right,"},
            {"start": 1, "end": 2, "text": "Useful sentence."},
        ]
        plan = plan_for(self.identity, [(0, 0.6), (0.9, 2.1)])
        with patch("app.story_finishing._measure", side_effect=TimeoutError):
            finished, report = finish_new_story(self.context, plan)
        self.assertEqual(len(finished.clips), 1)
        self.assertEqual(finished.clips[0].source_in, 0.9)
        self.context["project"]["brief"] = "Keep the All right opening."
        with patch("app.story_finishing._measure", side_effect=TimeoutError):
            preserved, _ = finish_new_story(self.context, plan)
        self.assertEqual(preserved.model_dump(), plan.model_dump())

    def test_creative_callouts_do_not_disable_existing_story_cleanup(self):
        from app.finishing_tools import FinishingTools

        self.asset["transcript_segments"][0]["words"] = [
            {"start": 0, "end": 0.2, "text": "All"},
            {"start": 0.2, "end": 0.4, "text": "right,"},
            {"start": 1, "end": 2, "text": "Useful sentence."},
        ]
        plan = plan_for(self.identity, [(0, 0.6), (0.9, 2.1)])
        plan.finishing = FinishingTools(
            callouts=[dict(start=0.9, end=1.5, text="Useful sentence")]
        )
        with patch("app.story_finishing._measure", side_effect=TimeoutError):
            finished, report = finish_new_story(self.context, plan)
        self.assertEqual(len(finished.clips), 1)
        self.assertAlmostEqual(finished.finishing.callouts[0].start, 0.3)
        self.assertAlmostEqual(finished.finishing.callouts[0].end, 0.9)
        self.assertEqual(plan.finishing.callouts[0].start, 0.9)
        self.assertEqual(report["hosted_model_calls"], 0)

    def test_audio_inspection_stops_at_the_shared_budget(self):
        plan = plan_for(self.identity, [(0, 1.2)] * 10)
        clock = [0.0]
        timeouts = []

        def measure(_asset, _clip, _settings, timeout):
            timeouts.append(timeout)
            clock[0] += timeout
            return {"silence_intervals": [], "loudness": {}}

        with (
            patch("app.story_finishing.time.monotonic", side_effect=lambda: clock[0]),
            patch("app.story_finishing._measure", side_effect=measure),
        ):
            finished, report = finish_new_story(self.context, plan)
        self.assertLessEqual(sum(timeouts), 8)
        self.assertLessEqual(len(timeouts), 6)
        self.assertEqual(finished.model_dump(), plan.model_dump())
        self.assertTrue(any("budget" in line for line in report["findings"]))

    def test_second_cleanup_failure_restores_the_original_validated_plan(self):
        plan = plan_for(self.identity, [(0, 6.2), (7.8, 9.2)])
        partially_changed = plan_for(self.identity, [(0, 1.1), (5, 6.2), (7.8, 9.2)])
        with (
            patch(
                "app.story_finishing._measure",
                return_value={
                    "silence_intervals": [{"start": 1.1, "end": 4.9}],
                    "loudness": {},
                },
            ),
            patch("app.story_finishing._disposable_opening", side_effect=[False, True]),
            patch(
                "app.story_finishing.apply_timeline_adjustments",
                side_effect=[
                    partially_changed,
                    ValueError("safe timeline bounds"),
                ],
            ),
        ):
            finished, report = finish_new_story(self.context, plan)
        self.assertEqual(finished.model_dump(), plan.model_dump())
        self.assertEqual(report["changes"], [])
        self.assertEqual(report["status"], "attention")
