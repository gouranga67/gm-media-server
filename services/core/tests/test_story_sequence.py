import json
import unittest
from copy import deepcopy

from app.story_sequence import add_narrative_links, narrative_links, story_sequence_review
from app.story_contract import selected_story_contract, check_story_contract
from test_revision_precision import fixture


class StorySequenceTests(unittest.TestCase):
    def test_context_links_remain_same_source_balanced_and_within_budget(self):
        assets = [dict(asset_id=str(n), transcript_segments=[dict(start=0,end=2,text="This is unfinished"),
            dict(start=2.1,end=4,text="because this explains it."), dict(start=4.1,end=6,text="It works.")]) for n in range(20)]
        hints = narrative_links(assets)
        self.assertEqual(len(hints), 12)
        self.assertEqual(len({h["asset_id"] for h in hints}), 12)
        public = {"assets": assets}
        original = deepcopy(assets)
        before = len(json.dumps(public, ensure_ascii=False,separators=(',',':')))
        add_narrative_links(public, before)
        self.assertNotIn("narrative_links", public)
        add_narrative_links(public, before+1800)
        self.assertIn("narrative_links", public)
        self.assertEqual(public["assets"], original)
        self.assertLessEqual(len(json.dumps(public,ensure_ascii=False,separators=(',',':'))),before+1800)

    def test_context_links_do_not_bridge_large_gaps(self):
        self.assertEqual(narrative_links([dict(asset_id="a",transcript_segments=[dict(start=0,end=2,text="unfinished"),dict(start=20,end=23,text="because a different take.")])]), [])

    def test_unusable_legacy_timing_does_not_break_optional_outline_or_invent_words(self):
        plan,asset=fixture()
        asset["transcript_segments"] += [None, {"start":"unknown","end":4,"text":"Unusable."}]
        asset["transcript_segments"][0]["words"] += [None,{"start":float("nan"),"end":2,"text":"Not evidence"}]
        review=story_sequence_review(plan,[asset])
        self.assertEqual(review["outline"][0]["text"],"A complete first thought.")
        narrative_links([asset])

    def test_actual_outline_contains_only_selected_recorded_words_and_does_not_edit_plan(self):
        plan, asset = fixture()
        original = plan.model_dump(mode="json")
        review = story_sequence_review(plan, [asset])
        self.assertEqual(review["outline"][0]["text"], "A complete first thought.")
        self.assertEqual(review["outline"][1]["text"], "")
        self.assertEqual(review["outline"][1]["start_seconds"], 3)
        self.assertEqual(plan.model_dump(mode="json"), original)
        self.assertEqual(review["hosted_model_calls"], 0)
        self.assertEqual(review["semantic_judgement"], "human_review_required")

    def test_selected_blooper_setup_and_reaction_are_protected_without_sales_shape(self):
        plan, asset = fixture()
        script = [dict(evidence_id=1,asset_id=asset["asset_id"],start=1,end=4,role="context",blooper_scope_version=1),
                  dict(evidence_id=2,asset_id=asset["asset_id"],start=5,end=8,role="ending",blooper_scope_version=1)]
        context = {"selected_concept":{"reel_kind":"bloopers","title":"Recorded stumble","script":script}}
        contract = selected_story_contract(context)
        self.assertIn("setup_incident_reaction", contract["policy"])
        check_story_contract(plan, contract, [asset])
        omitted = plan.model_copy(update={"clips":plan.clips[1:]},deep=True)
        with self.assertRaisesRegex(ValueError,"selected story contract"):
            check_story_contract(omitted, contract, [asset])
        reversed_plan = plan.model_copy(update={"clips":list(reversed(plan.clips))},deep=True)
        with self.assertRaisesRegex(ValueError,"out of order"):
            check_story_contract(reversed_plan, contract, [asset])
