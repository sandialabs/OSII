from osii.domain.processing.jobs import claim_next_queue_job, configure_job_store, get_run
from osii.worker import execute_job


def test_enrichment_job_queues_then_saves(client, temp_osii_root, sample_osii_object):
    response = client.post("/api/enrichment-jobs/run", json={"enricher_name": "stats_keywords", "scope": {"scope_type": "object", "file_id": sample_osii_object["file_id"]}})
    assert response.status_code == 200
    assert response.json()["status"] == "queued"
    configure_job_store(temp_osii_root)
    job = claim_next_queue_job("test-worker")
    assert job["run_id"] == response.json()["run_id"]
    execute_job(job)
    run = get_run(job["run_id"])
    assert run["status"] == "done"
    # Durable scope tools publish artifacts, rather than embedding output in run items.
    from osii.domain.processing.scope_batches_local import batch_result
    from osii.domain.artifacts.products import product_path, read_product
    result = batch_result(temp_osii_root, run["id"], "map-0")["result"]
    assert any(artifact["data"].get("artifact_type") == "table" for artifact in result["artifacts"])
    scope = {"scope_type": "object", "file_id": sample_osii_object["file_id"]}
    published = read_product(product_path(temp_osii_root, scope, "keywords--stats_keywords.json"))
    assert published["data"]["artifact_type"] == "table"
    assert published["data"]["rows"]
