import unittest
from contextlib import contextmanager
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch
from uuid import UUID

from fastapi import HTTPException
from psycopg.errors import UniqueViolation
from pydantic import ValidationError

from app.library_intake import IntakeReview, browse_filter, review_intake
from app.projects import create_asset
from app.schemas import AssetCreate

A = UUID("11111111-1111-4111-8111-111111111111")
P = UUID("22222222-2222-4222-8222-222222222222")
F = UUID("33333333-3333-4333-8333-333333333333")


class IntakeDatabase:
    def __init__(self):
        self.assets = {}
        self.metadata = {}
        self.imports = {}
        self.members = set()
        self.folders = {F}
        self.statements = []
        self.result = []

    @contextmanager
    def connection(self):
        before = deepcopy((self.assets, self.metadata, self.imports, self.members))
        try:
            yield self
        except Exception:
            self.assets, self.metadata, self.imports, self.members = before
            raise

    def execute(self, statement, parameters):
        sql = " ".join(statement.split())
        self.statements.append((statement, parameters))
        self.result = []
        if sql.startswith("INSERT INTO assets"):
            id, project_id, name, key, mime, size = parameters
            if id in self.assets:
                raise UniqueViolation("already registered")
            self.assets[id] = dict(id=id, project_id=project_id, source_name=name, storage_key=key,
                                   mime_type=mime, byte_size=size, status="uploading")
            self.result = [self.assets[id]]
        elif sql.startswith("SELECT id FROM library_collections"):
            self.result = [{"id": parameters[0]}] if parameters[0] in self.folders else []
        elif sql.startswith("INSERT INTO library_collection_assets"):
            self.members.add(tuple(parameters))
        elif sql.startswith("INSERT INTO asset_library_metadata"):
            self.metadata[parameters[0]] = {"display_name": parameters[1], "media_role": parameters[2]}
        elif sql.startswith("INSERT INTO library_intakes"):
            self.imports[parameters[0]] = {"preferences": parameters[1].obj, "reviewed_at": None}
        elif sql.startswith("SELECT * FROM assets"):
            self.result = [self.assets[parameters[0]]] if parameters[0] in self.assets else []
        elif sql.startswith("SELECT preferences FROM library_intakes"):
            self.result = [self.imports[parameters[0]]] if parameters[0] in self.imports else []
        elif sql.startswith("SELECT intake.asset_id"):
            self.result = [dict(asset_id=id, status=self.assets[id]["status"],
                                ingest_status=self.assets[id].get("ingest_status"), catalog_status=self.assets[id].get("catalog_status"))
                           for id in parameters[0] if id in self.imports]
        elif sql.startswith("UPDATE library_intakes SET reviewed_at"):
            for id in parameters[0]:
                self.imports[id]["reviewed_at"] = self.imports[id]["reviewed_at"] or "reviewed"
        else:
            raise AssertionError(sql)
        return self

    def fetchone(self):
        return self.result[0] if self.result else None

    def fetchall(self):
        return self.result


