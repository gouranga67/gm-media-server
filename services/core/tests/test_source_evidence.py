import subprocess
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.source_evidence import complete_thoughts, image_ocr, shared_evidence
from app import media_analysis, worker


class SourceEvidenceTests(unittest.TestCase):
    def test_ocr_retains_readable_lines_and_normalized_coordinates(self):
        tsv = 'level\tpage_num\tblock_num\tpar_num\tline_num\tleft\ttop\twidth\theight\tconf\ttext\n1\t1\t0\t0\t0\t0\t0\t1000\t500\t-1\t\n5\t1\t1\t1\t1\t100\t50\t200\t50\t95\tCastor\n5\t1\t1\t1\t1\t310\t50\t100\t50\t92\toil\n5\t1\t1\t1\t2\t100\t150\t20\t50\t30\tnoise\n'
        with patch('app.source_evidence.shutil.which', return_value='/usr/bin/tesseract'), patch('app.source_evidence.subprocess.run', return_value=SimpleNamespace(stdout=tsv)):
            report = image_ocr(Path('fixture.png'))
        self.assertEqual(report['lines'][0]['text'], 'Castor oil')
        self.assertEqual(report['lines'][0]['normalized_box'], [.1, .1, .31, .1])
        self.assertEqual(len(report['lines']), 1)

    def test_ocr_failure_is_explicit_not_invented_text(self):
        with patch('app.source_evidence.shutil.which', return_value='tesseract'), patch('app.source_evidence.subprocess.run', side_effect=subprocess.TimeoutExpired('tesseract', 25)):
            self.assertEqual(image_ocr(Path('fixture.png'))['status'], 'failed')

    def test_thought_boundaries_and_sampling_include_ending(self):
        segments = [{'words': [{'start': n, 'end': n+.8, 'text': f'Thought {n}.'} for n in range(50)]}]
        result = complete_thoughts(segments, 3)
        self.assertEqual([r['start'] for r in result], [0, 24, 49])
        self.assertTrue(all(r['punctuated_end'] for r in result))
        self.assertEqual(len(complete_thoughts(segments, 1)), 1)
        self.assertEqual(complete_thoughts(segments, 0), [])

    def test_product_alias_is_only_a_mention_not_visual_identity(self):
        evidence = shared_evidence({'source_name': 'clip.mp4'}, {'notes': 'use clean take'}, {},
            [{'start': 0, 'end': 3, 'text': 'This is castor oil.'}],
            [{'id': 'p', 'name': 'Castor oil', 'aliases': ['castor']}])
        self.assertEqual(evidence['mentioned_products'][0]['evidence'], 'text_mention')
        self.assertFalse(evidence['mentioned_products'][0]['visual_identity_verified'])
        absent = shared_evidence({}, {}, {}, [{'text': 'a castorwheel', 'start': 0, 'end': 1}],
            [{'id': 'p', 'name': 'castor', 'aliases': []}])
        self.assertEqual(absent['mentioned_products'], [])

    def test_forced_analysis_refresh_bypasses_duplicate_cache(self):
        with patch.object(worker, 'get_settings', return_value=SimpleNamespace()), patch.object(worker, 'connection') as database:
            self.assertIsNone(worker.reuse_exact_analysis({'previous_manifest': {'force_reanalysis': True}}))
            database.assert_not_called()

    def test_recognition_model_is_reused_with_identical_settings(self):
        import sys
        from unittest.mock import Mock
        factory = Mock()
        media_analysis._whisper_model.cache_clear()
        try:
            with patch.dict(sys.modules, {'faster_whisper': SimpleNamespace(WhisperModel=factory)}):
                self.assertIs(media_analysis._whisper_model('fixture', 'cpu', 'int8'), media_analysis._whisper_model('fixture', 'cpu', 'int8'))
                self.assertEqual(factory.call_count, 1)
        finally:
            media_analysis._whisper_model.cache_clear()

class PreciseEditingTests(unittest.TestCase):
    def setUp(self):
        from uuid import uuid4
        from app.edit_plan import TalkingHeadEditPlan
        self.asset_id = str(uuid4())
        self.plan = TalkingHeadEditPlan(schema_version='1.4', recipe='talking_head', caption_style='clean_blue_v1', audio_preset='spoken_voice_v1', end_card='none', editorial_summary='Keep the story.', clips=[dict(asset_id=self.asset_id, source_in=1,source_out=9,crop='center_fill')])

    def test_split_keeps_duration_and_correct_source_ranges(self):
        from app.edit_plan import apply_timeline_adjustments, edit_plan_duration, clip_handle
        handle=clip_handle(0,self.plan.clips[0].model_dump(mode='json'))
        split=apply_timeline_adjustments(self.plan,[dict(clip_index=0,clip_id=handle,split_at=4)])
        self.assertEqual(edit_plan_duration(split),8)
        self.assertEqual([(c.source_in,c.source_out) for c in split.clips],[(1,4),(4,9)])

    def test_stale_clip_handle_is_rejected(self):
        from app.edit_plan import apply_timeline_adjustments
        with self.assertRaisesRegex(ValueError,'refresh'):
            apply_timeline_adjustments(self.plan,[dict(clip_index=0,clip_id='a'*16,source_in=2)])

    def test_trim_moves_surviving_cue_and_discards_removed_cue(self):
        from app.edit_plan import apply_timeline_adjustments, CreativeEffectCue
        from uuid import uuid4
        self.plan.effects=[CreativeEffectCue(asset_id=uuid4(),start_seconds=0,duration_seconds=.3),CreativeEffectCue(asset_id=uuid4(),start_seconds=4,duration_seconds=.3)]
        trimmed=apply_timeline_adjustments(self.plan,[dict(clip_index=0,source_in=3)])
        self.assertEqual(len(trimmed.effects),1)
        self.assertEqual(trimmed.effects[0].start_seconds,2)

    def test_replacement_take_cannot_refer_to_outside_media(self):
        from app.edit_plan import apply_timeline_adjustments
        from uuid import uuid4
        with self.assertRaisesRegex(ValueError,'belong'):
            apply_timeline_adjustments(self.plan,[dict(clip_index=0,replacement_asset_id=str(uuid4()))],[])
