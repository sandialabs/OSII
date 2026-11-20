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
    monkeypatch.setattr(intake_routes, 'test_intake_processors', probe)
    report = client.post('/api/processing-flows/bundled/test').json()
    assert report['ok'] is True  # native fails, ordered Tika fallback succeeds
    assert report['results'][0]['attempts'][0]['processor'] == 'local.native-text'
    assert report['results'][0]['attempts'][1]['processor'] == 'tika'
    assert calls[0]['sample'] == 'purcell-first-page'
    assert get_flow(temp_osii_root, 'bundled')['test']['ok']
    settings = load_tools_config()
    settings['processor_settings'] = {'tika': {'chunk_chars': 2345}}
    save_tools_config(settings)
    assert get_flow(temp_osii_root, 'bundled')['test'] is None


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
