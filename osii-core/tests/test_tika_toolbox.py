from osii.configuration import builtin_tools_config
from osii.domain.processor_settings import merged_processor_settings
from osii.extraction.dispatcher import dispatch_extract


def test_legacy_routes_delegate_without_contacting_apache_tika(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr('osii.processors.remote.resolve_remote_processor', lambda name, kind: {'name': name})
    class Remote:
        def __init__(self, descriptor):
            assert descriptor['name'] == 'tika'
        def extract(self, **kw):
            calls.append(kw)
            return {'ok': True}
    monkeypatch.setattr('osii.processors.remote.RemoteExtractor', Remote)
    for name in ['tika', 'tika_catchall']:
        assert dispatch_extract(extractor_name=name, source_path=tmp_path/'a.pdf', data_volume_root=tmp_path, osii_store=tmp_path)['ok']
    assert len(calls) == 2
    assert builtin_tools_config()['tools']['tika']['aliases'] == ['tika_catchall']


def test_alias_uses_saved_endpoint(monkeypatch, tmp_path):
    monkeypatch.setattr('osii.domain.processor_settings.processor_settings', lambda root, name: {'tika_endpoint': 'http://saved:9998'} if name == 'tika' else {})
    assert merged_processor_settings(tmp_path, 'tika_catchall', {}) == {'tika_endpoint': 'http://saved:9998'}
