import unittest
from uuid import uuid4

from app.edit_plan import validate_edit_plan
from app.effect_renderer import append_effect_filters


class CreativeEffectPlanTests(unittest.TestCase):
    def setUp(self):
        self.source_id = uuid4()
        self.effect_id = uuid4()
        self.assets = [{"asset_id": str(self.source_id), "has_video": True, "has_audio": True,
                        "duration_seconds": 10.0, "transcript_segments": []}]
        self.effect = {"asset_id": str(self.effect_id), "kind": "sound_effect", "purpose": "payoff"}
        self.document = {
            "schema_version": "1.3", "recipe": "talking_head",
            "clips": [{"asset_id": str(self.source_id), "source_in": 0.0, "source_out": 5.0,
                       "crop": "center_fill", "transition": "cut", "visual_preset": "standard",
                       "story_role": "payoff", "editorial_intent": "Deliver the result."}],
            "caption_style": "clean_blue_v1", "audio_preset": "spoken_voice_v1", "end_card": "none",
            "editorial_summary": "A clear payoff.", "post_copy": "", "music_track_id": None,
            "music_mix": "none", "caption_position": "lower_safe", "caption_timing_offset_seconds": 0,
            "effects": [{"asset_id": str(self.effect_id), "start_seconds": 3.0,
                         "duration_seconds": 0.8, "position": "bottom", "intensity": "subtle",
                         "purpose": "payoff"}],
        }

    def test_approved_effect_is_bounded_by_job_level(self):
        plan = validate_edit_plan(self.document, self.assets,
            creative_direction={"music_mode": "none", "effect_level": "subtle"},
            creative_effects=[self.effect])
        self.assertEqual(len(plan.effects), 1)

    def test_effects_are_removed_when_job_disables_them(self):
        plan = validate_edit_plan(self.document, self.assets,
            creative_direction={"music_mode": "none", "effect_level": "off"},
            creative_effects=[self.effect])
        self.assertEqual(plan.effects, [])

    def test_unapproved_effect_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "approved library"):
            validate_edit_plan(self.document, self.assets,
                creative_direction={"music_mode": "none", "effect_level": "social"},
                creative_effects=[])

    def test_filter_extension_mixes_bounded_audio_cue(self):
        cue = type("Cue", (), {"start_seconds": 1.25, "duration_seconds": 0.5,
                                "intensity": "standard", "position": "bottom"})()
        graph = append_effect_filters("[base]null[vout];[voice]anull[aout]",
            [{"asset_id": str(self.effect_id), "kind": "sound_effect", "title": "Pop",
              "purpose": "payoff", "input_index": 2, "cue": cue}],
            width=540, height=960, total_duration=5.0)
        self.assertIn("adelay=1250|1250", graph)
        self.assertIn("volume=-8.0dB", graph)
        self.assertIn("alimiter=limit=0.95[aout]", graph)

    def test_filter_extension_overlays_a_bounded_visual_cue(self):
        cue = type("Cue", (), {"start_seconds": 2.0, "duration_seconds": 1.0,
                                "intensity": "subtle", "position": "top"})()
        graph = append_effect_filters("[base]null[vout];[voice]anull[aout]",
            [{"asset_id": str(self.effect_id), "kind": "sticker", "title": "Arrow",
              "purpose": "emphasis", "input_index": 3, "cue": cue}],
            width=540, height=960, total_duration=5.0)
        self.assertIn("[3:v:0]scale=108:-1", graph)
        self.assertIn("enable='between(t,2.000,3.000)'", graph)
        self.assertIn("[vout]", graph)
        self.assertIn("[afx0]anull[aout]", graph)

    def test_visual_effect_stays_beneath_captions(self):
        cue = type("Cue", (), {"start_seconds": 0.5, "duration_seconds": 1.0,
                                "intensity": "standard", "position": "center"})()
        graph = append_effect_filters(
            "[base]subtitles=filename='captions.ass'[vout];[voice]anull[aout]",
            [{"asset_id": str(self.effect_id), "kind": "gif", "title": "Reaction",
              "purpose": "reaction", "input_index": 2, "cue": cue}],
            width=540, height=960, total_duration=4.0)
        self.assertIn("[veffects]subtitles=filename='captions.ass'[vout]", graph)
        self.assertLess(graph.index("overlay="), graph.index("subtitles="))


if __name__ == "__main__":
    unittest.main()
