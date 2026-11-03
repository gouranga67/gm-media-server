import json
import tempfile
import unittest
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch
from uuid import uuid4

from fastapi import HTTPException
from pydantic import ValidationError
from app import release_acceptance as release
from test_publishing import settings


class ReleaseDatabase:
    def __init__(self):
        self.calls=[];self.saved={};self.current=[]
        self.run=dict(id=uuid4(),version=2,status='ready',preview_path='preview.mp4',approved_at=datetime.now(timezone.utc),manifest={'edit_plan_sha256':'b'*64})
        self.final=dict(id=uuid4(),video_path='final.mp4')
        self.post=dict(id=uuid4(),status='published',schedule_requested=True,publish_at=datetime.now(timezone.utc),approved_revision=1,platform='instagram',video_sha256='c'*64)
    @contextmanager
    def connection(self): yield self
    def execute(self,sql,params=()):
        self.calls.append((sql,params));row=None;rows=[]
        if sql.startswith('SELECT * FROM release_observations'):row=self.saved.get(params[0])
        elif sql.startswith('SELECT * FROM edit_runs'):row=self.run
        elif sql.startswith('SELECT id,video_path FROM final_exports'):row=self.final
        elif sql.startswith('SELECT p.id,p.status,p.schedule_requested,p.publish_at,p.approved_revision'):row=self.post
        elif sql.startswith('INSERT INTO release_observations'):
            id,build,key,result,note,job,run,post,evidence,actor=params
            self.saved[id]=dict(id=id,build_id=build,check_key=key,result=result,note=note,job_id=job,edit_run_id=run,publishing_post_id=post,evidence=evidence.obj,recorded_by=actor)
            row={'id':id}
        elif sql == release.CURRENT_SQL: rows=self.current
        elif sql == release.HISTORY_SQL: rows=list(self.saved.values())
        elif sql == release.QUEUE_SQL:row=dict(edits=1,analysis=2,exports=0,posts=0,uncertain_posts=0,failed_posts=4)
        elif "FROM social_connections" in sql: rows=[]
        elif sql.startswith('SELECT EXISTS'):row={'ready':True}
        elif sql.startswith('SELECT p.id') or sql.startswith('SELECT r.job_id'):rows=[]
        else:raise AssertionError(sql)
        return Mock(fetchone=lambda:row,fetchall=lambda:rows)


class ReleaseAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.root=Path(self.folder.name);self.config=settings(self.root)
        self.config.appliance_status_path=self.root/'appliance-health.json'
        self.config.tailscale_auth_required=True;self.config.tailscale_owner_login='owner'
        self.build='a'*40;self.now=datetime.now(timezone.utc);self.db=ReleaseDatabase()
        (self.root/'build.json').write_text(json.dumps({'commit':self.build}))
        for name in ('preview.mp4','final.mp4'):(self.root/name).write_bytes(b'available rendered fixture')
        for key,value in {'connection':self.db.connection,'get_settings':lambda:self.config,'require_owner':Mock(),'actor_login':lambda _: 'owner',
            'worker_evidence':lambda *_:dict(key='worker',label='Worker',scope='private',status='pass')}.items():
            wrapper=patch.object(release,key,value);wrapper.start();self.addCleanup(wrapper.stop)
    def payload(self,**updates):
        return release.ObservationCreate(**dict(id=uuid4(),build_id=self.build,check_key='library_intake',result='pass',note='Imported photos and video; found them in the correct folder.',observed=True,**updates))
    def health(self,**updates):
        value=dict(generated_at=self.now.isoformat(),services=dict(running=7,expected=7),disk=dict(available_bytes=100*1024**3,used_percent=50),
            backup=dict(state='ready',completed_at=self.now.isoformat()),offsite_backup=dict(state='attention',last_verified_at=self.now.isoformat(),message='raw private details'))
        value.update(updates);self.config.appliance_status_path.write_text(json.dumps(value));return value
    def proof(self,kind,**updates):
        value=dict(status='passed',completed_at=self.now.isoformat(),original_count=78,boot_id_changed=True,private_token='must not return',preview_path='must not return')
        value.update(updates);name='restore-verification.json' if kind=='restore' else 'reboot-recovery-drill.json'
        (self.root/name).write_text(json.dumps(value))
    def test_registration_is_explicit_append_only_and_idempotent(self):
        payload=self.payload();first=release.record_observation(payload,'owner');second=release.record_observation(payload,'owner')
        self.assertEqual(first['id'],second['id']);self.assertEqual(len(self.db.saved),1)
        self.assertEqual(first['posts_created'],0);self.assertEqual(first['model_calls'],0)
        self.assertFalse(any('UPDATE ' in sql or 'DELETE ' in sql or 'INSERT INTO publishing' in sql for sql,_ in self.db.calls))
        with self.assertRaises(HTTPException):release.record_observation(payload.model_copy(update={'note':'Different observation'}),'owner')
    def test_new_build_refuses_stale_form_but_preserves_exact_retry(self):
        payload=self.payload();release.record_observation(payload,'owner')
        (self.root/'build.json').write_text(json.dumps({'commit':'d'*40}))
        self.assertTrue(release.record_observation(payload,'owner')['recorded'])
        with self.assertRaisesRegex(HTTPException,'build changed'):release.record_observation(self.payload(),'owner')
        self.assertEqual(len(self.db.saved),1)
    def test_observation_requires_attestation_bounds_and_applicable_evidence(self):
        base=self.payload().model_dump()
        for updates in (dict(observed=False),dict(note='   '),dict(check_key='unknown'),dict(build_id='development'),dict(result='not_applicable'),dict(job_id=uuid4()),dict(check_key='story_playback'),dict(check_key='instagram_post'),dict(publishing_post_id=uuid4())):
            with self.subTest(updates=updates),self.assertRaises(ValidationError):release.ObservationCreate(**{**base,**updates})
        self.assertEqual(release.ObservationCreate(**{**base,'check_key':'facebook_post','result':'not_applicable'}).result,'not_applicable')
    def test_playback_pass_binds_exact_available_preview_and_final_export(self):
        payload=self.payload().model_copy(update=dict(check_key='story_playback',job_id=uuid4(),version=2))
        release.record_observation(payload,'owner');evidence=self.db.saved[payload.id]['evidence']['edit']
        self.assertEqual(evidence['run_id'],str(self.db.run['id']));self.assertEqual(evidence['final_export_id'],str(self.db.final['id']))
        self.assertEqual(evidence['version'],2)
        (self.root/'final.mp4').unlink()
        with self.assertRaisesRegex(HTTPException,'export'):release.record_observation(payload.model_copy(update={'id':uuid4()}),'owner')
        (self.root/'final.mp4').mkdir()
        with self.assertRaises(HTTPException):release.record_observation(payload.model_copy(update={'id':uuid4()}),'owner')
        self.db.run['preview_path']='../outside.mp4'
        with self.assertRaises(HTTPException):release.record_observation(payload.model_copy(update={'id':uuid4()}),'owner')
    def test_failure_can_be_recorded_without_a_playable_edit(self):
        release.record_observation(self.payload().model_copy(update={'result':'fail','check_key':'story_playback'}),'owner')
        self.assertEqual(next(iter(self.db.saved.values()))['result'],'fail')
    def test_publishing_pass_requires_matching_platform_published_and_explicit_schedule(self):
        base=self.payload().model_copy(update={'check_key':'scheduled_post','publishing_post_id':self.db.post['id']})
        for updates in (dict(status='queued'),dict(status='unknown'),dict(status='published',schedule_requested=None),dict(schedule_requested=False)):
            self.db.post.update(updates)
            with self.assertRaises(HTTPException):release.record_observation(base.model_copy(update={'id':uuid4()}),'owner')
        self.db.post.update(status='published',schedule_requested=True)
        release.record_observation(base,'owner')
        with self.assertRaises(HTTPException):release.record_observation(base.model_copy(update={'id':uuid4(),'check_key':'facebook_post'}),'owner')
    def test_recovery_needs_recent_machine_evidence_and_never_returns_raw_fields(self):
        base=self.payload().model_copy(update={'check_key':'restore_recovery'})
        with self.assertRaises(HTTPException):release.record_observation(base,'owner')
        self.proof('restore');release.record_observation(base,'owner')
        proof=self.db.saved[base.id]['evidence']['recovery'];self.assertEqual(proof['original_count'],78)
        self.assertNotIn('private_token',proof);self.assertNotIn('preview_path',proof)
        for changes in (dict(status='failed'),dict(completed_at=(self.now-timedelta(days=31)).isoformat()),dict(original_count=0)):
            self.proof('restore',**changes)
            with self.assertRaises(HTTPException):release.record_observation(base.model_copy(update={'id':uuid4()}),'owner')
        self.proof('reboot',boot_id_changed=False)
        with self.assertRaises(HTTPException):release.record_observation(base.model_copy(update={'id':uuid4(),'check_key':'reboot_recovery'}),'owner')
    def test_machine_readiness_rejects_stale_future_and_malformed_health(self):
        self.health();self.proof('restore');self.proof('reboot')
        queues=dict(uncertain_posts=0)
        report=release.technical_snapshot(self.config,True,[],queues,self.now)
        self.assertTrue(all(t['status']=='pass' for t in report if t['scope']=='private'))
        for change in (dict(generated_at=(self.now-timedelta(minutes=11)).isoformat()),dict(generated_at=(self.now+timedelta(minutes=1)).isoformat()),dict(services='bad'),dict(disk={'available_bytes':True,'used_percent':False})):
            self.health(**change);report=release.technical_snapshot(self.config,True,[],queues,self.now)
            self.assertEqual(next(t['status'] for t in report if t['key']=='runtime'),'pending')
    def test_technical_setup_cannot_substitute_for_human_or_real_post_acceptance(self):
        checks=[{**spec,'observation':None} for spec in release.SPEC.values()]
        tech=[dict(scope='private',status='pass'),dict(scope='publishing',status='pass')]
        self.assertFalse(release.outcome(checks,tech)['private_pilot_complete'])
        for item in checks:item['observation']={'result':'pass'}
        self.assertTrue(release.outcome(checks,tech)['publishing_acceptance_complete'])
        for item in checks:
            if item['key'] in ('instagram_post','facebook_post'):item['observation']={'result':'not_applicable'}
        self.assertFalse(release.outcome(checks,tech)['publishing_acceptance_complete'])
        self.assertFalse(release.outcome(checks,tech)['public_customer_launch_ready'])
        checks[0]['observation']={'result':'fail'};self.assertFalse(release.outcome(checks,tech)['private_pilot_complete'])
    def test_readiness_reads_only_and_old_build_checks_do_not_supply_current_acceptance(self):
        self.health();self.proof('restore');self.proof('reboot')
        self.db.saved[uuid4()]=dict(id=uuid4(),build_id='d'*40,check_key='library_intake',result='pass')
        report=release.readiness('owner')
        self.assertEqual(report['build_id'],self.build);self.assertFalse(report['private_pilot_complete'])
        self.assertEqual(report['queues']['failed_posts'],4);self.assertEqual(report['automatic_posts'],0)
        self.assertTrue(all(sql.startswith('SELECT') for sql,_ in self.db.calls))
        self.assertTrue(all(c['observation'] is None for c in report['checks']))
    def test_owner_gate_stops_reads_and_writes_before_database_access(self):
        self.db.calls=[]
        with patch.object(release,'require_owner',side_effect=HTTPException(403,'owner only')):
            for call in (lambda:release.readiness('viewer'),lambda:release.record_observation(self.payload(),'viewer')):
                with self.assertRaises(HTTPException):call()
        self.assertEqual(self.db.calls,[])

