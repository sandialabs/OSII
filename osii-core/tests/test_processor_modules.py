from __future__ import annotations

import io
from pathlib import Path
import subprocess
import sys

import pytest
import tomli_w

from osii.processor_modules import ModuleManifestError, active_processors, discover_processors

ROOT = Path(__file__).resolve().parents[2]


def write_module(root, folder='collection-data-card', **updates):
    directory = root / folder
    directory.mkdir(parents=True, exist_ok=True)
    (directory / 'pyproject.toml').write_text('[project]\nname="fixture-card"\nversion="0.1.0"\n')
    # Discovery must never import even the entry point or install dependencies.
    (directory / 'run.py').write_text('raise AssertionError("Discovery executed implementation")\n')
    processor = dict(id=folder, processor_id='example.' + folder, kind='enricher',
        display_name='Collection data card', description='Builds a data card for a collection.',
        command=['run.py'], port=18123, model_requirements={'chat': 'required'},
        config_schema={'type': 'object', 'properties': {'detail': {'type': 'string', 'default': 'short'}}})
    processor.update(updates)
    data = dict(schema_version=1, id=folder, extras=['cards'], processors=[processor])
    path = directory / 'processor-module.toml'
    path.write_text(tomli_w.dumps(data))
    return path


def test_new_module_drives_startup_registration_and_controls_without_central_edits(tmp_path, monkeypatch):
    # Use the actual launcher, without duplicating its discovery or registration code.
    sys.path.insert(0, str(ROOT / 'scripts'))
    import dev_stack as launcher
    from osii import configuration
    from osii.api import processor_admin_routes

    modules = tmp_path / 'processor modules'
    path = write_module(modules, requires=['card-binary'])
    monkeypatch.setenv('OSII_PROCESSOR_MODULES_DIR', str(modules))
    monkeypatch.setenv('OSII_COLLECTION_DATA_CARD_PORT', '18124')
    monkeypatch.setattr(configuration, 'load_tools_config', lambda *a: {'tools': {}})
    monkeypatch.setattr(processor_admin_routes, '_cached_descriptor', lambda *a: {})
    row = discover_processors(modules)[0]
    assert row.enable_env == 'OSII_ENABLE_COLLECTION_DATA_CARD'
    assert row.port_env == 'OSII_COLLECTION_DATA_CARD_PORT'
    registrations = configuration.configured_tools(profile='development')
    card = registrations['collection-data-card']
    assert card['processor_id'] == 'example.collection-data-card'
    assert card['runtime']['endpoint'] == 'http://127.0.0.1:18124'
    assert card['manifest_path'] == str(path)
    assert card['config_schema']['properties']['detail']['default'] == 'short'
    # Binding changes in tools.toml preserve discovery metadata and offline schema.
    monkeypatch.setattr(configuration, 'load_tools_config', lambda *a: {'tools': {
        'collection-data-card': {'model_access': {'mode': 'gateway', 'bindings': {'chat': 'chosen'}}}}})
    assert configuration.configured_tools(profile='development')['collection-data-card']['config_schema'] == card['config_schema']

    env = {'OSII_PROCESSOR_MODULES_DIR': str(modules), 'OSII_COLLECTION_DATA_CARD_PORT': '18124', 'OSII_START_PROCESSOR_MODULES': 'false'}
    service, = launcher.processor_module_services('uv', env)
    assert service.working_directory == path.parent
    assert service.processor_module and service.extras == ('cards',)
    assert '--extra' in service.command and 'cards' in service.command
    assert service.command[-4:] == ('--host', '127.0.0.1', '--port', '18124')
    assert not service.start_automatically
    supervisor = launcher.CapabilitySupervisor(services=[service], env=env, uv='uv', token='test')
    monkeypatch.setattr(supervisor, '_reachable', lambda *a: False)
    monkeypatch.setattr(launcher.shutil, 'which', lambda *a: None)
    assert 'card-binary' in supervisor.status(service.name)['prerequisite']
    monkeypatch.setattr(launcher.shutil, 'which', lambda *a: '/installed/card-binary')
    assert supervisor.status(service.name)['can_start']
    process = type('Process', (), {'stdout': io.BytesIO(b'ready\n'), 'returncode': None,
        'poll': lambda self: self.returncode})()
    commands = []
    monkeypatch.setattr(launcher.subprocess, 'Popen', lambda **kw: commands.append(kw) or process)
    monkeypatch.setattr(launcher, 'stop_service', lambda proc: setattr(proc, 'returncode', 0))
    assert supervisor.action(service.name, 'start')['status'] == 'running'
    assert commands[0]['cwd'] == path.parent
    assert supervisor.action(service.name, 'stop')['status'] == 'stopped'
    monkeypatch.setenv('OSII_ENABLE_COLLECTION_DATA_CARD', 'false')
    env['OSII_ENABLE_COLLECTION_DATA_CARD'] = 'false'
    assert launcher.processor_module_services('uv', env) == []
    assert 'collection-data-card' not in configuration.configured_tools(profile='development')


