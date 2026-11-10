import array
from copy import deepcopy
import math
from pathlib import Path
import shutil
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch
from uuid import uuid4

from fastapi import HTTPException
from pydantic import ValidationError
from psycopg.errors import UniqueViolation
from starlette.requests import Request

from app import creative_assets
from app.creative_selection import shortlist, bound_generated_treatments
from app.creative_treatments import Callout, Pointer, MusicRegion
from app.edit_plan import (
    TalkingHeadEditPlan,
    MontageEditPlan,
    schema_for_recipe,
    validate_edit_plan,
    apply_timeline_adjustments,
)
from app.edit_renderer import render_ass, _render_video
from app.finishing_tools import (
    FinishingTools,
    validate_finishing,
    apply_graph_finishing,
)
from app.montage_renderer import _render
from app.media_analysis import run_command, probe_media
from app.schemas import CreativeDescription


def plan(tools=None):
    return TalkingHeadEditPlan(
        schema_version="1.5",
        recipe="talking_head",
        clips=[dict(asset_id=uuid4(), source_in=0, source_out=3, crop="center_fill")],
        caption_style="clean_blue_v1",
        audio_preset="spoken_voice_v1",
        end_card="none",
        editorial_summary="The recorded story.",
        finishing=tools,
    )


class CreativeToolkitTests(unittest.TestCase):
    def test_treatments_reject_commands_nonfinite_and_unbounded_times(self):
        for text in (" ", r"{\pos(1,2)}override", "line\nbreak"):
            with self.assertRaises(ValidationError):
                Callout(start=0, end=1, text=text)
        for data in (
            dict(start=1, end=1, text="hello"),
            dict(start=0, end=9, text="hello"),
            dict(start=float("nan"), end=1, text="hello"),
        ):
            with self.assertRaises(ValidationError):
                Callout(**data)
        with self.assertRaises(ValidationError):
            Pointer(start=0, end=1, x=1)
        with self.assertRaises(ValidationError):
            MusicRegion(start=0, end=1, gain_db=12)

    def test_legacy_finishing_hash_inputs_do_not_gain_new_empty_arrays(self):
        data = FinishingTools().model_dump(mode="json")
        for key in ("callouts", "pointers", "music_regions"):
            self.assertNotIn(key, data)

    def test_real_tool_windows_and_selected_music_are_required(self):
        p = plan(FinishingTools(callouts=[dict(start=2, end=4, text="Late")]))
        with self.assertRaisesRegex(ValueError, "beyond"):
            validate_finishing(p, [])
        p = plan(FinishingTools(music_regions=[dict(start=1, end=2)]))
        with self.assertRaisesRegex(ValueError, "selected music"):
            validate_finishing(p, [])
        p = plan(FinishingTools(pointers=[dict(start=0, end=2), dict(start=1, end=3)]))
        with self.assertRaisesRegex(ValueError, "overlap"):
            validate_finishing(p, [])

    def test_callouts_and_pointers_share_caption_pass_below_dialogue(self):
        tools = FinishingTools(
            callouts=[dict(start=0.5, end=1.5, text="Real words", position="upper")],
            pointers=[
                dict(start=1, end=2, shape="circle"),
                dict(start=2, end=3, shape="arrow", direction="left"),
            ],
        )
        text = render_ass(
            [dict(start=0, end=2, text="Actual speech")],
            width=540,
            height=960,
            position="upper",
            treatments=tools,
        )
        self.assertIn("Dialogue: 0,", text)
        self.assertEqual(text.count("Dialogue: -1,"), 3)
        self.assertIn("\\pos(270,381)", text)  # Card text moves to the middle, clear of upper captions.
        self.assertIn("Dialogue: -3,", text)  # Backing panel below text.
        self.assertIn("\\frz180", text)
        self.assertIn("\\p1", text)

    def test_music_pause_changes_music_branch_only(self):
        p = plan(FinishingTools(music_regions=[dict(start=1, end=2)]))
        graph = "[voice]anull[acat];[track]anull[music];[acat][music]amix=inputs=2[aout];[base]null[vout]"
        result = apply_graph_finishing(graph, p, width=96, height=128, fps=30)
        self.assertIn("[voice]anull[acat]", result)
        self.assertIn("[track]anull,asetnsamples=n=480:p=0,volume=", result)
        self.assertIn("eval=frame[music]", result)
        self.assertNotIn("atempo", result)

    def test_reordering_retimes_treatments_with_their_content(self):
        p = plan(
            FinishingTools(
                callouts=[dict(start=0.5, end=1, text="Opening")],
                pointers=[dict(start=2, end=2.5)],
                music_regions=[dict(start=2.5, end=3)],
            )
        )
        p.clips.append(p.clips[0].model_copy(update=dict(source_in=3, source_out=6)))
        changed = apply_timeline_adjustments(p, [dict(clip_index=1, action="move_up")])
        self.assertEqual(changed.finishing.callouts[0].start, 3.5)
        self.assertEqual(changed.finishing.pointers[0].start, 5)
        self.assertEqual(changed.finishing.music_regions[0].start, 5.5)
        self.assertEqual(p.finishing.callouts[0].start, 0.5)

    def test_planner_receives_small_strict_tool_schema_in_both_engines(self):
        for recipe in ("talking_head", "montage"):
            schema = schema_for_recipe(recipe)
            self.assertIn("finishing", schema["required"])
            finishing = schema["properties"]["finishing"]["anyOf"][1]
            self.assertEqual(
                set(finishing["properties"]), {"callouts", "pointers", "music_regions", "visual_beats", "motions", "caption_regions"}
            )
            for prop in finishing["properties"].values():
                self.assertEqual(
                    set(prop["items"]["required"]), set(prop["items"]["properties"])
                )

    def test_audio_visual_pair_allowed_but_two_sounds_and_third_cue_are_not(self):
        p = plan()
        sound, visual, extra = str(uuid4()), str(uuid4()), str(uuid4())
        inventory = [
            dict(asset_id=identity, kind=kind, purpose="reveal")
            for identity, kind in [
                (sound, "sound_effect"),
                (visual, "sticker"),
                (extra, "sound_effect"),
            ]
        ]
        doc = p.model_dump(mode="json")
        doc["effects"] = [
            dict(asset_id=i, start_seconds=1, duration_seconds=0.5, purpose="reveal")
            for i in (sound, visual)
        ]
        args = dict(
            assets=[
                dict(
                    asset_id=str(p.clips[0].asset_id),
                    duration_seconds=3,
                    has_video=True,
                    has_audio=True,
                )
            ],
            creative_direction=dict(effect_level="social"),
            creative_effects=inventory,
        )
        self.assertEqual(len(validate_edit_plan(doc, **args).effects), 2)
        for ids in ((sound, extra), (sound, visual, extra)):
            doc["effects"] = [
                dict(
                    asset_id=i, start_seconds=1, duration_seconds=0.5, purpose="reveal"
                )
                for i in ids
            ]
            with self.assertRaisesRegex(ValueError, "apart"):
                validate_edit_plan(doc, **args)

    def test_bounded_shortlist_preserves_rights_inventory_and_purpose_diversity(self):
        items = [
            dict(
                asset_id=str(i),
                kind="sound_effect" if i % 2 else "sticker",
                title=f"Asset {i}",
                purpose=["hook", "reveal", "reaction"][i % 3],
                tags=["soap" if i == 39 else "click"],
                license_source_url="https://example.org/licence",
            )
            for i in range(40)
        ]
        context = dict(
            project=dict(brief="A soap reveal"),
            job=dict(effect_level="social"),
            assets=[],
            creative_effect_library=items,
        )
        before = deepcopy(context)
        selected = shortlist(context)
        self.assertEqual(len(selected), 18)
        self.assertIn("39", [item["asset_id"] for item in selected])
        self.assertEqual(
            {item["purpose"] for item in selected}, {"hook", "reveal", "reaction"}
        )
        self.assertEqual(context, before)
        context["job"]["effect_level"] = "off"
        self.assertEqual(shortlist(context), [])

    def test_serious_brief_does_not_retrieve_comic_assets(self):
        context = dict(
            project=dict(brief="Serious and respectful. No jokes."),
            job=dict(effect_level="social"),
            creative_effect_library=[
                dict(asset_id="a", kind="meme_sound", title="Joke", purpose="reaction"),
                dict(
                    asset_id="b",
                    kind="sound_effect",
                    title="Soft click",
                    purpose="emphasis",
                ),
            ],
        )
        self.assertEqual([i["asset_id"] for i in shortlist(context)], ["b"])

    def test_generated_treatments_share_effect_budget_without_recutting(self):
        p = plan(
            FinishingTools(
                callouts=[
                    dict(start=n * 0.3, end=n * 0.3 + 0.2, text="Real")
                    for n in range(4)
                ]
            )
        )
        context = dict(job=dict(effect_level="subtle"))
        bounded = bound_generated_treatments(context, p)
        self.assertEqual(len(bounded.finishing.callouts), 2)
        self.assertEqual(bounded.clips, p.clips)
        self.assertEqual(len(p.finishing.callouts), 4)
        self.assertEqual(context["creative_treatment_review"]["removed"], 2)


