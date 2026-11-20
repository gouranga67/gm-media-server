import hashlib
import asyncio
from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

from fastapi import HTTPException
from app import cutout_lab as lab
from app.cutout_lab_routes import CutoutComparisonRequest, create_cutout_preview, get_cutout_artifact


def sample(**changes):
    values = dict(job_id=uuid4(), asset_id=uuid4(), edit_version=2, plan_sha256='a'*64, clip_index=0, start=1, end=3)
    return lab.Sample(**(values | changes))


def metrics(**changes):
    return dict(sampled_frames=16, sample_fps=8, backend='opencv_cpu', threads=1, processing_seconds=.1) | changes


class CutoutLabTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory();self.addCleanup(directory.cleanup)
        self.root = Path(directory.name);self.source = self.root/'source.mkv';self.source.write_bytes(b'immutable source')
        self.settings = SimpleNamespace(media_root=self.root, cutout_model_path=self.root/'model.onnx',
            media_min_free_bytes=1, media_min_free_percent=.001)
        self.sample = sample()

    def fake_runner(self, payload, timeout):
        request = json.loads(payload);out = Path(request['output'])
        for name in lab.ARTIFACT_TYPES:(out/name).write_bytes(b'bounded synthetic artifact '+name.encode())
        return json.dumps(metrics()).encode(), b''

    def create_fixture(self):
        process=MagicMock(returncode=0);process.communicate.side_effect=self.fake_runner
        with patch('app.cutout_lab.checked_model',return_value=self.root/'model.onnx'),patch('app.cutout_lab.subprocess.Popen',return_value=process):
            result=lab.create_comparison(self.source,self.sample,self.settings)
        return result

    def test_sample_and_selection_are_bounded_to_ready_normal_speed_saved_source_ranges(self):
        for changes in (dict(start=float('nan')),dict(end=float('inf')),dict(end=4.01),dict(end=1.1),dict(clip_index=True)):
            with self.subTest(changes=changes),self.assertRaises(ValueError):sample(**changes)
        from test_stabilization import plan_for
        document=plan_for().model_dump(mode='json');row=dict(version=2,status='ready',document=document)
        selected=lab.select_sample(uuid4(),row,1,.5,1)
        self.assertEqual((selected.clip_index,selected.start,selected.end),(0,.5,1.5))
        self.assertEqual(lab.select_sample(uuid4(),row,1,2.4).end,3)
        for number,offset,seconds in ((True,0,1),(0,0,1),(2,0,1),(1,-1,1),(1,0,4),(1,2,2),(1,float('nan'),1)):
            with self.subTest(number=number,offset=offset,seconds=seconds),self.assertRaises(ValueError):
                lab.select_sample(uuid4(),row,number,offset,seconds)
        with self.assertRaisesRegex(ValueError,'latest'):lab.select_sample(uuid4(),row|dict(status='pending'),1)
        document['clips'][0].update(media_kind='image')
        with self.assertRaisesRegex(ValueError,'normal-speed'):lab.select_sample(uuid4(),row,1)
        document['clips'][0].update(media_kind='video',duration=2)
        with self.assertRaisesRegex(ValueError,'normal-speed'):lab.select_sample(uuid4(),row,1)

    def test_model_and_packaged_license_are_pinned_and_missing_weights_never_download_at_runtime(self):
        with self.assertRaisesRegex(ValueError,'pinned'):lab.checked_model(self.root/'missing.onnx')
        model=self.root/'wrong.onnx';model.write_bytes(b'wrong weights')
        with self.assertRaisesRegex(ValueError,'pinned'):lab.open_model(model)
        fetch=runpy.run_path(str(Path(__file__).resolve().parents[1]/'model-assets/fetch-cutout-model.py'))
        self.assertEqual(fetch['SHA256'],lab.MODEL_SHA256);self.assertEqual(fetch['SIZE'],lab.MODEL_SIZE)
        license_path=Path(__file__).resolve().parents[1]/'model-assets/PPHumanSeg-LICENSE'
        self.assertEqual(hashlib.sha256(license_path.read_bytes()).hexdigest(),fetch['LICENSE_SHA256'])
        self.assertIn('Apache License',license_path.read_text())
        response=MagicMock();response.__enter__.return_value.read.return_value=b'not the pinned model'
        with patch('urllib.request.urlopen',return_value=response):
            with self.assertRaisesRegex(ValueError,'pinned weights'):fetch['install'](self.root/'fetched-model')
        self.assertFalse((self.root/'fetched-model'/lab.MODEL_FILE).exists())

    def test_rgb_normalization_cpu_probability_contract_and_composition_alpha(self):
        import numpy as np
        frame=np.zeros((20,30,3),np.uint8);frame[:]=[0,127,255]
        model=MagicMock();scores=np.zeros((1,2,192,192),np.float32);scores[:,0]=1
        scores[:,:, :,96:]=0;scores[:,1,:,96:]=1;model.forward.return_value=scores
        alpha=lab.segment(model,frame)
        blob=model.setInput.call_args.args[0]
        self.assertAlmostEqual(float(blob[0,0,0,0]),1,places=4)
        self.assertAlmostEqual(float(blob[0,2,0,0]),-1,places=4)
        self.assertEqual(alpha.shape,(20,30));self.assertEqual(alpha.dtype,np.uint8)
        self.assertEqual(int(alpha[5,2]),0);self.assertEqual(int(alpha[5,-2]),255)
        panel=lab.comparison_panel(frame,np.zeros((20,30),np.uint8),2)
        self.assertEqual(panel.shape,(48,90,3));np.testing.assert_array_equal(panel[28:,:30],frame)
        self.assertFalse(np.array_equal(panel[28:,30:60],frame))
        model.forward.return_value=np.full((1,2,192,192),float('nan'),np.float32)
        with self.assertRaisesRegex(ValueError,'probabilities'):lab.segment(model,frame)

    def test_comparisons_are_private_source_bound_hashed_and_cached_without_applying_to_an_edit(self):
        before=self.source.read_bytes();result=self.create_fixture()
        self.assertFalse(result['eligible_for_edit_application']);self.assertFalse(result['quality_approved'])
        self.assertEqual(result['hosted_model_calls'],0);self.assertEqual(result['edit_versions_created'],0)
        self.assertEqual(result['original_files_changed'],0);self.assertEqual(self.source.read_bytes(),before)
        with patch('app.cutout_lab.checked_model',return_value=self.root/'model.onnx'),patch('app.cutout_lab.subprocess.Popen') as spawn:
            self.assertEqual(lab.create_comparison(self.source,self.sample,self.settings),result)
        spawn.assert_not_called()
        path,mime=lab.artifact_path(self.root,self.sample.job_id,result['cache_key'],'comparison.mp4')
        self.assertEqual(mime,'video/mp4');self.assertEqual(path.name,'comparison.mp4')
        path.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'changed'):lab.artifact_path(self.root,self.sample.job_id,result['cache_key'],'comparison.mp4')

    def test_chosen_background_is_bound_to_the_non_destructive_comparison(self):
        background=self.root/'background.jpg';background.write_bytes(b'background bytes')
        background_id=uuid4();process=MagicMock(returncode=0);process.communicate.side_effect=self.fake_runner
        with patch('app.cutout_lab.checked_model',return_value=self.root/'model.onnx'),patch('app.cutout_lab.subprocess.Popen',return_value=process):
            result=lab.create_comparison(self.source,self.sample,self.settings,
                background_source=background,background_asset_id=background_id)
        request=json.loads(process.communicate.call_args.args[0])
        self.assertEqual(request['background'],str(background))
        self.assertEqual(result['background_asset_id'],str(background_id))
        self.assertEqual(result['comparison_kind'],'chosen_background')
        self.assertFalse(result['eligible_for_edit_application'])

    def test_preview_uses_normalized_inputs_single_thread_and_a_killable_process_group(self):
        process=MagicMock(returncode=0);process.communicate.side_effect=self.fake_runner
        with patch('app.cutout_lab.checked_model',return_value=self.root/'model.onnx'),patch('app.cutout_lab.subprocess.Popen',return_value=process) as spawn:
            lab.create_comparison(self.source,self.sample,self.settings)
        self.assertEqual(process.communicate.call_args.kwargs['timeout'],20)
        self.assertTrue(spawn.call_args.kwargs['start_new_session'])
        self.assertEqual(spawn.call_args.kwargs['env']['CUDA_VISIBLE_DEVICES'],'-1')
        self.assertEqual(spawn.call_args.kwargs['env']['OMP_NUM_THREADS'],'1')

    def test_timeout_kills_decoder_group_cleans_partial_results_and_preserves_source(self):
        process=MagicMock(pid=321);process.communicate.side_effect=[subprocess.TimeoutExpired('lab',20),(b'',b'')]
        with patch('app.cutout_lab.checked_model',return_value=self.root/'model.onnx'),patch('app.cutout_lab.subprocess.Popen',return_value=process),patch('app.cutout_lab.os.killpg') as kill:
            with self.assertRaisesRegex(ValueError,'20-second'):lab.create_comparison(self.source,self.sample,self.settings)
        kill.assert_called_once();self.assertEqual(process.communicate.call_count,2)
        self.assertEqual(list(self.root.rglob('.work-*')),[]);self.assertEqual(list(self.root.rglob('report.json')),[])
        self.assertEqual(self.source.read_bytes(),b'immutable source')

    def test_nonfinite_wrong_backend_or_out_of_budget_metrics_are_not_published(self):
        for value in (metrics(processing_seconds=float('nan')),metrics(backend='cuda'),metrics(sampled_frames=999),metrics(processing_seconds=21)):
            with self.subTest(value=value),self.assertRaises(ValueError):lab.validate_measurements(value,self.sample)
        process=MagicMock(returncode=0);process.communicate.return_value=(json.dumps(metrics()).encode(),b'')
        with patch('app.cutout_lab.checked_model',return_value=self.root/'model.onnx'),patch('app.cutout_lab.subprocess.Popen',return_value=process):
            with self.assertRaisesRegex(ValueError,'incomplete'):lab.create_comparison(self.source,self.sample,self.settings)
        self.assertEqual(list(self.root.rglob('report.json')),[])

    def test_lock_is_nonblocking_and_cache_paths_refuse_escape_or_another_job(self):
        with lab.lab_slot(lab.lab_root(self.root)):
            with self.assertRaisesRegex(ValueError,'another cutout'):
                with lab.lab_slot(lab.lab_root(self.root)):pass
        with tempfile.TemporaryDirectory() as outside:
            job_dir=lab.lab_root(self.root)/str(self.sample.job_id);job_dir.symlink_to(outside,target_is_directory=True)
            with patch('app.cutout_lab.checked_model',return_value=self.root/'model.onnx'):
                with self.assertRaisesRegex(ValueError,'outside'):lab.create_comparison(self.source,self.sample,self.settings)
            job_dir.unlink()
        result=self.create_fixture()
        for job,key in ((uuid4(),result['cache_key']),(self.sample.job_id,'../outside')):
            with self.subTest(job=job,key=key),self.assertRaises((OSError,ValueError)):
                lab.read_report(self.root,job,key)

    def test_read_only_route_rejects_missing_jobs_and_returns_only_verified_private_artifacts(self):
        result=self.create_fixture();db=MagicMock();db.__enter__.return_value.execute.return_value.fetchone.return_value=dict(id=self.sample.job_id)
        with patch('app.cutout_lab_routes.connection',return_value=db),patch('app.cutout_lab_routes.get_settings',return_value=self.settings):
            response=get_cutout_artifact(self.sample.job_id,result['cache_key'],'contact.png')
            self.assertEqual(response.media_type,'image/png');self.assertIn('no-store',response.headers['cache-control'])
            self.assertEqual(response.headers['x-content-type-options'],'nosniff')
            with self.assertRaises(HTTPException):get_cutout_artifact(self.sample.job_id,result['cache_key'],'../source.mkv')
            db.__enter__.return_value.execute.return_value.fetchone.return_value=None
            with self.assertRaises(HTTPException) as error:get_cutout_artifact(self.sample.job_id,result['cache_key'],'contact.png')
            self.assertEqual(error.exception.status_code,404)

    def test_create_route_uses_saved_presenter_and_background_without_applying_edit(self):
        from test_stabilization import plan_for
        document=plan_for().model_dump(mode='json');foreground_id=UUID(document['clips'][0]['asset_id']);background_id=uuid4()
        job=dict(id=self.sample.job_id,composition=dict(mode='person_cutout',foreground_asset_id=str(foreground_id),
            background_asset_id=str(background_id)))
        row=dict(version=3,status='ready',document=document)
        database=MagicMock();database.__enter__.return_value.execute.return_value.fetchone.side_effect=[job,row]
        context=dict(assets=[dict(asset_id=str(foreground_id),_storage_key='foreground.mp4'),
            dict(asset_id=str(background_id),_storage_key='background.jpg')])
        expected=dict(cache_key='b'*64,eligible_for_edit_application=False)
        with patch('app.cutout_lab_routes.connection',return_value=database),\
             patch('app.cutout_lab_routes.build_editor_context',return_value=context),\
             patch('app.cutout_lab_routes.resolve_internal_asset_source',side_effect=[self.source,self.root/'background.jpg']),\
             patch('app.cutout_lab_routes.get_settings',return_value=self.settings),\
             patch('app.cutout_lab_routes.create_comparison',return_value=expected) as create:
            self.assertEqual(create_cutout_preview(self.sample.job_id,CutoutComparisonRequest(edit_version=3)),expected)
        self.assertEqual(create.call_args.kwargs['background_asset_id'],background_id)

    def test_wrapper_passes_bounded_arguments_without_a_shell_and_never_posts_or_revises(self):
        script=Path(__file__).resolve().parents[3]/'scripts/preview-cutout.py'
        wrapper=runpy.run_path(str(script))
        args=SimpleNamespace(job=self.sample.job_id,clip=1,offset=.5,seconds=2)
        command=wrapper['command'](args)
        self.assertEqual(command[:5],['docker','compose','exec','-T','worker'])
        self.assertIn('app.cutout_lab',command);self.assertNotIn('sh',command)
        for changes in (dict(clip=0),dict(offset=float('nan')),dict(seconds=4)):
            with self.subTest(changes=changes),self.assertRaises(ValueError):wrapper['command'](SimpleNamespace(**(vars(args)|changes)))

    def test_actual_asgi_route_serves_verified_byte_ranges_and_rejects_unknown_filenames(self):
        from fastapi import FastAPI
        from app.cutout_lab_routes import router
        report=self.create_fixture();db=MagicMock()
        db.__enter__.return_value.execute.return_value.fetchone.return_value=dict(id=self.sample.job_id)
        app=FastAPI();app.include_router(router)
        async def exchange(filename,headers=()):
            path=f'/api/v1/jobs/{self.sample.job_id}/cutout-lab/{report["cache_key"]}/{filename}'
            scope=dict(type='http',asgi=dict(version='3.0',spec_version='2.3'),http_version='1.1',method='GET',
                scheme='http',path=path,raw_path=path.encode(),query_string=b'',root_path='',headers=list(headers),
                server=('test',80),client=('test',1234))
            messages=[]
            async def receive():
                await asyncio.Event().wait()  # Response cancels the disconnect listener.
                return dict(type='http.disconnect')
            async def send(message):messages.append(message)
            await asyncio.wait_for(app(scope,receive,send),timeout=3)
            return messages
        with patch('app.cutout_lab_routes.connection',return_value=db),patch('app.cutout_lab_routes.get_settings',return_value=self.settings):
            messages=asyncio.run(exchange('comparison.mp4',[(b'range',b'bytes=0-7')]))
            self.assertEqual(messages[0]['status'],206)
            self.assertEqual(b''.join(m.get('body',b'') for m in messages[1:]),b'bounded ')
            self.assertEqual(dict(messages[0]['headers'])[b'cache-control'],b'private, no-store')
            self.assertEqual(asyncio.run(exchange('unexpected.bin'))[0]['status'],422)

    def test_wrapper_prints_private_comparison_links_and_sanitizes_failed_command_output(self):
        import sys
        report=self.create_fixture()
        wrapper=runpy.run_path(str(Path(__file__).resolve().parents[3]/'scripts/preview-cutout.py'))
        output=StringIO();errors=StringIO()
        with patch.object(sys,'argv',['preview-cutout.py',str(self.sample.job_id),'--clip','1']),patch('subprocess.run',return_value=SimpleNamespace(returncode=0,stdout=json.dumps(report),stderr='')) as run,patch('runpy.run_path',return_value={'BASE':'https://studio.test/api/media'}),redirect_stdout(output):
            self.assertEqual(wrapper['main'](),0)
        self.assertIn(f'https://studio.test/api/media/jobs/{self.sample.job_id}/cutout-lab/{report["cache_key"]}/comparison.mp4',output.getvalue())
        self.assertEqual(run.call_args.kwargs['timeout'],35);self.assertNotIn('shell',run.call_args.kwargs)
        with patch.object(sys,'argv',['preview-cutout.py',str(self.sample.job_id),'--clip','1']),patch('subprocess.run',return_value=SimpleNamespace(returncode=1,stdout='',stderr='private diagnostic placeholder')),redirect_stdout(output),redirect_stderr(errors):
            self.assertEqual(wrapper['main'](),1)
        self.assertNotIn('private diagnostic placeholder',errors.getvalue());self.assertIn('unchanged',errors.getvalue())

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg required')
    def test_actual_model_sample_writes_playable_silent_comparison_and_alpha_without_touching_source(self):
        import cv2
        import numpy as np
        model=Path(os.environ.get('CUTOUT_MODEL_PATH',lab.MODEL_PATH))
        if not model.exists():self.skipTest('pinned worker cutout model required')
        self.settings.cutout_model_path=model
        frame=np.full((180,240,3),60,np.uint8);cv2.circle(frame,(120,55),27,(150,180,210),-1)
        cv2.rectangle(frame,(80,85),(160,179),(30,100,200),-1)
        source=self.root/'source-real.mkv'
        subprocess.run(['ffmpeg','-v','error','-f','rawvideo','-pix_fmt','bgr24','-s','240x180','-r','8','-i','pipe:0',
            '-f','lavfi','-i','sine=frequency=600:sample_rate=48000:duration=2','-t','2','-c:v','ffv1','-c:a','pcm_s16le',str(source)],
            input=frame.tobytes()*16,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True,timeout=15)
        before=hashlib.sha256(source.read_bytes()).hexdigest();self.sample=self.sample.model_copy(update=dict(start=0,end=2))
        report=lab.create_comparison(source,self.sample,self.settings)
        video,_=lab.artifact_path(self.root,self.sample.job_id,report['cache_key'],'comparison.mp4')
        probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-of','json',str(video)],timeout=10))
        self.assertEqual([s['codec_type'] for s in probe['streams']],['video'])
        self.assertEqual(probe['streams'][0]['r_frame_rate'],'8/1');self.assertEqual(probe['streams'][0]['width'],720)
        self.assertEqual(probe['streams'][0]['height'],208);self.assertEqual(probe['streams'][0]['color_transfer'],'bt709')
        matte,_=lab.artifact_path(self.root,self.sample.job_id,report['cache_key'],'matte.png')
        image=cv2.imread(str(matte),cv2.IMREAD_UNCHANGED);self.assertEqual(image.shape,(180,240,4))
        self.assertEqual(report['metrics']['sampled_frames'],16);self.assertFalse(report['quality_approved'])
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),before)
