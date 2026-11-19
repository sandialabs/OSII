import pytest
from osii.domain.processing.defaults import intake_defaults

@pytest.mark.parametrize('preset, expected', [
    ('text', (False, False, False)), ('search', (False, True, False)),
    ('summary-search', (True, True, False)), ('full', (True, True, True)),
])
def test_intake_presets_are_explicit_and_do_not_process(preset, expected):
    value = intake_defaults({'OSII_INTAKE_PRESET': preset})
    assert tuple(value[k] for k in ('synthesize', 'build_embeddings', 'enrich')) == expected
    assert value['show_hidden'] is False
    assert value['include_subfolders'] is True

@pytest.mark.parametrize('values', [
    {'OSII_INTAKE_PRESET': 'typo'}, {'OSII_INTAKE_SHOW_HIDDEN': 'sometimes'},
    {'OSII_INTAKE_CHUNK_SIZE': '5', 'OSII_INTAKE_CHUNK_OVERLAP': '8'},
    {'OSII_INTAKE_CHUNK_SIZE': 'invalid'},
])
def test_invalid_intake_defaults_are_actionable(values):
    with pytest.raises(ValueError): intake_defaults(values)

def test_public_defaults_endpoint_uses_launch_configuration(client, monkeypatch):
    monkeypatch.setenv('OSII_INTAKE_PRESET', 'text')
    monkeypatch.setenv('OSII_INTAKE_INCLUDE_PATTERNS', '*.pdf,*.docx')
    monkeypatch.setenv('OSII_INTAKE_SYNTHESIZER', 'openai.synthesizer')
    result = client.get('/api/intake/defaults')
    assert result.status_code == 200
    assert result.json()['preset'] == 'text'
    assert result.json()['include_patterns'].splitlines() == ['*.pdf', '*.docx']
    assert result.json()['synthesizer'] == 'openai.synthesizer'


def test_saved_intake_defaults_override_legacy_env_and_preserve_other_config(client, monkeypatch):
    from osii.configuration import load_tools_config, save_tools_config
    save_tools_config({'version': 1, 'extension': {'keep': 'me'}, 'processor_settings': {'tika': {'chunk_chars': 123}}})
    monkeypatch.setenv('OSII_INTAKE_PRESET', 'full')
    monkeypatch.setenv('OSII_INTAKE_CHUNK_SIZE', '999')
    assert client.get('/api/intake/defaults').json()['preset'] == 'full'
    result = client.put('/api/intake/defaults', json={'preset': 'text', 'chunk_size': 512, 'chunk_overlap': 64})
    assert result.status_code == 200
    # A new request/reopened UI uses durable values, not the old bootstrap values.
    value = client.get('/api/intake/defaults').json()
    assert (value['preset'], value['chunk_size'], value['chunk_overlap']) == ('text', 512, 64)
    assert load_tools_config()['extension'] == {'keep': 'me'}
    assert load_tools_config()['processor_settings']['tika']['chunk_chars'] == 123
    assert client.put('/api/intake/defaults', json={'preset': 'search'}).status_code == 200
    assert client.get('/api/intake/defaults').json()['chunk_size'] == 512


@pytest.mark.parametrize('payload', [{'preset': 'oops'}, {'chunk_size': True}, {'chunk_size': 1, 'chunk_overlap': 2}, {'unknown': 'field'}])
def test_invalid_saved_defaults_do_not_overwrite_configuration(client, payload):
    from osii.configuration import processors_path
    client.get('/api/intake/defaults')
    before = processors_path().read_bytes()
    assert client.put('/api/intake/defaults', json=payload).status_code == 422
    assert processors_path().read_bytes() == before
