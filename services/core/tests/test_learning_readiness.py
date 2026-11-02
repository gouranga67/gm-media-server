import importlib.util
import io
import json
import unittest
from contextlib import redirect_stdout
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch


class LearningReadinessTests(unittest.TestCase):
    def verifier(self,filename="verify-phase14.py"):
        path=next((parent/"scripts"/filename for parent in Path(__file__).resolve().parents
            if (parent/"scripts"/filename).is_file()),None)
        # The normal core runner mounts host scripts alongside these tests.
        if path is None:
            self.skipTest("host verification script is exercised by the source checks")
        spec=importlib.util.spec_from_file_location("learning_readiness_fixture",path)
        module=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_readiness_never_overwrites_existing_scoped_timestamped_feedback(self):
        module=self.verifier()
        feedback=dict(edit_run_id="run",rating=5,tags=["clear_story"],note="Keep this teaching example.",
            would_use_again=True,scope="pacing",start_seconds=2,end_seconds=3,
            created_at="2026-11-01T00:00:00Z",updated_at="2026-11-01T00:00:00Z")
        before=deepcopy(feedback);calls=[]
        def request(path,method="GET",payload=None,expected=200):
            calls.append((path,method,payload))
            self.assertEqual(method,"GET")
            if path=="usage?days=0":return dict(job_history=[dict(id="job",history_kind="editing")])
            if path=="jobs/job/review":return dict(latest_run=dict(id="run",status="ready"),latest_feedback=feedback)
            if path=="learning/summary":return dict(hosted_model_calls=0,settings=dict(minimum_samples=3),scopes=dict(all={},talking_head={},montage={}))
            if path=="jobs/job/editor-context":return dict(learning_preferences=dict(hosted_model_calls=0))
            self.fail("unexpected verification request: "+path)
        output=io.StringIO()
        with patch.object(module,"request",side_effect=request),redirect_stdout(output):
            self.assertEqual(module.main(),0)
        report=json.loads(output.getvalue())
        self.assertTrue(report["read_only"])
        self.assertEqual(report["feedback_writes"],0)
        self.assertEqual(feedback,before)
        self.assertEqual(len(calls),4)

    def test_readiness_failure_never_tries_to_restore_or_replace_a_rating(self):
        module=self.verifier();calls=[]
        def request(path,method="GET",payload=None,expected=200):
            calls.append(method)
            if path=="usage?days=0":return dict(job_history=[dict(id="job",history_kind="editing")])
            if path=="jobs/job/review":return dict(latest_run=dict(id="run",status="ready"))
            return dict(hosted_model_calls=0,settings=dict(minimum_samples=1))
        with patch.object(module,"request",side_effect=request),self.assertRaisesRegex(RuntimeError,"fewer than three"):
            module.main()
        self.assertTrue(all(method=="GET" for method in calls))

    def test_live_renderer_creates_an_isolated_local_only_fixture(self):
        module=self.verifier("verify-phase5.py");calls=[]
        context=dict(assets=[dict(asset_id="source",has_video=True,has_audio=True,duration_seconds=12)])
        original=deepcopy(context)
        def request(path,*,method="GET",payload=None):
            calls.append((path,method,payload))
            if path=="projects":return 201,dict(id="fixture-project")
            if path=="projects/fixture-project/jobs":return 201,dict(id="fixture-job")
            if path=="jobs/fixture-job/assets":return 200,dict(attached_count=1)
            self.fail("unexpected fixture write: "+path)
        fixture_context=dict(ready_for_editing=True,assets=context["assets"])
        with patch.object(module,"request",side_effect=request),patch.object(module,"get_json",return_value=fixture_context):
            identity,result=module.create_fixture(context)
        self.assertEqual(identity,"fixture-job")
        self.assertEqual(result,fixture_context)
        self.assertEqual(calls[0][2]["privacy_mode"],"local_only")
        self.assertEqual(calls[1][2]["edit_style"],"clean")
        self.assertEqual(calls[2][2],dict(asset_ids=["source"]))
        self.assertEqual(context,original)

    def test_live_renderer_archives_only_its_fixture_on_success_and_failure(self):
        module=self.verifier("verify-phase5.py")
        for failed in (False,True):
            calls=[]
            def request(path,*,method="GET",payload=None):
                calls.append((path,method))
                return (200,dict(status="failed" if failed else "ready"))
            check=patch.object(module,"check_fixture",side_effect=RuntimeError("render fixture failed") if failed else None,
                return_value=dict(status="passed"))
            with patch.object(module,"find_ready_job",return_value=("real-job",{})),patch.object(module,"create_fixture",return_value=("fixture-job",{})),check,patch.object(module,"request",side_effect=request),redirect_stdout(io.StringIO()):
                if failed:
                    with self.assertRaisesRegex(RuntimeError,"render fixture failed"):module.main()
                else:self.assertEqual(module.main(),0)
            self.assertEqual(calls,[("jobs/fixture-job/preview","GET"),("jobs/fixture-job/archive","POST")])
