import array
from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from uuid import uuid4
from pydantic import ValidationError

from app.config import Settings
from app.creative_selection import bound_generated_treatments, remove_graphic_effects
from app.edit_plan import TalkingHeadEditPlan, MontageEditPlan, apply_timeline_adjustments, schema_for_recipe
from app.edit_renderer import render_ass, _render_video
from app.effect_registry import EFFECT_DEFINITIONS, EFFECT_REGISTRY_VERSION, public_effect_registry
from app.finishing_tools import FinishingTools, validate_finishing
from app.montage_renderer import _render as montage_render
from app.render_integrity import rendered_audio_packet_error
from app.revision_intent import local_revision, assert_revision_locks
from app.visual_beats import VisualBeat, append_visual_beats


def fixture():
    return TalkingHeadEditPlan(schema_version='1.5',recipe='talking_head',
        clips=[dict(asset_id=uuid4(),source_in=0,source_out=3,crop='center_fill')],
        caption_style='clean_blue_v1',audio_preset='spoken_voice_v1',end_card='none',editorial_summary='Recorded speech stays intact.',
        finishing=FinishingTools(visual_beats=[dict(start=.8,end=1.6,preset='clone_row'),dict(start=2,end=2.2,preset='impact_frame')]))


class VisualBeatTests(unittest.TestCase):
    def test_strict_bounded_schema_and_no_empty_legacy_hash_change(self):
        for value in (dict(start=0,end=.5,preset='impact_frame'),dict(start=0,end=3,preset='clone_row'),
                      dict(start=0,end=1,preset='live_cursor'),dict(start=0,end=1,preset='letter_dive'),
                      dict(start=0,end=1.5,preset='comment_drop'),
                      dict(start=0,end=1,preset='arbitrary_js')):
            with self.assertRaises(ValidationError): VisualBeat(**value)
        self.assertNotIn('visual_beats',FinishingTools().model_dump(mode='json'))
        legacy=VisualBeat(start=0,end=.2,preset='impact_frame')
        self.assertEqual(legacy.model_dump(mode='json'),dict(start=0,end=.2,preset='impact_frame'))
        configured=VisualBeat(start=0,end=2,preset='clone_row',intensity='strong',position='upper')
        self.assertEqual(configured.model_dump(mode='json')['intensity'],'strong')
        self.assertEqual(configured.model_dump(mode='json')['position'],'upper')
        with self.assertRaisesRegex(ValidationError,'fixed frame position'):
            VisualBeat(start=0,end=.2,preset='impact_frame',position='upper')
        live=VisualBeat(start=0,end=1,preset='live_cursor',intensity='strong',
            cursor_start_x=.2,cursor_start_y=.3,cursor_end_x=.8,cursor_end_y=.6,click=False)
        self.assertEqual(live.model_dump(mode='json'),dict(start=0,end=1,preset='live_cursor',intensity='strong',
            cursor_start_x=.2,cursor_start_y=.3,cursor_end_x=.8,cursor_end_y=.6,click=False))
        with self.assertRaisesRegex(ValidationError,'does not accept cursor parameters'):
            VisualBeat(start=0,end=.2,preset='impact_frame',click=True)
        with self.assertRaises(ValidationError):
            VisualBeat(start=0,end=1,preset='live_cursor',cursor_start_x=0,cursor_start_y=.3,cursor_end_x=.8,cursor_end_y=.6,click=True)
        letters=VisualBeat(start=0,end=1.4,preset='letter_dive',intensity='strong',position='upper',letter_text='  REAL  ')
        self.assertEqual(letters.model_dump(mode='json')['letter_text'],'REAL')
        with self.assertRaisesRegex(ValidationError,'plain text'):
            VisualBeat(start=0,end=1,preset='letter_dive',letter_text=r'{\move}')
        with self.assertRaisesRegex(ValidationError,'does not accept letter text'):
            VisualBeat(start=0,end=.2,preset='impact_frame',letter_text='NO')
        comment=VisualBeat(start=0,end=2,preset='comment_drop',position='lower',comment_text='  Real reaction  ')
        self.assertEqual(comment.model_dump(mode='json')['comment_text'],'Real reaction')
        with self.assertRaisesRegex(ValidationError,'plain text'):
            VisualBeat(start=0,end=2,preset='comment_drop',comment_text=r'{\fad}')
        with self.assertRaisesRegex(ValidationError,'does not accept comment text'):
            VisualBeat(start=0,end=1.4,preset='letter_dive',letter_text='YES',comment_text='NO')
        for recipe in ('talking_head','montage'):
            schema=schema_for_recipe(recipe)['properties']['finishing']['anyOf'][1]
            beat=schema['properties']['visual_beats']['items']
            self.assertEqual(set(beat['required']),set(beat['properties']))
            self.assertFalse(beat['additionalProperties'])

    def test_registry_is_versioned_complete_and_matches_the_schema(self):
        registry=public_effect_registry()
        self.assertEqual(registry['version'],EFFECT_REGISTRY_VERSION)
        self.assertEqual(registry['version'],4)
        self.assertEqual({item['preset'] for item in registry['effects']},{'impact_frame','clone_row','live_cursor','letter_dive','comment_drop'})
        self.assertEqual({item.preset for item in EFFECT_DEFINITIONS},{'impact_frame','clone_row','live_cursor','letter_dive','comment_drop'})
        for item in registry['effects']:
            self.assertLessEqual(item['minimum_duration_seconds'],item['default_duration_seconds'])
            self.assertLessEqual(item['default_duration_seconds'],item['maximum_duration_seconds'])
            self.assertTrue(item['preserves_dialogue'])
            self.assertTrue(item['captions_above_effect'])
            self.assertFalse(item['requires_segmentation'])
        live=next(item for item in registry['effects'] if item['preset']=='live_cursor')
        parameters={item['key']:item for item in live['parameters']}
        self.assertEqual(set(parameters),{'intensity','cursor_start_x','cursor_start_y','cursor_end_x','cursor_end_y','click'})
        self.assertEqual(parameters['cursor_start_x']['type'],'number')
        self.assertEqual((parameters['cursor_start_x']['minimum'],parameters['cursor_start_x']['maximum']),(.08,.92))
        self.assertEqual(parameters['click'],{'key':'click','label':'Click pulse','type':'boolean','default':True})
        letters=next(item for item in registry['effects'] if item['preset']=='letter_dive')
        text=next(item for item in letters['parameters'] if item['key']=='letter_text')
        self.assertEqual(text,{'key':'letter_text','label':'Text','type':'text','default':'','minimum_length':1,'maximum_length':18})
        comment=next(item for item in registry['effects'] if item['preset']=='comment_drop')
        text=next(item for item in comment['parameters'] if item['key']=='comment_text')
        self.assertEqual(text,{'key':'comment_text','label':'Comment','type':'text','default':'','minimum_length':1,'maximum_length':48})

    def test_registered_parameters_reach_only_the_bounded_filter_values(self):
        plan=fixture()
        plan.finishing.visual_beats=[
            VisualBeat(start=.5,end=.7,preset='impact_frame',intensity='strong'),
            VisualBeat(start=1,end=2,preset='clone_row',intensity='subtle',position='lower'),
            VisualBeat(start=2.1,end=3.1,preset='live_cursor',cursor_start_x=.2,cursor_start_y=.3,cursor_end_x=.8,cursor_end_y=.6,click=True),
        ]
        graph=append_visual_beats('[picture]null[vout]',plan,width=180,height=320)
        self.assertIn('color=0xF4C95D@1:t=5',graph)
        self.assertIn('color=black@0.5',graph)
        self.assertIn('overlay=x=(W-w)/2:y=H-h-38',graph)
        self.assertNotIn('subtle',graph)
        self.assertNotIn('lower',graph)
        self.assertIn('[beatbase2]null[beatbase3]',graph)

    def test_live_cursor_is_an_ass_vector_below_caption_dialogue(self):
        tools=FinishingTools(visual_beats=[dict(start=.2,end=1.2,preset='live_cursor',intensity='strong',
            cursor_start_x=.2,cursor_start_y=.25,cursor_end_x=.8,cursor_end_y=.5,click=True)])
        ass=render_ass([dict(start=0,end=2,text='Caption wins.')],width=180,height=320,treatments=tools)
        self.assertIn(r'\move(36,80,144,160,0,1000)',ass)
        self.assertIn(r'\p1}m 0 0 l 0 30',ass)
        self.assertIn(r'\pos(138,154)',ass)
        cursor_line=next(line for line in ass.splitlines() if r'\move(36,80,144,160' in line)
        caption_line=next(line for line in ass.splitlines() if line.startswith('Dialogue: 0,'))
        self.assertTrue(cursor_line.startswith('Dialogue: -1,'))
        self.assertTrue(caption_line.startswith('Dialogue: 0,'))

    def test_letter_dive_staggers_plain_text_below_caption_dialogue(self):
        tools=FinishingTools(visual_beats=[dict(start=.2,end=1.6,preset='letter_dive',intensity='strong',position='upper',letter_text='GO')])
        ass=render_ass([dict(start=0,end=2,text='Caption wins.')],width=180,height=320,treatments=tools)
        letters=[line for line in ass.splitlines() if line.startswith('Dialogue: -1,') and r'\fnDejaVu Sans' in line]
        self.assertEqual(len(letters),2)
        self.assertIn(r'\move(',letters[0])
        self.assertNotEqual(letters[0].split(',')[1],letters[1].split(',')[1])
        self.assertTrue(any(line.startswith('Dialogue: 0,') for line in ass.splitlines()))

    def test_comment_drop_reuses_the_caption_aware_comment_card(self):
        tools=FinishingTools(visual_beats=[dict(start=.2,end=2.2,preset='comment_drop',intensity='standard',position='lower',comment_text='Real reaction')])
        ass=render_ass([dict(start=0,end=2.5,text='Caption wins.',position='lower_safe')],width=180,height=320,treatments=tools)
        self.assertIn('Real reaction',ass)
        self.assertIn(r'\move(',ass)
        for layer in (-3,-2,-1,0):
            self.assertTrue(any(line.startswith(f'Dialogue: {layer},') for line in ass.splitlines()))

    def test_duration_overlap_budget_removal_and_retiming(self):
        plan=fixture()
        validate_finishing(plan,[])
        bad=plan.model_copy(deep=True)
        bad.finishing.visual_beats[0].end=4
        with self.assertRaisesRegex(ValueError,'beyond'): validate_finishing(bad,[])
        off=bound_generated_treatments(dict(job=dict(effect_level='off')),plan)
        self.assertFalse(off.finishing and off.finishing.visual_beats)
        self.assertFalse(remove_graphic_effects(plan).finishing)
        changed=apply_timeline_adjustments(plan,[dict(clip_index=0,source_in=.4)])
        self.assertAlmostEqual(changed.finishing.visual_beats[0].start,.4)
        self.assertEqual(plan.finishing.visual_beats[0].start,.8)
        collision=fixture()
        collision.finishing=FinishingTools(
            callouts=[dict(start=.5,end=1.5,text='Existing card')],
            visual_beats=[dict(start=1,end=2,preset='comment_drop',comment_text='New card')],
        )
        with self.assertRaisesRegex(ValueError,'cannot overlap another text callout'):
            validate_finishing(collision,[])

    def test_remove_effects_and_effect_lock_include_native_beats(self):
        plan=fixture().model_dump(mode='json')
        changed=local_revision(plan,'Remove effects')
        self.assertIsNotNone(changed)
        document=changed[0] if isinstance(changed,tuple) else changed
        self.assertFalse((document.get('finishing') or {}).get('visual_beats'))
        with self.assertRaisesRegex(ValueError,'protected effects'):
            assert_revision_locks(document,plan,['effects'],[])


