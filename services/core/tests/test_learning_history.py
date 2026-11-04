"""Full-history readiness, bounded history pages and zero-write review access."""
import tempfile
import unittest
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch
from uuid import UUID, uuid4

from fastapi import HTTPException
from app import learning_lab as lab
from test_learning_evidence import lesson
from test_learning_cases import strict_score


def trial(item, number, *, case=True, status='ready'):
    return dict(id=UUID(int=number),created_at=datetime(2026,11,1,tzinfo=timezone.utc),
        job_id=UUID(int=2000+number),version=2,status=status,preview_path='trial.mp4',
        evaluation_lesson_id=item['id'],evaluation_case_id=uuid4() if case else None,
        based_on_run_id=UUID(int=1000+number),baseline_version=1,baseline_status='ready',baseline_path='base.mp4',
        project_name=f'Playback {number}',baseline_provider='local_caption',candidate_provider='chatgpt_plan',test_case=None)


class HistoryDatabase:
    def __init__(self, item, rows, evaluations=()):
        self.item,self.rows,self.evaluations=item,rows,evaluations
        self.calls=[]
    def execute(self,sql,params=()):
        self.calls.append((sql,params));rows=[]
        if sql.startswith('SELECT * FROM learning_lessons WHERE'): rows=[self.item]
        elif sql.startswith('SELECT id,created_at FROM edit_runs'):
            rows=[row for row in self.rows if row['id']==params[0] and row['evaluation_lesson_id']==params[1]]
        elif sql.startswith('SELECT count(*)::integer AS count'):
            rows=[{'count':sum(row['evaluation_lesson_id']==params[0] for row in self.rows)}]
        elif sql.startswith(lab.TRIAL_SELECT_SQL):
            rows=[row for row in self.rows if row['evaluation_lesson_id']==params[0]]
            if len(params)==4: rows=[row for row in rows if (row['created_at'],row['id'])<(params[1],params[2])]
            rows=sorted(rows,key=lambda row:(row['created_at'],row['id']),reverse=True)[:params[-1]]
        elif 'FROM learning_evaluations' in sql:
            rows=[row for row in self.evaluations if row['candidate_run_id'] in params[1]]
        elif 'FROM ai_usage_events' not in sql: raise AssertionError(sql)
        return Mock(fetchall=lambda:deepcopy(rows),fetchone=lambda:deepcopy(rows[0]) if rows else None)
    def __enter__(self): return self
    def __exit__(self,*args): return False


