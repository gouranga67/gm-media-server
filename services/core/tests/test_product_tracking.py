import json
import math
from pathlib import Path
import shutil
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException
from app.edit_plan import derive_duration_variant, schema_for_recipe
from app.finishing_tools import FinishingTools, ProductTrack, ProductProfile, validate_finishing, retime_finishing
from app.product_tracking import (track_frames, inspect_clip, first_frame, prepare_product_tracking,
    measure_clip, crop_filter, tracking_manifest)
from app.visual_finishing import source_crop_filter
from app.editing import product_source_frame
import test_stabilization as stabilization_fixture
plan_for = stabilization_fixture.plan_for


def selection(index=0):
    return dict(clip_index=index, x=.5, y=.5, width=.1, height=.15)


def measured_profile(plan, seed=None):
    seed = seed or plan.finishing.product_tracks[0]
    clip = plan.clips[seed.clip_index]
    duration = float(clip.source_out - clip.source_in)
    return ProductProfile(**seed.model_dump(), asset_id=clip.asset_id, source_in=clip.source_in, source_out=clip.source_out,
        status="measured", source_width=640, source_height=360, note="Measured fixture.",
        points=[dict(time=i / 4, x=seed.x+i*.002, y=seed.y, width=seed.width, height=seed.height)
            for i in range(math.floor(duration*4))] + [dict(time=duration-.125,x=seed.x+.02,y=seed.y,width=seed.width,height=seed.height)])


