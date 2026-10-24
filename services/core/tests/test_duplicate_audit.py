import unittest
from datetime import datetime, timedelta, timezone
from uuid import UUID

from app.projects import _duplicate_audit


class DuplicateAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        now = datetime(2026, 10, 23, tzinfo=timezone.utc)
        duplicate_hash = "a" * 64
        unique_hash = "b" * 64
        self.rows = [
            {
                "id": UUID("11111111-1111-4111-8111-111111111111"),
                "project_id": UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
                "project_name": "Coast",
                "source_name": "oldest.mp4",
                "mime_type": "video/mp4",
                "byte_size": 100,
                "sha256": duplicate_hash,
                "created_at": now,
                "job_references": 1,
                "thumbnail_available": True,
            },
            {
                "id": UUID("22222222-2222-4222-8222-222222222222"),
                "project_id": UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"),
                "project_name": "Travel",
                "source_name": "most-used.mp4",
                "mime_type": "video/mp4",
                "byte_size": 100,
                "sha256": duplicate_hash,
                "created_at": now + timedelta(days=1),
                "job_references": 4,
                "thumbnail_available": True,
            },
            {
                "id": UUID("33333333-3333-4333-8333-333333333333"),
                "project_id": UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc"),
                "project_name": "Only once",
                "source_name": "unique.jpg",
                "mime_type": "image/jpeg",
                "byte_size": 40,
                "sha256": unique_hash,
                "created_at": now,
                "job_references": 0,
                "thumbnail_available": True,
            },
        ]

    def test_groups_only_exact_matches_and_recommends_most_used_copy(self) -> None:
        result = _duplicate_audit(self.rows, [])

        self.assertEqual(result["summary"]["originals_scanned"], 3)
        self.assertEqual(result["summary"]["duplicate_groups"], 1)
        self.assertEqual(result["summary"]["redundant_copies"], 1)
        self.assertEqual(result["summary"]["reclaimable_bytes"], 100)
        group = result["groups"][0]
        self.assertEqual(group["canonical_asset_id"], self.rows[1]["id"])
        self.assertFalse(group["reviewed"])

    def test_review_is_current_only_while_membership_matches(self) -> None:
        review = {
            "sha256": "a" * 64,
            "canonical_asset_id": self.rows[0]["id"],
            "asset_count": 2,
            "reviewed_at": datetime(2026, 10, 24, tzinfo=timezone.utc),
        }
        result = _duplicate_audit(self.rows, [review])

        self.assertTrue(result["groups"][0]["reviewed"])
        self.assertEqual(result["groups"][0]["canonical_asset_id"], self.rows[0]["id"])

        extra = dict(self.rows[0])
        extra["id"] = UUID("44444444-4444-4444-8444-444444444444")
        extra["source_name"] = "new-copy.mp4"
        stale = _duplicate_audit([*self.rows, extra], [review])
        self.assertFalse(stale["groups"][0]["reviewed"])

    def test_search_and_review_filters_do_not_change_global_summary(self) -> None:
        result = _duplicate_audit(self.rows, [], query="missing", review_state="reviewed")

        self.assertEqual(result["groups"], [])
        self.assertEqual(result["summary"]["duplicate_groups"], 1)

    def test_optimized_copy_is_retained_but_no_longer_reclaimable(self) -> None:
        review = {
            "sha256": "a" * 64,
            "canonical_asset_id": self.rows[1]["id"],
            "asset_count": 2,
            "reviewed_at": datetime(2026, 10, 24, tzinfo=timezone.utc),
        }
        self.rows[0]["storage_optimized"] = True
        result = _duplicate_audit(self.rows, [review])

        self.assertEqual(result["summary"]["redundant_copies"], 1)
        self.assertEqual(result["summary"]["optimized_copies"], 1)
        self.assertEqual(result["summary"]["reclaimable_bytes"], 0)
        self.assertFalse(result["groups"][0]["cleanup_ready"])


if __name__ == "__main__":
    unittest.main()
