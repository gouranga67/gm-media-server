import unittest
from contextlib import contextmanager
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

from fastapi import HTTPException
from pydantic import ValidationError

from app.library_organization import (OrganizationApply, OrganizationCreate, OrganizationDocument,
    OrganizationSuggestion, apply_organization, organization_model_context, process_one_organization,
    public_session, request_organization, validate_organization)


def source(mime="video/mp4", role="auto", custom_name=None, category="auto"):
    return dict(asset_id=str(uuid4()),source_name="VID_001.mp4",mime_type=mime,display_name=custom_name or "VID_001.mp4",
        custom_name=custom_name,media_role=role,media_category=category,tags=["existing"],notes="Keep these notes",
        sha256="a"*64,metadata_version="None",evidence=[],has_video=mime.startswith("video/"),
        _preview_key="private/thumbnail.jpg",_contact_sheet_key=None)


def suggestion(row, **changes):
    return dict(asset_id=row["asset_id"],display_name="Cream B-roll",media_role="broll",media_category="product",
        tags=["cream"],confidence="supported",reason="The supplied frame shows the cream product.") | changes


class OrganizationValidationTests(unittest.TestCase):
    def test_public_context_never_shares_private_paths_hashes_or_metadata_versions(self):
        text = str(organization_model_context([source()]))
        self.assertNotIn("private/", text)
        self.assertNotIn("sha256", text)
        self.assertNotIn("metadata_version", text)

    def test_photos_receive_descriptive_names_and_categories_without_video_labels(self):
        row = source(mime="image/png")
        result = validate_organization({"suggestions":[suggestion(row, display_name="Image of customer review",media_category="review")]}, [row], False)[0]
        self.assertEqual(result["media_category"], "review")
        self.assertEqual(result["media_role"], "auto")
        self.assertEqual(result["display_name"], "Image of customer review")

    def test_manual_names_roles_and_categories_survive_default_suggestions(self):
        row = source(custom_name="A"*255, role="talking", category="review")
        result = validate_organization({"suggestions":[suggestion(row)]}, [row], False)[0]
        self.assertEqual(result["display_name"], "A"*255)
        self.assertEqual(result["media_role"], "talking")
        self.assertEqual(result["media_category"], "review")
        renamed = validate_organization({"suggestions":[suggestion(row)]}, [row], True)[0]
        self.assertEqual(renamed["display_name"], "Cream B-roll")

    def test_transcribed_talking_take_cannot_be_auto_mislabelled_as_silent_broll(self):
        row = source(); row["evidence"] = [{"kind":"transcript","text":"I am introducing the soap and explaining how to use it."}]
        result = validate_organization({"suggestions":[suggestion(row)]}, [row], False)[0]
        self.assertEqual(result["media_role"], "talking")

    def test_uncertain_video_does_not_acquire_a_broll_role(self):
        row = source()
        result = validate_organization({"suggestions":[suggestion(row,confidence="uncertain")]}, [row], False)[0]
        self.assertEqual(result["media_role"], "auto")

    def test_unpictured_anonymous_image_does_not_gain_an_invented_topic(self):
        row = source(mime="image/png"); row.update(notes="",tags=[])
        result = validate_organization({"suggestions":[suggestion(row)]}, [row], False, pictured_asset_ids=set())[0]
        self.assertEqual(result["display_name"],row["display_name"])
        self.assertEqual(result["confidence"],"uncertain")
        self.assertEqual(result["media_category"],"auto")

    def test_missing_repeated_and_unknown_source_proposals_are_rejected(self):
        row = source(); other = source()
        for values in ([], [suggestion(other)], [suggestion(row),suggestion(row)]):
            with self.subTest(values=values), self.assertRaises(ValueError):
                validate_organization({"suggestions":values}, [row], False)

    def test_bounded_unique_selection_and_closed_structured_schema(self):
        id = uuid4()
        for ids in ([],[id,id],[uuid4() for _ in range(25)]):
            with self.assertRaises(ValidationError):
                OrganizationCreate(id=uuid4(), asset_ids=ids)
        schema = OrganizationDocument.model_json_schema()
        for item in [schema,*schema["$defs"].values()]:
            if item.get("type") == "object":
                self.assertFalse(item["additionalProperties"])
                self.assertEqual(set(item["properties"]),set(item["required"]))
        with self.assertRaises(ValidationError):
            OrganizationSuggestion(**suggestion(source(), display_name="../original.png"))


