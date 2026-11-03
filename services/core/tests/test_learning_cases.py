import tempfile
import unittest
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

from fastapi import HTTPException
from pydantic import ValidationError

from app.edit_plan import document_sha256
from app.learning_cases import CaseCreate, CaseAction, assert_case, create_case, task_snapshot, TASK_SQL, SOURCES_SQL
from app.learning_evidence import evaluation_result, with_trial_readiness, comparison_evidence, usage_snapshot
from app.learning_lab import EvaluationCreate, PlaybackRubric, LessonAction, change_status, TrialRequest, trial
from test_learning_evidence import lesson, score


def rubric(**changes):
    return {**dict(brief="same",story="better",speech="same",captions="same",visuals="same",audio="same"),**changes}


def strict_score(number, item, **changes):
    row = score(number,item=item)
    row["evidence"].update(version=2,case_id=str(uuid4()),case_snapshot_hash="c"*64,criteria_hash="d"*64,
        recording_group=f"shoot {number}",rubric=rubric(),reviewed_both=True,new_quality_findings=[],max_candidate_tokens=None,
        baseline_usage=dict(requests=1,total_tokens=1000,model_latency_ms=2000),
        candidate_usage=dict(requests=1,total_tokens=800,model_latency_ms=1800),**changes)
    return row


class CaseDatabase:
    def __init__(self):
        self.job_id, self.plan_id = uuid4(), uuid4()
        self.document = {"fixture":"a source-backed plan"}
        self.baseline = dict(id=uuid4(),job_id=self.job_id,version=1,status="ready",preview_path="base.mp4",edit_plan_id=self.plan_id,
            manifest=dict(edit_plan_sha256=document_sha256(self.document),sources=[dict(sha256="a"*64)]))
        self.task = dict(settings=dict(id=str(self.job_id),recipe="talking_head",edit_style="clean"),brief="Keep the recorded story.",privacy_mode="text_only",ai_copy_allowed=False)
        self.sources = [dict(id=str(uuid4()),sha256="a"*64,asset_status="ready",analysis_status="ready",analysis_hash="analysis",display_name="Cream explanation",ranges=[])]
        self.count = 1
        self.case = None
        self.calls = []

    @contextmanager
    def connection(self):
        yield self

    def execute(self,sql,params=()):
        self.calls.append((sql,params))
        row=None
        rows=[]
        if sql == TASK_SQL: row=self.task
        elif sql == SOURCES_SQL: rows=self.sources
        elif sql.startswith("SELECT count(*) AS count FROM job_assets"): row={"count":self.count}
        elif sql.startswith("SELECT document FROM edit_plans"): row={"document":self.document}
        elif sql.startswith("SELECT * FROM learning_cases"): row=self.case
        elif sql.startswith("SELECT id FROM jobs"): row={"id":self.job_id}
        elif sql.startswith("SELECT c.*,r.version"): row={**self.case,"base_version":1} if self.case else None
        elif sql.startswith("SELECT * FROM edit_runs"): row=self.baseline
        elif sql.startswith("INSERT INTO learning_cases"):
            id,job,base,label,group,category,expectations,budget,snapshot,hash,actor=params
            self.case=dict(id=id,job_id=job,baseline_run_id=base,label=label,recording_group=group,category=category,
                expectations=expectations,max_candidate_tokens=budget,snapshot=snapshot.obj,snapshot_hash=hash,created_by=actor,archived_at=None)
            row={"id":id}
        else: raise AssertionError(sql)
        return Mock(fetchone=lambda:row,fetchall=lambda:rows)


