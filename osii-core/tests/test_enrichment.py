import json

from osii.processor_sdk import (
    EntityListArtifactData,
    TableArtifactData,
)

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
            "Sandia National Laboratories published the analysis. "
            "We talk about other things."
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
    TableArtifactData.model_validate(keyword_payload)
    EntityListArtifactData.model_validate(entity_payload)
    thermal_phrase = next(row for row in rows if row["keyword"] == "thermal calibration drift")
    assert thermal_phrase["frequency"] == 2
    assert {row["n"] for row in rows}.issubset({2, 3, 4})
    assert all(row["keyword"] != "talk about" for row in rows)
    entity = next(item for item in entity_payload["entities"] if item["name"] == "Sandia National Laboratories")
    assert entity["entity_type"] == "organization_candidate"
    assert entity["attributes"]["frequency"] == 2
    assert entity["mentions"][0]["file_id"] == file_id
