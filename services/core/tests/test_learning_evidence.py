import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch
from uuid import uuid4

from fastapi import HTTPException
from app.edit_plan import document_sha256
from app.learning_evidence import comparison_evidence, evaluation_result, preview_available, usage_for_runs
from app.learning_lab import assert_holdout, change_status, LessonAction, trial_block_reason


def lesson():
    return dict(id=uuid4(),recipe="talking_head",edit_style="clean",directive="Keep complete recorded speech.",
        status="proposed",training_job_ids=[],training_source_hashes=["f"*64])


def score(number, *, delta=1, hashes=None, changed=True, item=None):
    item=item or lesson()
    base,candidate=str(uuid4()),str(uuid4())
    return dict(job_id=str(uuid4()),baseline_run_id=base,candidate_run_id=candidate,
        baseline_rating=3,candidate_rating=3+delta,evidence=dict(version=1,
            source_hashes=hashes or [f"{number:064x}"],baseline_run_id=base,candidate_run_id=candidate,
            baseline_plan_hash="a"*64,candidate_plan_hash="b"*64,executable_changed=changed,
            directive_hash=document_sha256({"directive":item["directive"]})))


class LearningEvidenceTests(unittest.TestCase):
    def test_fresh_independent_improvements_qualify_but_training_and_legacy_do_not(self):
        item=lesson()
        rows=[score(n,item=item) for n in range(3)]
        self.assertTrue(evaluation_result(rows,item=item)["can_promote"])
        rows[0]["evidence"]["source_hashes"]=["f"*64]
        report=evaluation_result(rows,item=item)
        self.assertFalse(report["can_promote"])
        self.assertEqual(report["excluded_comparisons"],1)
        rows[0]["evidence"]={}
        self.assertEqual(evaluation_result(rows,item=item)["held_out_jobs"],2)

    def test_connected_footage_overlap_cannot_manufacture_three_independent_comparisons(self):
        rows=[score(1,hashes=["a"*64]),score(2,hashes=["b"*64]),score(3,hashes=["a"*64,"b"*64])]
        report=evaluation_result(rows)
        self.assertEqual(report["held_out_jobs"],1)
        self.assertEqual(report["overlapping_comparisons"],2)
        self.assertFalse(report["can_promote"])
        rows[1]["candidate_rating"]=2
        self.assertEqual(evaluation_result(rows)["regressions"],1)

    def test_same_job_repeated_scores_count_once_at_the_lowest_delta(self):
        rows=[score(n) for n in range(3)]
        rows[1]["job_id"]=rows[0]["job_id"]
        rows[1]["candidate_rating"]=3
        self.assertEqual(evaluation_result(rows)["held_out_jobs"],2)
        self.assertEqual(evaluation_result(rows)["rating_delta"],.5)

    def test_unchanged_plan_never_gets_positive_credit_and_regressions_still_block(self):
        rows=[score(n,changed=False) for n in range(3)]
        self.assertFalse(evaluation_result(rows)["can_promote"])
        self.assertEqual(evaluation_result(rows)["rating_delta"],0)
        rows[0]["evidence"]["executable_changed"]=True
        self.assertTrue(evaluation_result(rows)["can_promote"])
        rows[1]["candidate_rating"]=2
        self.assertFalse(evaluation_result(rows)["can_promote"])

    def test_costs_cover_only_recorded_pairs_and_do_not_claim_missing_usage_is_free(self):
        rows=[score(n) for n in range(3)]
        self.assertIsNone(evaluation_result(rows)["token_delta"])
        rows[0]["evidence"].update(baseline_usage=dict(total_tokens=1000),candidate_usage=dict(total_tokens=700))
        report=evaluation_result(rows)
        self.assertEqual(report["costed_comparisons"],1)
        self.assertEqual(report["token_delta"],-300)

    def test_snapshot_is_bound_to_the_lesson_and_exact_run_pair(self):
        item=lesson()
        rows=[score(n,item=item) for n in range(3)]
        rows[0]["candidate_run_id"]=str(uuid4())
        rows[1]["evidence"]["directive_hash"]="0"*64
        rows[2]["evidence"]["source_hashes"]=[""]
        self.assertEqual(evaluation_result(rows,item=item)["held_out_jobs"],0)

    def test_readiness_explains_overlapping_missing_and_paid_trial_baselines(self):
        item=lesson()
        job=dict(id=str(uuid4()),recipe="talking_head",edit_style="clean",source_hashes=["a"*64])
        self.assertIsNone(trial_block_reason(item,job,[]))
        self.assertIn("overlaps",trial_block_reason(item,job,[dict(job_id=uuid4(),sha256="a"*64)]))
        self.assertIn("incomplete",trial_block_reason(item,{**job,"source_hashes":[""]},[]))
        self.assertIn("local-only",trial_block_reason(item,{**job,"privacy_mode":"local_only"},[]))
        self.assertIn("ordinary",trial_block_reason(item,{**job,"evaluation_lesson_id":uuid4()},[]))

    def test_server_rejects_fresh_job_that_reuploads_existing_trial_footage(self):
        item=lesson(); database=Mock()
        database.execute.return_value.fetchone.return_value=dict(recipe="talking_head",edit_style="clean")
        database.execute.return_value.fetchall.return_value=[dict(job_id=uuid4(),sha256="a"*64)]
        with patch("app.learning_lab.source_hashes",return_value=["a"*64]):
            with self.assertRaisesRegex(HTTPException,"overlaps"):
                assert_holdout(database,item,uuid4())
            # Rerating the already created comparison is allowed; its shared
            # footage still counts only once in evaluation_result.
            self.assertIsNone(assert_holdout(database,item,uuid4(),scoring=True))

    def test_usage_sums_recorded_request_and_repair_costs_without_provider_calls(self):
        database=Mock(); identity=uuid4()
        database.execute.return_value.fetchall.return_value=[dict(edit_run_id=identity,requests=2,total_tokens=900,model_latency_ms=2400)]
        self.assertEqual(usage_for_runs(database,[identity])[str(identity)]["requests"],2)
        database.reset_mock()
        self.assertEqual(usage_for_runs(database,[]),{})
        database.execute.assert_not_called()

    def test_saved_evidence_binds_real_previews_plans_sources_and_usage(self):
        from test_revision_precision import fixture
        plan,_=fixture(); old=plan.model_dump(mode="json")
        new=deepcopy(old);new["clips"][0]["source_audio_gain_db"]=3
        item=lesson()
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); (root/"base.mp4").write_bytes(b"baseline");(root/"trial.mp4").write_bytes(b"candidate")
            def run(name,doc):
                return dict(id=uuid4(),job_id=uuid4(),edit_plan_id=uuid4(),status="ready",preview_path=name,
                    manifest=dict(edit_plan_sha256=document_sha256(doc),sources=[dict(sha256="a"*64)]))
            baseline,candidate=run("base.mp4",old),run("trial.mp4",new)
            database=Mock();database.execute.return_value.fetchone.side_effect=[dict(document=old),dict(document=new)]
            with patch("app.learning_lab.source_hashes",return_value=["a"*64]),patch("app.learning_evidence.usage_for_runs",return_value={}):
                evidence=comparison_evidence(database,item,baseline,candidate,root)
            self.assertTrue(evidence["executable_changed"])
            self.assertEqual(evidence["source_hashes"],["a"*64])
            self.assertIsNone(evidence["candidate_usage"])
            self.assertEqual(evidence["baseline_plan_hash"],document_sha256(old))
            candidate["manifest"]["edit_plan_sha256"]="b"*64
            database.execute.return_value.fetchone.side_effect=[dict(document=old),dict(document=new)]
            with patch("app.learning_lab.source_hashes",return_value=["a"*64]),patch("app.learning_evidence.usage_for_runs",return_value={}):
                with self.assertRaisesRegex(HTTPException,"provenance"):
                    comparison_evidence(database,item,baseline,candidate,root)
            self.assertFalse(preview_available({**baseline,"preview_path":"../outside.mp4"},root))
            (root/"base.mp4").unlink()
            self.assertFalse(preview_available(baseline,root))

    def test_owner_promotion_rechecks_evidence_and_rollback_does_not_erase_ratings(self):
        item=lesson(); database=MagicMock();database.__enter__.return_value=database
        database.execute.return_value.fetchall.return_value=[score(n,item=item,changed=False) for n in range(3)]
        with patch("app.learning_lab.require_owner"),patch("app.learning_lab.actor_login",return_value="owner"),patch("app.learning_lab.lesson",return_value=item),patch("app.learning_lab.connection",return_value=database):
            with self.assertRaisesRegex(HTTPException,"not passed"):
                change_status(item["id"],LessonAction(action="promote"))
            self.assertFalse(any("UPDATE learning_lessons" in c.args[0] for c in database.execute.call_args_list))
            result=change_status(item["id"],LessonAction(action="rollback"))
        self.assertEqual(result["status"],"rolled_back")
        self.assertFalse(any("DELETE" in c.args[0] for c in database.execute.call_args_list))

    def test_trial_retry_reuses_the_existing_candidate_without_spending_again(self):
        from app import editing
        from app.schemas import RevisionCreate
        database=MagicMock();database.__enter__.return_value=database
        existing=dict(id=uuid4(),version=2,baseline_version=1,status="ready",preview_path="trial.mp4")
        context=dict(ready_for_editing=True,assets=[],project=dict(privacy_mode="text_only"))
        for version in (1,2):
            with self.subTest(version=version):
                database.execute.return_value.fetchone.side_effect=[dict(id=uuid4()),existing]
                capacity=Mock()
                with patch.multiple(editing,_context_or_http=Mock(return_value=context),connection=Mock(return_value=database),assert_job_capacity=capacity):
                    payload=RevisionCreate(base_version=version,evaluation_lesson_id=uuid4())
                    if version==1:
                        result=editing._request_revision(uuid4(),payload)
                        self.assertEqual(result["id"],existing["id"])
                    else:
                        with self.assertRaisesRegex(HTTPException,"already has a trial"):
                            editing._request_revision(uuid4(),payload)
                capacity.assert_not_called()
        self.assertFalse(any("INSERT" in call.args[0] for call in database.execute.call_args_list))

    def test_trial_cannot_bundle_other_changes_or_omit_the_baseline(self):
        from app.schemas import RevisionCreate
        from pydantic import ValidationError
        for extra in (dict(base_version=None),dict(effects_enabled=False),dict(broll_enabled=False),
                      dict(caption_settings=dict(position="upper")),dict(locked_elements=["captions"])):
            with self.subTest(extra=extra),self.assertRaises(ValidationError):
                RevisionCreate(**{**dict(base_version=1,evaluation_lesson_id=uuid4()),**extra})

    def test_lab_reads_eligibility_cost_and_saved_ratings_without_starting_work(self):
        from app import learning_lab
        from types import SimpleNamespace
        item=lesson(); baseline,candidate,job_id=uuid4(),uuid4(),uuid4()
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); (root/"base.mp4").write_bytes(b"baseline");(root/"trial.mp4").write_bytes(b"candidate")
            trial=dict(id=candidate,job_id=job_id,version=2,status="ready",preview_path="trial.mp4",
                evaluation_lesson_id=item["id"],based_on_run_id=baseline,baseline_version=1,baseline_status="ready",baseline_path="base.mp4")
            saved=score(1,item=item);saved.update(lesson_id=item["id"],candidate_run_id=candidate,job_id=job_id,note="Better pacing.")
            job=dict(id=uuid4(),name="Fresh recording",recipe="talking_head",edit_style="clean",version=1,status="ready",preview_path="base.mp4",source_hashes=["b"*64])
            database=MagicMock();database.__enter__.return_value=database
            def query(sql,params=()):
                if "SELECT * FROM learning_lessons" in sql: rows=[item]
                elif "FROM learning_evaluations" in sql: rows=[saved]
                elif "b.status AS baseline_status" in sql: rows=[trial]
                elif sql==learning_lab.JOBS_SQL: rows=[job]
                else: rows=[]
                return Mock(fetchall=lambda:rows)
            database.execute.side_effect=query
            with patch("app.learning_lab.connection",return_value=database),patch("app.learning_lab.get_settings",return_value=SimpleNamespace(media_root=root)):
                report=learning_lab.lab()
            self.assertEqual(report["version"],2)
            self.assertEqual(report["hosted_model_calls"],0)
            self.assertTrue(report["trials"][0]["baseline_available"])
            self.assertTrue(report["trials"][0]["candidate_available"])
            self.assertIsNone(report["trials"][0]["candidate_usage"])
            self.assertEqual(report["trials"][0]["comparison"]["note"],"Better pacing.")
            self.assertTrue(report["lessons"][0]["trial_options"][0]["eligible"])
            self.assertNotIn("preview_path",report["trials"][0])
            self.assertFalse(any("INSERT" in call.args[0] or "UPDATE " in call.args[0] for call in database.execute.call_args_list))

    def test_score_endpoint_saves_server_snapshot_without_promoting_or_replanning(self):
        from app import learning_lab
        item=lesson(); base_id,candidate_id,job_id=uuid4(),uuid4(),uuid4()
        candidate=dict(id=candidate_id,job_id=job_id,status="ready",based_on_run_id=base_id,revision_note=item["directive"])
        baseline=dict(id=base_id,job_id=job_id,status="ready")
        saved=score(1,item=item);saved.update(job_id=job_id,baseline_run_id=base_id,candidate_run_id=candidate_id)
        saved["evidence"].update(baseline_run_id=str(base_id),candidate_run_id=str(candidate_id))
        database=MagicMock();database.__enter__.return_value=database
        database.execute.return_value.fetchone.side_effect=[candidate,baseline]
        database.execute.return_value.fetchall.return_value=[saved]
        with patch("app.learning_lab.require_owner"),patch("app.learning_lab.actor_login",return_value="owner"),patch("app.learning_lab.lesson",return_value=item),patch("app.learning_lab.connection",return_value=database),patch("app.learning_lab.assert_holdout"),patch("app.learning_lab.get_settings"),patch("app.learning_lab.comparison_evidence",return_value=saved["evidence"]):
            result=learning_lab.evaluate(item["id"],learning_lab.EvaluationCreate(candidate_run_id=candidate_id,baseline_rating=3,candidate_rating=4,note="A measured comparison."))
        values=next(call.args[1] for call in database.execute.call_args_list if "INSERT INTO learning_evaluations" in call.args[0])
        self.assertEqual(values[-1].obj,saved["evidence"])
        self.assertEqual(values[7],"A measured comparison.")
        self.assertFalse(result["can_promote"])
        self.assertFalse(any("UPDATE learning_lessons" in call.args[0] or "INSERT INTO edit_runs" in call.args[0] for call in database.execute.call_args_list))