class OrganizationApplyTests(unittest.TestCase):
    def setUp(self):
        self.sources = [source(),source(mime="image/png")]
        self.row = dict(id=uuid4(),status="ready",inventory=self.sources,applied_asset_ids=[])
        self.database = Mock()
        self.database.execute.return_value.fetchone.return_value = self.row
        self.database.execute.return_value.fetchall.return_value = [{"id":item["asset_id"]} for item in self.sources]
        self.payload = OrganizationApply(suggestions=[OrganizationSuggestion(**suggestion(self.sources[0])),
            OrganizationSuggestion(**suggestion(self.sources[1],media_role="auto",media_category="review"))])
        @contextmanager
        def connection(): yield self.database
        self.connection = patch("app.library_organization.connection",connection); self.connection.start(); self.addCleanup(self.connection.stop)
        self.inventory = patch("app.library_organization.load_organization_inventory",return_value=self.sources)
        self.inventory_mock = self.inventory.start(); self.addCleanup(self.inventory.stop)

    def test_apply_changes_metadata_only_and_repeated_application_is_a_noop(self):
        result = apply_organization(self.row["id"],self.payload)
        self.assertEqual(result["updated"],2)
        inserts = [call for call in self.database.execute.call_args_list if "INSERT INTO asset_library_metadata" in call.args[0]]
        self.assertEqual(len(inserts),2)
        sql = inserts[0].args[0]
        updates = sql.split("DO UPDATE SET")[1]
        self.assertNotIn("notes=",updates)
        self.assertNotIn("favorite=",updates)
        self.assertIn("WITH ORDINALITY",updates)
        self.assertFalse(any("DELETE" in call.args[0] or "UPDATE assets" in call.args[0] for call in self.database.execute.call_args_list))
        self.row["applied_asset_ids"] = result["applied_asset_ids"]
        self.database.reset_mock()
        again = apply_organization(self.row["id"],self.payload)
        self.assertEqual(again["updated"],0)
        self.assertFalse(any("INSERT" in call.args[0] for call in self.database.execute.call_args_list))

    def test_stale_metadata_or_trashed_assets_prevent_all_writes(self):
        changed = deepcopy(self.sources); changed[0]["metadata_version"] = "changed"
        self.inventory_mock.return_value = changed
        with self.assertRaises(HTTPException):
            apply_organization(self.row["id"],self.payload)
        self.assertFalse(any("INSERT" in call.args[0] for call in self.database.execute.call_args_list))
        self.database.reset_mock(); self.database.execute.return_value.fetchall.return_value = []
        with self.assertRaises(HTTPException):
            apply_organization(self.row["id"],self.payload)
        self.assertFalse(any("INSERT" in call.args[0] for call in self.database.execute.call_args_list))

    def test_unknown_source_and_photo_video_labels_are_rejected_before_writes(self):
        bad = OrganizationApply(suggestions=[OrganizationSuggestion(**suggestion(source()))])
        with self.assertRaises(HTTPException):
            apply_organization(self.row["id"],bad)
        bad = OrganizationApply(suggestions=[OrganizationSuggestion(**suggestion(self.sources[1]))])
        self.database.execute.return_value.fetchall.return_value = [{"id":self.sources[1]["asset_id"]}]
        with self.assertRaises(HTTPException):
            apply_organization(self.row["id"],bad)
        self.assertFalse(any("INSERT" in call.args[0] for call in self.database.execute.call_args_list))


class OrganizationWorkerTests(unittest.TestCase):
    def test_worker_makes_one_request_records_usage_and_never_renames_automatically(self):
        for privacy in ("hybrid","text_only"):
            with self.subTest(privacy=privacy):
                inventory = [source(mime="image/png")]
                row = dict(id=uuid4(),inventory=inventory,privacy_mode=privacy,rename_existing=False)
                database = Mock(); database.execute.return_value.fetchone.side_effect = [row,None]
                @contextmanager
                def connection(): yield database
                settings = SimpleNamespace(edit_lease_seconds=900,chatgpt_model="fixture-model",media_root="/not-used")
                state = SimpleNamespace(active_organization_request_id=None)
                with patch("app.library_organization.connection",connection),patch("app.library_organization.get_settings",return_value=settings), \
                     patch("app.library_organization.assert_ai_budget"),patch("app.library_organization.usable_chatgpt_credentials",return_value={"access_token":"fixture"}), \
                     patch("app.library_organization.high_impact_visuals",return_value=[]) as images, \
                     patch("app.library_organization._request_plan",return_value=({"suggestions":[suggestion(inventory[0])]}, {"total_tokens":123})) as provider:
                    self.assertTrue(process_one_organization(state)); self.assertFalse(process_one_organization(state))
                provider.assert_called_once()
                self.assertEqual(images.call_count,1 if privacy == "hybrid" else 0)
                self.assertTrue(any("INSERT INTO ai_usage_events" in call.args[0] for call in database.execute.call_args_list))
                self.assertFalse(any("INSERT INTO asset_library_metadata" in call.args[0] for call in database.execute.call_args_list))
                self.assertIsNone(state.active_organization_request_id)

    def test_invalid_proposal_still_records_usage_without_retrying(self):
        row = dict(id=uuid4(),inventory=[source()],privacy_mode="text_only",rename_existing=False)
        database = Mock(); database.execute.return_value.fetchone.side_effect = [row,None]
        @contextmanager
        def connection(): yield database
        with patch("app.library_organization.connection",connection),patch("app.library_organization.get_settings",return_value=SimpleNamespace(edit_lease_seconds=900,chatgpt_model="fixture")), \
             patch("app.library_organization.assert_ai_budget"),patch("app.library_organization.usable_chatgpt_credentials",return_value={"access_token":"fixture"}), \
             patch("app.library_organization._request_plan",return_value=({"suggestions":[]},{"total_tokens":23})) as provider:
            self.assertTrue(process_one_organization(SimpleNamespace(active_organization_request_id=None)))
        provider.assert_called_once()
        self.assertTrue(any("INSERT INTO ai_usage_events" in call.args[0] for call in database.execute.call_args_list))
        self.assertTrue(any("status='failed'" in call.args[0] for call in database.execute.call_args_list))

    def test_request_nonce_reuses_saved_results_and_refuses_different_selections(self):
        payload = OrganizationCreate(id=uuid4(),asset_ids=[uuid4()])
        row = dict(id=payload.id,asset_ids=[str(id) for id in payload.asset_ids],rename_existing=False,privacy_mode="hybrid",inventory=[source()])
        database = Mock(); database.execute.return_value.fetchone.return_value = row
        @contextmanager
        def connection(): yield database
        with patch("app.library_organization.connection",connection),patch("app.library_organization.load_organization_inventory") as load:
            self.assertNotIn("inventory",request_organization(payload))
            with self.assertRaises(HTTPException):
                request_organization(OrganizationCreate(id=payload.id,asset_ids=[uuid4()]))
        load.assert_not_called()
        self.assertNotIn("inventory",public_session(row))
