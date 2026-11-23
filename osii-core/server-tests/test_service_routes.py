import pytest
from fastapi import HTTPException
from conftest import login
from osii.server import service_routes


def test_service_controls_require_admin_and_csrf(client, monkeypatch):
    calls = []
    monkeypatch.setattr(service_routes, "controller", lambda method, path: calls.append((method, path)) or {"services": []})
    assert client.get('/api/admin/services').status_code == 401
    for role in ['reader', 'curator']:
        login(client, role)
        assert client.get('/api/admin/services').status_code == 403
        assert client.get('/api/admin/services/extractor/logs').status_code == 403
        assert client.post('/api/admin/services/extractor/restart', json={}).status_code == 403
    assert not calls
    login(client)
    assert client.get('/api/admin/services').status_code == 200
    csrf = client.headers.pop('X-CSRF-Token')
    assert client.post('/api/admin/services/extractor/restart', json={}).status_code == 403
    client.headers['X-CSRF-Token'] = csrf
    assert client.post('/api/admin/services/extractor/restart', json={}).status_code == 200
    assert calls[-1] == ('POST', '/services/extractor/restart')
    previous = len(calls)
    assert client.post('/api/admin/services/osii-api/restart', json={}).status_code == 404
    assert client.post('/api/admin/services/extractor/delete', json={}).status_code == 404
    assert len(calls) == previous


def test_missing_controller_fails_closed(client, monkeypatch):
    monkeypatch.delenv('OSII_TOOL_CONTROL_SOCKET', raising=False)
    login(client)
    result = client.get('/api/admin/services')
    assert result.status_code == 503
    assert 'not configured' in result.json()['detail']


def test_health_failure_does_not_hide_restart(client, monkeypatch):
    monkeypatch.setattr(service_routes, 'controller', lambda *args: {'services': [{'id':'extractor', 'url':'http://tool.test', 'status':'running','can_restart':True}]})
    def fail(*args): raise RuntimeError('private error text')
    monkeypatch.setattr('osii.processor_sdk.ProcessorClient.health', fail)
    login(client)
    row = client.get('/api/admin/services').json()['services'][0]
    assert row['status'] == 'unhealthy' and row['can_restart']
    assert 'private error text' not in row['detail']
