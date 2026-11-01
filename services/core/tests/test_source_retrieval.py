import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock, patch
from uuid import uuid4

from PIL import Image

from app.concept_inventory import (MAX_INVENTORY_CHARACTERS, _sample, balanced_sources,
    compact_inventory, load_inventory, public_inventory)
from app.concept_schemas import ConceptRequestCreate
from app.editor_visual_context import high_impact_visuals
from app.source_retrieval import focus_query, focused_passages, match_score, source_score
from test_concepts import asset


class SharedRetrievalTests(unittest.TestCase):
    def test_exact_words_and_product_aliases_do_not_become_substring_matches(self):
        products=[{"name":"Castor oil cream","aliases":["night balm"]}]
        query=focus_query("Please make a reel about night balm",products)
        self.assertGreater(match_score("Our castor oil cream feels soft.",query),0)
        self.assertEqual(match_score("The creamery has nightlife.",query),0)
        self.assertEqual(focus_query("Surprise me with a new reel from our library").terms,())
        self.assertEqual(focus_query("Come up with a new reel concept from the footage library we have").terms,())
        self.assertEqual(match_score("ＳＯＡＰ",focus_query("soap")),1)

    def test_query_is_bounded_and_only_contains_quoted_normalized_words(self):
        query=focus_query('soap | !cream "); DROP TABLE assets; -- ' + " ".join(f"term{n}" for n in range(100)))
        self.assertLessEqual(len(query.terms),32)
        self.assertNotIn(";",query.search_text)
        self.assertNotIn("--",query.search_text)
        self.assertNotIn("|",query.search_text)

    def test_incomplete_legacy_evidence_does_not_break_preview_ranking(self):
        source={"source_name":"Soap detail","recognized_text":{"legacy":"unknown"},
            "transcript_segments":[None,{"text":"Soap detail."}]}
        self.assertGreater(source_score(source,focus_query("soap")),0)

    def test_stored_speech_and_ocr_rank_camera_named_sources_before_the_cap(self):
        rows=[{**asset(n,f"group-{n}"),"display_name":f"VID{n}.mp4"} for n in range(70)]
        rows[-1]["manifest"]={"derived":{"ocr":{"lines":[{"text":"Customer review of soap"}]}}}
        chosen=balanced_sources(rows,"soap",3,transcript_matches={str(rows[-2]["id"]):0.1})
        self.assertEqual({row["id"] for row in chosen[:2]},{rows[-1]["id"],rows[-2]["id"]})
        self.assertEqual(len(chosen),3)
        self.assertGreater(source_score(rows[-1],focus_query("soap")),0)

    def test_relevant_group_is_not_diluted_by_many_unrelated_groups(self):
        matches=[{**asset(n,"relevant"),"display_name":"Soap detail"} for n in range(5)]
        unrelated=[{**asset(n+20,f"other-{n}"),"display_name":"Other recording"} for n in range(20)]
        chosen=balanced_sources(unrelated+matches,"soap",5)
        self.assertEqual({r["id"] for r in chosen},{r["id"] for r in matches})

    def test_strongly_labelled_pictures_cannot_use_every_recorded_script_slot(self):
        photos=[{**asset(n),"mime_type":"image/png","display_name":"Soap review product detail"} for n in range(65)]
        speech={**asset(99),"display_name":"VID99.mp4"}
        chosen=balanced_sources(photos+[speech],"soap review",60,transcript_matches={str(speech["id"]):0.1})
        self.assertIn(speech,chosen)
        self.assertEqual(len(chosen),60)

    def test_canonical_keeps_identity_while_duplicate_evidence_contributes_to_ranking(self):
        canonical={**asset(1),"display_name":"VID1.mp4"}
        alias={**canonical,"id":uuid4(),"display_name":"Soap demonstration"}
        unrelated={**asset(2),"display_name":"VID2.mp4"}
        before=deepcopy([canonical,unrelated,alias])
        chosen=balanced_sources([canonical,unrelated,alias],"soap",1)
        self.assertEqual(chosen,[canonical])
        self.assertEqual([canonical,unrelated,alias],before)

    def test_focus_finds_middle_speech_keeps_neighbours_and_source_endings(self):
        passages=[dict(evidence_id=n,start=n*2,end=n*2+1.9,text="The recorded soap detail." if n==19 else f"Recorded passage {n}.") for n in range(36)]
        self.assertNotIn(19,{p["evidence_id"] for p in _sample(passages,12)})
        selected=focused_passages(passages,focus_query("soap"),_sample)
        self.assertTrue({0,18,19,20,35}.issubset(p["evidence_id"] for p in selected))
        self.assertLessEqual(len(selected),12)
        self.assertEqual(focused_passages(passages,focus_query(""),_sample),_sample(passages,12))
        self.assertEqual(focused_passages(passages,focus_query("missing"),_sample),_sample(passages,12))

    def test_focus_does_not_bridge_distant_takes(self):
        passages=[dict(evidence_id=1,start=0,end=3,text="A distant setup."),
            dict(evidence_id=2,start=100,end=103,text="A soap detail."),
            dict(evidence_id=3,start=200,end=203,text="A different ending.")]
        selected=focused_passages(passages,focus_query("soap"),_sample,limit=1)
        self.assertEqual([p["evidence_id"] for p in selected],[2])

    def test_compact_focus_keeps_exact_speech_and_same_budget_without_private_vocabulary(self):
        row=asset(1)
        segments=[dict(id=n+1,asset_id=row["id"],start_seconds=n*3,end_seconds=n*3+2.9,
            text="This is the recorded soap explanation." if n==19 else f"This is recorded passage {n}.") for n in range(40)]
        original=deepcopy(segments)
        inventory=compact_inventory([row],segments,ConceptRequestCreate(id=uuid4(),focus="soap"))
        self.assertTrue(any(p["text"]==segments[19]["text"] and p["start"]==57 for p in inventory["evidence"]))
        report=inventory["_retrieval"]
        self.assertEqual(report["focus_matching_passages_included"],1)
        self.assertEqual(report["speech_passages_available"],40)
        self.assertEqual(report["hosted_retrieval_calls"],0)
        public=json.dumps(public_inventory(inventory),ensure_ascii=False)
        self.assertNotIn("_retrieval_products",public)
        self.assertNotIn("private/",public)
        self.assertLessEqual(len(public),MAX_INVENTORY_CHARACTERS)
        self.assertEqual(segments,original)

    def test_focus_picture_is_included_without_more_images_or_original_reads(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            Image.new("RGB",(90,120),"blue").save(root/"preview.jpg")
            assets=[dict(asset_id=str(uuid4()),mime_type="image/png",source_name=f"IMG{n}.png",
                _preview_key="preview.jpg",transcript_segments=[]) for n in range(30)]
            assets[-1]["source_evidence"]={"recognized_text":[{"text":"Night balm customer review"}]}
            context={"assets":assets,"project":{"brief":"Show castor oil cream reviews"},
                "_retrieval_products":[{"name":"Castor oil cream","aliases":["night balm"]}]}
            before=deepcopy(context)
            content=high_impact_visuals(context,root)
            self.assertEqual(sum(item["type"]=="input_image" for item in content),4)
            mapping=" ".join(item.get("text","") for item in content)
            self.assertIn(assets[-1]["asset_id"],mapping)
            self.assertIn("24 of 30",mapping)
            self.assertIn("do not verify",mapping)
            self.assertEqual(context,before)


class RetrievalInventoryFlowTests(unittest.TestCase):
    def test_scoped_stored_text_query_runs_before_source_cap_and_reports_sampling(self):
        rows=[{**asset(n),"display_name":f"VID{n}.mp4"} for n in range(61)]
        row=rows[-1]
        segments=[dict(id=1,asset_id=row["id"],start_seconds=0,end_seconds=4,text="Here is the recorded soap demonstration.")]
        database=Mock()
        def query(sql,params=()):
            if "SELECT a.id" in sql:
                self.assertIn("a.library_status='active'",sql)
                self.assertIn("m.collection_id=%s",sql)
                result=rows
            elif "SELECT id,name,aliases" in sql:
                result=[]
            elif "WITH focus AS" in sql:
                self.assertIn("role='avoid'",sql)
                self.assertEqual(params[1],[r["id"] for r in rows])
                result=[{"asset_id":row["id"],"text_rank":0.1}]
            elif "SELECT id, asset_id" in sql:
                self.assertIn(row["id"],params[0])
                result=segments
            else:
                result=[]
            return Mock(fetchall=lambda:result)
        database.execute.side_effect=query
        payload=ConceptRequestCreate(id=uuid4(),focus="soap",collection_id=uuid4())
        with patch("app.concept_inventory.attach_word_times",side_effect=lambda rows,segments,**kwargs:segments):
            inventory,coverage=load_inventory(database,payload)
        self.assertEqual(coverage["sources_considered"],60)
        self.assertEqual(coverage["retrieval"]["focus_matching_sources_available"],1)
        self.assertEqual(coverage["retrieval"]["focus_matching_sources_considered"],1)
        self.assertTrue(coverage["retrieval"]["sampling_limited"])
        self.assertEqual(coverage["retrieval"]["focus_matching_passages_included"],1)
        self.assertEqual(inventory["evidence"][0]["text"],segments[0]["text"])
