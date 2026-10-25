import importlib.util
from pathlib import Path
import unittest


SCRIPT = Path(__file__).resolve().parents[3] / "scripts/verify-phase16.py"


@unittest.skipUnless(SCRIPT.exists(), "readiness script is covered in source CI")
class CreativeReadinessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("creative_readiness", SCRIPT)
        cls.checker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.checker)

    def setUp(self):
        self.effect = {"id": "effect-1", "kind": "sound_effect", "purpose": "emphasis",
                       "license_name": "CC0-1.0", "license_source_url": "https://example.com/license",
                       "allowed_platforms": ["instagram"]}
        self.context = {"job": {"target_platform": "instagram"}, "creative_effect_library": []}

    def test_empty_catalogue_is_not_reported_as_effects_ready(self):
        self.assertFalse(self.checker.inspect_libraries([], [], self.context)["creative_effects_ready"])

    def test_readiness_requires_both_sound_and_visual_assets(self):
        effects = [self.effect, {**self.effect, "id": "effect-2", "kind": "sticker"}]
        self.context["creative_effect_library"] = [{**item, "asset_id": item["id"]} for item in effects]
        self.assertTrue(self.checker.inspect_libraries([], effects, self.context)["creative_effects_ready"])

    def test_missing_license_evidence_fails_verification(self):
        with self.assertRaisesRegex(RuntimeError, "license metadata"):
            self.checker.inspect_libraries([], [{**self.effect, "license_source_url": ""}], self.context)

    def test_incompatible_assets_are_excluded_from_editor_inventory(self):
        effect = {**self.effect, "allowed_platforms": ["youtube"]}
        self.assertFalse(self.checker.inspect_libraries([], [effect], self.context)["creative_effects_ready"])
        self.context["creative_effect_library"] = [{**effect, "asset_id": effect["id"]}]
        with self.assertRaisesRegex(RuntimeError, "platform-compatible"):
            self.checker.inspect_libraries([], [effect], self.context)

    def test_editor_metadata_must_agree_with_catalogue(self):
        self.context["creative_effect_library"] = [{**self.effect, "asset_id": self.effect["id"],
                                                    "license_name": "unreviewed"}]
        with self.assertRaisesRegex(RuntimeError, "metadata differs"):
            self.checker.inspect_libraries([], [self.effect], self.context)


if __name__ == "__main__":
    unittest.main()
