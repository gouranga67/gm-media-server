from datetime import datetime, timezone
import unittest
from unittest.mock import MagicMock, patch
from uuid import uuid4

from app.editing import job_review, prompt_history
from app.schemas import JobReviewResponse, PromptHistoryResponse


class PromptHistoryTests(unittest.TestCase):
    def entry(self, kind="original", status="awaiting_review"):
        return {"id": str(uuid4()), "job_id": uuid4(), "project_name": "Product ad",
                "prompt": "Keep the story clear.\nPreserve ‘castor oil’. 🌿", "kind": kind,
                "version": 3 if kind == "revision" else None, "status": status,
                "created_at": datetime.now(timezone.utc), "archived": True}

    def test_history_preserves_failed_revision_text_and_archived_jobs(self):
        rows = [self.entry("revision", "failed"), self.entry(), self.entry()]
        with patch("app.editing.connection") as connection:
            database = connection.return_value.__enter__.return_value
            database.execute.return_value.fetchall.return_value = rows
            response = PromptHistoryResponse.model_validate(prompt_history(query=" castor oil ", limit=2, offset=5))
        self.assertEqual(len(response.items), 2)
        self.assertTrue(response.has_more)
        self.assertEqual(response.next_offset, 7)
        self.assertEqual(response.items[0].status, "failed")
        self.assertTrue(response.items[0].archived)
        self.assertEqual(response.items[0].prompt, rows[0]["prompt"])
        query, parameters = database.execute.call_args.args
        self.assertEqual(parameters[1:], ("castor oil", "castor oil", 3, 5))
        self.assertIn("ORDER BY created_at DESC, id DESC", query)

    def test_empty_history_does_not_advance_pagination(self):
        with patch("app.editing.connection") as connection:
            connection.return_value.__enter__.return_value.execute.return_value.fetchall.return_value = []
            response = prompt_history(query="", limit=30, offset=0)
        self.assertEqual(response, {"items": [], "has_more": False, "next_offset": 0})

    def test_review_exposes_original_prompt_even_before_first_render(self):
        now = datetime.now(timezone.utc)
        job = {"id": uuid4(), "project_id": uuid4(), "recipe": "talking_head", "status": "draft",
               "revision": 0, "created_at": now, "updated_at": now}
        original = "Make a coherent ad.\nKeep the words <exactly> as spoken."
        context = {"project": {"name": "Product ad", "brief": original}, "assets": []}
        with patch("app.editing.connection") as connection, \
             patch("app.editing._context_or_http", return_value=context), \
             patch("app.editing._select_final_export", return_value=None), \
             patch("app.editing._job_usage", return_value={}):
            database = connection.return_value.__enter__.return_value
            database.execute.return_value.fetchone.side_effect = [job, None]
            database.execute.return_value.fetchall.return_value = []
            response = JobReviewResponse.model_validate(job_review(job["id"]))
        self.assertEqual(response.original_prompt, original)
        self.assertEqual(response.project_name, "Product ad")
        self.assertIsNone(response.latest_run)


if __name__ == "__main__":
    unittest.main()
