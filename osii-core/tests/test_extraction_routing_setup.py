import asyncio
from pathlib import Path

import pytest

from osii.api import extractor_routes as routes
from osii.extraction.dispatcher import dispatch_extract


@pytest.fixture(autouse=True)
def offline_tools(monkeypatch):
    monkeypatch.setattr('osii.configuration.configured_tools', lambda: {})


def test_tesseract_rejects_incompatible_primary_and_fallback():
    for primary, fallbacks in [('local.tesseract-page-ocr', []), ('tika', ['toolbox.tesseract-opencv'])]:
        errors, _ = routes.validate_routes({'routes': [{'name': 'bad', 'extractor': primary, 'fallbacks': fallbacks, 'extensions': ['.csv']}]})
        assert any('cannot accept .csv' in error for error in errors)
    errors, _ = routes.validate_routes({'routes': [{'name': 'images', 'extractor': 'local.tesseract-page-ocr', 'extensions': ['.pdf', '.png']}]})
    assert not errors


def test_import_is_validated_without_saving(monkeypatch):
    monkeypatch.setattr(routes, 'save_tools_config', lambda *a: pytest.fail('Import must not save'))
    result = asyncio.run(routes.import_extractor_routes({'toml': '[[routes.extractor]]\nname="pdf"\nextractor="local.tesseract-page-ocr"\nextensions=[".pdf"]'}))
    assert result['ok']
    assert result['routes'][0]['extensions'] == ['.pdf']
    assert not asyncio.run(routes.import_extractor_routes({'toml': '[broken'}))['ok']
    assert not asyncio.run(routes.import_extractor_routes({'toml': '[[routes.extractor]]\nname="bad"\nextractor="local.tesseract-page-ocr"\nextensions=["*"]'}))['ok']


def test_dispatch_rejects_unsupported_type_before_remote_call(monkeypatch, tmp_path):
    monkeypatch.setattr('osii.processors.remote.resolve_remote_processor', lambda *a: {'capabilities': {'file_extensions': ['.pdf']}})
    monkeypatch.setattr('osii.processors.remote.RemoteExtractor', lambda *a: pytest.fail('Must not invoke tool'))
    with pytest.raises(ValueError, match='does not accept .csv'):
        dispatch_extract(extractor_name='external.pdf', source_path=Path('table.csv'), data_volume_root=tmp_path, osii_store=tmp_path)


def test_automatic_model_skips_disabled_default(monkeypatch, tmp_path):
    from osii import configuration
    monkeypatch.setattr(configuration, 'tool_for_processor', lambda *a: ('wiki', {'model_access': {'mode': 'gateway'}}))
    models = {'disabled': {'enabled': False, 'capabilities': ['chat']}, 'working': {'enabled': True, 'capabilities': ['chat']}}
    monkeypatch.setattr(configuration, 'load_models_config', lambda *a: {'models': models, 'defaults': {'chat': 'disabled'}})
    monkeypatch.setattr(configuration, 'model_connection', lambda alias, *a: models.get(alias))
    assert configuration.resolve_tool_models('wiki', {'chat': 'required'}, tmp_path) == {'chat': 'working'}
    with pytest.raises(ValueError, match='enabled chat model'):
        configuration.resolve_tool_models('wiki', {'chat': 'required'}, tmp_path, {'chat': 'disabled'})
