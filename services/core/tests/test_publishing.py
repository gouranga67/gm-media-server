import hashlib
import json
import tempfile
import unittest
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

from cryptography.fernet import Fernet
from fastapi import HTTPException
from pydantic import SecretStr, ValidationError

from app import (
    publishing as pub,
    meta_publishing as meta,
    publishing_captions as captions,
)


def settings(root=Path("/tmp")):
    return SimpleNamespace(
        meta_publishing_enabled=True,
        meta_app_id="123",
        meta_app_secret=SecretStr("a" * 32),
        meta_token_encryption_key=SecretStr(Fernet.generate_key().decode()),
        meta_graph_version="v24.0",
        meta_app_origin="https://studio.example.invalid",
        meta_login_config_id="",
        media_root=root,
        edit_lease_seconds=900,
        chatgpt_model="fixture-model",
    )


class MetaTransportTests(unittest.TestCase):
    def test_binary_upload_streams_the_local_file_in_bounded_chunks(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "video.mp4"
            content = b"x" * (2 * 1024 * 1024 + 3)
            path.write_bytes(content)
            channel = Mock()
            channel.getresponse.return_value.status = 200
            channel.getresponse.return_value.read.return_value = b'{"success":true}'
            with patch.object(
                meta.http.client, "HTTPSConnection", return_value=channel
            ) as connect:
                meta.upload_file(
                    "https://rupload.facebook.com/video-upload/v24.0/123",
                    path,
                    "private-token",
                )
            self.assertEqual(connect.call_args.args[0], "rupload.facebook.com")
            self.assertEqual(
                b"".join(c.args[0] for c in channel.send.call_args_list), content
            )
            self.assertEqual(channel.send.call_count, 3)
            self.assertTrue(
                all(len(c.args[0]) <= 1024 * 1024 for c in channel.send.call_args_list)
            )
            headers = {c.args[0]: c.args[1] for c in channel.putheader.call_args_list}
            self.assertEqual(headers["file_size"], str(len(content)))
            self.assertEqual(headers["offset"], "0")
            channel.close.assert_called_once()

    def test_tokens_are_encrypted_and_wrong_keys_fail_without_exposing_them(self):
        config = settings()
        secret = "sensitive-access-token"
        value = meta.encrypt_token(config, secret)
        self.assertNotIn(secret, value)
        self.assertEqual(meta.decrypt_token(config, value), secret)
        with self.assertRaisesRegex(meta.MetaError, "Reconnect"):
            meta.decrypt_token(settings(), value)
        self.assertNotIn(secret, str(config.meta_app_secret))

    def test_upload_destination_rejects_redirects_credentials_and_untrusted_hosts(self):
        self.assertEqual(
            meta.validate_upload_uri(
                "https://rupload.facebook.com/ig-api-upload/v24.0/123"
            )[0],
            "rupload.facebook.com",
        )
        for uri in [
            "http://rupload.facebook.com/video-upload/a",
            "https://rupload.facebook.com.evil.invalid/video-upload/a",
            "https://secret@rupload.facebook.com/video-upload/a",
            "https://127.0.0.1/video-upload/a",
            "https://rupload.facebook.com/private",
            "https://rupload.facebook.com:8443/video-upload/a",
        ]:
            with self.subTest(uri=uri), self.assertRaises(meta.MetaError):
                meta.validate_upload_uri(uri)

    def test_instagram_creation_and_facebook_creation_use_direct_uploads(self):
        post = dict(
            platform="instagram",
            external_id="123",
            caption="Reviewed caption",
            cover_time_seconds=1.5,
        )
        with patch.object(
            meta,
            "api",
            return_value={
                "id": "456",
                "uri": "https://rupload.facebook.com/ig-api-upload/v24.0/456",
            },
        ) as api:
            self.assertEqual(meta.begin_upload(settings(), post, "token")[0], "456")
        params = api.call_args.kwargs["params"]
        self.assertEqual(params["upload_type"], "resumable")
        self.assertNotIn("video_url", params)
        self.assertEqual(params["caption"], "Reviewed caption")
        self.assertEqual(params["thumb_offset"], "1500")
        post["platform"] = "facebook"
        with patch.object(
            meta,
            "api",
            return_value={
                "video_id": "456",
                "upload_url": "https://rupload.facebook.com/video-upload/v24.0/456",
            },
        ):
            self.assertEqual(meta.begin_upload(settings(), post, "token")[0], "456")

    def test_missing_publish_identity_is_an_ambiguous_write_not_a_safe_retry(self):
        post = dict(platform="instagram", external_id="123", remote_container_id="456")
        with patch.object(meta, "api", return_value={}):
            with self.assertRaises(meta.MetaError) as caught:
                meta.publish(settings(), post, "token")
        self.assertTrue(caught.exception.ambiguous)

    def test_raw_provider_errors_and_tokens_are_not_exposed(self):
        from urllib.error import HTTPError, URLError
        from io import BytesIO

        for error in [
            HTTPError(
                "https://secret.invalid",
                400,
                "secret message",
                {},
                BytesIO(
                    json.dumps(
                        {"error": {"code": 190, "message": "private-token"}}
                    ).encode()
                ),
            ),
            URLError("private-token"),
        ]:
            opener = Mock()
            opener.open.side_effect = error
            with patch.object(meta, "build_opener", return_value=opener):
                with self.assertRaises(meta.MetaError) as caught:
                    meta.api(
                        settings(),
                        "123/media_publish",
                        method="POST",
                        token="private-token",
                    )
            self.assertNotIn("private-token", str(caught.exception))
            self.assertEqual(opener.open.call_count, 1)

    def test_processing_states_are_distinct_from_published(self):
        post = dict(platform="facebook", remote_container_id="123")
        for response, expected in [
            (
                {
                    "status": {
                        "video_status": "ready",
                        "processing_phase": {"status": "complete"},
                    }
                },
                "ready",
            ),
            ({"status": {"publishing_phase": {"status": "complete"}}}, "published"),
            ({"status": {"video_status": "processing"}}, "processing"),
        ]:
            with patch.object(meta, "api", return_value=response):
                self.assertEqual(
                    meta.processing_status(settings(), post, "token"), expected
                )


class DraftApprovalTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.TemporaryDirectory()
        self.addCleanup(self.root.cleanup)
        self.settings = settings(Path(self.root.name))
        self.file = Path(self.root.name) / "final.mp4"
        self.file.write_bytes(b"approved-render")
        self.export = dict(
            id=uuid4(),
            job_id=uuid4(),
            status="ready",
            approved_at=datetime.now(timezone.utc),
            video_path="final.mp4",
            version=3,
            document={"post_copy": "Already approved copy"},
            manifest={
                "render": {"width": 1080, "height": 1920},
                "creative_effects": [],
            },
        )
        self.draft = dict(
            id=uuid4(),
            final_export_id=self.export["id"],
            video_sha256=hashlib.sha256(b"approved-render").hexdigest(),
            caption="Exact caption",
            revision=2,
        )
        self.account = dict(
            id=uuid4(),
            active=True,
            platform="instagram",
            token_expires_at=datetime.now(timezone.utc) + timedelta(days=10),
        )
        self.database = Mock()
        self.database.execute.return_value.fetchall.return_value = [self.account]

        @contextmanager
        def connection():
            yield self.database

        for target, value in [
            ("connection", connection),
            ("get_settings", lambda: self.settings),
            ("owner", lambda _: "owner@example.invalid"),
            ("_draft", lambda *a, **kw: self.draft),
            ("export_row", lambda *a, **kw: self.export),
            ("_posts", lambda *a: []),
            ("_public_draft", lambda db, row: row),
            ("_audit", Mock()),
        ]:
            wrapper = patch.object(pub, target, value)
            wrapper.start()
            self.addCleanup(wrapper.stop)
        self.payload = pub.PublishRequest(
            request_id=uuid4(), revision=2, connection_ids=[self.account["id"]]
        )

    def test_approval_only_enqueues_and_pins_export_revision_and_account(self):
        with patch.object(meta, "api") as api:
            pub.approve_post(self.draft["id"], self.payload)
        api.assert_not_called()
        inserts = [
            c
            for c in self.database.execute.call_args_list
            if "INSERT INTO publishing_posts" in c.args[0]
        ]
        self.assertEqual(len(inserts), 1)
        self.assertIn(self.account["id"], inserts[0].args[1])
        self.assertIn(2, inserts[0].args[1])

    def test_changed_caption_file_or_expired_account_prevents_any_post(self):
        for change in ("caption", "file", "account"):
            with self.subTest(change=change):
                self.database.reset_mock()
                self.draft["revision"] = 2
                self.file.write_bytes(b"approved-render")
                self.account["active"] = True
                if change == "caption":
                    self.draft["revision"] = 3
                if change == "file":
                    self.file.write_bytes(b"replaced-render")
                if change == "account":
                    self.account["active"] = False
                with self.assertRaises(HTTPException):
                    pub.approve_post(self.draft["id"], self.payload)
                self.assertFalse(
                    any(
                        "INSERT INTO publishing_posts" in c.args[0]
                        for c in self.database.execute.call_args_list
                    )
                )

    def test_double_click_reuses_the_same_post_and_different_request_is_rejected(self):
        prior = [
            dict(
                connection_id=self.account["id"],
                approval_request_id=self.payload.request_id,
                approved_revision=2,
            )
        ]
        with patch.object(pub, "_posts", return_value=prior):
            pub.approve_post(self.draft["id"], self.payload)
            with self.assertRaises(HTTPException):
                pub.approve_post(
                    self.draft["id"],
                    self.payload.model_copy(update={"request_id": uuid4()}),
                )
        self.assertFalse(
            any(
                "INSERT INTO publishing_posts" in c.args[0]
                for c in self.database.execute.call_args_list
            )
        )

    def test_preview_square_and_missing_files_are_not_publishable(self):
        for change in ("square", "missing"):
            with self.subTest(change=change):
                self.export["manifest"]["render"]["width"] = 1080
                if change == "square":
                    self.export["manifest"]["render"]["height"] = 1080
                else:
                    self.export["video_path"] = "missing.mp4"
                with self.assertRaises(HTTPException):
                    pub.export_file(self.settings, self.export)
        with patch.object(
            pub, "require_owner", side_effect=HTTPException(403, "owner required")
        ):
            # Routes must use the shared owner gate, not merely trust a role string.
            with self.assertRaises(HTTPException):
                pub.require_owner("viewer@example.invalid")

    def test_platform_permissions_include_historical_effect_lookup(self):
        self.export["manifest"]["creative_effects"] = [{"asset_id": str(uuid4())}]
        self.database.execute.return_value.fetchone.return_value = {
            "allowed_platforms": ["instagram"]
        }
        pub.validate_platform_rights(self.export, "instagram")
        with self.assertRaises(HTTPException):
            pub.validate_platform_rights(self.export, "facebook")

    def test_explicit_ai_copy_and_timezone_are_required(self):
        with self.assertRaises(ValidationError):
            captions.CaptionRequest(id=uuid4(), allow_ai_copy=False)
        with self.assertRaises(ValidationError):
            pub.PublishRequest(
                request_id=uuid4(),
                revision=1,
                connection_ids=[uuid4()],
                publish_at=datetime.now(),
            )
        with self.assertRaises(ValidationError):
            pub.PublishRequest(
                request_id=uuid4(),
                revision=1,
                connection_ids=[self.account["id"], self.account["id"]],
            )


class PublishingWorkerTests(unittest.TestCase):
    def test_failed_status_read_after_publish_never_becomes_a_safe_new_post(self):
        self.post["status"] = "publishing"
        with (
            patch.object(
                meta,
                "processing_status",
                side_effect=meta.MetaError("Reconnect", reconnect=True),
            ),
            patch.object(meta, "publish") as send,
        ):
            pub.process_one_post(self.state)
        send.assert_not_called()
        self.assertEqual(self.save.call_args.kwargs["status"], "unknown")

    def setUp(self):
        self.config = settings()
        self.post = dict(
            id=uuid4(),
            draft_id=uuid4(),
            connection_id=uuid4(),
            caption="Approved caption",
            final_export_id=uuid4(),
            video_sha256="a" * 64,
            platform="instagram",
            external_id="123",
            active=True,
            token_expires_at=None,
            token_ciphertext=meta.encrypt_token(self.config, "secret-token"),
            status="processing",
            remote_container_id="456",
            checks=0,
        )
        self.database = Mock()
        self.database.execute.return_value.fetchone.side_effect = lambda: self.post

        @contextmanager
        def connection():
            yield self.database

        for target, value in [
            ("connection", connection),
            ("get_settings", lambda: self.config),
            ("_save_post", Mock()),
            ("export_row", Mock(return_value={"manifest": {}})),
            ("export_file", Mock(return_value=(Path("/not-read"), "a" * 64))),
            ("validate_platform_rights", Mock()),
        ]:
            wrapper = patch.object(pub, target, value)
            result = wrapper.start()
            self.addCleanup(wrapper.stop)
            if target == "_save_post":
                self.save = result
        self.state = SimpleNamespace(active_publishing_post_id=None)

    def test_processing_check_is_read_only_until_ready(self):
        with (
            patch.object(meta, "processing_status", return_value="processing"),
            patch.object(meta, "publish") as publish,
        ):
            self.assertTrue(pub.process_one_post(self.state))
        publish.assert_not_called()
        self.assertIsNone(self.state.active_publishing_post_id)

    def test_ready_publish_persists_irreversible_stage_before_the_api_call(self):
        events = []
        self.save.side_effect = lambda *args, **kwargs: events.append(kwargs)

        def publish(*args):
            self.assertEqual(events[-1]["status"], "publishing")
            return "789"

        with (
            patch.object(meta, "processing_status", return_value="ready"),
            patch.object(meta, "publish", side_effect=publish) as request,
            patch.object(
                meta,
                "permalink",
                return_value="https://www.instagram.com/reel/fixture/",
            ),
        ):
            self.assertTrue(pub.process_one_post(self.state))
        request.assert_called_once()
        self.assertEqual(events[-1]["status"], "published")
        self.assertEqual(events[-1]["remote_media_id"], "789")

    def test_uncertain_publish_is_not_automatically_repeated(self):
        with (
            patch.object(meta, "processing_status", return_value="ready"),
            patch.object(
                meta, "publish", side_effect=meta.MetaError("Uncertain", ambiguous=True)
            ) as publish,
        ):
            pub.process_one_post(self.state)
        publish.assert_called_once()
        self.assertEqual(self.save.call_args.kwargs["status"], "unknown")
        self.post["status"] = "publishing"
        with (
            patch.object(meta, "processing_status", return_value="ready"),
            patch.object(meta, "publish") as publish,
        ):
            pub.process_one_post(self.state)
        publish.assert_not_called()

    def test_previously_published_remote_container_is_reconciled_without_reposting(
        self,
    ):
        self.post["status"] = "publishing"
        with (
            patch.object(meta, "processing_status", return_value="published"),
            patch.object(meta, "publish") as publish,
            patch.object(meta, "permalink", return_value=None),
        ):
            pub.process_one_post(self.state)
        publish.assert_not_called()
        self.assertEqual(self.save.call_args.kwargs["status"], "published")

    def test_queued_upload_persists_container_before_streaming_and_never_publishes_yet(
        self,
    ):
        self.post["status"] = "queued"

        def upload(uri, path, token):
            self.assertEqual(self.save.call_args.kwargs["remote_container_id"], "456")

        with (
            patch.object(
                meta,
                "begin_upload",
                return_value=(
                    "456",
                    "https://rupload.facebook.com/ig-api-upload/v24.0/456",
                ),
            ),
            patch.object(meta, "upload_file", side_effect=upload) as send,
            patch.object(meta, "publish") as publish,
        ):
            pub.process_one_post(self.state)
        send.assert_called_once()
        publish.assert_not_called()
        self.assertEqual(self.save.call_args.kwargs["status"], "processing")

    def test_disconnected_account_never_uploads(self):
        self.post.update(active=False, status="queued")
        with patch.object(meta, "begin_upload") as upload:
            pub.process_one_post(self.state)
        upload.assert_not_called()
        self.assertEqual(self.save.call_args.kwargs["status"], "failed")

    def test_recovery_marks_interrupted_writes_unknown_and_leaves_queue_approval_intact(
        self,
    ):
        pub.recover_interrupted_publishing()
        sql = " ".join(c.args[0] for c in self.database.execute.call_args_list)
        self.assertIn("status='unknown'", sql)
        self.assertNotIn("SET status='queued'", sql)


class OAuthTests(unittest.TestCase):
    def test_owner_gate_prevents_reading_or_mutating_account_connections(self):
        with (
            patch.object(pub, "actor_login", return_value="viewer@example.invalid"),
            patch.object(
                pub, "require_owner", side_effect=HTTPException(403, "owner required")
            ),
            patch.object(pub, "connection") as database,
        ):
            for action in [
                lambda: pub.list_connections(),
                lambda: pub.start_meta(),
                lambda: pub.disconnect(uuid4()),
            ]:
                with self.assertRaises(HTTPException) as caught:
                    action()
                self.assertEqual(caught.exception.status_code, 403)
        database.assert_not_called()

    def test_invalid_or_replayed_state_does_not_exchange_a_code(self):
        db = Mock()
        db.execute.return_value.fetchone.return_value = None

        @contextmanager
        def connection():
            yield db

        with (
            patch.object(pub, "connection", connection),
            patch.object(pub, "get_settings", return_value=settings()),
            patch.object(pub, "owner", return_value="owner@example.invalid"),
            patch.object(meta, "api") as api,
        ):
            with self.assertRaises(HTTPException):
                pub.complete_meta(
                    pub.OAuthComplete(code="private-code", state="s" * 40)
                )
        api.assert_not_called()
        query, args = db.execute.call_args.args
        self.assertIn("actor_login=%s", query)
        self.assertNotIn("s" * 40, args)

    def test_oauth_callback_never_returns_tokens_and_records_only_encrypted_tokens(
        self,
    ):
        config = settings()
        db = Mock()
        db.execute.return_value.fetchone.return_value = {"state_hash": "valid"}

        @contextmanager
        def connection():
            yield db

        responses = [
            {"access_token": "short-token"},
            {"access_token": "long-token", "expires_in": 10000},
            {
                "data": [
                    {"permission": s, "status": "granted"}
                    for s in pub.SCOPES.split(",")
                ]
            },
            {
                "data": [
                    {
                        "id": "123",
                        "name": "Studio Page",
                        "access_token": "page-private-token",
                        "tasks": ["CREATE_CONTENT"],
                        "instagram_business_account": {
                            "id": "456",
                            "username": "studio",
                        },
                    }
                ]
            },
        ]
        with (
            patch.object(pub, "connection", connection),
            patch.object(pub, "get_settings", return_value=config),
            patch.object(pub, "owner", return_value="owner@example.invalid"),
            patch.object(meta, "api", side_effect=responses),
        ):
            result = pub.complete_meta(
                pub.OAuthComplete(code="private-code", state="s" * 40)
            )
        self.assertEqual(result, {"connected": 2})
        self.assertNotIn("page-private-token", str(db.execute.call_args_list))
        self.assertNotIn("long-token", str(db.execute.call_args_list))


class CaptionWorkerTests(unittest.TestCase):
    def test_caption_evidence_uses_the_approved_vtt_not_omitted_source_chunks(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "captions.vtt"
            path.write_text(
                "WEBVTT\n\n1\n00:00:00.000 --> 00:00:02.000\nA complete approved sentence.\n",
                encoding="utf-8",
            )
            export = {
                "project_name": "Title",
                "brief": "Brief",
                "document": {},
                "captions_path": "captions.vtt",
            }
            db = Mock()
            with patch.object(
                captions, "get_settings", return_value=settings(Path(directory))
            ):
                result = captions.caption_context(db, export)
            self.assertEqual(
                result["approved_on_screen_transcript"], "A complete approved sentence."
            )
            self.assertNotIn("-->", str(result))
            db.execute.assert_not_called()

    def test_caption_request_is_one_bounded_call_and_does_not_change_draft_or_post(
        self,
    ):
        db = Mock()
        row = {"id": uuid4(), "draft_id": uuid4()}
        db.execute.return_value.fetchone.return_value = row

        @contextmanager
        def connection():
            yield db

        options = {
            "options": [
                {"label": label, "text": "Source-backed caption."}
                for label in ("Concise", "Story", "Question")
            ]
        }
        with (
            patch.object(captions, "connection", connection),
            patch.object(captions, "get_settings", return_value=settings()),
            patch.object(captions, "assert_ai_budget"),
            patch.object(captions, "_draft", return_value={"final_export_id": uuid4()}),
            patch.object(captions, "export_row", return_value={}),
            patch.object(
                captions,
                "caption_context",
                return_value={"recorded_speech": "Real words"},
            ),
            patch.object(
                captions,
                "usable_chatgpt_credentials",
                return_value={"access_token": "test"},
            ),
            patch.object(
                captions, "_request_plan", return_value=(options, {"total_tokens": 55})
            ) as provider,
        ):
            self.assertTrue(
                captions.process_one_caption(
                    SimpleNamespace(active_publishing_caption_id=None)
                )
            )
        provider.assert_called_once()
        sql = " ".join(c.args[0] for c in db.execute.call_args_list)
        self.assertIn("INSERT INTO ai_usage_events", sql)
        self.assertNotIn("UPDATE publishing_drafts", sql)
        self.assertNotIn("INSERT INTO publishing_posts", sql)