class ReleaseConfigurationTests(unittest.TestCase):
    def test_real_runtime_settings_require_explicit_private_access(self):
        from app.config import Settings
        from app.release_acceptance import technical_snapshot
        from test_publishing import settings
        base=dict(database_url='postgresql://fixture.invalid/database',upload_hook_secret='x'*32)
        self.assertFalse(Settings(**base,tailscale_auth_required=False).tailscale_auth_required)
        self.assertTrue(Settings(**base,tailscale_auth_required='true').tailscale_auth_required)
        with tempfile.TemporaryDirectory() as directory:
            config=settings(Path(directory));config.appliance_status_path=Path(directory)/'health.json'
            config.tailscale_auth_required=False;config.tailscale_owner_login='owner'
            report=technical_snapshot(config,True,[],{'uncertain_posts':0},datetime.now(timezone.utc))
            self.assertEqual(next(item['status'] for item in report if item['key']=='private_access'),'pending')

    def test_restore_status_writer_records_success_and_failure_without_raw_output(self):
        import subprocess
        import sys
        script=Path(__file__).resolve().parent.parent.parent.parent/'scripts'/'verify-backup-restore.sh'
        if not script.exists():script=Path('/app/scripts/verify-backup-restore.sh')
        code=script.read_text().split("<<'PY'\n",1)[1].split('\nPY',1)[0]
        with tempfile.TemporaryDirectory() as directory:
            for state,count in (('running',0),('passed',78),('failed',0)):
                subprocess.run([sys.executable,'-c',code,directory,state,str(count),'2026-11-03T00:00:00Z'],check=True,capture_output=True)
                report=json.loads((Path(directory)/'restore-verification.json').read_text())
                self.assertEqual(report['status'],state);self.assertEqual(report['original_count'],count)
                self.assertEqual(report['completed_at'] is None,state=='running')
                self.assertEqual(set(report),{'version','status','original_count','started_at','completed_at','method'})
                self.assertEqual(list(Path(directory).glob('.restore-status-*')),[])

    def test_worker_evidence_uses_a_bounded_read_and_declines_stale_future_or_invalid_records(self):
        from types import SimpleNamespace
        from redis.exceptions import RedisError
        config=SimpleNamespace(redis_url='redis://fixture.invalid',worker_heartbeat_key='fixture',worker_heartbeat_ttl_seconds=45)
        now=datetime.now(timezone.utc);client=Mock()
        with patch.object(release.Redis,'from_url',return_value=client) as connect:
            for age,expected in ((1,'pass'),(46,'pending'),(-1,'pending')):
                client.get.return_value=json.dumps({'unix_time':now.timestamp()-age,'private_token':'not returned'})
                report=release.worker_evidence(config,now);self.assertEqual(report['status'],expected);self.assertNotIn('private_token',report)
            client.get.return_value='[]';self.assertEqual(release.worker_evidence(config,now)['status'],'pending')
            client.get.side_effect=RedisError('private transport details')
            self.assertEqual(release.worker_evidence(config,now)['status'],'pending')
        self.assertEqual(connect.call_args.kwargs['socket_timeout'],2)
        self.assertEqual(connect.call_args.kwargs['socket_connect_timeout'],2)
        client.set.assert_not_called();client.delete.assert_not_called()


if __name__ == '__main__': unittest.main()
