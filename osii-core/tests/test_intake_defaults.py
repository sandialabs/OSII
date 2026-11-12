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
