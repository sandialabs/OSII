import json
import pytest
from osii.domain.processing import jobs
from osii.domain import tool_actions
from osii.domain.processing.scope_batches_local import (
    LocalBatchStorage,
    details,
    batch_result,
)
from osii.domain.artifacts.enrichment_artifacts import write_scope_enrichment_variant
from osii.enrichment.stats_keywords import StatsKeywordsEnricher
from osii.worker import execute_job


def submit(root, scope):
    return tool_actions.submit_tool(
        root, {"enricher_name": "stats_keywords", "scope": scope}
    )["run_id"]


def test_long_text_is_not_truncated_and_results_are_replayable(
    temp_osii_root, sample_osii_object, monkeypatch
):
    from osii.domain.artifacts.text_representations import (
        get_preferred_text_representation,
    )

    root = temp_osii_root
    fid = sample_osii_object["file_id"]
    preferred = get_preferred_text_representation(root, fid)
    text = "ordinary words " * 20000 + " finalsentinel"
    (root / preferred["path"]).write_text(text)
    monkeypatch.setattr(
        tool_actions, "resolve_enricher", lambda _: StatsKeywordsEnricher()
    )
    run_id = submit(root, {"scope_type": "object", "file_id": fid})
    storage = LocalBatchStorage(root, run_id)
    assert storage.summary()["map_batches"] > 1
    assert (
        "".join(
            row["text"] for batch in storage.rows("map", 0) for row in batch["inputs"]
        )
        == text
    )
    job = jobs.claim_next_queue_job("worker")
    execute_job(job)
    assert jobs.get_run(run_id)["status"] == "done"
    assert storage.summary()["processed_characters"] == len(text)
    assert storage.summary()["completed_documents"] == 1
    assert "finalsentinel" in json.dumps(list(storage.rows("map", 0)))
    first = details(root, run_id, limit=1)
    assert first["next_cursor"] == 1 and "result" not in first["items"][0]
    assert batch_result(root, run_id, "map-0")["result"]["artifacts"]

    # Lost acknowledgements replay saved batches and product publication.
    def never(**kwargs):
        raise AssertionError("Completed work was repeated")

    monkeypatch.setattr(StatsKeywordsEnricher, "enrich", never)
    execute_job(job)
    assert jobs.get_run(run_id)["status"] == "done"


def test_native_batch_outputs_do_not_publish_over_shared_products(
    temp_osii_root, sample_osii_object, monkeypatch
):
    from osii.domain.artifacts.products import product_path, read_product
    from osii.enrichment.common import collect_scope_texts

    root = temp_osii_root
    fid = sample_osii_object["file_id"]
    scope = {"scope_type": "object", "file_id": fid}
    calls = []

    class Pausing:
        name = "stats_keywords"

        def describe(self):
            return {"name": self.name, "version": "1"}

        def enrich(self, **arguments):
            rows, _ = collect_scope_texts(root, scope)
            calls.append(rows[0]["text"])
            result = write_scope_enrichment_variant(
                root,
                scope,
                kind="wiki",
                method=self.name,
                payload={
                    "artifact_type": "wiki_markdown",
                    "title": "Batch wiki",
                    "markdown": rows[0]["text"],
                    "citations": [],
                },
            )
            jobs.control_run(run_id, "pause")
            return {"ok": True, "result": result}

    monkeypatch.setattr(tool_actions, "resolve_enricher", lambda _: Pausing())
    write_scope_enrichment_variant(
        root,
        scope,
        kind="wiki",
        method="stats_keywords",
        payload={
            "artifact_type": "wiki_markdown",
            "title": "Existing",
            "markdown": "Previous published result",
            "citations": [],
        },
    )
    run_id = submit(root, scope)
    job = jobs.claim_next_queue_job("worker")
    execute_job(job)
    assert jobs.get_run(run_id)["status"] == "paused"
    assert (
        read_product(product_path(root, scope, "wiki--stats_keywords.json"))["data"][
            "markdown"
        ]
        == "Previous published result"
    )
    jobs.pause_queue_job(job["id"])
    jobs.control_run(run_id, "resume")
    execute_job(jobs.claim_next_queue_job("resumed"))
    assert len(calls) == 1
    assert jobs.get_run(run_id)["status"] == "done"


def test_batch_result_addresses_are_bounded(temp_osii_root):
    with pytest.raises(ValueError):
        batch_result(temp_osii_root, "run", "../../secrets")
    with pytest.raises(ValueError):
        details(temp_osii_root, "run", limit=100000)


def test_keyword_ranking_combines_complete_batch_counts(
    temp_osii_root, sample_osii_object, monkeypatch
):
    from osii.domain.artifacts.text_representations import (
        get_preferred_text_representation,
    )
    from osii.domain.artifacts.products import product_path, read_product

    root = temp_osii_root
    fid = sample_osii_object["file_id"]
    scope = {"scope_type": "object", "file_id": fid}
    preferred = get_preferred_text_representation(root, fid)
    (root / preferred["path"]).write_text(
        "alpha " * 10000 + "beta " * 9500 + " the " * 10000 + " beta " * 4000
    )
    monkeypatch.setattr(
        tool_actions, "resolve_enricher", lambda _: StatsKeywordsEnricher()
    )
    run_id = tool_actions.submit_tool(
        root,
        {
            "enricher_name": "stats_keywords",
            "scope": scope,
            "enricher_config": {"top_k": 1},
        },
    )["run_id"]
    execute_job(jobs.claim_next_queue_job("worker"))
    assert LocalBatchStorage(root, run_id).summary()["map_batches"] > 1
    result = read_product(product_path(root, scope, "keywords--stats_keywords.json"))[
        "data"
    ]
    assert result["rows"] == [{"term": "beta", "count": 13500}]


def test_changed_inputs_retain_batch_results_without_publishing(
    temp_osii_root, sample_osii_object, monkeypatch
):
    from osii.domain.artifacts.text_representations import (
        get_preferred_text_representation,
    )
    from osii.domain.storage.commits import CommitConflict
    from osii.domain.artifacts.products import product_path

    root = temp_osii_root
    fid = sample_osii_object["file_id"]
    scope = {"scope_type": "object", "file_id": fid}
    tool = StatsKeywordsEnricher()
    original = tool.enrich

    def changed(**arguments):
        result = original(**arguments)
        preferred = get_preferred_text_representation(root, fid)
        (root / preferred["path"]).write_text("Changed during processing")
        return result

    monkeypatch.setattr(tool, "enrich", changed)
    monkeypatch.setattr(tool_actions, "resolve_enricher", lambda _: tool)
    run_id = submit(root, scope)
    job = jobs.claim_next_queue_job("worker")
    with pytest.raises(CommitConflict, match="input text or membership changed"):
        execute_job(job)
    assert LocalBatchStorage(root, run_id).summary()["completed_batches"] == 1
    assert jobs.get_run(run_id)["status"] == "error"
    assert not product_path(root, scope, "batch-results--stats_keywords.json").exists()
