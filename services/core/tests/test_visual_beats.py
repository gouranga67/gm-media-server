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
                      dict(start=0,end=.5,preset='voice_note'),
                      dict(start=0,end=2,preset='post_wall'),
                      dict(start=0,end=1.5,preset='sketch_words'),
                      dict(start=0,end=2,preset='rack_focus'),
                      dict(start=0,end=.7,preset='paper_tear'),
                      dict(start=0,end=2,preset='dolly_zoom'),
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
        wall=VisualBeat(start=0,end=3,preset='post_wall',intensity='strong',post_texts=['  Real footage  ','Review first'])
        self.assertEqual(wall.model_dump(mode='json')['post_texts'],['Real footage','Review first'])
        with self.assertRaisesRegex(ValidationError,'two or three'):
            VisualBeat(start=0,end=3,preset='post_wall',post_texts=['Only one'])
        with self.assertRaisesRegex(ValidationError,'short plain'):
            VisualBeat(start=0,end=3,preset='post_wall',post_texts=['Good',r'{\move}'])
        with self.assertRaisesRegex(ValidationError,'does not accept post text'):
            VisualBeat(start=0,end=2.6,preset='voice_note',post_texts=['No','Cards'])
        sketch=VisualBeat(start=0,end=1.6,preset='sketch_words',intensity='strong',position='upper',sketch_text='  KEEP IT REAL  ')
        self.assertEqual(sketch.model_dump(mode='json')['sketch_text'],'KEEP IT REAL')
        with self.assertRaisesRegex(ValidationError,'at most three words'):
            VisualBeat(start=0,end=1.6,preset='sketch_words',sketch_text='ONE TWO THREE FOUR')
        with self.assertRaisesRegex(ValidationError,'plain text'):
            VisualBeat(start=0,end=1.6,preset='sketch_words',sketch_text=r'{\clip}')
        with self.assertRaisesRegex(ValidationError,'does not accept sketch text'):
            VisualBeat(start=0,end=3,preset='post_wall',post_texts=['One','Two'],sketch_text='NO')
        focus=VisualBeat(start=0,end=2,preset='rack_focus',intensity='strong',
            focus_start_x=.3,focus_start_y=.2,focus_end_x=.7,focus_end_y=.8)
        self.assertEqual(focus.model_dump(mode='json')['focus_end_x'],.7)
        with self.assertRaisesRegex(ValidationError,'visible focus move'):
            VisualBeat(start=0,end=2,preset='rack_focus',focus_start_x=.5,focus_start_y=.5,focus_end_x=.51,focus_end_y=.51)
        with self.assertRaises(ValidationError):
            VisualBeat(start=0,end=2,preset='rack_focus',focus_start_x=.1,focus_start_y=.5,focus_end_x=.6,focus_end_y=.5)
        with self.assertRaisesRegex(ValidationError,'does not accept focus coordinates'):
            VisualBeat(start=0,end=1.6,preset='sketch_words',sketch_text='REAL',focus_start_x=.3)
        tear=VisualBeat(start=1,end=1.7,preset='paper_tear',intensity='strong',boundary_index=1,tear_direction='right')
        self.assertEqual(tear.model_dump(mode='json')['boundary_index'],1)
        with self.assertRaisesRegex(ValidationError,'requires a clip boundary'):
            VisualBeat(start=1,end=1.7,preset='paper_tear',boundary_index=1)
        with self.assertRaisesRegex(ValidationError,'does not accept paper tear parameters'):
            VisualBeat(start=0,end=.2,preset='impact_frame',boundary_index=1)
        dolly=VisualBeat(start=0,end=2,preset='dolly_zoom',intensity='strong',dolly_clip_index=0,
            dolly_direction='pull_out',dolly_anchor_x=.4,dolly_anchor_y=.6)
        self.assertEqual(dolly.model_dump(mode='json')['dolly_direction'],'pull_out')
        with self.assertRaisesRegex(ValidationError,'requires one clip'):
            VisualBeat(start=0,end=2,preset='dolly_zoom',dolly_clip_index=0,dolly_direction='push_in')
        with self.assertRaisesRegex(ValidationError,'does not accept dolly zoom parameters'):
            VisualBeat(start=0,end=.2,preset='impact_frame',dolly_clip_index=0)
        for recipe in ('talking_head','montage'):
            schema=schema_for_recipe(recipe)['properties']['finishing']['anyOf'][1]
            beat=schema['properties']['visual_beats']['items']
            self.assertEqual(set(beat['required']),set(beat['properties']))
            self.assertFalse(beat['additionalProperties'])

    def test_registry_is_versioned_complete_and_matches_the_schema(self):
        registry=public_effect_registry()
        self.assertEqual(registry['version'],EFFECT_REGISTRY_VERSION)
        self.assertEqual(registry['version'],11)
        expected={'impact_frame','clone_row','live_cursor','letter_dive','comment_drop','voice_note','post_wall','sketch_words','rack_focus','paper_tear','dolly_zoom'}
        self.assertEqual({item['preset'] for item in registry['effects']},expected)
        self.assertEqual({item.preset for item in EFFECT_DEFINITIONS},expected)
        for item in registry['effects']:
            self.assertLessEqual(item['minimum_duration_seconds'],item['default_duration_seconds'])
            self.assertLessEqual(item['default_duration_seconds'],item['maximum_duration_seconds'])
            self.assertTrue(item['preserves_dialogue'])
            self.assertTrue(item['captions_above_effect'])
            self.assertFalse(item['requires_segmentation'])
            self.assertTrue(item['best_for'])
            self.assertTrue(item['avoid_when'])
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
        voice=next(item for item in registry['effects'] if item['preset']=='voice_note')
        self.assertEqual({item['key'] for item in voice['parameters']},{'intensity','position'})
        self.assertEqual((voice['minimum_duration_seconds'],voice['default_duration_seconds'],voice['maximum_duration_seconds']),(1,2.6,5))
        wall=next(item for item in registry['effects'] if item['preset']=='post_wall')
        parameters={item['key']:item for item in wall['parameters']}
        self.assertEqual(set(parameters),{'intensity','post_texts'})
        self.assertEqual(parameters['post_texts'],{'key':'post_texts','label':'Source-backed cards','type':'text_list','default':[],
            'minimum_items':2,'maximum_items':3,'item_maximum_length':42})
        sketch=next(item for item in registry['effects'] if item['preset']=='sketch_words')
        parameters={item['key']:item for item in sketch['parameters']}
        self.assertEqual(set(parameters),{'intensity','position','sketch_text'})
        self.assertEqual(parameters['sketch_text'],{'key':'sketch_text','label':'Words','type':'text','default':'','minimum_length':1,'maximum_length':24})
        focus=next(item for item in registry['effects'] if item['preset']=='rack_focus')
        parameters={item['key']:item for item in focus['parameters']}
        self.assertEqual(set(parameters),{'intensity','focus_start_x','focus_start_y','focus_end_x','focus_end_y'})
        self.assertEqual((parameters['focus_start_x']['minimum'],parameters['focus_start_x']['maximum'],parameters['focus_start_x']['default']),(.3,.7,.35))
        self.assertEqual((parameters['focus_end_y']['minimum'],parameters['focus_end_y']['maximum'],parameters['focus_end_y']['default']),(.18,.82,.55))
        tear=next(item for item in registry['effects'] if item['preset']=='paper_tear')
        parameters={item['key']:item for item in tear['parameters']}
        self.assertEqual(set(parameters),{'intensity','boundary_index','tear_direction'})
        self.assertEqual((tear['minimum_duration_seconds'],tear['default_duration_seconds'],tear['maximum_duration_seconds']),(.4,.7,1))
        self.assertEqual(parameters['boundary_index'],{'key':'boundary_index','label':'Clip boundary','type':'number','default':1,'minimum':1,'maximum':47})
        self.assertEqual(parameters['tear_direction']['values'],['left','right'])
        dolly=next(item for item in registry['effects'] if item['preset']=='dolly_zoom')
        parameters={item['key']:item for item in dolly['parameters']}
        self.assertEqual(set(parameters),{'intensity','dolly_clip_index','dolly_direction','dolly_anchor_x','dolly_anchor_y'})
        self.assertEqual((dolly['minimum_duration_seconds'],dolly['default_duration_seconds'],dolly['maximum_duration_seconds']),(1,2,8))
        self.assertEqual(parameters['dolly_direction']['values'],['push_in','pull_out'])
        self.assertEqual((parameters['dolly_anchor_x']['minimum'],parameters['dolly_anchor_x']['maximum']),(.3,.7))

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

    def test_rack_focus_builds_only_a_bounded_simulated_focus_graph(self):
        plan=fixture()
        plan.finishing.visual_beats=[VisualBeat(start=.4,end=2.4,preset='rack_focus',intensity='strong',
            focus_start_x=.3,focus_start_y=.2,focus_end_x=.7,focus_end_y=.8)]
        graph=append_visual_beats('[picture]null[vout]',plan,width=180,height=320)
        self.assertIn('[beatbase0]split=3[focusbed0][focusblurinput0][focussharp0]',graph)
        self.assertIn('gblur=sigma=12:steps=2',graph)
        self.assertIn("crop=w=90:h=96",graph)
        self.assertIn(r"min(max((t-0.400)/2.000\,0)\,1)",graph)
        self.assertNotIn('depth',graph)

    def test_paper_tear_freezes_the_outgoing_frame_into_bounded_strips(self):
        plan=fixture()
        plan.finishing.visual_beats=[VisualBeat(start=1,end=1.7,preset='paper_tear',intensity='strong',
            boundary_index=1,tear_direction='left')]
        graph=append_visual_beats('[picture]null[vout]',plan,width=180,height=320)
        self.assertIn('[beatbase0]split=2[tearbed0][tearoutgoing0]',graph)
        self.assertIn('trim=start=0.900:end=1.000,reverse,trim=end_frame=1',graph)
        self.assertIn('split=9[tearstrip0_0]',graph)
        self.assertEqual(graph.count('color=0xF7F1E3@0.96'),9)
        self.assertIn(r"overlay=x='-w*min(max((t-1.000)/0.700\,0)\,1)'",graph)

    def test_dolly_zoom_builds_only_a_bounded_crop_and_scale_illusion(self):
        plan=fixture()
        plan.finishing.visual_beats=[VisualBeat(start=0,end=3,preset='dolly_zoom',intensity='strong',
            dolly_clip_index=0,dolly_direction='push_in',dolly_anchor_x=.3,dolly_anchor_y=.7)]
        graph=append_visual_beats('[picture]null[vout]',plan,width=180,height=320)
        self.assertIn('[beatbase0]split=2[dollybed0][dollysource0]',graph)
        self.assertIn(r"scale=w='trunc(180*(1+0.20*min(max((t-0.000)/3.000\,0)\,1))/2)*2'",graph)
        self.assertIn("crop=w=180:h=320:x='(iw-ow)*0.3000':y='(ih-oh)*0.7000'",graph)
        self.assertNotIn('parallax',graph)

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

    def test_voice_note_draws_a_caption_aware_real_audio_card(self):
        tools=FinishingTools(visual_beats=[dict(start=.2,end=2.8,preset='voice_note',intensity='standard',position='lower')])
        ass=render_ass([dict(start=0,end=3,text='Caption wins.',position='lower_safe')],width=180,height=320,treatments=tools)
        self.assertIn('0:03',ass)
        self.assertIn(r'\move(',ass)
        self.assertGreaterEqual(sum(line.startswith('Dialogue: -1,') for line in ass.splitlines()),12)
        self.assertTrue(any(line.startswith('Dialogue: -3,') for line in ass.splitlines()))
        self.assertTrue(any(line.startswith('Dialogue: 0,') for line in ass.splitlines()))

    def test_post_wall_staggers_source_backed_cards_below_captions(self):
        tools=FinishingTools(visual_beats=[dict(start=.2,end=3.2,preset='post_wall',intensity='strong',
            post_texts=['Real footage','Local render','Review first'])])
        ass=render_ass([dict(start=0,end=3.5,text='Caption wins.',position='lower_safe')],width=180,height=320,treatments=tools)
        for text in ('Real footage','Local render','Review first'):
            self.assertIn(text,ass)
        panels=[line for line in ass.splitlines() if line.startswith('Dialogue: -3,')]
        self.assertEqual(len(panels),3)
        self.assertEqual(len({line.split(',')[1] for line in panels}),3)
        self.assertTrue(all(r'\move(' in line for line in panels))
        self.assertTrue(any(line.startswith('Dialogue: 0,') for line in ass.splitlines()))

    def test_sketch_words_draw_separate_marker_words_below_captions(self):
        tools=FinishingTools(visual_beats=[dict(start=.2,end=1.8,preset='sketch_words',intensity='strong',
            position='lower',sketch_text='KEEP IT REAL')])
        ass=render_ass([dict(start=0,end=2,text='Caption wins.',position='lower_safe')],width=180,height=320,treatments=tools)
        for word in ('KEEP','IT','REAL'):
            self.assertIn(word,ass)
        words=[line for line in ass.splitlines() if line.startswith('Dialogue: -1,') and r'\fnDejaVu Sans' in line]
        self.assertEqual(len(words),3)
        self.assertEqual(len({line.split(',')[1] for line in words}),3)
        self.assertIn(r'\fscx12\t(',ass)
        self.assertTrue(any(line.startswith('Dialogue: 0,') for line in ass.splitlines()))

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
        tear_plan=fixture()
        tear_plan.clips.append(tear_plan.clips[0].model_copy(update={'source_in':3,'source_out':5}))
        tear_plan.finishing=FinishingTools(visual_beats=[dict(start=3,end=3.7,preset='paper_tear',boundary_index=1,tear_direction='left')])
        validate_finishing(tear_plan,[])
        moved=apply_timeline_adjustments(tear_plan,[dict(clip_index=0,source_in=.2)])
        self.assertFalse(moved.finishing.visual_beats,'boundary transitions must be explicitly reselected after timeline edits')
        misplaced=tear_plan.model_copy(deep=True);misplaced.finishing.visual_beats[0].start=2.9
        with self.assertRaisesRegex(ValueError,'start exactly'):validate_finishing(misplaced,[])
        competing=tear_plan.model_copy(deep=True);competing.clips[1].transition='cross_dissolve'
        with self.assertRaisesRegex(ValueError,'another transition'):validate_finishing(competing,[])
        dolly_plan=fixture();dolly_plan.finishing=FinishingTools(visual_beats=[dict(start=0,end=3,preset='dolly_zoom',
            dolly_clip_index=0,dolly_direction='push_in',dolly_anchor_x=.5,dolly_anchor_y=.5)])
        validate_finishing(dolly_plan,[])
        moved=apply_timeline_adjustments(dolly_plan,[dict(clip_index=0,source_in=.2)])
        self.assertFalse(moved.finishing.visual_beats,'shot-bound camera effects must be reselected after timeline edits')
        partial=dolly_plan.model_copy(deep=True);partial.finishing.visual_beats[0].end=2.9
        with self.assertRaisesRegex(ValueError,'exactly one complete clip'):validate_finishing(partial,[])
        camera_conflict=dolly_plan.model_copy(deep=True);camera_conflict.clips[0].visual_preset='punch_in'
        with self.assertRaisesRegex(ValueError,'another camera move'):validate_finishing(camera_conflict,[])
        collision=fixture()
        collision.finishing=FinishingTools(
            callouts=[dict(start=.5,end=1.5,text='Existing card')],
            visual_beats=[dict(start=1,end=2,preset='comment_drop',comment_text='New card')],
        )
        with self.assertRaisesRegex(ValueError,'cannot overlap another text callout'):
            validate_finishing(collision,[])
        collision.finishing=FinishingTools(
            callouts=[dict(start=.5,end=1.5,text='Existing card')],
            visual_beats=[dict(start=1,end=2.5,preset='sketch_words',sketch_text='REAL WORDS')],
        )
        with self.assertRaisesRegex(ValueError,'cannot overlap another text callout'):
            validate_finishing(collision,[])
        collision.finishing=FinishingTools(
            callouts=[dict(start=.5,end=1.5,text='Existing card')],
            visual_beats=[dict(start=1,end=3,preset='post_wall',post_texts=['One','Two'])],
        )
        with self.assertRaisesRegex(ValueError,'cannot overlap another text callout'):
            validate_finishing(collision,[])
        collision.finishing=FinishingTools(
            callouts=[dict(start=.5,end=1.5,text='Existing card')],
            visual_beats=[dict(start=1,end=2.5,preset='voice_note')],
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

    def test_simulated_rack_focus_keeps_the_window_sharp_and_audio_continuous(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'focus-source.mp4';captions=root/'captions.ass';output=root/'focus-output.mp4'
            self.ff('-f','lavfi','-i','testsrc2=s=180x320:r=30:d=2.5',
                '-f','lavfi','-i','sine=frequency=440:sample_rate=48000:duration=2.5',
                '-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac',str(source))
            tools=FinishingTools(visual_beats=[dict(start=.2,end=2.2,preset='rack_focus',intensity='strong',
                focus_start_x=.35,focus_start_y=.35,focus_end_x=.65,focus_end_y=.65)])
            plan=TalkingHeadEditPlan(schema_version='1.5',recipe='talking_head',
                clips=[dict(asset_id=uuid4(),source_in=0,source_out=2.5,crop='center_fill')],
                caption_style='clean_blue_v1',audio_preset='spoken_voice_v1',end_card='none',
                editorial_summary='Simulated focus verification.',finishing=tools)
            captions.write_text(render_ass([],width=180,height=320,treatments=tools))
            _render_video([(source,0,2.5)],plan,captions,output,60,width=180,height=320)
            def frame(path,t):
                return self.ff('-ss',str(t),'-i',str(path),'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','pipe:1')
            original,rendered=frame(source,1.2),frame(output,1.2)
            def mean_error(box):
                x0,y0,x1,y1=box;values=[]
                for y in range(y0,y1):
                    for x in range(x0,x1):
                        at=(y*180+x)*3
                        values.extend(abs(original[at+c]-rendered[at+c]) for c in range(3))
                return sum(values)/len(values)
            inside=mean_error((60,130,120,190));outside=mean_error((0,10,35,90))
            self.assertLess(inside,outside*.75,'the moving focus window should retain more source detail than the blurred bed')
            pcm=array.array('h',self.ff('-i',str(output),'-vn','-ac','1','-ar','8000','-f','s16le','pipe:1'))
            for t in (.1,.8,1.6,2.3):
                samples=pcm[round(t*8000):round((t+.1)*8000)]
                self.assertGreater(sum(abs(v) for v in samples)/len(samples),500)
            self.assertIsNone(rendered_audio_packet_error(output,60))

    def test_paper_tear_reveals_the_real_incoming_clip_and_keeps_audio_continuous(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'tear-source.mp4';captions=root/'captions.ass';output=root/'tear-output.mp4'
            self.ff('-f','lavfi','-i',"color=c=red:s=180x320:r=30:d=3,drawbox=x=0:y=0:w=iw:h=ih:c=blue:t=fill:enable='gte(t,1.5)'",
                '-f','lavfi','-i','sine=frequency=440:sample_rate=48000:duration=3',
                '-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac',str(source))
            asset=uuid4()
            tools=FinishingTools(visual_beats=[dict(start=1.5,end=2.2,preset='paper_tear',intensity='strong',
                boundary_index=1,tear_direction='left')])
            plan=TalkingHeadEditPlan(schema_version='1.5',recipe='talking_head',
                clips=[dict(asset_id=asset,source_in=0,source_out=1.5,crop='center_fill'),
                       dict(asset_id=asset,source_in=1.5,source_out=3,crop='center_fill')],
                caption_style='clean_blue_v1',audio_preset='spoken_voice_v1',end_card='none',
                editorial_summary='Paper transition verification.',finishing=tools)
            validate_finishing(plan,[])
            captions.write_text(render_ass([],width=180,height=320,treatments=tools))
            _render_video([(source,0,1.5),(source,1.5,3)],plan,captions,output,60,width=180,height=320)
            def frame(t):return self.ff('-ss',str(t),'-i',str(output),'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','pipe:1')
            def colour_counts(buf):
                pixels=[tuple(buf[i:i+3]) for i in range(0,len(buf),3)]
                return (sum(r>b+60 for r,g,b in pixels),sum(b>r+60 for r,g,b in pixels))
            early=colour_counts(frame(1.55));middle=colour_counts(frame(1.85));after=colour_counts(frame(2.3))
            self.assertGreater(early[0],early[1]*3,'the frozen outgoing frame should initially cover the cut')
            self.assertGreater(middle[0],1000);self.assertGreater(middle[1],1000)
            self.assertGreater(after[1],after[0]*20,'the real incoming clip must remain after the tear')
            pcm=array.array('h',self.ff('-i',str(output),'-vn','-ac','1','-ar','8000','-f','s16le','pipe:1'))
            for t in (1.4,1.6,2.1,2.4):
                samples=pcm[round(t*8000):round((t+.1)*8000)]
                self.assertGreater(sum(abs(v) for v in samples)/len(samples),500)
            self.assertIsNone(rendered_audio_packet_error(output,60))

    def test_dolly_zoom_enlarges_the_real_picture_and_keeps_audio_continuous(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'dolly-source.mp4';captions=root/'captions.ass';output=root/'dolly-output.mp4'
            self.ff('-f','lavfi','-i','color=c=blue:s=180x320:r=30:d=3,drawbox=x=60:y=110:w=60:h=100:c=red:t=fill',
                '-f','lavfi','-i','sine=frequency=440:sample_rate=48000:duration=3',
                '-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac',str(source))
            asset=uuid4()
            tools=FinishingTools(visual_beats=[dict(start=0,end=2,preset='dolly_zoom',intensity='strong',
                dolly_clip_index=0,dolly_direction='push_in',dolly_anchor_x=.5,dolly_anchor_y=.5)])
            plan=TalkingHeadEditPlan(schema_version='1.5',recipe='talking_head',
                clips=[dict(asset_id=asset,source_in=0,source_out=2,crop='center_fill'),
                       dict(asset_id=asset,source_in=2,source_out=3,crop='center_fill')],
                caption_style='clean_blue_v1',audio_preset='spoken_voice_v1',end_card='none',
                editorial_summary='Dolly-style crop verification.',finishing=tools)
            validate_finishing(plan,[])
            captions.write_text(render_ass([],width=180,height=320,treatments=tools))
            _render_video([(source,0,2),(source,2,3)],plan,captions,output,60,width=180,height=320)
            def frame(t):return self.ff('-ss',str(t),'-i',str(output),'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','pipe:1')
            def red_pixels(buf):
                return sum(buf[i] > buf[i+2] + 60 for i in range(0,len(buf),3))
            early,late=red_pixels(frame(.05)),red_pixels(frame(1.85))
            self.assertGreater(late,early*1.2,'the fixed-anchor push should enlarge the real centre subject')
            pcm=array.array('h',self.ff('-i',str(output),'-vn','-ac','1','-ar','8000','-f','s16le','pipe:1'))
            for t in (.1,1,1.9,2.4):
                samples=pcm[round(t*8000):round((t+.1)*8000)]
                self.assertGreater(sum(abs(v) for v in samples)/len(samples),500)
            self.assertIsNone(rendered_audio_packet_error(output,60))
