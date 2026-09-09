def test_synthesis_api_starts_job(client, monkeypatch, sample_osii_object):
    file_id = sample_osii_object["file_id"]

    class FakeSynth:
        def synthesize(self, *, osii_store, file_id, expert_context=None, synthesizer_config=None):
            return {"synth_rel": f"objects/{file_id}/synth.txt"}

    monkeypatch.setattr("osii.api.synthesis_routes.get_synthesizer", lambda name: FakeSynth())

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
    assert "run_id" in data
