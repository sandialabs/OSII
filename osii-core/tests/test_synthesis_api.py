from osii.domain.processing.jobs import claim_next_queue_job, get_run
from osii.worker import execute_job


def test_synthesis_api_starts_job(client, sample_osii_object, monkeypatch):
    monkeypatch.delenv("OSII_SYNTHESIZER_FALLBACKS", raising=False)
    file_id = sample_osii_object["file_id"]
    response = client.post(
        f"/api/synthesis/objects/{file_id}",
        json={
            "synthesizer_name": "firstN",
            "expert_context": "Focus on calibration.",
            "synthesizer_config": {"max_chars": 1000},
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["file_id"] == file_id
    assert data["synthesizer_name"] == "firstN"
    assert data["status"] == "queued"
    execute_job(claim_next_queue_job())
    assert get_run(data["run_id"])["status"] == "done"
    assert (
        get_run(data["run_id"])["items"][0]["synthesis"]
        == f"objects/{file_id}/synth.txt"
    )
