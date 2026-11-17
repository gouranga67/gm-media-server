import unittest
from types import SimpleNamespace

from app.brief_contract import check_brief_contract
from app.editing_contract import brief_contract


def words(text, start=0.0):
    result = []
    at = start
    for token in text.split():
        result.append({"start": at, "end": at + 0.3, "text": token})
        at += 0.35
    return result


class BriefContractTests(unittest.TestCase):
    def setUp(self):
        self.asset_id = "asset-1"
        self.script = "Welcome to Azura Agency we help creators turn attention into revenue talk to us today"
        timed = words(self.script)
        self.assets = [{
            "asset_id": self.asset_id,
            "transcript_segments": [{
                "start": 0,
                "end": timed[-1]["end"],
                "text": self.script,
                "words": timed,
            }],
        }]

    def plan(self, source_in=0.0, source_out=20.0):
        return SimpleNamespace(clips=[SimpleNamespace(
            asset_id=self.asset_id,
            source_in=source_in,
            source_out=source_out,
        )])

    def test_complete_supplied_script_is_checked(self):
        contract = brief_contract("Use this script exactly:\n" + self.script)
        review = check_brief_contract(self.plan(), contract, self.assets)
        self.assertEqual(review["status"], "checked")
        self.assertTrue(review["checks"][0]["present"])

    def test_supported_script_omission_rejects_the_plan(self):
        contract = brief_contract("Use this script exactly:\n" + self.script)
        with self.assertRaisesRegex(ValueError, "proposed edit omits"):
            check_brief_contract(self.plan(0, 2.5), contract, self.assets)

    def test_supported_ordered_points_must_remain_in_order(self):
        contract = brief_contract(
            "- Welcome to Azura Agency\n"
            "- Turn attention into revenue\n"
            "- Talk to us today"
        )
        review = check_brief_contract(self.plan(), contract, self.assets)
        self.assertEqual(review["status"], "checked")
        reversed_words = words("talk to us today turn attention into revenue welcome to Azura Agency")
        assets = [{"asset_id": self.asset_id, "transcript_segments": [{
            "start": 0,
            "end": reversed_words[-1]["end"],
            "text": "",
            "words": reversed_words,
        }]}]
        with self.assertRaisesRegex(ValueError, "missing or out of order"):
            check_brief_contract(self.plan(), contract, assets)

    def test_visual_scene_direction_stays_honest_about_human_review(self):
        contract = brief_contract(
            "Scene 1: Show the red product on the desk\n"
            "Scene 2: Cut to a customer reaction"
        )
        review = check_brief_contract(self.plan(), contract, self.assets)
        self.assertEqual(review["status"], "attention")
        self.assertIn("human review", review["findings"][-1])

    def test_missing_source_script_is_not_falsely_reported_as_plan_failure(self):
        contract = brief_contract("Use this script exactly:\nA completely different speech")
        review = check_brief_contract(self.plan(), contract, self.assets)
        self.assertEqual(review["status"], "attention")
        self.assertFalse(review["checks"][0]["source_supported"])


if __name__ == "__main__":
    unittest.main()