@unittest.skipUnless(shutil.which('ffmpeg'),'ffmpeg required for actual effect and sound verification')
class VisualBeatRenderTests(unittest.TestCase):
    def ff(self,*args):
        return subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-nostdin','-y',*args],capture_output=True,check=True,timeout=60).stdout

    def test_effect_windows_captions_and_continuous_audio_in_both_engines(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'source.mp4';captions=root/'captions.ass'
            self.ff('-f','lavfi','-i',"color=c=0x254050:s=180x320:r=30:d=3,drawbox=x=60:y=80:w=60:h=120:c=red:t=fill,drawbox=x=60:y=80:w=60:h=120:c=lime:t=fill:enable='gte(t,1.2)'",
                '-f','lavfi','-i','sine=frequency=440:sample_rate=48000:duration=3','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac',str(source))
            p=fixture()
            p.finishing.visual_beats.insert(0,VisualBeat(start=.1,end=.7,preset='live_cursor',
                cursor_start_x=.2,cursor_start_y=.15,cursor_end_x=.8,cursor_end_y=.15,click=True))
            p.finishing.visual_beats.append(VisualBeat(start=2.3,end=2.9,preset='letter_dive',
                intensity='strong',position='upper',letter_text='GO'))
            captions.write_text(render_ass([dict(start=0,end=3,text='Keep speech intact.')],width=180,height=320,treatments=p.finishing))
            settings=Settings(database_url='postgresql://unused',upload_hook_secret='x'*32,media_root=root)
            for recipe in ('talking_head','montage'):
                output=root/f'{recipe}.mp4'
                if recipe=='talking_head':
                    _render_video([(source,0,3)],p,captions,output,60,width=180,height=320)
                else:
                    values=p.model_dump(mode='json');values['recipe']='montage';values.pop('caption_style')
                    values['audio_preset']='montage_mix_v1'
                    values['clips'][0].update(source_out=1.5,duration=1.5,media_kind='video',include_source_audio=True)
                    values['clips'].append({**values['clips'][0],'source_in':1.5,'source_out':3})
                    montage=MontageEditPlan.model_validate(values)
                    context=dict(assets=[dict(asset_id=str(p.clips[0].asset_id),_storage_key=source.name,has_audio=True)],music_library=[],creative_effect_library=[])
                    montage_render(context,montage,output,width=180,height=320,final=False,settings=settings,captions_path=captions)
                def frame(t):
                    return self.ff('-ss',str(t),'-i',str(output),'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','pipe:1')
                def pixel(buf,x,y):return tuple(buf[(y*180+x)*3:(y*180+x)*3+3])
                before,during,after=frame(.5),frame(1.1),frame(1.8)
                # The moving white cursor is visible near its mid-path point.
                self.assertGreater(sum(min(pixel(before,x,y))>170 for y in range(42,72) for x in range(100,125)),10)
                # Three full-shot panels each retain the red subject at x=30,90,150.
                for x in (30,90,150):
                    self.assertGreater(pixel(during,x,160)[0],130)
                later=frame(1.4)
                for x in (30,90,150):
                    self.assertGreater(pixel(later,x,160)[1],170,'all three copies must advance with the source')
                    self.assertLess(pixel(later,x,160)[0],90)
                self.assertLess(pixel(before,30,160)[0],80)
                self.assertLess(pixel(after,30,160)[0],80)
                impact=frame(2.1)
                self.assertGreater(pixel(impact,1,1)[0],140)
                self.assertLess(pixel(after,1,1)[0],80)
                letters=frame(2.7)
                self.assertGreater(sum(min(pixel(letters,x,y))>170 for y in range(50,90) for x in range(55,125)),20)
                # White subtitle pixels remain in the lower safe band during the clone row.
                self.assertGreater(sum(min(pixel(during,x,y))>170 for y in range(220,250) for x in range(180)),20)
                pcm=array.array('h',self.ff('-i',str(output),'-vn','-ac','1','-ar','8000','-f','s16le','pipe:1'))
                for t in (.2,1,1.8,2.1,2.6):
                    samples=pcm[round(t*8000):round((t+.1)*8000)]
                    self.assertGreater(sum(abs(v) for v in samples)/len(samples),500,'speech tone must stay continuous')
                self.assertIsNone(rendered_audio_packet_error(output,60))
