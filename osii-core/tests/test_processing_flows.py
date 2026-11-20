from copy import deepcopy
from types import SimpleNamespace
import pytest
from osii.configuration import load_tools_config, save_tools_config
from osii.domain.processing.flows import get_flow
from osii.domain.processing.jobs import configure_job_store, claim_next_queue_job, get_run, save_run


def test_flows_list_without_testing_services_and_enable_all_processes(client, monkeypatch):
    monkeypatch.setattr('requests.post', lambda *a, **kw: pytest.fail('Listing flows must not invoke models'))
    flows = client.get('/api/processing-flows').json()['flows']
    assert {flow['id'] for flow in flows} >= {'bundled', 'advanced-ocr'}
    assert flows[0]['test'] is None
    assert flows[0]['enricher_name']
    assert flows[0]['routes'][0]['extractor'] == 'local.native-text'


def test_flow_sample_uses_ordered_fallbacks_and_invalidates_after_edit(client, temp_osii_root, monkeypatch):
    from osii.api import intake_routes
    calls = []
    def probe(request, payload):
        calls.append(payload)
        targets = payload.get('processors') or [{'name': 'embedding'}]
        return {'tested_at': '2026-11-19T00:00:00Z', 'results': [{'processor': target['name'], 'ok': target['name'] != 'local.native-text'} for target in targets]}
    settings = load_tools_config()
    settings['processing_flows'] = {'test-fallback': {'name': 'Fallback test', 'routes': [
        {'name': 'pdf', 'extensions': ['.pdf'], 'extractor': 'local.native-text', 'fallbacks': ['local.tesseract-page-ocr']}]}}
    save_tools_config(settings)
    monkeypatch.setattr(intake_routes, 'test_intake_processors', probe)
    report = client.post('/api/processing-flows/test-fallback/test').json()
    assert {step.get('step') for step in report['results']} == {'extract', 'synthesize', 'enrich', 'embed'}
    assert report['ok'] is True  # native fails, ordered OCR fallback succeeds
    assert report['results'][0]['attempts'][0]['processor'] == 'local.native-text'
    assert report['results'][0]['attempts'][1]['processor'] == 'local.tesseract-page-ocr'
    assert calls[0]['sample'] == 'nist-cloud-definition'
    assert get_flow(temp_osii_root, 'test-fallback')['test']['ok']
    settings = load_tools_config()
    settings['processor_settings'] = {'local.native-text': {'chunk_chars': 2345}}
    save_tools_config(settings)
    assert get_flow(temp_osii_root, 'test-fallback')['test'] is None


def test_queued_flow_survives_config_change_and_worker_restart(client, temp_data_root, temp_osii_root, monkeypatch):
    from osii.api import runs_routes
    from osii.worker import execute_job
    monkeypatch.setattr(runs_routes, 'embedding_readiness', lambda root: {'available': True})
    source = temp_data_root / 'test.txt'; source.write_text('one selected file')
    response = client.post('/api/runs', json={'queue_paths': [str(source)], 'processing_flow_id': 'bundled'})
    assert response.status_code == 200, response.text
    before = deepcopy(get_flow(temp_osii_root, 'bundled'))
    settings = load_tools_config()
    settings['processing_flows'] = {'bundled': {**{k: v for k, v in before.items() if k not in {'test', 'fingerprint', 'id'}}, 'name': 'Changed later', 'routes': [{'name': 'new', 'extensions': ['*'], 'extractor': 'tika', 'fallbacks': []}]}}
    save_tools_config(settings)
    configure_job_store(temp_osii_root)  # reopen the durable queue
    job = claim_next_queue_job('restarted-worker')
    assert job['payload']['routes_snapshot'] == before['routes']
    assert all(job['payload'][key] for key in ('run_extraction', 'build_embeddings', 'synthesizer_name', 'enricher_name'))
    captured = []
    def worker(**kwargs):
        captured.append(kwargs['routes_snapshot'])
        run = get_run(kwargs['run_id']); run['status'] = 'paused'; save_run(run)
    monkeypatch.setattr(runs_routes, 'run_worker', worker)
    monkeypatch.setattr('osii.domain.processing.standalone.validate_embedding_binding', lambda *a: None)
    execute_job(job)
    assert captured == [before['routes']]
    assert get_run(response.json()['id'])['processing_flow']['name'] == before['name']