class LearningHistoryTests(unittest.TestCase):
    def setUp(self):
        self.item={**lesson(),'evaluation_protocol':2}
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.root=Path(self.folder.name)
        (self.root/'base.mp4').write_bytes(b'baseline');(self.root/'trial.mp4').write_bytes(b'candidate')
    def patches(self,database):
        return patch.multiple(lab,connection=Mock(return_value=database),require_owner=Mock(),actor_login=Mock(return_value='owner'),get_settings=Mock(return_value=SimpleNamespace(media_root=self.root)))

    def test_hidden_queued_and_unreviewed_trials_block_the_same_report_used_for_promotion(self):
        scores=[strict_score(n,self.item) for n in range(3)]
        rows=[dict(id=row['candidate_run_id'],status='ready',evaluation_case_id=uuid4()) for row in scores]
        rows += [dict(id=uuid4(),status='ready',evaluation_case_id=None) for _ in range(100)]
        rows += [dict(id=uuid4(),status='planning',evaluation_case_id=uuid4()),dict(id=uuid4(),status='ready',evaluation_case_id=uuid4())]
        report=lab.promotion_report(self.item,scores,rows)
        self.assertFalse(report['can_promote']);self.assertEqual(report['total_trials'],105)
        self.assertEqual(report['history_scope'],'all_saved_trials')
        self.assertEqual(report['active_trials'],1);self.assertEqual(report['unreviewed_trials'],1)
        self.assertEqual(report['held_out_jobs'],3)
        self.assertTrue(lab.promotion_report(self.item,scores,rows[:-2])['can_promote'])

    def test_overview_does_not_use_the_limited_preview_rows_for_readiness(self):
        item=self.item;scores=[{**strict_score(n,item),'lesson_id':item['id']} for n in range(3)]
        visible=[trial(item,n,case=False) for n in range(1,101)]
        states=[{key:row[key] for key in ('id','status','evaluation_case_id','evaluation_lesson_id')} for row in visible]
        states.append(dict(id=uuid4(),status='ready',evaluation_case_id=uuid4(),evaluation_lesson_id=item['id']))
        database=MagicMock();database.__enter__.return_value=database
        def query(sql,params=()):
            if sql.startswith('SELECT * FROM learning_lessons'): rows=[item]
            elif sql==lab.TRIAL_STATES_SQL: rows=states
            elif sql.startswith(lab.TRIAL_SELECT_SQL): rows=visible
            elif 'FROM learning_evaluations' in sql: rows=scores
            else: rows=[]
            return Mock(fetchall=lambda:deepcopy(rows))
        database.execute.side_effect=query
        with self.patches(database): result=lab.lab()
        self.assertEqual(len(result['trials']),100)
        report=result['lessons'][0]['evaluation'];self.assertFalse(report['can_promote'])
        self.assertEqual(report['total_trials'],101);self.assertEqual(report['unreviewed_trials'],1)
        self.assertTrue(all(not any(word in call.args[0] for word in ('INSERT','UPDATE ','DELETE')) for call in database.execute.call_args_list))

    def test_keyset_pages_handle_identical_timestamps_without_duplicates_or_cross_lesson_rows(self):
        rows=[trial(self.item,n) for n in range(1,66)]+[trial(lesson(),99)]
        database=HistoryDatabase(self.item,rows)
        ids=[];before=None
        with self.patches(database):
            for _ in range(4):
                result=lab.lesson_comparisons(self.item['id'],before=before,limit=20)
                self.assertLessEqual(len(result['items']),20);self.assertEqual(result['total'],65)
                self.assertEqual(result['hosted_model_calls'],0)
                ids += [row['id'] for row in result['items']]
                before=UUID(result['next_before']) if result['next_before'] else None
        self.assertIsNone(before);self.assertEqual(ids,[UUID(int=n) for n in range(65,0,-1)])
        self.assertEqual(len(set(ids)),65)
        selects=[params for sql,params in database.calls if sql.startswith(lab.TRIAL_SELECT_SQL)]
        self.assertTrue(all(params[-1]==21 for params in selects))
        self.assertFalse(any(any(word in sql for word in ('INSERT','UPDATE ','DELETE')) for sql,_ in database.calls))

    def test_page_sanitizes_paths_and_reuses_exact_saved_score_and_usage(self):
        row=trial(self.item,1);saved=dict(candidate_run_id=row['id'],baseline_rating=3,candidate_rating=4,note='Preserved ending',evidence={'rubric':{'story':'better'},'executable_changed':True})
        database=HistoryDatabase(self.item,[row],[saved])
        with self.patches(database): result=lab.lesson_comparisons(self.item['id'],limit=20)
        public=result['items'][0]
        self.assertNotIn('preview_path',public);self.assertNotIn('baseline_path',public)
        self.assertTrue(public['baseline_available']);self.assertTrue(public['candidate_available'])
        self.assertEqual(public['baseline_usage']['total_tokens'],0);self.assertIsNone(public['candidate_usage'])
        self.assertEqual(public['comparison']['note'],'Preserved ending');self.assertTrue(public['executable_changed'])

    def test_missing_preview_or_baseline_stays_visible_but_cannot_be_scored(self):
        row=trial(self.item,1);row.update(baseline_status=None,baseline_path=None,baseline_version=None,based_on_run_id=None,preview_path='missing.mp4')
        database=HistoryDatabase(self.item,[row])
        with self.patches(database): result=lab.lesson_comparisons(self.item['id'],limit=20)
        self.assertEqual(len(result['items']),1)
        self.assertFalse(result['items'][0]['baseline_available']);self.assertFalse(result['items'][0]['candidate_available'])

    def test_foreign_or_deleted_cursor_is_rejected_before_page_queries(self):
        database=HistoryDatabase(self.item,[trial(lesson(),10)])
        with self.patches(database),self.assertRaises(HTTPException) as raised:
            lab.lesson_comparisons(self.item['id'],before=UUID(int=10),limit=20)
        self.assertEqual(raised.exception.status_code,409)
        self.assertFalse(any(sql.startswith(lab.TRIAL_SELECT_SQL) for sql,_ in database.calls))

    def test_empty_history_has_no_cursor_or_model_usage_query(self):
        database=HistoryDatabase(self.item,[])
        with self.patches(database): result=lab.lesson_comparisons(self.item['id'],limit=20)
        self.assertEqual(result['items'],[]);self.assertIsNone(result['next_before']);self.assertEqual(result['total'],0)
        self.assertFalse(any('ai_usage_events' in sql for sql,_ in database.calls))

    def test_history_is_owner_only_and_cannot_start_work(self):
        with patch.object(lab,'actor_login',return_value='viewer'),patch.object(lab,'require_owner',side_effect=HTTPException(403,'owner only')),patch.object(lab,'connection') as database:
            with self.assertRaises(HTTPException) as raised: lab.lesson_comparisons(self.item['id'],limit=20)
        self.assertEqual(raised.exception.status_code,403);database.assert_not_called()
