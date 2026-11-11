import unittest
from types import SimpleNamespace

from app.editing_contract import editing_contract, contract_instructions, editing_receipt
from app.editor_provider import _model_content
from app.finishing_tools import FinishingTools


class EditingContractTests(unittest.TestCase):
    def context(self, brief, **job):
        return {"job": {"recipe": "talking_head", "edit_style": "high_impact", **job},
                "project": {"brief": brief, "privacy_mode": "text_only"}, "assets": []}

    def test_visual_style_does_not_force_conversation_into_an_ad(self):
        context = self.context("Make a great video about our day out")
        contract = editing_contract(context)
        self.assertEqual(contract["audio_pacing"], "connected_passages")
        self.assertEqual(contract["purpose"], "story")
        self.assertFalse(contract["creative_quotas"])
        prompt = _model_content(context, SimpleNamespace(editor_max_context_characters=120000))[0]["text"]
        self.assertIn("A change in picture need not change the audio", prompt)
        self.assertNotIn("energetic edits of 20 seconds or longer", prompt)

    def test_explicit_audio_direction_and_negation(self):
        for brief, expected in (
            ("Make an ad", "tight_dialogue"),
            ("Make an ad; preserve the full explanation", "connected_passages"),
            ("Keep the conversation and natural sound", "connected_passages"),
            ("Tighten the pauses", "tight_dialogue"),
            ("Don't tighten the pauses", "connected_passages"),
            ("Make a cinematic montage", "music_led"),
            ("Make a montage but keep the dialogue", "connected_passages"),
        ):
            with self.subTest(brief=brief):
                self.assertEqual(editing_contract(self.context(brief))["audio_pacing"], expected)

    def test_bloopers_and_complete_speech_have_priority_over_decoration(self):
        context = self.context("Make a bloopers reel", editorial_policy={"intent": "bloopers"})
        self.assertEqual(editing_contract(context)["purpose"], "bloopers")
        prompt = contract_instructions(context)
        self.assertIn("not a quota or an advertisement template", prompt)
        self.assertIn("no minimum number of treatments", prompt)

    def test_receipt_distinguishes_replay_from_model_planning(self):
        from app.edit_plan import TalkingHeadEditPlan
        from uuid import uuid4
        plan = TalkingHeadEditPlan(schema_version="1.4", recipe="talking_head",
            clips=[dict(asset_id=uuid4(), source_in=0, source_out=3, crop="center_fill")],
            caption_style="clean_blue_v1", audio_preset="spoken_voice_v1", end_card="none",
            editorial_summary="Complete passage")
        context = self.context("A day out")
        context["plan_source"] = "saved_plan"
        replay = editing_receipt(context, plan, "chatgpt_plan")
        self.assertEqual(replay["plan_source"], "saved_plan")
        self.assertIsNone(replay["planning_contract"])
        context.update(plan_source="model_plan", planning_contract=editing_contract(context),
            local_plan_repairs=["removed_unrequested_music", "removed_unrequested_music"],
            story_finishing={"changes": ["Shortened measured waiting."]},
            creative_treatment_review={"removed": 1, "reason": "shared_effect_budget",
                                       "rejected_visual_beats": ["impact_frame"]})
        context["job"]["effect_level"] = "social"
        plan = plan.model_copy(update={"finishing": FinishingTools(visual_beats=[
            dict(start=.5,end=1.5,preset="clone_row",intensity="strong",position="upper")
        ])}, deep=True)
        fresh = editing_receipt(context, plan, "chatgpt_plan")
        self.assertEqual(fresh["version"], 2)
        self.assertEqual(fresh["planning_contract"]["audio_pacing"], "connected_passages")
        self.assertEqual(fresh["local_repairs"], ["removed_unrequested_music"])
        self.assertEqual(fresh["local_story_changes"], ["Shortened measured waiting."])
        decisions = fresh["effect_decisions"]
        self.assertEqual(decisions["registry_version"], 11)
        self.assertEqual(len(decisions["items"]), 11)
        selected = next(item for item in decisions["items"] if item["preset"] == "clone_row")
        self.assertEqual((selected["decision"], selected["eligibility"]), ("selected", "eligible"))
        self.assertEqual(selected["evidence"], ["0.50–1.50s · strong strength"])
        rejected = next(item for item in decisions["items"] if item["preset"] == "impact_frame")
        self.assertEqual((rejected["decision"], rejected["eligibility"]), ("rejected", "eligible"))
        self.assertIn("shared effect budget", rejected["reason"])
        tear = next(item for item in decisions["items"] if item["preset"] == "paper_tear")
        self.assertEqual((tear["decision"], tear["eligibility"]), ("skipped", "ineligible"))
        self.assertIn("No eligible ordinary cut", tear["reason"])
        self.assertEqual(decisions["counts"], {"selected": 1, "rejected": 1, "skipped": 9})