def test_new_module_appears_in_setup_before_it_runs(tmp_path, monkeypatch, client):
    from osii.api import processor_admin_routes
    from osii.domain.processing import capability_readiness as readiness
    modules = tmp_path / 'modules'
    write_module(modules)
    monkeypatch.setenv('OSII_PROCESSOR_MODULES_DIR', str(modules))
    monkeypatch.setattr(processor_admin_routes, '_cached_descriptor', lambda *a: {})
    monkeypatch.setattr(readiness, 'discover_remote_processors', lambda **kw: [])
    monkeypatch.setattr(readiness, '_service_probe', lambda *a: (False, 'not started'))
    records = client.get('/api/admin/processors').json()['processors']
    assert any(item['processor_id'] == 'example.collection-data-card' for item in records)
    summary = client.get('/api/intake/readiness').json()
    card = next(item for item in summary['enrichers'] if item['id'] == 'example.collection-data-card')
    assert not card['available']
    assert card['origin']['manifest'].endswith('processor-module.toml')
    assert card['config_schema']['properties']['detail']['default'] == 'short'


def test_discovery_is_bounded_and_never_imports_modules(tmp_path):
    write_module(tmp_path)
    (tmp_path / 'ignored' / 'deep').mkdir(parents=True)
    (tmp_path / 'ignored' / 'deep' / 'processor-module.toml').write_text('invalid toml [')
    (tmp_path / '.hidden').mkdir()
    (tmp_path / '.hidden' / 'processor-module.toml').write_text('invalid toml [')
    assert len(discover_processors(tmp_path)) == 1


@pytest.mark.parametrize('updates', [
    {'kind': 'retriever'}, {'kind': []}, {'port': 0}, {'port': True},
    {'command': []}, {'command': ['run.py', '--host=0.0.0.0']},
    {'port_env': 'lowercase'}, {'aliases': 'wrong'}, {'unknown_field': 'typo'},
    {'model_access': 'none'}, {'model_requirements': {'chat': 'typo'}},
    {'readiness_path': '//elsewhere/health'},
])
def test_invalid_manifest_is_reported_before_any_execution(tmp_path, updates):
    path = write_module(tmp_path, **updates)
    with pytest.raises(ModuleManifestError, match='processor-module.toml'):
        discover_processors(tmp_path)


def test_bad_schema_and_toml_have_actionable_paths(tmp_path):
    path = write_module(tmp_path)
    path.write_text('schema_version = 2\n')
    with pytest.raises(ModuleManifestError, match='schema_version'):
        discover_processors(tmp_path)
    path.write_text('[broken')
    with pytest.raises(ModuleManifestError, match='processor-module.toml'):
        discover_processors(tmp_path)


@pytest.mark.parametrize('field, value', [('id', 'collection-data-card'), ('registration_id', 'collection-data-card'), ('processor_id', 'example.collection-data-card'), ('aliases', ['example.collection-data-card'])])
def test_duplicate_identities_are_rejected(tmp_path, field, value):
    write_module(tmp_path)
    write_module(tmp_path, 'other', **{field: value})
    with pytest.raises(ModuleManifestError, match='duplicate'):
        discover_processors(tmp_path)


def test_resolved_ports_conflict_but_omitted_processors_do_not(tmp_path):
    write_module(tmp_path)
    write_module(tmp_path, 'other', port=18125)
    with pytest.raises(ModuleManifestError, match='conflicts'):
        active_processors(tmp_path, {'OSII_OTHER_PORT': '18123'})
    assert len(active_processors(tmp_path, {'OSII_OTHER_PORT': '18123', 'OSII_ENABLE_OTHER': 'false'})) == 1
    with pytest.raises(ModuleManifestError, match='OSII_OTHER_PORT'):
        active_processors(tmp_path, {'OSII_OTHER_PORT': 'bad'})


