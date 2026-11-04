"""Bounded source pages and exact carried-over selections; browsing cannot create work."""
import asyncio
import unittest
from unittest.mock import MagicMock, patch
from uuid import UUID

from fastapi import FastAPI
from app import library_intake as library

A = UUID("11111111-1111-4111-8111-111111111111")
P = UUID("22222222-2222-4222-8222-222222222222")
F = UUID("33333333-3333-4333-8333-333333333333")


class LibraryPickerTests(unittest.TestCase):
    def test_source_filters_are_applied_before_pagination_and_never_include_trash(self):
        where, values = library.browse_filter("broll", "all", False, F, False, "cream", [A], "video", P, True)
        self.assertEqual(values, ["active", "video/%", P, "broll", F, "%cream%", [A]])
        self.assertNotIn("cream", where)
        for text in ("assets.sha256 IS NOT NULL", "assets.byte_size IS NOT NULL", "assets.mime_type IS NOT NULL",
                     "assets.library_status = 'active'", "assets.project_id = %s"):
            self.assertIn(text, where)
        trash, values = library.browse_filter("trash", "all", False, None, False, "", [], for_editing=True)
        self.assertIn("assets.library_status = 'active'", trash)
        self.assertEqual(values, ["archived"])  # Conflicting scopes yield no selectable archived rows.

    def test_page_binds_scope_and_offset_and_hydrates_only_the_page(self):
        database = MagicMock(); database.__enter__.return_value = database
        def query(sql, params=()):
            result = MagicMock()
            if sql.startswith("WITH candidates"):
                result.fetchone.return_value = {"total": 620, "ids": [A]}
            elif "GROUP BY assets.id" in sql:
                result.fetchall.return_value = [{"id": A}]
            else:
                result.fetchone.return_value = {"active": 620, "trash": 0, "stored_bytes": 1}
            return result
        database.execute.side_effect = query
        with patch.object(library, "connection", return_value=database):
            result = library.browse_library(view="all", category="all", favorite=False, collection_id=F,
                unfiled=False, query="", match_ids=[], copies=False, sort="newest", limit=60, offset=540,
                media_kind="video", project_id=P, for_editing=True)
        self.assertEqual(result["total"], 620); self.assertEqual(result["items"], [{"id": A}])
        sql, params = database.execute.call_args_list[0].args
        self.assertEqual(params[-2:], [60, 540]); self.assertIn(P, params); self.assertIn(F, params)
        self.assertIn("FROM filtered ORDER BY", sql)
        self.assertEqual(database.execute.call_args_list[1].args[1], ([A],))

    def test_exact_selection_does_not_substitute_duplicates_or_return_private_paths(self):
        database = MagicMock(); database.__enter__.return_value = database
        database.execute.return_value.fetchall.return_value = [{"id": A}]
        with patch.object(library, "connection", return_value=database):
            self.assertEqual(library.selected_library_assets([A]), [{"id": A}])
        sql, params = database.execute.call_args.args
        self.assertEqual(params, ([A],))
        self.assertIn("assets.id=ANY(%s::uuid[])", sql)
        self.assertNotIn("canonical_asset_id", sql)
        for field in ("storage_key", "preview_path", "INSERT", "UPDATE", "DELETE"):
            self.assertNotIn(field, sql)

    def test_project_choices_are_metadata_only_and_use_the_same_ready_scope(self):
        database = MagicMock(); database.__enter__.return_value = database
        database.execute.return_value.fetchall.return_value = [{"id": P, "name": "Cream"}]
        with patch.object(library, "connection", return_value=database):
            self.assertEqual(library.picker_projects(), [{"id": P, "name": "Cream"}])
        sql = database.execute.call_args.args[0]
        self.assertIn("SELECT DISTINCT projects.id,projects.name", sql)
        self.assertIn(library.PICKER_READY, sql)
        self.assertNotIn("projects.brief", sql)

    def test_http_validation_bounds_selection_and_page_sizes_before_database_access(self):
        app = FastAPI(); app.include_router(library.router, prefix="/library")
        async def status(path):
            pathname, _, query = path.partition("?")
            messages = []
            async def receive(): return {"type": "http.request", "body": b"", "more_body": False}
            async def send(value): messages.append(value)
            scope = dict(type="http", asgi={"version": "3.0"}, http_version="1.1", method="GET",
                scheme="http", path=pathname, raw_path=pathname.encode(), query_string=query.encode(),
                root_path="", headers=[], client=("127.0.0.1", 1), server=("fixture", 80))
            await app(scope, receive, send)
            return messages[0]["status"]
        with patch.object(library, "connection") as database:
            for path in ("/library/selection", "/library/selection?asset_ids=invalid",
                         "/library/selection?" + "&".join([f"asset_ids={A}"] * 101),
                         "/library/browse?limit=101", "/library/browse?offset=-1",
                         "/library/browse?media_kind=unknown", "/library/browse?project_id=invalid"):
                self.assertEqual(asyncio.run(status(path)), 422, path)
            database.assert_not_called()
