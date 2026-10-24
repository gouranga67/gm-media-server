import unittest

from app.visual_index import (
    canonical_assignments,
    evenly_limit,
    normalized_dot,
    representative_times,
    select_visual_matches,
)


class VisualIndexTests(unittest.TestCase):
    def test_only_current_duplicate_review_collapses_to_canonical(self) -> None:
        assets = [
            {"id": "a", "sha256": "same"},
            {"id": "b", "sha256": "same"},
            {"id": "c", "sha256": "other"},
        ]
        current = canonical_assignments(
            assets,
            [{"sha256": "same", "canonical_asset_id": "b", "asset_count": 2}],
        )
        stale = canonical_assignments(
            assets,
            [{"sha256": "same", "canonical_asset_id": "b", "asset_count": 1}],
        )

        self.assertEqual(current, {"a": "b", "b": "b", "c": "c"})
        self.assertEqual(stale, {"a": "a", "b": "b", "c": "c"})

    def test_representative_times_scale_with_scene_duration(self) -> None:
        self.assertEqual(representative_times(2.0, 3.0), [2.5])
        self.assertEqual(representative_times(0.0, 6.0), [0.75, 2.25, 3.75, 5.25])
        self.assertEqual(len(representative_times(10.0, 100.0)), 48)

    def test_representative_times_never_leave_the_source_range(self) -> None:
        for start, end in ((0.0, 0.0), (0.0, 0.25), (8.0, 19.0), (60.0, 90.0)):
            values = representative_times(start, end)
            self.assertTrue(values)
            self.assertTrue(all(start <= value <= end for value in values))

    def test_normalized_dot_is_cosine_similarity(self) -> None:
        self.assertAlmostEqual(normalized_dot([1, 0], [1, 0]), 1.0)
        self.assertAlmostEqual(normalized_dot([1, 0], [0, 1]), 0.0)
        self.assertAlmostEqual(normalized_dot([2, 0], [-3, 0]), -1.0)

    def test_normalized_dot_rejects_mismatched_dimensions(self) -> None:
        with self.assertRaisesRegex(ValueError, "dimensions"):
            normalized_dot([1, 2], [1])

    def test_evenly_limit_preserves_first_middle_and_last_coverage(self) -> None:
        self.assertEqual(evenly_limit(list(range(10)), 3), [0, 4, 9])

    def test_visual_match_selection_removes_weak_long_tail(self) -> None:
        selected = select_visual_matches(
            [(0.356, "car"), (0.259, "person"), (0.249, "stage"), (0.19, "weak")],
            20,
        )
        self.assertEqual(selected, [(0.356, "car")])

    def test_visual_match_selection_keeps_close_ranked_candidates(self) -> None:
        selected = select_visual_matches(
            [(0.25, "one"), (0.23, "two"), (0.205, "three"), (0.17, "weak")],
            20,
        )
        self.assertEqual(selected, [(0.25, "one"), (0.23, "two"), (0.205, "three")])


if __name__ == "__main__":
    unittest.main()
