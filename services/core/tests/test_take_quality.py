import unittest
from uuid import uuid4

from app.edit_plan import edit_plan_duration, repair_predictable_plan_defaults, validate_edit_plan
from app.story_intelligence import build_story_assessment, select_story_moments
from app.take_quality import editing_policy, production_chatter_reason, take_quality_report


class TakeQualityTests(unittest.TestCase):
    def setUp(self):
        self.asset_id = str(uuid4())
        self.asset = {"asset_id": self.asset_id, "has_video": True, "has_audio": True,
            "duration_seconds": 20, "transcript_segments": []}
        self.document = {"schema_version": "1.3", "recipe": "talking_head",
            "clips": [{"asset_id": self.asset_id, "source_in": 0, "source_out": 8,
                       "crop": "center_fill", "visual_preset": "standard"}],
            "caption_style": "clean_blue_v1", "audio_preset": "spoken_voice_v1", "end_card": "none",
            "editorial_summary": "A product story", "music_track_id": None, "music_mix": "none"}
        self.policy = editing_policy({"project_name": "Interesting Ad", "brief": "Make it funny and engaging"})

    def test_funny_or_meme_heavy_does_not_request_bloopers(self):
        self.assertTrue(self.policy["promotional"])
        self.assertFalse(self.policy["bloopers_requested"])
        self.assertFalse(editing_policy({"brief": "Make a funny ad", "effect_level": "meme_heavy"})["bloopers_requested"])
        self.assertTrue(editing_policy({"brief": "Make a blooper reel"})["bloopers_requested"])
        self.assertFalse(editing_policy({"brief": "Make a funny ad without bloopers"})["bloopers_requested"])

    def test_flags_setup_without_confusing_a_viewer_question_for_a_readiness_check(self):
        self.assertEqual(production_chatter_reason("Ready?"), "readiness_check")
        self.assertEqual(production_chatter_reason("Alright now, let's try a different"), "retake_direction")
        self.assertIsNone(production_chatter_reason("Ready to learn how this works?"))
        self.assertIsNone(production_chatter_reason("Try a different colour for your room."))

    def test_existing_story_indexes_stop_promoting_chatter_and_generic_scene_windows(self):
        moments = [
            {"asset_id": "a", "kind": "spoken", "text": "Ready?", "start_seconds": 0,
             "intrinsic_score": 0.9, "role_scores": {"hook": 0.9}, "suggested_roles": ["hook"]},
            {"asset_id": "a", "kind": "spoken", "text": "The product solves this problem.",
             "start_seconds": 3, "intrinsic_score": 0.5, "role_scores": {"payoff": 0.8}},
            {"asset_id": "a", "kind": "spoken", "text": "Let's try a different take.",
             "start_seconds": 8, "role_scores": {"ending": 0.9}},
            {"asset_id": "a", "kind": "visual_window", "text": "Source-derived scene window",
             "role_scores": {"hook": 0.65, "ending": 0.65}},
        ]
        selected = select_story_moments(moments, "", limit=2)
        self.assertEqual(selected[0]["text"], "The product solves this problem.")
        assessment = build_story_assessment(select_story_moments(moments, ""))
        self.assertEqual(assessment["candidate_moments"]["ending"], [])
        self.assertEqual(assessment["candidate_moments"]["hook"], [])
        self.assertEqual(moments[0]["role_scores"]["hook"], 0.9, "stored data must remain untouched")

    def test_take_comparison_keeps_the_complete_continuation(self):
        report = take_quality_report([
            {"start": 0, "end": 3, "text": "It's super hydrating and leaves her 50-year-old skin."},
            {"start": 4, "end": 5.2, "text": "Not saying it again."},
            {"start": 9, "end": 11, "text": "It's super hydrating and leaves her skin"},
            {"start": 11, "end": 12.5, "text": "feeling soft and smooth."},
        ])
        self.assertEqual(report["production_chatter"][0]["text"], "Not saying it again.")
        group = report["repeated_take_groups"][0]
        self.assertEqual(group["compare_first_start"], 9)
        self.assertIn("feeling soft and smooth", group["candidates"][1]["text"])

    def test_reports_are_bounded_and_do_not_duplicate_a_long_transcript_into_context(self):
        segments = [{"start": index * 4, "end": index * 4 + 1, "text": "Ready?"} for index in range(100)]
        segments += [{"start": 500 + index * 4, "end": 502 + index * 4,
                      "text": "This product has a useful feature " + "detail " * 500} for index in range(40)]
        report = take_quality_report(segments)
        self.assertEqual(report["production_chatter_count"], 100)
        self.assertEqual(len(report["production_chatter"]), 24)
        self.assertLessEqual(len(report["repeated_take_groups"][0]["candidates"]), 4)
        self.assertTrue(all(len(item["text"]) <= 300 for group in report["repeated_take_groups"]
                            for item in group["candidates"]))

    def test_new_story_rejects_retakes_but_exact_rerender_is_unchanged(self):
        self.asset["transcript_segments"] = [{"start": 2, "end": 4, "text": "Not saying it again."}]
        direction = {"editorial_policy": self.policy}
        with self.assertRaisesRegex(ValueError, "production/retake chatter"):
            validate_edit_plan(self.document, [self.asset], creative_direction=direction, enforce_story_quality=True)
        old = validate_edit_plan(self.document, [self.asset], creative_direction=direction)
        self.assertEqual(old.clips[0].source_out, 8)
        allowed = validate_edit_plan(self.document, [self.asset], enforce_story_quality=True,
            creative_direction={"editorial_policy": {**self.policy, "bloopers_requested": True}})
        self.assertEqual(allowed.clips[0].source_out, 8)

    def test_new_ad_tightens_long_gaps_without_clipping_words_and_retimes_fx(self):
        self.asset["transcript_segments"] = [{"start": 0, "end": 8, "text": "setup payoff",
            "words": [{"start": 0.5, "end": 1, "text": "setup"},
                      {"start": 6.5, "end": 7.5, "text": "payoff"}]}]
        effect_id = str(uuid4())
        self.document["effects"] = [{"asset_id": effect_id, "start_seconds": 6.5,
            "duration_seconds": 0.5, "position": "top", "intensity": "subtle", "purpose": "payoff"}]
        plan = validate_edit_plan(self.document, [self.asset], enforce_story_quality=True,
            creative_direction={"editorial_policy": self.policy, "effect_level": "subtle"},
            creative_effects=[{"asset_id": effect_id, "purpose": "payoff"}])
        self.assertLess(edit_plan_duration(plan), 4)
        self.assertLess(plan.clips[0].source_in, 0.5)
        self.assertGreater(plan.clips[-1].source_out, 7.5)
        self.assertLess(plan.effects[0].start_seconds, 3)

    def test_explicit_pause_request_is_respected(self):
        policy = editing_policy({"brief": "Make an ad and keep the long pause before the reveal"})
        self.assertTrue(policy["preserve_pauses_requested"])
        self.asset["transcript_segments"] = [{"start": 1, "end": 7, "text": "two words",
            "words": [{"start": 1, "end": 2}, {"start": 6, "end": 7}]}]
        plan = validate_edit_plan(self.document, [self.asset], enforce_story_quality=True,
                                  creative_direction={"editorial_policy": policy})
        self.assertEqual(edit_plan_duration(plan), 8)

    def test_effect_collisions_do_not_replan_the_story_or_change_unknown_assets(self):
        effect_id = str(uuid4())
        cues = [{"asset_id": effect_id, "start_seconds": start} for start in (2.0, 2.2, 4.0)]
        document = {**self.document, "effects": cues}
        repaired, repairs = repair_predictable_plan_defaults(document,
            creative_direction={"effect_level": "social"}, creative_effects=[{"asset_id": effect_id}])
        self.assertEqual(repaired["clips"], document["clips"])
        self.assertEqual(len(repaired["effects"]), 2)
        self.assertIn("reduced_effect_cue_collisions_without_changing_story", repairs)
        untouched, _ = repair_predictable_plan_defaults(document,
            creative_direction={"effect_level": "social"}, creative_effects=[])
        self.assertEqual(untouched["effects"], cues)


if __name__ == "__main__":
    unittest.main()
