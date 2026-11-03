import json
import unittest
from contextlib import contextmanager
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

from fastapi import HTTPException
from pydantic import ValidationError

from app.blooper_incidents import build_incidents, validate_incident_selection
from app.blooper_focus import selected_blooper_scope, validate_blooper_scope, attach_word_times
from app.concept_inventory import compact_inventory, public_inventory, validate_concepts, MAX_INVENTORY_CHARACTERS
from app.concept_provider import generate_concepts
from app.concept_schemas import ConceptRequestCreate, ConceptSelection, BlooperConceptProposals
from app.concepts import request_concepts, render_selected_concepts
from app.context_links import context_links
from app.config import Settings


def passage(text, start=0, identity="a", index=1, step=.3):
    words=[dict(text=word,start=round(start+i*step,3),end=round(start+(i+1)*step,3)) for i,word in enumerate(text.split())]
    return dict(id=index,asset_id=identity,start_seconds=start,end_seconds=words[-1]['end'],text=text,words=words)


def source(identity="a"):
    return dict(id=identity,sha256="fixture-"+identity,source_name="camera.mp4",display_name="Fixture",
        project_name="Fixture",mime_type="video/mp4",media_role="auto",manifest={})


def bundle_fixture():
    request=ConceptRequestCreate(id=uuid4(),reel_kind="bloopers")
    segments=[passage("The new Wobbly Widget, that is hard to say.")]
    inventory=compact_inventory([source()],segments,request)
    bundle=inventory['evidence'][0]
    proposal=dict(title="The widget stumble",angle="Keep the attempted name and the speaker's own pronunciation comment.",
        script=[dict(evidence_id=bundle['evidence_id'],role="payoff")],visuals=[],incident_ids=[bundle['incident_id']])
    return request,inventory,proposal


