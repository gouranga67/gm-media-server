import unittest
from copy import deepcopy

from app.blooper_detection import find_blooper_evidence


def passage(id, text, start=0, end=3, asset="a"):
    return dict(id=id, text=text, start_seconds=start, end_seconds=end, asset_id=asset)


class BlooperDetectionTests(unittest.TestCase):
    def test_self_correction_keeps_adjacent_setup_and_real_recovery(self):
        source = [passage(1, "Here is the product name."),
                  passage(2, "I can't pronounce that!", 3, 5),
                  passage(3, "[laughter] Okay, let's try again.", 5, 8),
                  passage(4, "A later unrelated topic.", 20, 23)]
        original = deepcopy(source)
        evidence = find_blooper_evidence(source)
        self.assertEqual(set(evidence), {1, 2, 3})
        self.assertFalse(evidence[1]["blooper_candidate"])
        self.assertIn("word_stumble", evidence[2]["blooper_signals"])
        self.assertIn("transcribed_laughter", evidence[3]["blooper_signals"])
        self.assertTrue(all(item["confidence"] == "possible" for item in evidence.values()))
        self.assertEqual(source, original)

    def test_context_never_crosses_recordings_or_long_silent_gaps(self):
        evidence = find_blooper_evidence([
            passage(1, "Oops, I got that wrong.", asset="a"),
            passage(2, "A different speaker's line.", 3, 5, asset="b"),
            passage(3, "A line much later.", 30, 33, asset="a"),
        ])
        self.assertEqual(set(evidence), {1})

    def test_repeated_take_is_weak_evidence_only_within_the_same_recording(self):
        first = "This product has a useful feature."
        evidence = find_blooper_evidence([passage(1, first), passage(2, first, 6, 9),
                                         passage(3, first, 200, 203), passage(4, first, 6, 9, asset="b")])
        self.assertEqual(set(evidence), {1, 2})
        self.assertEqual(evidence[1]["blooper_signals"], ["possible_alternate_take"])

    def test_ordinary_speech_claims_questions_and_empty_time_are_not_errors(self):
        evidence = find_blooper_evidence([
            passage(1, "Ready to learn how this works?"),
            passage(2, "Using the wrong product can be difficult.", 4, 6),
            passage(3, "This is the correct price and product name.", 8, 11),
            passage(4, "", 12, 15),
        ])
        self.assertFalse(evidence)

    def test_restart_lost_line_and_transcribed_laughter_are_candidates(self):
        for text, reason in (("Start that again.", "retake_direction"),
                             ("I forgot my lines.", "lost_line"),
                             ("I I I really did that.", "repeated_start"),
                             ("(laughing)", "transcribed_laughter")):
            with self.subTest(text=text):
                self.assertIn(reason, find_blooper_evidence([passage(1, text)])[1]["blooper_signals"])

    def test_invalid_times_do_not_become_source_evidence(self):
        evidence = find_blooper_evidence([passage(1, "Oops!", -1, 3), passage(2, "Oops!", 0, float("inf")),
                                         passage(3, "Oops!", 5, 2), passage(4, "Oops!", 0, 100)])
        self.assertFalse(evidence)