class LearningCaseTests(unittest.TestCase):
    def setUp(self):
        self.db = CaseDatabase()

    def save(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder)/"base.mp4").write_bytes(b"baseline")
            payload=CaseCreate(id=uuid4(),job_id=self.db.job_id,base_version=1,label="Complete explanation",
                recording_group="Cream shoot Monday",expectations="Keep all five points and complete spoken words.")
            with patch("app.learning_cases.connection",self.db.connection),patch("app.learning_cases.require_owner"), \
                 patch("app.learning_cases.actor_login",return_value="owner"),patch("app.learning_cases.get_settings",return_value=SimpleNamespace(media_root=Path(folder))):
                create_case(payload)
            return payload

    def test_saving_freezes_exact_task_plan_sources_and_criteria_without_a_trial(self):
        self.save()
        self.assertEqual(self.db.case["snapshot"]["baseline_plan_hash"],document_sha256(self.db.document))
        self.assertEqual(self.db.case["snapshot"]["task"]["brief"],self.db.task["brief"])
        self.assertEqual(self.db.case["snapshot_hash"],document_sha256(self.db.case["snapshot"]))
        self.assertFalse(any("INSERT INTO edit_runs" in sql or "UPDATE learning_lessons" in sql for sql,_ in self.db.calls))

    def test_saving_retry_reuses_request_and_rejects_a_different_baseline_or_criteria(self):
        payload=self.save()
        with patch("app.learning_cases.connection",self.db.connection),patch("app.learning_cases.require_owner"),patch("app.learning_cases.actor_login",return_value="owner"):
            self.assertEqual(create_case(payload)["id"],payload.id)
            for change in (dict(base_version=2),dict(expectations="Different task"),dict(id=uuid4())):
                with self.assertRaises(HTTPException): create_case(CaseCreate(**{**payload.model_dump(),**change}))
        self.assertEqual(sum(sql.startswith("INSERT INTO learning_cases") for sql,_ in self.db.calls),1)

    def test_case_rechecks_labels_brief_settings_and_analysis_before_trial_or_score(self):
        self.save()
        self.assertEqual(assert_case(self.db,self.db.case["id"],self.db.job_id,self.db.baseline)["id"],self.db.case["id"])
        original = deepcopy((self.db.task,self.db.sources))
        for kind in ("brief","labels","analysis","ranges"):
            self.db.task,self.db.sources=deepcopy(original)
            if kind=="brief":self.db.task["brief"]="A different product brief"
            elif kind=="labels":self.db.sources[0]["display_name"]="Something else"
            elif kind=="analysis":self.db.sources[0]["analysis_hash"]="new alignment"
            else:self.db.sources[0]["ranges"]=[[1,2,"avoid","False start"]]
            with self.subTest(kind=kind),self.assertRaisesRegex(HTTPException,"changed since"):
                assert_case(self.db,self.db.case["id"],self.db.job_id,self.db.baseline)

    def test_archived_case_blocks_new_experiments_but_keeps_old_scores_reviewable(self):
        self.save();self.db.case["archived_at"]="yesterday"
        with self.assertRaisesRegex(HTTPException,"restore this test case"):
            assert_case(self.db,self.db.case["id"],self.db.job_id,self.db.baseline,new_trial=True)
        self.assertIsNotNone(assert_case(self.db,self.db.case["id"],self.db.job_id,self.db.baseline))

    def test_missing_analysis_unknown_hashes_and_changed_render_provenance_cannot_be_frozen(self):
        original=deepcopy((self.db.baseline,self.db.sources,self.db.count))
        for kind in ("missing","unknown","failed","plan","rendered"):
            self.db.baseline,self.db.sources,self.db.count=deepcopy(original)
            if kind=="missing":self.db.count=2
            elif kind=="unknown":self.db.sources[0]["sha256"]=""
            elif kind=="failed":self.db.sources[0]["analysis_status"]="failed"
            elif kind=="plan":self.db.baseline["manifest"]["edit_plan_sha256"]="b"*64
            else:self.db.baseline["manifest"]["sources"]=[dict(sha256="b"*64)]
            with self.subTest(kind=kind),self.assertRaises(HTTPException):task_snapshot(self.db,self.db.job_id,self.db.baseline)

    def test_case_inputs_and_qualification_limits_are_explicit_and_bounded(self):
        values=dict(id=uuid4(),job_id=uuid4(),base_version=1,label="Test",recording_group="Shoot",expectations="Keep all points")
        for changes in (dict(expectations=" "),dict(recording_group=""),dict(base_version=0),dict(max_candidate_tokens=0),dict(max_candidate_tokens=2_000_001),dict(unknown=True)):
            with self.subTest(changes=changes),self.assertRaises(ValidationError):CaseCreate(**{**values,**changes})
        self.assertEqual(CaseCreate(**{**values,"recording_group":" Cream   shoot "}).recording_group,"Cream shoot")

    def test_case_requires_correct_baseline_and_cannot_be_an_unrelated_revision(self):
        from app.schemas import RevisionCreate
        self.save()
        with self.assertRaises(HTTPException):assert_case(self.db,self.db.case["id"],uuid4(),self.db.baseline)
        with self.assertRaises(ValidationError):RevisionCreate(note="Change everything",evaluation_case_id=uuid4())

    def test_trial_forwards_saved_case_without_seeding_human_criteria_into_editor_note(self):
        case,job,item=uuid4(),uuid4(),uuid4()
        with patch("app.learning_lab.require_owner"),patch("app.editing.request_revision",return_value={"id":"trial"}) as request:
            trial(item,TrialRequest(job_id=job,base_version=1,case_id=case),"owner@example.test")
        payload=request.call_args.args[1]
        self.assertEqual(payload.evaluation_case_id,case)
        self.assertEqual(payload.evaluation_lesson_id,item)
        self.assertEqual(payload.note,"")


class SavedCaseEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.item={**lesson(),"evaluation_protocol":2}
        self.rows=[strict_score(n,self.item) for n in range(3)]

    def test_three_changed_measured_pairs_with_checklists_can_qualify(self):
        report=evaluation_result(self.rows,item=self.item)
        self.assertTrue(report["can_promote"])
        self.assertEqual(report["costed_comparisons"],3)
        self.assertEqual(report["token_delta"],-200)

    def test_known_local_execution_is_zero_hosted_usage_but_unknown_usage_is_not(self):
        self.assertEqual(usage_snapshot({"provider":"local_caption"},None)["total_tokens"],0)
        self.assertIsNone(usage_snapshot({"provider":"chatgpt_plan"},None))
        self.assertIsNone(usage_snapshot({},None))
        measured={"requests":1,"total_tokens":800,"model_latency_ms":20}
        self.assertIs(usage_snapshot({"provider":"local_caption"},measured),measured)

    def test_protocol_upgrade_keeps_legacy_results_without_counting_them_in_the_new_cohort(self):
        old=score(9,item=self.item,delta=-1)
        report=evaluation_result([*self.rows,old],item=self.item)
        self.assertEqual(report["excluded_comparisons"],1)
        self.assertTrue(report["can_promote"])
        report=with_trial_readiness(report,self.item,[dict(id=uuid4(),status="ready",evaluation_case_id=None)],self.rows)
        self.assertEqual(report["legacy_trials"],1)
        self.assertTrue(report["can_promote"])

    def test_same_recording_group_counts_once_despite_different_file_hashes(self):
        for row in self.rows:row["evidence"]["recording_group"]=" Cream   Shoot Monday "
        self.assertEqual(evaluation_result(self.rows,item=self.item)["held_out_jobs"],1)
        self.assertFalse(evaluation_result(self.rows,item=self.item)["can_promote"])

    def test_higher_overall_rating_cannot_hide_caption_or_sync_regression(self):
        self.rows[0]["evidence"]["rubric"]["speech"]="worse"
        report=evaluation_result(self.rows,item=self.item)
        self.assertFalse(report["can_promote"])
        self.assertEqual(report["rubric_regressions"],1)

    def test_missing_usage_exceeded_budget_and_new_technical_warning_each_block(self):
        for change,key in ((dict(candidate_usage=None),"unmeasured_pairs"),
                           (dict(max_candidate_tokens=700),"budget_exceeded_pairs"),
                           (dict(new_quality_findings=["speech_joins"]),"technical_regressions")):
            rows=deepcopy(self.rows);rows[0]["evidence"].update(change)
            report=evaluation_result(rows,item=self.item)
            self.assertFalse(report["can_promote"])
            self.assertEqual(report[key],1)

    def test_unchanged_edit_or_no_specific_checklist_improvement_cannot_qualify(self):
        for row in self.rows:row["evidence"]["rubric"]=rubric(story="same")
        self.assertFalse(evaluation_result(self.rows,item=self.item)["can_promote"])
        for row in self.rows:row["evidence"].update(rubric=rubric(),executable_changed=False)
        self.assertFalse(evaluation_result(self.rows,item=self.item)["can_promote"])

    def test_legacy_scores_and_incomplete_review_cannot_qualify_new_protocol(self):
        for change in (dict(version=1),dict(reviewed_both=False),dict(rubric={"story":"better"}),dict(case_snapshot_hash="")):
            rows=deepcopy(self.rows);rows[0]["evidence"].update(change)
            result=evaluation_result(rows,item=self.item)
            self.assertEqual(result["excluded_comparisons"],1)
            self.assertFalse(result["can_promote"])

    def test_pending_and_unreviewed_ready_trials_block_but_failed_trials_are_reported(self):
        report=evaluation_result(self.rows,item=self.item)
        for status in ("pending","planning","rendering","ready"):
            result=with_trial_readiness(report,self.item,[dict(id=uuid4(),status=status,evaluation_case_id=uuid4())],self.rows)
            self.assertFalse(result["can_promote"])
        result=with_trial_readiness(report,self.item,[dict(id=uuid4(),status="failed")],self.rows)
        self.assertEqual(result["failed_trials"],1)
        self.assertTrue(result["can_promote"])

    def test_status_changes_append_versioned_evidence_and_are_idempotent(self):
        db=Mock();db.execute.return_value.fetchall.return_value=self.rows
        item={**self.item,"deployment_version":3,"status":"proposed"}
        @contextmanager
        def connection():yield db
        with patch("app.learning_lab.connection",connection),patch("app.learning_lab.require_owner"), \
             patch("app.learning_lab.actor_login",return_value="owner"),patch("app.learning_lab.lesson",return_value=item):
            result=change_status(item["id"],LessonAction(action="promote"))
            self.assertEqual(result["deployment_version"],4)
            values=next(params for sql,params in (call.args for call in db.execute.call_args_list) if "INSERT INTO learning_lesson_events" in sql)
            self.assertEqual(values[2:6],(4,"promote","proposed","promoted"))
            self.assertEqual(len(values[-1].obj["case_ids"]),3)
            item.update(status="promoted",deployment_version=4)
            db.reset_mock();change_status(item["id"],LessonAction(action="promote"))
            self.assertFalse(any("UPDATE learning_lessons" in call.args[0] for call in db.execute.call_args_list))
            with self.assertRaisesRegex(HTTPException,"roll back"):change_status(item["id"],LessonAction(action="upgrade"))
            change_status(item["id"],LessonAction(action="rollback"))
            self.assertFalse(any("DELETE" in call.args[0] for call in db.execute.call_args_list))

    def test_scoring_schema_requires_every_checklist_dimension_when_supplied(self):
        with self.assertRaises(ValidationError):EvaluationCreate(candidate_run_id=uuid4(),baseline_rating=4,candidate_rating=5,rubric={"story":"better"})
        self.assertEqual(PlaybackRubric(**rubric()).speech,"same")


if __name__ == "__main__":unittest.main()