class IncidentBundleTests(unittest.TestCase):
    def test_attempt_and_real_comment_form_one_immutable_bundle(self):
        raw=passage("The new Wobbly Widget, that is hard to say.")
        before=deepcopy(raw)
        bundle=build_incidents([raw])[0]
        self.assertEqual(bundle['text'],raw['text'])
        self.assertIn('Wobbly Widget',bundle['setup']['text'])
        self.assertIn('hard to say',bundle['reaction']['text'])
        self.assertEqual(bundle['reaction']['kind'],'recorded_self_comment')
        self.assertEqual(bundle['confidence'],'possible')
        self.assertEqual(bundle['catalogue_ids'],[1])
        self.assertEqual(raw,before)
        self.assertEqual(build_incidents([raw]),[bundle])
        self.assertTrue(-(2**53)<bundle['evidence_id']<0)

    def test_later_incidents_in_a_long_chunk_are_not_discarded(self):
        text=("A long clean introduction with details about our products. "*8
              +"The new Wobbly Widget, that is hard to say. "
              +"Here is a separate recorded explanation of our cream. I forgot my lines.")
        raw=passage(text)
        self.assertGreater(raw['end_seconds'],25)
        bundles=build_incidents([raw])
        self.assertGreaterEqual(len(bundles),2)
        self.assertTrue(any('forgot my lines' in b['text'] for b in bundles))
        self.assertTrue(all(b['end']-b['start']<=12 for b in bundles))
        self.assertTrue(all('long clean introduction' not in b['text'] for b in bundles))

    def test_laughter_clean_repeats_and_unattached_corrections_are_insufficient(self):
        for text in ('[laughter]', 'I forgot my lines.', 'Oops!',
            'A complete clean recorded claim. A complete clean recorded claim.',
            'Here is our gentle cream. [laughter]',
            'Here is our gentle cream. Oops!'):
            with self.subTest(text=text):
                self.assertEqual(build_incidents([passage(text)]),[])

    def test_instructional_or_hypothetical_clues_do_not_make_an_incident(self):
        for text in ('If you forgot the line, say I forgot my lines.',
                     "When anyone asks a question, say I got that wrong.",
                     "The example phrase is I forgot my lines."):
            self.assertEqual(build_incidents([passage(text)]),[])

    def test_oops_requires_and_keeps_its_actual_nearby_response(self):
        raw=passage('This is our new product. Oops! [laughter]')
        bundle=build_incidents([raw])[0]
        self.assertEqual(bundle['reaction']['text'],'[laughter]')
        self.assertEqual(bundle['reaction']['kind'],'transcribed_laughter')
        self.assertIn('our new product',bundle['setup']['text'])

    def test_question_and_uncertainty_keep_the_real_unresolved_ending(self):
        bundle=build_incidents([passage("This restores your hair. What does it restore? I don't know. What does it")])[0]
        self.assertEqual(bundle['blooper_signals'],['question_then_uncertainty'])
        self.assertTrue(bundle['text'].endswith("I don't know."))
        self.assertIn('What does it restore?',bundle['text'])
        self.assertEqual(build_incidents([passage("This is a complete statement. I don't know.")]),[])

    def test_context_never_bridges_recordings_missing_words_or_long_gaps(self):
        attempt=passage('This is our new product.')
        response=passage('Oops! [laughter]',start=attempt['end_seconds']+.1,index=2)
        self.assertTrue(build_incidents([attempt,response]))
        self.assertFalse(build_incidents([attempt,{**response,'asset_id':'b'}]))
        self.assertFalse(build_incidents([attempt,passage('Oops! [laughter]',start=20,index=2)]))
        missing=passage('A missing timing fragment.',start=attempt['end_seconds'],index=3)
        missing.pop('words')
        self.assertFalse(build_incidents([attempt,missing,response]))

    def test_corrupt_or_incomplete_word_data_cannot_create_precise_bundles(self):
        for change in (lambda s:s['words'].pop(),lambda s:s['words'][0].update(start=float('nan')),
                       lambda s:s['words'][3].update(start=0),lambda s:s.pop('words')):
            raw=passage('The new Wobbly Widget, that is hard to say.')
            change(raw)
            self.assertEqual(build_incidents([raw]),[])

    def test_source_inspection_is_limited_to_cached_transcripts_with_clues(self):
        raw=passage(('A long clean introduction. '*30)+'The new Wobbly Widget, that is hard to say.')
        clean=passage('Here is an ordinary complete claim.',identity='b',index=2)
        transcript=[dict(words=raw['words'])]
        with patch('app.config.get_settings',return_value=object()),patch('app.content_catalog._transcript_segments',return_value=transcript) as read:
            result=attach_word_times([source(),source('b')],[raw,clean],include_long_incidents=True)
        read.assert_called_once()
        self.assertTrue(result[0]['words'])
        self.assertFalse(result[1]['words'])

    def test_avoid_ranges_are_not_bridged_by_a_bundle_even_when_between_words(self):
        first=passage('This is our new product.')
        second=passage('Oops! [laughter]',start=first['end_seconds']+.3,index=2)
        self.assertTrue(build_incidents([first,second]))
        avoid=[dict(asset_id='a',start_seconds=first['end_seconds']+.05,end_seconds=first['end_seconds']+.15)]
        self.assertEqual(build_incidents([first,second],avoid),[])

    def test_normalized_word_offsets_retain_source_ranges_after_unicode_text(self):
        raw=passage('The Straße product name, that is hard to say.')
        bundle=build_incidents([raw])[0]
        expected=next(w['start'] for w in raw['words'] if w['text']=='hard')
        self.assertEqual(bundle['incident']['start'],expected)
        self.assertEqual(build_incidents([{**raw,'start_seconds':None}]),[])

    def test_manual_job_hints_reuse_words_deduplicate_and_respect_avoid(self):
        from app.blooper_incidents import manual_incident_hints
        raw=passage('The new Wobbly Widget, that is hard to say.')
        asset=dict(asset_id='a',sha256='same',has_audio=True,transcript_segments=[dict(start=raw['start_seconds'],end=raw['end_seconds'],text=raw['text'],words=raw['words'])])
        before=deepcopy(asset)
        hints=manual_incident_hints([asset,{**asset,'asset_id':'duplicate'}])
        self.assertEqual(len(hints),1)
        self.assertEqual(hints[0]['asset_id'],'a')
        self.assertNotIn('text',hints[0])
        self.assertEqual(asset,before)
        asset['source_evidence']=dict(user_ranges=[dict(role='avoid',start_seconds=0,end_seconds=1)])
        self.assertEqual(manual_incident_hints([asset]),[])

    def test_optional_manual_hints_fit_the_existing_context_ceiling(self):
        from app.editor_provider import _public_context, _base_public_context
        raw=passage('The new Wobbly Widget, that is hard to say.')
        context=dict(job=dict(editorial_policy=dict(bloopers_requested=True)),assets=[dict(asset_id='a',has_audio=True,
            transcript_segments=[dict(start=0,end=raw['end_seconds'],text=raw['text'],words=raw['words'])])])
        public=_public_context(context,5000)
        self.assertTrue(public['recorded_incident_hints'])
        self.assertLessEqual(len(json.dumps(public,separators=(',',':'),ensure_ascii=False)),5000)
        ceiling=len(json.dumps(_base_public_context(context,5000),separators=(',',':'),ensure_ascii=False))+5
        tight=_public_context(context,ceiling)
        self.assertNotIn('recorded_incident_hints',tight)
        self.assertEqual(public['assets'][0]['transcript_segments'],tight['assets'][0]['transcript_segments'])


