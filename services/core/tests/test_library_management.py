import unittest
from contextlib import contextmanager
from copy import deepcopy
from unittest.mock import patch
from uuid import UUID

from fastapi import HTTPException
from pydantic import ValidationError

from app.library import update_library_batch
from app.editor_provider import _public_context
from app.schemas import LibraryAssetUpdate, LibraryBatchUpdate

A = UUID("11111111-1111-4111-8111-111111111111")
B = UUID("22222222-2222-4222-8222-222222222222")


class MemoryLibrary:
    def __init__(self):
        self.rows = {
            A: dict(id=A, mime_type="video/mp4", display_name="Camera file", media_role="auto", notes="Keep", favorite=True, library_status="active", job_references=3),
            B: dict(id=B, mime_type="video/mp4", display_name="Other file", media_role="auto", notes="B", favorite=False, library_status="active", job_references=0),
        }
        self.statements = []

    @contextmanager
    def connection(self):
        before = deepcopy(self.rows)
        try:
            yield self
        except Exception:
            self.rows = before
            raise

    def execute(self, sql, parameters):
        self.statements.append((sql, parameters))
        if "SELECT id, mime_type" in sql:
            self.results = [self.rows[id] for id in parameters[0] if id in self.rows]
        elif "SET library_status" in sql:
            for id in parameters[1]:
                self.rows[id]["library_status"] = parameters[0]
        elif "INSERT INTO asset_library_metadata" in sql:
            key = "display_name" if "display_name" in sql else "media_category" if "media_category" in sql else "media_role"
            self.rows[parameters[0]][key] = parameters[1]
        else:
            raise AssertionError(f"Unexpected statement: {sql}")
        return self

    def fetchall(self):
        return self.results


class LibraryManagementTests(unittest.TestCase):
    def setUp(self):
        self.database = MemoryLibrary()
        mock = patch("app.library.connection", self.database.connection)
        mock.start()
        self.addCleanup(mock.stop)

    def test_batch_rename_preserves_role_notes_originals_and_job_references(self):
        update_library_batch(LibraryBatchUpdate(asset_ids=[B, A], action="rename", name_prefix="  Cream   close-up "))
        self.assertEqual(self.database.rows[B]["display_name"], "Cream close-up 001")
        self.assertEqual(self.database.rows[A]["display_name"], "Cream close-up 002")
        self.assertEqual(self.database.rows[A]["notes"], "Keep")
        self.assertEqual(self.database.rows[A]["media_role"], "auto")
        self.assertEqual(self.database.rows[A]["job_references"], 3)
        self.assertTrue(self.database.rows[A]["favorite"])
        self.assertIn("ORDER BY id FOR UPDATE", self.database.statements[0][0])

    def test_single_rename_does_not_add_a_sequence_number(self):
        update_library_batch(LibraryBatchUpdate(asset_ids=[A], action="rename", name_prefix="Product introduction"))
        self.assertEqual(self.database.rows[A]["display_name"], "Product introduction")

    def test_role_change_preserves_metadata(self):
        update_library_batch(LibraryBatchUpdate(asset_ids=[A], action="role", media_role="broll"))
        self.assertEqual(self.database.rows[A]["media_role"], "broll")
        self.assertEqual(self.database.rows[A]["display_name"], "Camera file")

    def test_trash_and_restore_keep_used_originals_and_metadata(self):
        before = deepcopy(self.database.rows[A])
        for action, state in (("trash", "archived"), ("restore", "active")):
            result = update_library_batch(LibraryBatchUpdate(asset_ids=[A, B], action=action))
            self.assertEqual(result["updated"], 2)
            self.assertEqual(self.database.rows[A]["library_status"], state)
        self.assertEqual(self.database.rows[A], before)
        self.assertFalse(any("DELETE" in sql for sql, _ in self.database.statements))

    def test_missing_asset_rejects_entire_batch_before_writing(self):
        before = deepcopy(self.database.rows[A])
        del self.database.rows[B]
        with self.assertRaises(HTTPException) as context:
            update_library_batch(LibraryBatchUpdate(asset_ids=[A, B], action="trash"))
        self.assertEqual(context.exception.status_code, 409)
        self.assertEqual(self.database.rows[A], before)
        self.assertEqual(len(self.database.statements), 1)

    def test_roles_reject_mixed_photos_and_video_atomically(self):
        self.database.rows[B]["mime_type"] = "image/jpeg"
        with self.assertRaises(HTTPException):
            update_library_batch(LibraryBatchUpdate(asset_ids=[A, B], action="role", media_role="broll"))
        self.assertEqual(self.database.rows[A]["media_role"], "auto")

    def test_photo_categories_work_without_video_role_labels_or_other_metadata_changes(self):
        self.database.rows[B]["mime_type"] = "image/png"
        update_library_batch(LibraryBatchUpdate(asset_ids=[B], action="category", media_category="review"))
        self.assertEqual(self.database.rows[B]["media_category"], "review")
        self.assertEqual(self.database.rows[B]["media_role"], "auto")
        self.assertEqual(self.database.rows[B]["notes"], "B")
        self.assertEqual(self.database.rows[B]["display_name"], "Other file")

    def test_mutation_requires_a_nonempty_name_or_explicit_role(self):
        for values in (dict(action="rename"), dict(action="role"), dict(action="category"), dict(action="rename", name_prefix="x" * 252)):
            with self.assertRaises(HTTPException):
                update_library_batch(LibraryBatchUpdate(asset_ids=[A, B], **values))
        self.assertFalse(self.database.statements)

    def test_schema_rejects_duplicates_blank_names_and_oversized_batches(self):
        for values in (dict(asset_ids=[]), dict(asset_ids=[A, A]), dict(asset_ids=[A] * 501), dict(asset_ids=[A], name_prefix="   ")):
            with self.assertRaises(ValidationError):
                LibraryBatchUpdate(action="rename", **values)

    def test_planner_compaction_retains_explicit_names_and_footage_role(self):
        context = {"assets": [{"asset_id": str(A), "library_name": "Cream close-up", "library_role": "broll", "_storage_key": "private/path", "transcript_segments": []}]}
        compact = _public_context(context, 120_000)["assets"][0]
        self.assertEqual(compact["library_name"], "Cream close-up")
        self.assertEqual(compact["library_role"], "broll")
        self.assertNotIn("_storage_key", compact)

    def test_legacy_metadata_client_does_not_request_a_role_reset(self):
        payload = LibraryAssetUpdate(display_name="Name", notes="Notes", tags=["product"])
        self.assertIsNone(payload.media_role)
        self.assertEqual(LibraryAssetUpdate(media_role="talking").media_role, "talking")


if __name__ == "__main__":
    unittest.main()