class LibraryIntakeTests(unittest.TestCase):
    def setUp(self):
        self.db = IntakeDatabase()
        for path in ("app.projects.connection", "app.library_intake.connection"):
            mocked = patch(path, self.db.connection)
            mocked.start()
            self.addCleanup(mocked.stop)
        mocked = patch("app.projects.get_settings", return_value=SimpleNamespace(max_upload_bytes=1000))
        mocked.start()
        self.addCleanup(mocked.stop)

    def payload(self, **changes):
        return AssetCreate(id=A, source_name="VID.mp4", mime_type="video/mp4", byte_size=20,
            library_intake={"collection_id": F, "display_name": " Cream   close-up ", "media_role": "broll", **changes})

    def test_registration_atomically_saves_destination_and_labels_before_upload(self):
        result = create_asset(P, self.payload())
        self.assertEqual(result["status"], "uploading")
        self.assertEqual(result["source_name"], "VID.mp4")
        self.assertEqual(self.db.metadata[A], {"display_name": "Cream close-up", "media_role": "broll"})
        self.assertEqual(self.db.members, {(F, A)})
        self.assertIsNone(self.db.imports[A]["reviewed_at"])
        self.assertFalse(any("job_assets" in sql or "UPDATE assets" in sql for sql, _ in self.db.statements))

    def test_missing_destination_rolls_back_asset_and_metadata(self):
        self.db.folders.clear()
        with self.assertRaises(HTTPException) as error:
            create_asset(P, self.payload())
        self.assertEqual(error.exception.status_code, 409)
        self.assertEqual((self.db.assets, self.db.metadata, self.db.members, self.db.imports), ({}, {}, set(), {}))

    def test_registration_retry_never_overwrites_later_names_or_reopens_inbox(self):
        create_asset(P, self.payload())
        self.db.metadata[A]["display_name"] = "Owner corrected name"
        self.db.imports[A]["reviewed_at"] = "yesterday"
        create_asset(P, self.payload())
        self.assertEqual(self.db.metadata[A]["display_name"], "Owner corrected name")
        self.assertEqual(self.db.imports[A]["reviewed_at"], "yesterday")
        self.assertEqual(len(self.db.members), 1)

    def test_retry_with_changed_preferences_is_explicit_conflict(self):
        create_asset(P, self.payload())
        with self.assertRaises(HTTPException) as error:
            create_asset(P, self.payload(display_name="Different batch"))
        self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(self.db.metadata[A]["display_name"], "Cream close-up")

    def test_existing_job_upload_does_not_create_intake_record(self):
        create_asset(P, AssetCreate(id=A, source_name="old.mp4", mime_type="video/mp4", byte_size=5))
        self.assertFalse(self.db.imports)
        self.assertFalse(self.db.metadata)

    def test_review_waits_for_ingest_and_analysis_and_is_idempotent(self):
        create_asset(P, self.payload())
        with self.assertRaises(HTTPException):
            review_intake(IntakeReview(asset_ids=[A]))
        self.assertIsNone(self.db.imports[A]["reviewed_at"])
        self.db.assets[A].update(status="ready", ingest_status="ready", catalog_status="ready")
        original = deepcopy(self.db.assets)
        for _ in range(2):
            self.assertEqual(review_intake(IntakeReview(asset_ids=[A]))["updated"], 1)
        self.assertEqual(self.db.assets, original)
        self.assertEqual(self.db.imports[A]["reviewed_at"], "reviewed")

    def test_review_missing_member_is_atomic_and_dismiss_never_deletes(self):
        create_asset(P, self.payload())
        with self.assertRaises(HTTPException):
            review_intake(IntakeReview(asset_ids=[A, F], action="dismiss"))
        self.assertIsNone(self.db.imports[A]["reviewed_at"])
        review_intake(IntakeReview(asset_ids=[A], action="dismiss"))
        self.assertIn(A, self.db.assets)
        self.assertIn((F, A), self.db.members)
        self.assertFalse(any("DELETE" in sql for sql, _ in self.db.statements))

    def test_schema_preserves_job_contract_and_rejects_invalid_preferences(self):
        for changes in ({"job_id": F, "library_intake": {}}, {"mime_type": "image/png", "library_intake": {"media_role": "broll"}},
                        {"library_intake": {"display_name": "   "}}, {"library_intake": {"unknown": "value"}}):
            with self.assertRaises(ValidationError):
                AssetCreate(source_name="x", mime_type=changes.get("mime_type", "video/mp4"), byte_size=1,
                            **{k: v for k, v in changes.items() if k != "mime_type"})
        for ids in ([], [A, A], [A] * 101):
            with self.assertRaises(ValidationError):
                IntakeReview(asset_ids=ids)

    def test_browse_filters_bind_user_values_and_bound_evidence_to_matching_assets(self):
        where, values = browse_filter("broll", "product", True, F, True, "owner's cream", [A])
        self.assertNotIn("owner's", where)
        self.assertIn("EXISTS", where)
        self.assertIn("NOT EXISTS", where)
        self.assertIn("COALESCE(meta.media_role, 'auto') = %s", where)
        self.assertEqual(values, ["active", "broll", "product", F, "%owner's cream%", [A]])


if __name__ == "__main__":
    unittest.main()