class CreativeImportTests(unittest.IsolatedAsyncioTestCase):
    async def test_streamed_import_records_guidance_without_buffering_request_body(
        self,
    ):
        with tempfile.TemporaryDirectory() as directory:
            seen = []

            async def receive():
                return {
                    "type": "http.request",
                    "body": b"fixture audio",
                    "more_body": False,
                }

            request = Request(
                dict(
                    type="http",
                    method="POST",
                    headers=[(b"content-type", b"audio/ogg")],
                ),
                receive,
            )
            database = MagicMock()
            database.execute.return_value.fetchone.return_value = dict(id=str(uuid4()))
            settings = SimpleNamespace(
                media_root=Path(directory), analysis_command_timeout_seconds=5
            )
            with patch.multiple(
                creative_assets,
                get_settings=lambda: settings,
                ensure_capacity=lambda _: None,
                require_owner=lambda _: None,
                actor_login=lambda _: "owner",
                probe_media=lambda path, timeout: dict(
                    streams=[dict(type="audio")], format=dict(duration_seconds=0.5)
                ),
                connection=MagicMock(return_value=database),
            ):
                database.__enter__.return_value = database
                result = await creative_assets.import_creative_asset(
                    request,
                    kind="sound_effect",
                    filename="ding.ogg",
                    title="Ding",
                    creator="Creator",
                    tags="ding, reveal",
                    purpose="reveal",
                    mood="bright",
                    energy="low",
                    use_when="A real reveal",
                    avoid_when="Important speech",
                    license_name="CC0-1.0",
                    license_source_url="https://example.org/source",
                    license_proof="licence",
                    attribution="",
                    allowed_platforms="all_social",
                    commercial_use_confirmed=True,
                    x_gm_user_login="owner",
                )
            sql, values = database.execute.call_args.args
            self.assertEqual(sql.count("%s"), len(values))
            self.assertIn("A real reveal", values)
            self.assertIn("Important speech", values)
            self.assertEqual(len(list(Path(directory).rglob("ding.ogg"))), 1)
            self.assertEqual(result["kind"], "sound_effect")

    async def test_oversized_stream_stops_and_cleans_partial_file(self):
        with tempfile.TemporaryDirectory() as directory:
            chunks = iter([b"abc", b"def", b"never"])
            seen = []

            async def receive():
                value = next(chunks)
                seen.append(value)
                return dict(type="http.request", body=value, more_body=True)

            request = Request(dict(type="http", method="POST", headers=[]), receive)
            settings = SimpleNamespace(
                media_root=Path(directory), analysis_command_timeout_seconds=5
            )
            with patch.multiple(
                creative_assets,
                get_settings=lambda: settings,
                ensure_capacity=lambda _: None,
                require_owner=lambda _: None,
                actor_login=lambda _: "owner",
                MAX_UPLOAD_BYTES=5,
            ):
                with self.assertRaises(HTTPException) as caught:
                    await creative_assets.import_creative_asset(
                        request,
                        kind="sound_effect",
                        filename="ding.ogg",
                        title="Ding",
                        creator="",
                        tags="",
                        purpose="reveal",
                        mood="bright",
                        energy="low",
                        use_when="",
                        avoid_when="",
                        license_name="CC0-1.0",
                        license_source_url="https://example.org/source",
                        license_proof="",
                        attribution="",
                        allowed_platforms="all_social",
                        commercial_use_confirmed=True,
                        x_gm_user_login="owner",
                    )
            self.assertEqual(caught.exception.status_code, 413)
            self.assertEqual(seen, [b"abc", b"def"])
            self.assertFalse([p for p in Path(directory).rglob("*") if p.is_file()])

    def test_description_requires_nonblank_title(self):
        with self.assertRaises(ValidationError):
            CreativeDescription(title="  ")


