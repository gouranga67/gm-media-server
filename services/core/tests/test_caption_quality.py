from copy import deepcopy
import unittest
from pydantic import ValidationError

from app.caption_layout import (phrase_groups, sentence_case_events, single_caption_lane,
    aligned_caption_words, balanced_lines, caption_lines, text_width)
from app.creative_treatments import Callout
from app.edit_renderer import render_ass
from app.finishing_tools import FinishingTools
from app.subtitle_document import SubtitleCue, validate_cues, parse_ass


def words(text):
    return [dict(text=w, start=i*.25, end=i*.25+.22) for i,w in enumerate(text.split())]


class CaptionQualityTests(unittest.TestCase):
    def test_source_backed_numeric_claim_does_not_leave_clients_hanging(self):
        source=words("generated 40 million dollars in revenue for clients")
        groups=phrase_groups(source)
        self.assertEqual([w for g in groups for w in g],source)
        self.assertGreaterEqual(len(groups[-1]),2)
        self.assertTrue(all(len(g)<=7 and g[-1]['end']-g[0]['start']<=2.6 for g in groups))

    def test_sentence_and_pause_boundaries_beat_visual_balance(self):
        source=words("This works. Here is why we recommend it.")
        groups=phrase_groups(source)
        self.assertEqual([w['text'] for w in groups[0]],['This','works.'])
        source[2]['start']+=.8
        source[2]['end']+=.8
        self.assertEqual([w['text'] for w in phrase_groups(source)[0]],['This','works.'])

    def test_sentence_case_continues_across_cards_and_preserves_names(self):
        events=[dict(start=0,end=1,text="we use NASA"),dict(start=1,end=2,text="and i love it."),dict(start=2,end=3,text="do you?")]
        original=deepcopy(events)
        output=sentence_case_events(events)
        self.assertEqual([e['text'] for e in output],['We use NASA','and I love it.','Do you?'])
        self.assertEqual(events,original)
        self.assertEqual(sentence_case_events([dict(start=0,end=1,text='eBay works')],[dict(replacement_text='eBay')])[0]['text'],'eBay works')
        for text in ('eBay works. iPhone works.', '$40 million in revenue.'):
            self.assertEqual(sentence_case_events([dict(start=0,end=1,text=text)])[0]['text'],text)

    def test_punctuation_is_restored_only_with_exact_lexical_agreement(self):
        segment=dict(text="Do you love castor oil?",words=words('do you love castor oil'))
        self.assertEqual(aligned_caption_words(segment)[-1]['text'],'oil?')
        segment['text']='Do you love coconut oil?'
        self.assertEqual(aligned_caption_words(segment),segment['words'])

    def test_overlapping_cues_keep_every_word_in_a_single_lane(self):
        events=[dict(start=0,end=2,text='we love castor oil'),dict(start=1.8,end=3,text='castor oil today')]
        output=single_caption_lane(events)
        self.assertEqual(output,[dict(start=0,end=3,text='we love castor oil today')])
        self.assertEqual(len(events),2)

    def test_overlap_rejection_exempts_hidden_cues_not_other_positions(self):
        a=dict(id='a',start=0,end=2,text='Hello')
        b=dict(id='b',start=1,end=3,text='World',position='upper')
        with self.assertRaisesRegex(ValueError,'cannot overlap'):
            validate_cues([a,b],3)
        self.assertEqual(len(validate_cues([a,{**b,'hidden':True}],3)),2)

    def test_manual_line_breaks_survive_save_and_render(self):
        cue=SubtitleCue(id='a',start=0,end=2,text='  Castor   oil\r\nfor your skin  ')
        self.assertEqual(cue.text,'Castor oil\nfor your skin')
        ass=render_ass([dict(start=0,end=2,text=cue.text)])
        self.assertEqual(parse_ass(ass)[0]['text'],cue.text)
        with self.assertRaises(ValidationError):
            SubtitleCue(id='b',start=0,end=2,text='one\ntwo\nthree')

    def test_measured_layout_fits_two_lines_at_every_delivery_aspect(self):
        for width,height in ((540,960),(1080,1920),(540,540),(960,540)):
            size=round(34*height/960)
            usable=width*.74
            text,size=caption_lines('generated 40 million dollars in revenue for','DejaVu Sans',size,usable)
            self.assertLessEqual(len(text.splitlines()),2)
            self.assertTrue(all(text_width(row,'DejaVu Sans',size)<=usable for row in text.splitlines()))
        with self.assertRaisesRegex(ValueError,'split it'):
            caption_lines('very long manual text '*30,'DejaVu Sans',34,400)
        text,_=caption_lines('Generated 40 million dollars','DejaVu Sans',34,404)
        self.assertNotIn('40\nmillion',text)

    def test_per_cue_lower_position_uses_same_platform_safe_band(self):
        for platform,y in (('tiktok',691),('instagram',730),('all_social',720)):
            self.assertIn(f'\\pos(270,{y})',render_ass([dict(start=0,end=1,text='Safe',position='lower_safe')],target_platform=platform))

    def test_headline_and_subtitles_are_distinct_and_number_is_not_invented(self):
        tools=FinishingTools(callouts=[Callout(start=.5,end=2.5,text='$40 million in client revenue',style='headline')])
        events=[dict(start=0,end=3,text='Generated 40 million dollars in revenue.')]
        ass=render_ass(events,treatments=tools)
        self.assertIn('$40 MILLION',ass)
        self.assertIn('IN CLIENT REVENUE',ass)
        self.assertIn('Dialogue: -3,',ass)
        self.assertIn('\\fs48',ass)
        self.assertEqual(' '.join(parse_ass(ass)[0]['text'].split()),events[0]['text'])

