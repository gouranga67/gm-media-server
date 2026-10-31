"""Explicit AI-music approval preserves provenance without relaxing effects."""

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from fastapi import HTTPException
from starlette.requests import Request

from app import creative_assets
from app.edit_renderer import _selected_music
from app.music_import import _parser
from app.montage_renderer import _manifest
from app.edit_plan import MontageEditPlan


class ApprovedMusicTests(unittest.IsolatedAsyncioTestCase):
    async def import_fixture(self, directory, *, kind="music", generated=False):
        async def receive():
            return {"type": "http.request", "body": b"fixture", "more_body": False}

        request = Request({"type": "http", "method": "POST", "headers": []}, receive)
        database = MagicMock()
        database.__enter__.return_value = database
        database.execute.return_value.fetchone.return_value = {"id": str(uuid4())}
        with patch.multiple(
            creative_assets,
            require_owner=lambda _: None,
            actor_login=lambda _: "owner",
            ensure_capacity=lambda _: None,
            get_settings=lambda: SimpleNamespace(media_root=Path(directory), analysis_command_timeout_seconds=5),
            probe_media=lambda *_: {"streams": [{"type": "audio"}], "format": {"duration_seconds": 1}},
            connection=MagicMock(return_value=database),
        ):
            result = await creative_assets.import_creative_asset(
                request, kind=kind, filename="fixture.mp3", title="Chosen music", creator="Artist",
                tags="", purpose="emphasis", mood="warm", energy="low", use_when="", avoid_when="",
                license_name="Pixabay Content License", license_source_url="https://pixabay.com/music/example-123/",
                license_proof="Downloaded source certificate retained", attribution="Artist via Pixabay",
                allowed_platforms="instagram", commercial_use_confirmed=True,
                ai_generated_music=generated, x_gm_user_login="owner",
            )
        return result, database.execute.call_args.args

    async def test_ai_import_records_both_generation_and_explicit_approval(self):
        with tempfile.TemporaryDirectory() as directory:
            result, (sql, parameters) = await self.import_fixture(directory, generated=True)
        self.assertEqual(result["kind"], "music")
        self.assertEqual(sql.count("%s"), len(parameters))
        self.assertIn("synthetic_media, synthetic_music_approved", sql)
        self.assertEqual(parameters[11:13], (True, True))
        self.assertEqual(parameters[13], '["instagram"]')

    async def test_non_ai_import_retains_false_flags(self):
        with tempfile.TemporaryDirectory() as directory:
            _, (_, parameters) = await self.import_fixture(directory)
        self.assertEqual(parameters[11:13], (False, False))

    async def test_music_exception_cannot_import_synthetic_effects(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(HTTPException) as caught:
                await self.import_fixture(directory, kind="sound_effect", generated=True)
            self.assertEqual(caught.exception.status_code, 422)
            self.assertFalse(any(Path(directory).iterdir()))

    def test_render_music_metadata_retains_approval_and_original_source(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "music.mp3"
            source.write_bytes(b"fixture")
            identity = str(uuid4())
            context = {"music_library": [{"track_id": identity, "_storage_key": "music.mp3",
                        "synthetic_media": True, "synthetic_music_approved": True,
                        "license_source_url": "https://pixabay.com/music/example-123/"}]}
            path, metadata = _selected_music(context, SimpleNamespace(music_track_id=identity, music_mix="subtle"),
                                             SimpleNamespace(media_root=Path(directory)))
            self.assertEqual(path, source)
            self.assertTrue(metadata["synthetic_media"])
            self.assertTrue(metadata["synthetic_music_approved"])
            self.assertEqual(metadata["license_source_url"], context["music_library"][0]["license_source_url"])
            self.assertNotIn("_storage_key", metadata)

    def test_cli_requires_an_explicit_ai_music_flag(self):
        args = ["--source", "/tmp/music.mp3", "--title", "Chosen music", "--mood", "warm", "--energy", "low",
                "--license-name", "Pixabay Content License", "--license-source-url", "https://pixabay.com/music/example-123/",
                "--license-proof", "certificate retained", "--platform", "instagram", "--commercial-use-confirmed"]
        self.assertFalse(_parser().parse_args(args).ai_generated_music)
        self.assertTrue(_parser().parse_args([*args, "--ai-generated-music"]).ai_generated_music)

    def test_montage_manifest_reports_ai_music_truthfully_without_changing_footage_policy(self):
        identity, track = uuid4(), uuid4()
        plan = MontageEditPlan(
            schema_version="1.5", recipe="montage", audio_preset="montage_mix_v1",
            end_card="none", editorial_summary="A source-backed montage.", music_track_id=track, music_mix="subtle",
            clips=[dict(asset_id=identity, media_kind="video", source_in=0, source_out=1,
                        duration=1, crop="center_fill", transition="cut") for _ in range(2)],
        )
        context = {"job": {"id": uuid4()}, "assets": [{"asset_id": str(identity)}]}
        for synthetic in (True, False):
            with patch("app.montage_renderer._selected_music", return_value=(None, {"synthetic_media": synthetic})), \
                 patch("app.montage_renderer.selected_effects", return_value=[]):
                manifest = _manifest(context, plan, 1, "test", "test", "test", 540, 960, {}, {}, SimpleNamespace())
            self.assertEqual(manifest["content_policy"]["synthetic_music"], synthetic)
            for kind in ("synthetic_image", "synthetic_video", "synthetic_voice"):
                self.assertFalse(manifest["content_policy"][kind])