class ProductTrackingTests(unittest.TestCase):
    def test_opt_in_limits_bindings_conflicts_and_legacy_hashes(self):
        for key in ("product_tracks", "product_profiles"):
            self.assertNotIn(key, FinishingTools().model_dump(mode="json"))
            for recipe in ("talking_head", "montage"):
                self.assertNotIn(key, json.dumps(schema_for_recipe(recipe)))
        for seed in (selection() | dict(x=0), selection() | dict(width=.01), selection() | dict(y=float('nan')),
            selection() | dict(clip_index=True)):
            with self.subTest(seed=seed), self.assertRaises(ValueError):
                ProductTrack(**seed)
        for tools in (dict(product_tracks=[selection()]*2), dict(product_tracks=[selection(2)]),
            dict(product_tracks=[selection()], smart_framing="face"),
            dict(product_tracks=[selection()], stabilize_clips=[0]),
            dict(product_tracks=[selection()], motions=[dict(clip_index=0, points=[dict(time=0, zoom=1.1)])])):
            with self.subTest(tools=tools), self.assertRaises(ValueError):
                validate_finishing(plan_for(**tools), [])
        for montage in (False, True):
            plan=plan_for(montage,product_tracks=[selection()]);validate_finishing(plan,[])
            plan.clips[0].source_out=9
            with self.assertRaises(ValueError):validate_finishing(plan,[])
        plan=plan_for(True,product_tracks=[selection()]);plan.clips[0].duration=2
        with self.assertRaises(ValueError):validate_finishing(plan,[])
        plan.clips[0].media_kind="image"
        with self.assertRaises(ValueError):validate_finishing(plan,[])

    def test_saved_paths_are_source_and_seed_bound_and_cleared_on_timeline_changes(self):
        plan=plan_for(count=2,product_tracks=[selection(),selection(1)])
        plan.finishing.product_profiles=[measured_profile(plan,s) for s in plan.finishing.product_tracks]
        validate_finishing(plan,[])
        stale=plan.model_copy(deep=True);stale.finishing.product_tracks[0].x=.6
        with self.assertRaisesRegex(ValueError,"different selection"):validate_finishing(stale,[])
        stale=plan.model_copy(deep=True);stale.finishing.product_profiles[0].asset_id=uuid4()
        with self.assertRaisesRegex(ValueError,"different source range"):validate_finishing(stale,[])
        cleared=retime_finishing(plan.finishing,[[0,6,0]],plan.clips,[(0,0,3),(1,0,3)])
        self.assertEqual(cleared.product_tracks,[]);self.assertEqual(cleared.product_profiles,[])
        variant=derive_duration_variant(plan,4)
        self.assertEqual([s.clip_index for s in variant.finishing.product_tracks],[0])
        validate_finishing(variant,[])
        self.assertEqual(len(plan.finishing.product_tracks),2)

    def test_local_pass_replays_success_or_decline_and_timeout_preserves_cut(self):
        plan=plan_for(product_tracks=[selection()]);context=dict(assets=[dict(asset_id=str(plan.clips[0].asset_id))])
        plain=plan_for()
        with patch('app.product_tracking.measure_clip') as measure:
            self.assertIs(prepare_product_tracking(context,plain),plain)
        measure.assert_not_called()
        with patch('app.product_tracking.measure_clip',return_value=measured_profile(plan)) as measure:
            result=prepare_product_tracking(context,plan,SimpleNamespace())
            replay=prepare_product_tracking(context,result,SimpleNamespace())
            self.assertEqual(measure.call_count,1)
            self.assertEqual(replay.finishing.product_profiles,result.finishing.product_profiles)
        self.assertEqual(result.clips,plan.clips)
        with patch('app.product_tracking.measure_clip',side_effect=subprocess.TimeoutExpired('tracking',1)):
            declined=prepare_product_tracking(context,plan,SimpleNamespace())
        self.assertEqual(declined.finishing.product_profiles[0].status,'unavailable')
        self.assertEqual(crop_filter(declined,0,540,960),'')

    def test_tracker_follows_known_translation_and_declines_occlusion_ambiguity_and_textureless_targets(self):
        import numpy as np
        template=np.random.default_rng(4).integers(30,240,(30,32),dtype=np.uint8)
        frames=[]
        for i in range(16):
            f=np.full((180,320),80,np.uint8);f[75:105,144+i*2:176+i*2]=template;frames.append(f)
        seed=ProductTrack(clip_index=0,x=.5,y=.5,width=.1,height=30/180)
        path=track_frames(frames,seed)
        self.assertAlmostEqual(path[-1]['x'],190/320,places=5)
        lost=[f.copy() for f in frames];lost[8][:]=80
        with self.assertRaisesRegex(ValueError,"unclear"):track_frames(lost,seed)
        ambiguous=np.full((180,320),80,np.uint8)
        ambiguous[75:105,144:160]=template[:,:16];ambiguous[75:105,164:180]=template[:,:16]
        with self.assertRaisesRegex(ValueError,"ambiguous"):
            track_frames([ambiguous],ProductTrack(clip_index=0,x=152/320,y=.5,width=.05,height=30/180))
        with self.assertRaisesRegex(ValueError,"detail"):track_frames([np.full((180,320),80,np.uint8)]*8,seed)
        with self.assertRaisesRegex(ValueError,"small"):track_frames(frames,ProductTrack(**selection()).model_copy(update={'width':.04,'height':.04}))

    def test_crop_uses_source_clock_only_and_declines_unsafe_delivery_aspect(self):
        for montage in (False,True):
            plan=plan_for(montage,product_tracks=[selection()])
            plan.finishing.product_profiles=[measured_profile(plan)]
            graph=stabilization_fixture.StabilizationTests.graph(plan,Path('captions.ass'),180,320)
            plain=stabilization_fixture.StabilizationTests.graph(plan.model_copy(update={'finishing':FinishingTools()}),Path('captions.ass'),180,320)
            self.assertIn("iw*(",graph)
            self.assertEqual([s for s in graph.split(';') if s.startswith(('[0:a','[1:a'))],
                [s for s in plain.split(';') if s.startswith(('[0:a','[1:a'))])
            self.assertEqual(source_crop_filter(plan,0,180,320),crop_filter(plan,0,180,320))
            report=tracking_manifest(plan,180,320)
            self.assertTrue(report['profiles'][0]['framing_applied']);self.assertEqual(report['hosted_model_calls'],0)
            plan.finishing.product_profiles[0].points[0].width=.7
            self.assertEqual(crop_filter(plan,0,180,320),'')

    def test_first_frame_api_rejects_stale_missing_or_ineligible_source_before_decode(self):
        plan=plan_for();row=dict(version=2,document=plan.model_dump(mode='json'))
        from unittest.mock import MagicMock
        db=MagicMock();db.__enter__.return_value.execute.return_value.fetchone.return_value=row
        with patch('app.editing.connection',return_value=db),patch('app.editing._context_or_http',return_value={'assets':[]}),patch('app.product_tracking.first_frame') as decode:
            for version,index,code in ((1,0,409),(2,9,422),(2,0,404)):
                with self.subTest(version=version,index=index),self.assertRaises(HTTPException) as error:
                    product_source_frame(uuid4(),version,index)
                self.assertEqual(error.exception.status_code,code)
        decode.assert_not_called()

    def test_timed_out_child_and_decoder_are_killed_together(self):
        plan=plan_for(product_tracks=[selection()]);seed=plan.finishing.product_tracks[0]
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'source.mp4';source.write_bytes(b'fixture')
            from unittest.mock import MagicMock
            process=MagicMock(pid=123);process.communicate.side_effect=[subprocess.TimeoutExpired('tracker',1),(b'',b'')]
            with patch('app.editor_context.resolve_internal_asset_source',return_value=source),patch('app.product_tracking.subprocess.Popen',return_value=process),patch('app.product_tracking.os.killpg') as kill:
                with self.assertRaises(subprocess.TimeoutExpired):measure_clip({},plan.clips[0],seed,SimpleNamespace(media_root=Path(d)),.1)
            self.assertEqual(process.communicate.call_count,2);kill.assert_called_once()

    def test_source_frame_resolves_only_the_attached_internal_source_and_returns_private_jpeg(self):
        from unittest.mock import MagicMock
        plan=plan_for();plan.clips[0].source_in=1;plan.clips[0].source_out=4
        job=uuid4();db=MagicMock()
        db.__enter__.return_value.execute.return_value.fetchone.return_value=dict(version=2,document=plan.model_dump(mode='json'))
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'source.mp4';source.write_bytes(b'fixture')
            context={'assets':[dict(asset_id=str(plan.clips[0].asset_id),_storage_key='source.mp4')]}
            with patch('app.editing.connection',return_value=db),patch('app.editing._context_or_http',return_value=context) as load,patch('app.editing.get_settings',return_value=SimpleNamespace(media_root=root)),patch('app.product_tracking.first_frame',return_value=b'jpeg') as decode:
                response=product_source_frame(job,2,0)
            load.assert_called_once_with(job,internal=True)
            decode.assert_called_once_with(source,1.,3.)
            self.assertEqual(response.body,b'jpeg');self.assertEqual(response.media_type,'image/jpeg')
            self.assertIn('no-store',response.headers['cache-control'])

    def test_transient_process_failure_is_not_cached_but_deliberate_decline_is_replayed(self):
        from unittest.mock import MagicMock
        plan=plan_for(product_tracks=[selection()]);seed=plan.finishing.product_tracks[0]
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'source.mp4';source.write_bytes(b'fixture')
            process=MagicMock(returncode=1);process.communicate.return_value=(b'',b'private decoder error')
            with patch('app.editor_context.resolve_internal_asset_source',return_value=source),patch('app.product_tracking.subprocess.Popen',return_value=process):
                with self.assertRaisesRegex(ValueError,'temporarily'):measure_clip({},plan.clips[0],seed,SimpleNamespace(media_root=root),1)
                self.assertEqual(list(root.rglob('*.json')),[])
                process.returncode=0;process.communicate.return_value=(json.dumps(dict(status='unavailable',note='Target lost; framing retained.')).encode(),b'')
                decline=measure_clip({},plan.clips[0],seed,SimpleNamespace(media_root=root),1)
                count=process.communicate.call_count
                self.assertEqual(measure_clip({},plan.clips[0],seed,SimpleNamespace(media_root=root),1),decline)
                self.assertEqual(process.communicate.call_count,count)

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg required')
    def test_real_decode_source_frame_cache_and_two_renderers_keep_target_visible_and_audio_identical(self):
        import numpy as np
        from PIL import Image
        from io import BytesIO
        from app.edit_renderer import render_ass
        def run(args,**kwargs):
            result=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30,**kwargs)
            self.assertEqual(result.returncode,0,result.stderr.decode(errors='replace')[-2000:])
            return result.stdout
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);width,height=480,270
            patch_rgb=np.zeros((32,32,3),np.uint8)
            patch_rgb[:,:,0]=np.random.default_rng(2).integers(30,255,(32,32),dtype=np.uint8)
            frames=[]
            for i in range(24):
                frame=np.full((height,width,3),60,np.uint8);frame[119:151,184+4*i:216+4*i]=patch_rgb;frames.append(frame)
            source=root/'product.mkv'
            run(['ffmpeg','-v','error','-nostdin','-f','rawvideo','-pix_fmt','rgb24','-s',f'{width}x{height}','-r','8','-i','pipe:0',
                '-f','lavfi','-i','sine=frequency=650:sample_rate=48000:duration=3','-t','3','-c:v','ffv1','-c:a','pcm_s16le',str(source)],input=b''.join(f.tobytes() for f in frames))
            seed=ProductTrack(clip_index=0,x=200/width,y=.5,width=32/width,height=32/height)
            measured=inspect_clip(source,0,3,seed)
            self.assertEqual(measured['status'],'measured');self.assertAlmostEqual(measured['points'][-1]['x'],292/480,places=4)
            for duration in (1.01, 2.04, 2.91):
                short=inspect_clip(source,0,duration,seed)
                ProductProfile(**seed.model_dump(),asset_id=uuid4(),source_in=0,source_out=duration,**short)
            offset_seed=seed.model_copy(update={'x':232/480})
            offset=inspect_clip(source,1,1.91,offset_seed)
            self.assertAlmostEqual(offset['points'][0]['x'],232/480,places=4)
            image=Image.open(BytesIO(first_frame(source,0,3)))
            self.assertEqual(image.size,(480,270))
            settings=SimpleNamespace(media_root=root)
            for montage in (False,True):
                plan=plan_for(montage,product_tracks=[seed.model_dump()])
                with patch('app.editor_context.resolve_internal_asset_source',return_value=source):
                    p=measure_clip({},plan.clips[0],seed,settings,6)
                    with patch('app.product_tracking.subprocess.Popen') as spawn:
                        self.assertEqual(measure_clip({},plan.clips[0],seed,settings,6),p)
                    spawn.assert_not_called()
                plan.finishing.product_profiles=[p]
                ass=root/'captions.ass';ass.write_text(render_ass([]))
                graph=stabilization_fixture.StabilizationTests.graph(plan,ass,180,320)
                baseline=stabilization_fixture.StabilizationTests.graph(plan.model_copy(update={'finishing':FinishingTools()}),ass,180,320)
                outputs=[]
                for n,g in enumerate((graph,baseline)):
                    dest=root/f'{montage}-{n}.mkv';args=['ffmpeg','-v','error','-nostdin','-threads','1','-i',str(source)]
                    if montage:args+=['-threads','1','-i',str(source)]
                    run(args+['-filter_complex_threads','1','-filter_complex',g,'-map','[vout]','-map','[aout]',
                        '-c:v','ffv1','-c:a','pcm_s16le',str(dest)])
                    outputs.append(dest)
                pcm=lambda path:run(['ffmpeg','-v','error','-i',str(path),'-map','0:a:0','-f','s16le','pipe:1'])
                self.assertEqual(pcm(outputs[0]),pcm(outputs[1]))
                # Inspect the tracked first shot, not montage's unmarked second shot.
                raw=run(['ffmpeg','-v','error','-i',str(outputs[0]),'-t','3','-f','rawvideo','-pix_fmt','rgb24','pipe:1'])
                pictures=np.frombuffer(raw,np.uint8).reshape(-1,320,180,3)
                self.assertEqual(len(pictures),90)
                for picture in pictures[::5]:
                    ys,xs=np.where((picture[:,:,0]>105)&(picture[:,:,1]<40)&(picture[:,:,2]<40))
                    self.assertGreater(len(xs),300)
                    self.assertLess(abs(float(xs.mean())-90),8)
            # Largest saved path must remain an executable FFmpeg expression.
            longest=plan_for(product_tracks=[selection()]);longest.clips[0].source_out=8
            longest.finishing.product_profiles=[measured_profile(longest)]
            self.assertEqual(len(longest.finishing.product_profiles[0].points),33)
            graph=stabilization_fixture.StabilizationTests.graph(longest,ass,180,320)
            run(['ffmpeg','-v','error','-nostdin','-i',str(source),'-filter_complex_threads','1',
                '-filter_complex',graph,'-map','[vout]','-map','[aout]','-t','0.04','-f','null','-'])
