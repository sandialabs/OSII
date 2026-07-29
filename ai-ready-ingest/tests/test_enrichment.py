from osii.enrichment.llm_wiki_stub import LlmWikiStubEnricher
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