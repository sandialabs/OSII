"""Synthesis metadata is bounded, optional, grounded and independently inspectable."""
import json
import pytest
from osii.processor_sdk import SynthesisRequest, DocumentMetadata
from osii.processors.text import chat_synthesizer_descriptor
from osii.processors.document_metadata import parse_document_metadata, metadata_prompt
from osii.processors.synthesis import synthesize_bounded, synthesis_call_estimate


def suggested():
    return {"title":{"value":"Wartime Kitchen Gardens","qualifier":"Inferred from subject matter","evidence":"Grow vegetables at home"},
        "author":{"value":None,"qualifier":"No author is identified in the extracted text","evidence":None},
        "date":{"value":"circa 1940s","qualifier":"Approximate period; no publication date printed","evidence":"wartime"}}


def test_metadata_retains_unknowns_qualitative_dates_and_verifiable_evidence():
    response=parse_document_metadata(json.dumps(suggested()),text="Grow vegetables at home during wartime.",model="test")
    assert response['author']['value'] is None
    assert response['date']['value']=='circa 1940s'
    assert response['title']['evidence']=='Grow vegetables at home'
    assert response['method']=='text_llm'
    assert DocumentMetadata.model_validate(response).model=='test'
    source=suggested();source['date']['evidence']='invented quotation'
    response=parse_document_metadata(json.dumps(source),text='wartime',model='test')
    assert response['date']['evidence'] is None
    assert 'could not be verified' in response['date']['qualifier']


@pytest.mark.parametrize('value',['# A title', '{}', '{"title":{"value":[]}}', 'x'*16001])
def test_bad_metadata_does_not_become_a_silent_guess(value):
    with pytest.raises(ValueError,match='invalid JSON or fields'):
        parse_document_metadata(value,text='Evidence',model='test')


def test_metadata_step_is_checkpointed_and_a_failure_reuses_synthesis():
    request=SynthesisRequest(request_id='m',scope={'scope_type':'object','scope_id':'doc',
        'documents':[{'file_id':'doc','filename':'OPAQUE.pdf','text':'Grow vegetables at home during wartime.'}]})
    cache={};calls=[]
    def checkpoint(key,value=None):
        if value is not None: cache[key]=value
        return cache.get(key)
    def complete(messages):
        calls.append(messages)
        if len(calls)==2: return '# Invalid metadata',{}
        if 'OSII DOCUMENT METADATA EXTRACTION' in messages[0]['content']: return json.dumps(suggested()),{}
        return '# Gardening Summary\nGrounded source.',{}
    with pytest.raises(ValueError,match='invalid JSON'):
        synthesize_bounded(request,chat_synthesizer_descriptor(),'test',complete,checkpoint=checkpoint)
    assert len(cache)==1  # Invalid metadata is never cached as successful.
    response=synthesize_bounded(request,chat_synthesizer_descriptor(),'test',complete,checkpoint=checkpoint)
    assert len(calls)==3
    assert response.metadata['document_title']=='Wartime Kitchen Gardens'
    assert response.metadata['document_metadata']['author']['value'] is None
    assert response.metadata['model_calls']==synthesis_call_estimate(38)==2
    request.config={'extract_metadata':False}
    response=synthesize_bounded(request,chat_synthesizer_descriptor(),'test',lambda _:('# Summary',{}))
    assert 'document_metadata' not in response.metadata


def test_metadata_prompt_has_bounded_source_context_and_no_full_corpus_access():
    prompt=metadata_prompt('START '+ 'x'*200000 + ' END','Summary')
    assert 'START' in prompt and ' END' in prompt
    assert len(prompt)<26000


def test_six_metadata_fields_keep_descriptive_and_source_titles_distinct():
    source = suggested()
    source.update(descriptive_title={"value":"Gardening during shortages"}, agency={"value":"Ministry of Food", "evidence":"Ministry of Food"}, document_type={"value":"Public information leaflet"})
    record = parse_document_metadata(json.dumps(source), text="Grow vegetables at home during wartime. Ministry of Food", model="test")
    assert record["descriptive_title"]["value"] != record["title"]["value"]
    assert record["agency"]["evidence"] == "Ministry of Food"
    assert record["document_type"]["value"] == "Public information leaflet"
    source["document_type"]["evidence"] = "fabricated quotation"
    assert parse_document_metadata(json.dumps(source), text="Grow vegetables", model="test")["document_type"]["evidence"] is None


def test_ollama_metadata_uses_schema_without_constraining_markdown(monkeypatch, tmp_path):
    monkeypatch.setenv("OSII_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("OSII_ROOT", str(tmp_path / ".osii"))
    from app.main import CLIENTS, ProviderSynthesizer
    calls = []
    def fake_request(method, path, **kwargs):
        payload = kwargs["payload"]
        calls.append(payload)
        if "format" in payload:
            return {"message":{"content":json.dumps({**suggested(), "descriptive_title":{"value":"Wartime garden advice"}, "agency":{}, "document_type":{}})}}
        return {"message":{"content":"# Gardening\n\nGrounded synthesis."}}
    monkeypatch.setattr(CLIENTS["ollama"], "request", fake_request)
    request = SynthesisRequest(request_id="schema", scope={"scope_type":"object", "scope_id":"doc", "documents":[{"file_id":"doc", "filename":"opaque.pdf", "text":"Grow vegetables at home during wartime."}]})
    response = ProviderSynthesizer("ollama").synthesize(request)
    assert "format" not in calls[0]
    assert set(calls[1]["format"]["required"]) == {"descriptive_title", "title", "author", "date", "agency", "document_type"}
    assert response.metadata["document_metadata"]["descriptive_title"]["value"] == "Wartime garden advice"