def test_module_manifest_cannot_escape_module_root(tmp_path):
    outside = tmp_path / 'outside'
    write_module(outside)
    root = tmp_path / 'modules'
    root.mkdir()
    (root / 'symlink').symlink_to(outside / 'collection-data-card', target_is_directory=True)
    with pytest.raises(ModuleManifestError, match='inside'):
        discover_processors(root)


def test_launcher_imports_without_installed_application_dependencies():
    result = subprocess.run([sys.executable, '-S', str(ROOT/'scripts/dev_stack.py'), '--help'], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert 'usage:' in result.stdout


def test_all_existing_processors_keep_their_switches_and_ids():
    processors = discover_processors(ROOT/'osii-processor-modules')
    assert {row.id for row in processors} == {'tika','banyan','tesseract-opencv','readable-wiki','concept-entity-wiki','csv-extractor','collection-table'}
    assert next(row for row in processors if row.id == 'banyan').registration_id == 'banyan-nemotron-parse'
    assert next(row for row in processors if row.id == 'tika').port_env == 'OSII_TIKA_ADAPTER_PORT'


def test_new_offline_extractor_uses_manifest_file_type_rules(tmp_path, monkeypatch):
    from osii.api.extractor_routes import validate_routes
    root = tmp_path / 'modules'
    write_module(root, 'custom-reader', kind='extractor', model_requirements={}, capabilities={'file_extensions': ['.foo']})
    monkeypatch.setenv('OSII_PROCESSOR_MODULES_DIR', str(root))
    monkeypatch.setattr('osii.api.processor_admin_routes._cached_descriptor', lambda *a: {})
    monkeypatch.setattr('osii.configuration.load_tools_config', lambda *a: {})
    route = {'name':'custom', 'extractor':'example.custom-reader', 'extensions':['.foo']}
    assert not validate_routes({'routes':[route]})[0]
    route['extensions'] = ['.pdf']
    assert any('cannot accept .pdf' in message for message in validate_routes({'routes':[route]})[0])


def test_descriptor_identity_mismatch_is_clear_in_setup(tmp_path, monkeypatch, client):
    from osii.domain.processing import capability_readiness as readiness
    root = tmp_path / 'modules'
    write_module(root)
    monkeypatch.setenv('OSII_PROCESSOR_MODULES_DIR', str(root))
    monkeypatch.setattr(readiness, '_service_probe', lambda *a: (True, 'up'))
    monkeypatch.setattr(readiness, 'discover_remote_processors', lambda **kw: [{'name':'wrong.processor', 'kind':'extractor', 'base_url':'http://127.0.0.1:18123'}])
    payload = client.get('/api/intake/readiness').json()
    card = next(item for item in payload['enrichers'] if item['id']=='example.collection-data-card')
    assert not card['available'] and 'does not match manifest' in card['detail']
    assert not any(item['id']=='wrong.processor' for item in payload['extractors'])


def test_missing_module_project_is_not_allowed_to_use_parent_workspace(tmp_path):
    path = write_module(tmp_path)
    (path.parent / 'pyproject.toml').unlink()
    with pytest.raises(ModuleManifestError, match='pyproject.toml is required'):
        discover_processors(tmp_path)


def test_core_service_name_cannot_be_shadowed(tmp_path):
    sys.path.insert(0, str(ROOT / 'scripts'))
    import dev_stack
    write_module(tmp_path, 'worker')
    with pytest.raises(ModuleManifestError, match='conflicts with a Core service'):
        dev_stack.processor_module_services('uv', {'OSII_PROCESSOR_MODULES_DIR':str(tmp_path)})


def test_disabling_module_does_not_persist_machine_specific_manifest_metadata(tmp_path, monkeypatch):
    from osii.api import processor_admin_routes as admin
    root = tmp_path / 'modules'
    write_module(root)
    monkeypatch.setenv('OSII_PROCESSOR_MODULES_DIR', str(root))
    saved = {'tools': {'collection-data-card': {'model_access': {'mode':'gateway', 'bindings':{'chat':'chosen'}}}}}
    monkeypatch.setattr(admin, 'load_tools_config', lambda *a: saved)
    monkeypatch.setattr(admin, 'save_tools_config', lambda *a: None)
    admin._save_tool(tmp_path, 'collection-data-card', None)
    override = saved['tools']['collection-data-card']
    assert override == {'enabled':False, 'model_access':{'mode':'gateway','bindings':{'chat':'chosen'}}}
    assert 'manifest_path' not in override and 'implementation' not in override