@unittest.skipUnless(
    shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg required"
)
class CreativeRenderTests(unittest.TestCase):
    def test_preview_and_export_treatments_are_visible_and_music_mutes_without_losing_voice(
        self,
    ):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.mkv"
            music = root / "music.wav"
            run_command(
                [
                    "ffmpeg",
                    "-v",
                    "error",
                    "-y",
                    "-f",
                    "lavfi",
                    "-i",
                    "color=blue:s=128x192:r=60:d=3",
                    "-f",
                    "lavfi",
                    "-i",
                    "sine=frequency=1000:sample_rate=48000:duration=3",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "ultrafast",
                    "-c:a",
                    "pcm_s16le",
                    str(source),
                ],
                timeout=15,
            )
            run_command(
                [
                    "ffmpeg",
                    "-v",
                    "error",
                    "-y",
                    "-f",
                    "lavfi",
                    "-i",
                    "sine=frequency=400:sample_rate=48000:duration=3",
                    str(music),
                ],
                timeout=15,
            )
            for recipe in ("talking_head", "montage"):
                for final in (False, True):
                    with self.subTest(recipe=recipe, final=final):
                        p = plan(
                            FinishingTools(
                                callouts=[dict(start=0.7, end=2.3, text="Real words")],
                                pointers=[dict(start=0.7, end=2.3, x=0.7, y=0.4)],
                                music_regions=[dict(start=0.8, end=1.8)],
                            )
                        )
                        p.music_track_id = uuid4()
                        p.music_mix = "present"
                        if recipe == "montage":
                            p = MontageEditPlan(
                                schema_version="1.5",
                                recipe="montage",
                                clips=[
                                    dict(
                                        asset_id=p.clips[0].asset_id,
                                        source_in=n * 1.5,
                                        source_out=(n + 1) * 1.5,
                                        duration=1.5,
                                        media_kind="video",
                                        include_source_audio=True,
                                        crop="center_fill",
                                    )
                                    for n in (0, 1)
                                ],
                                audio_preset="montage_mix_v1",
                                end_card="none",
                                editorial_summary="The same speech.",
                                finishing=p.finishing,
                                music_track_id=p.music_track_id,
                                music_mix=p.music_mix,
                            )
                        ass = root / "treatments.ass"
                        ass.write_text(
                            render_ass(
                                [], width=128, height=192, treatments=p.finishing
                            )
                        )
                        output = root / f"{recipe}-{final}.mp4"
                        before = p.model_dump(mode="json")
                        if recipe == "talking_head":
                            _render_video(
                                [(source, 0, 3)],
                                p,
                                ass,
                                output,
                                30,
                                width=128,
                                height=192,
                                final_quality=final,
                                music_source=music,
                            )
                        else:
                            context = dict(
                                job=dict(music_mode="present"),
                                assets=[
                                    dict(
                                        asset_id=str(p.clips[0].asset_id),
                                        has_audio=True,
                                        has_video=True,
                                    )
                                ],
                                music_library=[],
                                creative_effect_library=[],
                            )
                            with (
                                patch(
                                    "app.montage_renderer._render_source",
                                    return_value=source,
                                ),
                                patch(
                                    "app.montage_renderer._selected_music",
                                    return_value=(music, None),
                                ),
                            ):
                                _render(
                                    context,
                                    p,
                                    output,
                                    width=128,
                                    height=192,
                                    final=final,
                                    settings=SimpleNamespace(
                                        analysis_command_timeout_seconds=30
                                    ),
                                    captions_path=ass,
                                )
                        self.assertEqual(p.model_dump(mode="json"), before)
                        self.assertAlmostEqual(
                            probe_media(output, 10)["format"]["duration_seconds"],
                            3,
                            delta=0.1,
                        )
                        raw = subprocess.check_output(
                            [
                                "ffmpeg",
                                "-v",
                                "error",
                                "-i",
                                str(output),
                                "-an",
                                "-f",
                                "rawvideo",
                                "-pix_fmt",
                                "rgb24",
                                "-",
                            ],
                            timeout=15,
                        )

                        def changed(at):
                            frame = raw[
                                round(at * 30) * 128 * 192 * 3 : round(at * 30 + 1)
                                * 128
                                * 192
                                * 3
                            ]
                            return sum(
                                frame[i] > 70 and frame[i + 1] > 70
                                for i in range(0, len(frame), 3)
                            )

                        self.assertGreater(changed(1.1), 100)
                        self.assertLess(changed(0.2), 20)
                        self.assertLess(changed(2.7), 20)
                        samples = array.array(
                            "h",
                            subprocess.check_output(
                                [
                                    "ffmpeg",
                                    "-v",
                                    "error",
                                    "-i",
                                    str(output),
                                    "-vn",
                                    "-ac",
                                    "1",
                                    "-ar",
                                    "48000",
                                    "-f",
                                    "s16le",
                                    "-",
                                ],
                                timeout=15,
                            ),
                        )

                        def amplitude(frequency, at):
                            values = samples[
                                round(at * 48000) : round((at + 0.15) * 48000)
                            ]
                            real = sum(
                                value * math.cos(2 * math.pi * frequency * n / 48000)
                                for n, value in enumerate(values)
                            )
                            imaginary = sum(
                                value * math.sin(2 * math.pi * frequency * n / 48000)
                                for n, value in enumerate(values)
                            )
                            return math.hypot(real, imaginary) / len(values)

                        before_music, muted, returned = [
                            amplitude(400, at) for at in (0.3, 1.2, 2.1)
                        ]
                        self.assertLess(muted, min(before_music, returned) * 0.12)
                        self.assertGreater(
                            amplitude(1000, 1.2), amplitude(1000, 0.3) * 0.5
                        )
