from osii.domain.processing.jobs import claim_next_queue_job, configure_job_store, get_run
from osii.worker import execute_job
import json


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
    assert run["items"][0]["status"] == "done"
   
    artifact_path = (
        temp_osii_root
        / "objects"
        / sample_osii_object["file_id"]
        / "enrichments"
        / "keywords--stats_keywords.json"
    )
    assert artifact_path.is_file()
   
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert artifact["artifact_type"] == "table"
    assert artifact["title"] == "Keyword frequencies"
    assert isinstance(artifact["rows"], list)    