@pytest.mark.parametrize('payload', [{}, {'name': '', 'routes': []}, {'name': 'Bad', 'routes': []}])
def test_flow_rejects_empty_rules_and_names(client, payload):
    assert client.put('/api/processing-flows/custom', json=payload).status_code == 422


def test_collection_processing_keeps_scope_and_does_not_enter_simple_intake(client, temp_osii_root, temp_data_root, monkeypatch):
    from osii.api import runs_routes
    from osii.domain.scopes.collections import create_collection, add_documents_to_collection
    collection = create_collection(temp_osii_root, name='Review')
    add_documents_to_collection(temp_osii_root, collection['id'], ['document-id'])
    path = temp_data_root / 'doc.txt'; path.write_text('selected collection member')
    monkeypatch.setattr('osii.domain.artifacts.source_files.get_source_file_path', lambda *a: path)
    monkeypatch.setattr(runs_routes, 'embedding_readiness', lambda root: {'available': True})
    response = client.post(f"/api/collections/{collection['id']}/process", json={'processing_flow_id': 'bundled'})
    assert response.status_code == 200, response.text
    run = get_run(response.json()['id'])
    assert run['workflow'] == 'library'
    assert run['collection_id'] == collection['id']
    assert run['processing_flow']['id'] == 'bundled'


def test_flow_queue_does_not_repeat_endpoint_tests(client, temp_data_root, monkeypatch):
    monkeypatch.setattr('osii.api.runs_routes.embedding_readiness', lambda *a: pytest.fail('Do not retest providers while queueing a named flow'))
    source = temp_data_root / 'file.txt'; source.write_text('selected file')
    response = client.post('/api/runs', json={'queue_paths': [str(source)], 'processing_flow_id': 'bundled'})
    assert response.status_code == 200, response.text


def test_metadata_only_preview_does_not_load_rules_or_read_originals(client, temp_data_root, monkeypatch):
    from pathlib import Path
    source = temp_data_root / 'file.txt'; source.write_text('read only by worker')
    original = Path.open
    def no_content(path, *a, **kw):
        if path == source:
            pytest.fail('Metadata preview read original content')
        return original(path, *a, **kw)
    monkeypatch.setattr(Path, 'open', no_content)
    monkeypatch.setattr('osii.api.intake_routes.add_extractor_plan', lambda *a, **kw: pytest.fail('Metadata preview loaded rules'))
    response = client.post('/api/resolve', json={'queue_paths': [str(source)], 'metadata_only': True})
    assert response.status_code == 200, response.text
    assert response.json()['preview']['matched_count'] == 1


def test_collection_processing_missing_originals_leaves_history_unchanged(client, temp_osii_root, monkeypatch):
    from osii.domain.scopes.collections import create_collection, add_documents_to_collection, list_collection_documents
    collection = create_collection(temp_osii_root, name='Disconnected source')
    add_documents_to_collection(temp_osii_root, collection['id'], ['missing-original'])
    monkeypatch.setattr('osii.domain.artifacts.source_files.get_source_file_path', lambda *a: None)
    response = client.post(f"/api/collections/{collection['id']}/process", json={})
    assert response.status_code == 409
    assert response.json()['detail']['file_ids'] == ['missing-original']
    assert list_collection_documents(temp_osii_root, collection['id']) == ['missing-original']


def test_standard_pdf_sample_has_text_on_every_page():
    import pymupdf
    from osii.domain.processing.flows import TEXT_LAYER_SAMPLE, TEXT_LAYER_SAMPLE_PAGE
    with pymupdf.open(TEXT_LAYER_SAMPLE) as pdf:
        assert len(pdf) == 7
        assert all(len(page.get_text().strip()) > 100 for page in pdf)
        text = pdf[TEXT_LAYER_SAMPLE_PAGE].get_text()
        assert 'Cloud computing is a model' in text
        assert len(text) > 2000