class ModernConceptTests(unittest.TestCase):
    def test_selected_bundle_has_a_structured_incident_citation(self):
        request,inventory,proposal=bundle_fixture()
        result=validate_concepts(dict(concepts=[proposal]),inventory,request.id)[0]
        self.assertEqual(result['script'][0]['text'],inventory['evidence'][0]['text'])
        self.assertEqual(result['blooper_review']['incident_count'],1)
        self.assertEqual(result['blooper_review']['semantic_judgement'],'human_review_required')
        bad=deepcopy(proposal);bad['incident_ids']=['unknown']
        self.assertEqual(validate_concepts(dict(concepts=[bad]),inventory,request.id),[])
        self.assertEqual(len(validate_concepts(dict(concepts=[bad,proposal]),inventory,request.id)),1)
        self.assertEqual(validate_concepts(dict(concepts=[]),inventory,request.id),[])

    def test_unknown_and_missing_incident_citations_cannot_bypass_the_contract(self):
        request,inventory,proposal=bundle_fixture()
        proposal.pop('incident_ids')
        with self.assertRaises(ValidationError):
            validate_concepts(dict(concepts=[proposal]),inventory,request.id)
        schema=BlooperConceptProposals.model_json_schema()
        for definition in [schema,*schema['$defs'].values()]:
            if definition.get('type')=='object':
                self.assertFalse(definition['additionalProperties'])
                self.assertEqual(set(definition['required']),set(definition['properties']))

    def test_overlapping_versions_of_the_same_incident_cannot_be_selected_together(self):
        _,inventory,_=bundle_fixture()
        first=inventory['evidence'][0];second={**deepcopy(first),'incident_id':'different-id'}
        with self.assertRaisesRegex(ValueError,'overlap'):
            validate_incident_selection([first,second],[first['incident_id'],second['incident_id']])

    def test_renderer_scope_protects_setup_and_response_not_only_the_clue(self):
        request,inventory,proposal=bundle_fixture()
        selected=validate_concepts(dict(concepts=[proposal]),inventory,request.id)[0]
        scope=selected_blooper_scope(dict(selected_concept=selected))
        beat=selected['script'][0]
        clip=SimpleNamespace(asset_id=beat['asset_id'],source_in=beat['start'],source_out=beat['end'])
        validate_blooper_scope(SimpleNamespace(clips=[clip]),dict(selected_blooper_scope=scope))
        clip.source_in=beat['incident']['start']
        with self.assertRaisesRegex(ValueError,'setup/reaction'):
            validate_blooper_scope(SimpleNamespace(clips=[clip]),dict(selected_blooper_scope=scope))

    def test_fresh_incomplete_discovery_does_not_queue_or_call_a_model(self):
        request=ConceptRequestCreate(id=uuid4(),reel_kind='bloopers')
        inventory=compact_inventory([source()],[passage('Oops!')],request)
        database=Mock();database.execute.return_value.fetchone.side_effect=[None,dict(count=0)]
        @contextmanager
        def connection(): yield database
        with patch('app.concepts.connection',connection),patch('app.concepts.assert_ai_budget'),patch('app.concepts.load_inventory',return_value=(inventory,{})),patch('app.concepts.generate_concepts') as provider:
            with self.assertRaises(HTTPException) as error:
                request_concepts(request)
        self.assertIn('No complete recorded blooper bundles',error.exception.detail)
        self.assertFalse(any('INSERT' in c.args[0] for c in database.execute.call_args_list))
        provider.assert_not_called()

    def test_budget_never_splits_a_bundle_and_does_not_grow_the_inventory_limit(self):
        rows=[source(str(i)) for i in range(60)]
        segments=[passage('The new Wobbly Widget, that is hard to say.',identity=str(i),index=i+1) for i in range(60)]
        inventory=compact_inventory(rows,segments,ConceptRequestCreate(id=uuid4(),reel_kind='bloopers'))
        self.assertTrue(inventory['evidence'])
        self.assertLessEqual(len(json.dumps(public_inventory(inventory),ensure_ascii=False)),MAX_INVENTORY_CHARACTERS)
        for item in inventory['evidence']:
            self.assertTrue(item['setup'] and item['reaction'] and item['incident_id'])
            validate_incident_selection([item],[item['incident_id']])

    def test_concept_producer_uses_one_strict_call_without_private_paths(self):
        _,inventory,_=bundle_fixture()
        settings=Settings(database_url='postgresql://example.invalid/test',upload_hook_secret='x'*32)
        with patch('app.concept_provider.usable_chatgpt_credentials',return_value=dict(access_token='fixture')),patch('app.concept_provider._request_plan',return_value=(dict(concepts=[]),{})) as call:
            generate_concepts(inventory,'text_only',settings)
        call.assert_called_once()
        task=call.call_args.kwargs['structured_task']
        self.assertEqual(task['schema'],BlooperConceptProposals.model_json_schema())
        self.assertIn('Cite the incident_ids',task['content'][0]['text'])
        self.assertNotIn('_storage_key',task['content'][0]['text'])

    def test_new_selection_rechecks_bundle_and_existing_job_remains_idempotent(self):
        request,inventory,proposal=bundle_fixture()
        concept=validate_concepts(dict(concepts=[proposal]),inventory,request.id)[0]
        concept['script'][0].pop('reaction')
        session=dict(id=request.id,status='ready',concepts=[concept],inventory=inventory,reel_kind='bloopers')
        database=Mock()
        database.execute.return_value.fetchone.return_value=session
        database.execute.return_value.fetchall.return_value=[]
        @contextmanager
        def connection(): yield database
        payload=ConceptSelection(concept_ids=[concept['id']])
        with patch('app.concepts.connection',connection):
            with self.assertRaises(HTTPException) as error:
                render_selected_concepts(request.id,payload,None)
        self.assertEqual(error.exception.status_code,409)
        self.assertFalse(any('INSERT' in c.args[0] for c in database.execute.call_args_list))
        job=uuid4()
        database.execute.return_value.fetchall.return_value=[dict(concept_id=concept['id'],job_id=job)]
        with patch('app.concepts.connection',connection):
            result=render_selected_concepts(request.id,payload,None)
        self.assertEqual(result['jobs'][0]['job_id'],str(job))


