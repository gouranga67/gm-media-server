import unittest
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from app.blooper_detection import find_blooper_evidence
from app.blooper_focus import (
    attach_word_times,
    focus_blooper_passages,
    selected_blooper_scope,
    validate_blooper_scope,
)
from app.concept_inventory import compact_inventory, validate_concepts
from app.concept_schemas import ConceptRequestCreate


def passage(identity, text, start=0):
    words = [
        {
            "text": word,
            "start": round(start + i * 0.4, 3),
            "end": round(start + (i + 1) * 0.4, 3),
        }
        for i, word in enumerate(text.split())
    ]
    return {
        "id": identity,
        "asset_id": "a",
        "start_seconds": start,
        "end_seconds": words[-1]["end"],
        "text": text,
        "words": words,
    }


class BlooperFocusTests(unittest.TestCase):
    def setUp(self):
        self.segments = [
            passage(
                1,
                "Welcome to our complete introduction and description of every useful size, the new, the new Wobbly Widget, that's hard to say,",
            ),
            passage(
                2,
                "The new Wobbly Widget works, and here is a long catalogue of extra unrelated products and specifications.",
                10.4,
            ),
        ]
        # Keep the synthetic segments adjacent using actual word times.
        offset = self.segments[0]["end_seconds"] + 0.2
        self.segments[1] = passage(2, self.segments[1]["text"], offset)

    def focus(self):
        return focus_blooper_passages(
            self.segments, find_blooper_evidence(self.segments)
        )

    def test_long_take_becomes_incident_and_short_recovery_without_the_pitch(self):
        before = deepcopy(self.segments)
        result = self.focus()
        self.assertGreater(result[1]["start"], 0)
        self.assertIn("Wobbly Widget", result[1]["text"])
        self.assertIn("hard to say", result[1]["text"])
        self.assertNotIn("complete introduction", result[1]["text"])
        self.assertEqual(result[2]["text"], "The new Wobbly Widget works,")
        self.assertNotIn("catalogue", result[2]["text"])
        self.assertLess(
            sum(item["end"] - item["start"] for item in result.values()), 12
        )
        self.assertEqual(before, self.segments)
        self.assertTrue(
            all(item["blooper_scope_version"] == 1 for item in result.values())
        )

    def test_no_interpolated_timings_for_long_or_incomplete_word_data(self):
        for mutate in [
            lambda s: s.pop("words"),
            lambda s: s["words"].pop(),
            lambda s: s["words"][0].update(start=float("nan")),
            lambda s: s["words"][1].update(start=0),
        ]:
            with self.subTest(mutate=mutate):
                segments = deepcopy(self.segments)
                mutate(segments[0])
                self.assertNotIn(
                    1, focus_blooper_passages(segments, find_blooper_evidence(segments))
                )

    def test_does_not_cut_a_long_unfinished_reaction_at_an_arbitrary_word(self):
        segment = passage(
            1,
            "Oops I am describing a very long unfinished thought without a clause boundary and it keeps going for a considerable time",
        )
        self.assertEqual(
            focus_blooper_passages([segment], find_blooper_evidence([segment])), {}
        )

    def test_short_existing_passage_remains_available_without_word_times(self):
        segment = {
            "id": 1,
            "asset_id": "a",
            "start_seconds": 0,
            "end_seconds": 3,
            "text": "Oops, I got that wrong.",
        }
        result = focus_blooper_passages([segment], find_blooper_evidence([segment]))
        self.assertEqual(result[1]["start"], 0)
        self.assertEqual(result[1]["end"], 3)
        self.assertEqual(result[1]["text"], segment["text"])

    def test_neighbour_context_never_crosses_a_recording(self):
        self.segments[1]["asset_id"] = "b"
        self.assertNotIn(2, self.focus())

    def test_precise_passages_flow_through_the_existing_concept_schema(self):
        row = {
            "id": "a",
            "sha256": "fixture",
            "source_name": "fixture.mp4",
            "display_name": "Fixture",
            "project_name": "Fixture",
            "mime_type": "video/mp4",
            "media_role": "auto",
            "manifest": {},
        }
        request = ConceptRequestCreate(id=uuid4(), reel_kind="bloopers")
        inventory = compact_inventory([row], self.segments, request)
        bundle = inventory["evidence"][0]
        proposal = {
            "concepts": [
                {
                    "title": "The widget stumble",
                    "angle": "Keep the recorded stumble and short recovery.",
                    "script": [
                        {"evidence_id": bundle["evidence_id"], "role": "hook"},
                    ],
                    "incident_ids": [bundle["incident_id"]],
                    "visuals": [],
                }
            ]
        }
        selected = validate_concepts(proposal, inventory, request.id)[0]
        self.assertLess(selected["estimated_seconds"], 12)
        self.assertNotIn("catalogue", selected["script"][-1]["text"])
        scope = selected_blooper_scope({"selected_concept": selected})
        self.assertEqual(len(scope), 1)
        self.assertTrue(scope[0]["incident"])
        legacy = deepcopy(selected)
        legacy["script"][0].pop("blooper_scope_version")
        self.assertEqual(selected_blooper_scope({"selected_concept": legacy}), [])

    def test_validator_rejects_full_take_expansion_and_missing_incident(self):
        focus = self.focus()[1]
        scope = [{"asset_id": "a", **focus}]
        clip = SimpleNamespace(
            asset_id="a", source_in=focus["start"], source_out=focus["end"]
        )
        direction = {"selected_blooper_scope": scope}
        validate_blooper_scope(SimpleNamespace(clips=[clip]), direction)
        clip.source_in = 0
        with self.assertRaisesRegex(ValueError, "extends beyond"):
            validate_blooper_scope(SimpleNamespace(clips=[clip]), direction)
        clip.source_in = focus["start"]
        clip.source_out = focus["incident"]["start"] - 0.1
        with self.assertRaisesRegex(ValueError, "omitted.*incident"):
            validate_blooper_scope(SimpleNamespace(clips=[clip]), direction)
        validate_blooper_scope(SimpleNamespace(clips=[clip]), {})

    def test_word_hydration_reads_only_stored_transcripts_and_handles_corrupt_words(
        self,
    ):
        raw = [
            {
                "words": [
                    None,
                    {"start": "invalid", "end": 1},
                    {"text": "Oops!", "start": 0, "end": 1},
                ]
            }
        ]
        segment = {
            "id": 1,
            "asset_id": "a",
            "start_seconds": 0,
            "end_seconds": 1,
            "text": "Oops!",
        }
        with (
            patch("app.config.get_settings", return_value=object()),
            patch("app.content_catalog._transcript_segments", return_value=raw) as read,
        ):
            result = attach_word_times(
                [{"id": "a", "manifest": {}}, {"id": "unrelated", "manifest": {}}],
                [segment],
            )
        read.assert_called_once()
        self.assertEqual(len(result[0]["words"]), 1)
        self.assertNotIn("words", segment)