def test_preflight_sends_the_bundled_text_layer_sample(client, monkeypatch):
    import base64
    import pymupdf
    from osii.processor_sdk import ProcessorClient
    monkeypatch.setattr('osii.processors.remote.resolve_remote_processor', lambda *a: {'base_url': 'http://test-reader', 'name': 'local.native-text', 'capabilities': {'file_extensions': ['.pdf']}})
    monkeypatch.setattr(ProcessorClient, '_get', lambda *a: {})
    checked = []
    def extract(self, request):
        with pymupdf.open(stream=base64.b64decode(request.document.content_base64), filetype='pdf') as pdf:
            assert len(pdf) == 1
            text = pdf[0].get_text()
            assert 'Cloud computing is a model' in text
            checked.append(text)
        return SimpleNamespace(segments=[SimpleNamespace(text=text)])
    monkeypatch.setattr(ProcessorClient, 'extract', extract)
    response = client.post('/api/intake/preflight', json={'processors': [{'name': 'local.native-text', 'kind': 'extractor'}], 'sample': 'nist-cloud-definition'})
    assert response.status_code == 200
    assert response.json()['results'][0]['ok'] is True
    assert checked


def test_missing_bundled_sample_is_a_clear_failure(client, monkeypatch, tmp_path):
    from osii.processor_sdk import ProcessorClient
    monkeypatch.setattr('osii.processors.remote.resolve_remote_processor', lambda *a: {'base_url': 'http://test-reader', 'name': 'local.native-text', 'capabilities': {'file_extensions': ['.pdf']}})
    monkeypatch.setattr(ProcessorClient, '_get', lambda *a: {})
    monkeypatch.setattr('osii.domain.processing.flows.TEXT_LAYER_SAMPLE', tmp_path / 'missing.pdf')
    response = client.post('/api/intake/preflight', json={'processors': [{'name': 'local.native-text', 'kind': 'extractor'}], 'sample': 'nist-cloud-definition'})
    result = response.json()['results'][0]
    assert result['ok'] is False
    assert 'Bundled sample PDF is missing' in result['diagnostics']['error']


def test_changing_sample_invalidates_an_old_flow_report(client, temp_osii_root, tmp_path, monkeypatch):
    from osii.domain.processing import flows
    before = get_flow(temp_osii_root, 'bundled')
    settings = load_tools_config()
    settings['processing_flow_tests'] = {'bundled': {'fingerprint': before['fingerprint'], 'ok': True, 'results': [], 'tested_at': 'earlier'}}
    save_tools_config(settings)
    assert get_flow(temp_osii_root, 'bundled')['test'] is not None
    replacement = tmp_path / 'different.pdf'; replacement.write_bytes(b'changed sample')
    monkeypatch.setattr(flows, 'TEXT_LAYER_SAMPLE', replacement)
    assert get_flow(temp_osii_root, 'bundled')['test'] is None


def test_archived_tika_saved_flow_and_registration_do_not_return_in_setup(client, temp_osii_root):
    from osii.configuration import configured_tools, processors_path
    settings = load_tools_config()
    settings.update({"tools": {"tika": {"enabled": True, "processor_id": "tika", "runtime": {"mode": "external", "endpoint": "http://127.0.0.1:8102"}}},
        "processing_flows": {"previous": {"name": "Previous flow", "routes": [
            {"name": "pdf", "extensions": [".pdf"], "extractor": "tika_catchall", "fallbacks": ["local.native-text"]}]}},
        "processor_settings": {"tika": {"chunk_chars": 1234}}})
    save_tools_config(settings)
    original = processors_path().read_bytes()
    flow = get_flow(temp_osii_root, "previous")
    assert flow["routes"][0]["extractor"] == "local.native-text"
    assert flow["routes"][0]["fallbacks"] == []
    assert "tika" not in configured_tools(temp_osii_root)
    assert not any(p["id"] == "tika" for p in client.get("/api/admin/processor-settings/startup").json()["processors"])
    assert processors_path().read_bytes() == original
    for flow in client.get("/api/processing-flows").json()["flows"]:
        assert all(not {"tika", "tika_catchall"} & {route["extractor"], *route.get("fallbacks", [])} for route in flow["routes"])