class ContextLinkTests(unittest.TestCase):
    def test_adjacent_reference_numbers_and_product_aliases_are_explicit_evidence(self):
        evidence=[dict(evidence_id=1,asset_id='a',start=0,end=2,text='Our soft cream is available.'),
            dict(evidence_id=2,asset_id='a',start=2.1,end=4,text='It is not for children under 3.',needs_context=True)]
        links=context_links(evidence,[dict(id='cream',name='Gentle Cream',aliases=['soft cream'])])
        self.assertEqual(links['passages'][0]['spoken_product_mentions'],['Gentle Cream'])
        self.assertEqual(links['passages'][1]['inspect_previous_evidence_id'],1)
        self.assertEqual(links['passages'][1]['keep_qualifiers_and_numbers'],['not','3'])
        self.assertEqual(links['hosted_retrieval_calls'],0)

    def test_missing_preceding_context_is_not_borrowed_from_a_different_source(self):
        evidence=[dict(evidence_id=1,asset_id='a',start=0,end=2,text='Our cream is ready.'),
            dict(evidence_id=2,asset_id='b',start=2.1,end=4,text='This is not the same product.')]
        link=context_links(evidence)['passages'][0]
        self.assertTrue(link['preceding_context_unavailable'])
        self.assertNotIn('inspect_previous_evidence_id',link)

    def test_shared_openings_are_comparisons_not_equivalent_product_claims(self):
        evidence=[dict(evidence_id=i,asset_id=str(i),start=0,end=3,text=t) for i,t in enumerate([
            'Here is our complete recorded product demonstration with cream.',
            'Here is our complete recorded product demonstration without cream.',
            'Here is our complete recorded product demonstration with soap.'])]
        links=context_links(evidence,[dict(id='cream',name='cream'),dict(id='soap',name='soap')])
        self.assertEqual(links['compare_takes'][0]['evidence_ids'],[0,1])
        self.assertIn('not equivalent takes',links['note'])
        self.assertNotIn('equivalent',links['compare_takes'][0]['basis'])

    def test_small_budgets_drop_optional_hints_instead_of_exceeding_the_limit(self):
        evidence=[dict(evidence_id=i,asset_id='a',start=i,end=i+.9,text='This is not the only option for 42 people.') for i in range(30)]
        links=context_links(evidence,character_budget=500)
        self.assertLessEqual(len(json.dumps(links,ensure_ascii=False)),500)
        self.assertIsNone(context_links(evidence,character_budget=10))
