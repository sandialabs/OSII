import base64

import pytest
import requests
from fastapi.testclient import TestClient
from osii.processor_sdk import DocumentInput, ExtractionRequest
from tika_adapter.main import TikaExtractor, app, endpoint


@pytest.fixture(autouse=True)
def unmanaged_tests(monkeypatch):
    monkeypatch.setenv('OSII_TIKA_MANAGED', 'false')


def request(config=None):
    return ExtractionRequest(request_id='test', document=DocumentInput(file_id='test', filename='a.pdf', media_type='application/pdf', content_base64=base64.b64encode(b'%PDF input').decode()), config=config or {})


def test_forwards_only_selected_bytes_and_returns_grounded_chunks(monkeypatch):
    calls = []
    def put(url, **kwargs):
        calls.append((url, kwargs))
        result = requests.Response()
        result.status_code = 200
        result._content = b'abcdef'
        return result
    monkeypatch.setattr(requests, 'put', put)
    result = TikaExtractor().extract(request({'tika_endpoint': 'http://tika.example:9998/base/', 'chunk_chars': 4}))
    assert calls[0][0] == 'http://tika.example:9998/base/tika'
    assert calls[0][1]['data'] == b'%PDF input'
    assert [s.text for s in result.segments] == ['abcd', 'ef']
    assert result.segments[1].source_origin['extracted_char_start'] == 4
    assert 'bbox' not in result.segments[0].source_origin


@pytest.mark.parametrize('value', ['file:///tmp/a', 'http://user:password@host', 'http://host?secret=1'])
def test_rejects_invalid_endpoint(value):
    with pytest.raises(ValueError):
        endpoint(value)


def test_unavailable_upstream_is_clear_and_does_not_crash_adapter(monkeypatch):
    def unavailable(*a, **kw):
        raise requests.ConnectionError('offline')
    monkeypatch.setattr(requests, 'get', unavailable)
    monkeypatch.setattr(requests, 'put', unavailable)
    client = TestClient(app)
    assert client.get('/health').status_code == 200
    health = client.get('/upstream-health', params={'tika_endpoint': 'http://offline:9998'})
    assert health.status_code == 503
    assert health.json()['detail'] == 'Apache Tika is unavailable at http://offline:9998. Check the server and its endpoint in Setup.'
    result = client.post('/v1/extract', json=request().model_dump(mode='json'))
    assert result.status_code == 422
    assert 'Apache Tika extraction failed' in result.json()['detail']
    assert client.get('/v1/descriptor').json()['name'] == 'tika'


@pytest.mark.parametrize('runtime_error,expected', [(None, 'preparing its first runtime download'), ('certificate verification failed', 'could not start: certificate verification failed')])
def test_managed_preparation_or_failure_is_visible_without_terminal(monkeypatch, runtime_error, expected):
    from types import SimpleNamespace
    monkeypatch.setattr(app.state, 'tika_runtime', SimpleNamespace(enabled=True, error=runtime_error, process=None), raising=False)
    monkeypatch.setattr(requests, 'get', lambda *a, **kw: (_ for _ in ()).throw(requests.ConnectionError('offline')))
    response = TestClient(app).get('/upstream-health')
    assert response.status_code == 503
    assert expected in response.json()['detail']


def test_blank_endpoint_follows_managed_default_and_descriptor_uses_manifest():
    from tika_adapter.main import DEFAULT_ENDPOINT
    from tika_adapter.runtime import MANIFEST
    assert endpoint('') == DEFAULT_ENDPOINT
    assert TikaExtractor.descriptor.config_schema == MANIFEST['config_schema']
