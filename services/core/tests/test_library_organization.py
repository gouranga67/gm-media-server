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
        tags=["cream"],confidence="supported",reason="The supplied frame shows the cream product.",folder=None) | changes


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

    def test_stored_original_filename_is_renamed_without_replacing_custom_names(self):
        for stored in ("VID_001.mp4", " vid_001.MP4 "):
            with self.subTest(stored=stored):
                row = source(custom_name=stored)
                row["evidence"] = [{"kind":"transcript", "text":"We stock castor oil in several sizes."}]
                proposal = suggestion(row, display_name="Talking about castor oil sizes")
                result = validate_organization({"suggestions":[proposal]}, [row], False, set())[0]
                self.assertEqual(result["display_name"], "Talking about castor oil sizes")
                self.assertEqual(result["media_role"], "talking")
                self.assertFalse(organization_model_context([row])[0]["name_is_custom"])
        row = source(custom_name="Our castor oil range")
        self.assertTrue(organization_model_context([row])[0]["name_is_custom"])
        result = validate_organization({"suggestions":[suggestion(row)]}, [row], False)[0]
        self.assertEqual(result["display_name"], "Our castor oil range")

    def test_stored_filename_does_not_count_as_evidence_for_an_unseen_image(self):
        row = source(mime="image/png", custom_name="VID_001.mp4")
        row.update(notes="", tags=[])
        result = validate_organization({"suggestions":[suggestion(row)]}, [row], False, set())[0]
        self.assertEqual(result["display_name"], row["display_name"])
        self.assertEqual(result["confidence"], "uncertain")

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

    def test_folder_suggestions_are_opt_in_grounded_and_use_real_folder_ids(self):
        row = source(); folder = {"id":str(uuid4()),"name":"Cream launch"}
        doc = {"suggestions":[suggestion(row,folder=folder)]}
        self.assertIsNone(validate_organization(doc,[row],False)[0]["folder"])
        result = validate_organization(doc,[row],False,folder_options=[folder])[0]
        self.assertEqual(result["folder"],folder)
        same_name = {"suggestions":[suggestion(row,folder={"id":None,"name":"cream launch"})]}
        self.assertEqual(validate_organization(same_name,[row],False,folder_options=[folder])[0]["folder"],folder)
        with self.assertRaises(ValueError):
            validate_organization(doc,[row],False,folder_options=[])
        doc["suggestions"][0]["folder"] = {"id":None,"name":"  Cream   B-roll  "}
        self.assertEqual(validate_organization(doc,[row],False,folder_options=[])[0]["folder"]["name"],"Cream B-roll")
        doc["suggestions"][0]["confidence"] = "uncertain"
        self.assertIsNone(validate_organization(doc,[row],False,folder_options=[])[0]["folder"])
        row.update(notes="",tags=[])
        doc["suggestions"][0]["confidence"] = "supported"
        self.assertIsNone(validate_organization(doc,[row],False,set(),[])[0]["folder"])

    def test_folder_names_reject_paths_blank_and_excessive_length(self):
        for name in ("  ","../cream","cream/broll","cream\\broll","a"*121,"cream\0"):
            with self.subTest(name=name), self.assertRaises(ValidationError):
                OrganizationSuggestion(**suggestion(source(),folder={"id":None,"name":name}))
        # Existing folder names are logical labels and may contain a slash.
        existing = OrganizationSuggestion(**suggestion(source(),folder={"id":uuid4(),"name":"Cream / soap"}))
        self.assertEqual(existing.folder.name,"Cream / soap")

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
        self.row = dict(id=uuid4(),status="ready",inventory=self.sources,applied_asset_ids=[],
            suggestions=[suggestion(row) | {"previous_name":row["display_name"]} for row in self.sources])
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

    def test_folder_choices_require_explicit_apply_and_legacy_sessions_stay_names_only(self):
        data = self.payload.model_dump()
        data["suggestions"][0]["folder"] = {"id":None,"name":"Cream"}
        payload = OrganizationApply.model_validate(data)
        apply_organization(self.row["id"],payload)
        self.assertFalse(any("INSERT INTO library_collection" in call.args[0] for call in self.database.execute.call_args_list))
        receipt = next(c.args[1][1].obj for c in self.database.execute.call_args_list if "SET applied_asset_ids=" in c.args[0])
        self.assertFalse(receipt[0]["folder_applied"])
        self.assertEqual(receipt[0]["previous_name"],self.sources[0]["display_name"])
        self.database.reset_mock()
        payload.apply_folders = True
        with self.assertRaises(HTTPException) as error:
            apply_organization(self.row["id"],payload)
        self.assertEqual(error.exception.status_code,409)

    def test_new_folder_apply_is_additive_transactional_and_retries_do_not_duplicate(self):
        self.row["include_folders"] = True
        target = {"id":None,"name":"Cream launch"}
        payload = OrganizationApply(suggestions=[OrganizationSuggestion(**suggestion(self.sources[0],folder=target)),
            OrganizationSuggestion(**suggestion(self.sources[1],media_role="auto",folder=target))],apply_folders=True)
        result = apply_organization(self.row["id"],payload)
        calls = self.database.execute.call_args_list
        creates = [call for call in calls if "INSERT INTO library_collections" in call.args[0]]
        adds = [call for call in calls if "INSERT INTO library_collection_assets" in call.args[0]]
        self.assertEqual(len(creates),1); self.assertEqual(len(adds),2)
        self.assertIn("ON CONFLICT (lower(name))",creates[0].args[0])
        self.assertTrue(all("ON CONFLICT DO NOTHING" in call.args[0] for call in adds))
        self.assertLess(calls.index(creates[0]),next(i for i,c in enumerate(calls) if "SELECT id FROM assets" in c.args[0]))
        self.assertFalse(any("DELETE" in call.args[0] for call in calls))
        receipt = next(c.args[1][1].obj for c in calls if "SET applied_asset_ids=" in c.args[0])
        self.assertTrue(receipt[0]["folder_applied"])
        self.assertEqual(receipt[0]["folder"]["name"],"Cream launch")
        self.row["applied_asset_ids"] = result["applied_asset_ids"]
        self.database.reset_mock()
        self.assertEqual(apply_organization(self.row["id"],payload)["updated"],0)
        self.assertFalse(any("INSERT" in call.args[0] for call in self.database.execute.call_args_list))

    def test_deleted_or_renamed_folder_blocks_all_metadata_writes(self):
        self.row["include_folders"] = True
        folder = {"id":str(uuid4()),"name":"Original folder name"}
        payload = OrganizationApply(suggestions=[OrganizationSuggestion(**suggestion(self.sources[0],folder=folder))],apply_folders=True)
        for current in (None,dict(id=folder["id"],name="Renamed")):
            def execute(sql, params=None):
                return SimpleNamespace(fetchone=lambda: current if "FROM library_collections" in sql else self.row)
            self.database.reset_mock(); self.database.execute.side_effect = execute
            with self.assertRaises(HTTPException) as error:
                apply_organization(self.row["id"],payload)
            self.assertEqual(error.exception.status_code,409)
            self.assertFalse(any("INSERT" in call.args[0] for call in self.database.execute.call_args_list))


