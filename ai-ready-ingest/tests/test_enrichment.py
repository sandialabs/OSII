import json

from osii_processor_sdk import (
    Capability,
    ProcessorDescriptor,
    ProcessorKind,
    ProvenanceRef,
    SynthesisResponse,
)

from osii.enrichment.llm_wiki import LlmWikiEnricher
from osii.enrichment.llm_wiki_stub import LlmWikiStubEnricher
from osii.enrichment.linguistic_examples import (
    EntityCandidateEnricher,
    NounAdjectiveNgramEnricher,
)
from osii.enrichment.stats_keywords import StatsKeywordsEnricher


def test_stats_keywords_object_scope(temp_osii_root, sample_osii_object):
    enricher = StatsKeywordsEnricher()

    result = enricher.enrich(
        osii_store=temp_osii_root,
        scope={"scope_type": "object", "file_id": sample_osii_object["file_id"]},
        enricher_config={"top_k": 10},
    )

    assert result["ok"] is True
    assert result["result"]["scope_type"] == "object"
    assert result["result"]["kind"] == "keywords"


def test_llm_wiki_stub_collection_scope(temp_osii_root, sample_osii_object):
    from osii.domain.scopes.collections import create_collection, add_documents_to_collection

    file_id = sample_osii_object["file_id"]
    collection = create_collection(
        temp_osii_root,
        name="wiki-set",
        description="wiki test",
        kind="manual",
        color=None,
    )
    add_documents_to_collection(temp_osii_root, collection["id"], [file_id])

    enricher = LlmWikiStubEnricher()

    result = enricher.enrich(
        osii_store=temp_osii_root,
        scope={"scope_type": "collection", "collection_id": collection["id"]},
        enricher_config={},
    )

    assert result["ok"] is True
    assert result["result"]["scope_type"] == "collection"
    assert result["result"]["kind"] == "wiki"


def test_llm_wiki_document_and_collection_scopes(
    temp_osii_root,
    sample_osii_object,
    monkeypatch,
):
    from osii.domain.scopes.collections import create_collection, add_documents_to_collection

    calls = []

    class FakeProcessorClient:
        def __init__(self, base_url):
            assert base_url == "http://wiki-synthesizer"

        def synthesize(self, request):
            calls.append(request)
            return SynthesisResponse(
                request_id=request.request_id,
                processor=ProcessorDescriptor(
                    name="ollama.synthesizer",
                    version="1.0.0",
                    display_name="Ollama Synthesizer",
                    description="test",
                    kind=ProcessorKind.SYNTHESIZER,
                    capabilities=Capability(scope_types=["object", "collection"]),
                ),
                markdown="# Demo Wiki\n\nThermal calibration drift was reduced [sha256-test123].",
                citations=[ProvenanceRef(file_id="sha256-test123")],
                metadata={"provider": "ollama", "model": "llama3.2:1b"},
            )

    monkeypatch.setattr(
        "osii.enrichment.llm_wiki.selected_processor",
        lambda capability, osii_root=None: "ollama.synthesizer",
    )
    monkeypatch.setattr(
        "osii.enrichment.llm_wiki.resolve_remote_processor",
        lambda name, kind: {
            "name": name,
            "kind": kind,
            "base_url": "http://wiki-synthesizer",
        },
    )
    monkeypatch.setattr("osii.enrichment.llm_wiki.ProcessorClient", FakeProcessorClient)

    file_id = sample_osii_object["file_id"]
    document_result = LlmWikiEnricher().enrich(
        osii_store=temp_osii_root,
        scope={"scope_type": "object", "file_id": file_id},
        enricher_config={"title": "Document Demo"},
    )

    collection = create_collection(
        temp_osii_root,
        name="wiki-set",
        description="wiki test",
        kind="manual",
        color=None,
    )
    add_documents_to_collection(temp_osii_root, collection["id"], [file_id])
    collection_result = LlmWikiEnricher().enrich(
        osii_store=temp_osii_root,
        scope={"scope_type": "collection", "collection_id": collection["id"]},
        enricher_config={"title": "Collection Demo"},
    )

    assert document_result["result"]["scope_type"] == "object"
    assert collection_result["result"]["scope_type"] == "collection"
    assert [call.scope.scope_type for call in calls] == ["object", "collection"]
    assert all(call.config["instructions"].startswith("Create a useful") for call in calls)

    document_payload = json.loads(
        (temp_osii_root / "objects" / file_id / "enrichments" / "wiki--llm_wiki.json").read_text(encoding="utf-8")
    )
    collection_payload = json.loads(
        (
            temp_osii_root
            / "collections"
            / collection["id"]
            / "enrichments"
            / "wiki--llm_wiki.json"
        ).read_text(encoding="utf-8")
    )
    assert document_payload["artifact_type"] == "wiki_markdown"
    assert document_payload["markdown"].startswith("# Document Demo")
    assert "## Sources" in document_payload["markdown"]
    assert f"`[{file_id}]`" in document_payload["markdown"]
    assert document_payload["citations"] == [{
        "file_id": file_id,
        "segment_id": None,
        "page": None,
        "char_start": None,
        "char_end": None,
        "source_origin": {},
    }]
    assert collection_payload["title"] == "Collection Demo"


def test_linguistic_keyword_and_entity_examples(temp_osii_root, sample_osii_object):
    from osii.domain.storage.objects import write_text_file

    file_id = sample_osii_object["file_id"]
    write_text_file(
        temp_osii_root,
        file_id,
        (
            "Thermal calibration drift affects local sensor measurements. "
            "Thermal calibration drift requires careful analysis. "
            "Sandia National Laboratories reviewed the sensor. "
            "Sandia National Laboratories published the analysis."
        ),
    )

    keyword_result = NounAdjectiveNgramEnricher().enrich(
        osii_store=temp_osii_root,
        scope={"scope_type": "object", "file_id": file_id},
    )
    entity_result = EntityCandidateEnricher().enrich(
        osii_store=temp_osii_root,
        scope={"scope_type": "object", "file_id": file_id},
    )

    assert keyword_result["ok"] is True
    assert entity_result["ok"] is True
    keyword_payload = json.loads(
        (
            temp_osii_root
            / "objects"
            / file_id
            / "enrichments"
            / "keywords--noun_adjective_ngrams.json"
        ).read_text(encoding="utf-8")
    )
    entity_payload = json.loads(
        (
            temp_osii_root
            / "objects"
            / file_id
            / "enrichments"
            / "entities--entity_candidates.json"
        ).read_text(encoding="utf-8")
    )

    rows = keyword_payload["rows"]
    thermal_phrase = next(row for row in rows if row["keyword"] == "thermal calibration drift")
    assert thermal_phrase["frequency"] == 2
    assert {row["n"] for row in rows}.issubset({2, 3, 4})
    entity = next(item for item in entity_payload["entities"] if item["name"] == "Sandia National Laboratories")
    assert entity["entity_type"] == "organization_candidate"
    assert entity["attributes"]["frequency"] == 2
    assert entity["mentions"][0]["file_id"] == file_id
