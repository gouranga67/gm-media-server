import importlib.util
import io
from contextlib import redirect_stdout
from pathlib import Path
import unittest
from unittest.mock import patch


class ReleaseReadinessScriptTests(unittest.TestCase):
    def setUp(self):
        source=Path(__file__).resolve().parent.parent.parent.parent/'scripts'/'verify-phase31.py'
        if not source.exists():source=Path('/app/scripts/verify-phase31.py')
        spec=importlib.util.spec_from_file_location('release_readiness_fixture',source)
        self.module=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.module)
        self.calls=[]
        self.report=dict(version=1,schema_ready=True,build_id='a'*40,private_pilot_complete=False,publishing_acceptance_complete=False,
            public_customer_launch_ready=False,automatic_posts=0,automatic_model_calls=0,checks=[],technical=[])
    def request(self,path,method='GET',payload=None):
        self.calls.append((path,method,payload))
        return {'release_acceptance':dict(version=1,automatic_posts=False)} if path=='system' else self.report
    def call(self,*flags):
        with patch.object(self.module.runpy,'run_path',return_value={'request':self.request}),patch('sys.argv',['verify-phase31.py',*flags]),redirect_stdout(io.StringIO()):
            self.module.main()
    def test_readiness_distinguishes_installed_infrastructure_from_acceptance(self):
        self.call();self.assertEqual(self.calls,[('system','GET',None),('release/readiness','GET',None)])
        self.assertFalse(self.report['private_pilot_complete'])
    def test_explicit_acceptance_requirements_fail_without_running_a_test(self):
        for flag in ('--require-private','--require-publishing'):
            self.calls=[]
            with self.assertRaises(RuntimeError):self.call(flag)
            self.assertTrue(all(method=='GET' and body is None for _,method,body in self.calls))
    def test_public_launch_and_side_effect_claims_are_rejected(self):
        for field,value in (('public_customer_launch_ready',True),('automatic_posts',1),('schema_ready',False)):
            with self.subTest(field=field):
                original=self.report[field];self.report[field]=value
                with self.assertRaises(RuntimeError):self.call()
                self.report[field]=original