class OrganizationWorkerTests(unittest.TestCase):
    def test_worker_makes_one_request_records_usage_and_never_renames_automatically(self):
        for privacy in ("hybrid","text_only"):
            with self.subTest(privacy=privacy):
                inventory = [source(mime="image/png")]
                folder = {"id":str(uuid4()),"name":"Cream launch"}
                row = dict(id=uuid4(),inventory=inventory,privacy_mode=privacy,rename_existing=False,
                    include_folders=privacy == "hybrid",folder_options=[folder])
                database = Mock(); database.execute.return_value.fetchone.side_effect = [row,None]
                @contextmanager
                def connection(): yield database
                settings = SimpleNamespace(edit_lease_seconds=900,chatgpt_model="fixture-model",media_root="/not-used")
                state = SimpleNamespace(active_organization_request_id=None)
                with patch("app.library_organization.connection",connection),patch("app.library_organization.get_settings",return_value=settings), \
                     patch("app.library_organization.assert_ai_budget"),patch("app.library_organization.usable_chatgpt_credentials",return_value={"access_token":"fixture"}), \
                     patch("app.library_organization.high_impact_visuals",return_value=[]) as images, \
                     patch("app.library_organization._request_plan",return_value=({"suggestions":[suggestion(inventory[0],folder=folder)]}, {"total_tokens":123})) as provider:
                    self.assertTrue(process_one_organization(state)); self.assertFalse(process_one_organization(state))
                provider.assert_called_once()
                prompt = provider.call_args.kwargs["structured_task"]["content"][0]["text"]
                self.assertEqual("Cream launch" in prompt,privacy == "hybrid")
                self.assertEqual(images.call_count,1 if privacy == "hybrid" else 0)
                self.assertTrue(any("INSERT INTO ai_usage_events" in call.args[0] for call in database.execute.call_args_list))
                self.assertFalse(any("INSERT INTO asset_library_metadata" in call.args[0] for call in database.execute.call_args_list))
                self.assertFalse(any("INSERT INTO library_collections" in call.args[0] for call in database.execute.call_args_list))
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
            with self.assertRaises(HTTPException):
                request_organization(OrganizationCreate(id=payload.id,asset_ids=payload.asset_ids,include_folders=True))
        load.assert_not_called()
        self.assertNotIn("inventory",public_session(row))
