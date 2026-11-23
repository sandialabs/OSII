"""Declarative processor discovery shared by Core and the dependency-free launcher.

Only direct-child processor-module.toml files are read. Discovery never imports
module implementations, probes endpoints, installs dependencies, or runs commands.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import tomllib
from typing import Any, Mapping

MANIFEST_NAME = 'processor-module.toml'
KINDS = {'extractor', 'synthesizer', 'embedder', 'enricher'}
SLUG = re.compile(r'^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$')
IDENTITY = re.compile(r'^[a-z0-9][a-z0-9._-]*$')
ENV_NAME = re.compile(r'^[A-Z][A-Z0-9_]*$')


class ModuleManifestError(RuntimeError):
    """Invalid local module metadata; includes the manifest path and field."""


def enabled(value: str) -> bool:
    return value.strip().lower() not in {'false', '0', 'no', 'off'}


def load_startup_settings(env: Mapping[str, str]) -> dict[str, Any]:
    """Launcher-safe read; Core owns writes and legacy migration."""
    directory = Path(env.get('OSII_CONFIG_DIR', 'osii-data/config'))
    path = directory / 'processors.toml'
    if not path.exists():
        path = directory / 'tools.toml'  # Existing installations, before Core migrates.
    try:
        value = tomllib.loads(path.read_text(encoding='utf-8')).get('processor_startup', {})
    except FileNotFoundError:
        return {}
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ModuleManifestError(f'{path}: cannot read processor startup settings: {exc}') from exc
    if not isinstance(value, dict):
        raise ModuleManifestError(f'{path}: processor_startup must be a table')
    if any(not isinstance(settings, dict) for settings in value.values()):
        raise ModuleManifestError(f'{path}: each processor_startup service must be a table')
    return value


def modules_directory(env: Mapping[str, str] | None = None, checkout: Path | None = None) -> Path:
    env = os.environ if env is None else env
    checkout = checkout or Path(__file__).resolve().parents[2]
    configured = env.get('OSII_PROCESSOR_MODULES_DIR')
    directory = Path(configured).expanduser() if configured else checkout / 'osii-processor-modules'
    directory = directory if directory.is_absolute() else checkout / directory
    if configured and not directory.is_dir():
        raise ModuleManifestError(f'OSII_PROCESSOR_MODULES_DIR is not a directory: {directory}')
    return directory.resolve()


@dataclass(frozen=True)
class ModuleProcessor:
    manifest: Path
    module_id: str
    id: str
    registration_id: str
    processor_id: str
    kind: str
    display_name: str
    description: str
    command: tuple[str, ...]
    port: int
    port_env: str
    extras: tuple[str, ...]
    requires: tuple[str, ...]
    aliases: tuple[str, ...]
    model_access: str
    model_requirements: dict[str, str]
    capabilities: dict[str, Any]
    config_schema: dict[str, Any]
    health_path: str
    readiness_path: str
    readiness_config: tuple[str, ...]
    startup_schema: dict[str, Any]
    enabled_by_default: bool

    @property
    def directory(self) -> Path:
        return self.manifest.parent

    @property
    def enable_env(self) -> str:
        return 'OSII_ENABLE_' + self.id.upper().replace('-', '_')

    def is_enabled(self, env: Mapping[str, str]) -> bool:
        override = env.get(self.enable_env)
        return self.enabled_by_default if override is None else enabled(override)

    def resolved_port(self, env: Mapping[str, str]) -> int:
        try:
            port = int(env.get(self.port_env, str(self.port)))
            if not 1 <= port <= 65535:
                raise ValueError()
        except ValueError as exc:
            raise ModuleManifestError(f'{self.manifest}: {self.port_env} must be a port between 1 and 65535') from exc
        return port

    def registration(self, env: Mapping[str, str]) -> dict[str, Any]:
        return {
            'enabled': self.is_enabled(env), 'processor_id': self.processor_id,
            'display_name': self.display_name, 'description': self.description, 'kind': self.kind,
            'aliases': list(self.aliases),
            'runtime': {'mode': 'external', 'endpoint': f'http://127.0.0.1:{self.resolved_port(env)}'},
            'model_access': {'mode': self.model_access, **({'bindings': {}} if self.model_access == 'gateway' else {})},
            'model_requirements': self.model_requirements, 'capabilities': self.capabilities,
            'config_schema': self.config_schema, 'manifest_path': str(self.manifest),
            'implementation': str(self.directory), 'readiness_path': self.readiness_path,
            'readiness_config': list(self.readiness_config),
        }

    def startup_environment(self, env: Mapping[str, str], settings: Mapping[str, Any]) -> dict[str, str]:
        """Explicit deployment overrides win over saved Setup choices and defaults."""
        result = {}
        for name, property in self.startup_schema.get('properties', {}).items():
            value = env.get(name, settings.get(name, property['default']))
            if name not in env:
                _startup_scalar(value, property, name, self.manifest)
            result[name] = str(value).lower() if isinstance(value, bool) else str(value)
        return result


def _text(value: Any, field: str, path: Path) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ModuleManifestError(f'{path}: {field} must be a non-empty string')
    return value


def _strings(value: Any, field: str, path: Path) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ModuleManifestError(f'{path}: {field} must be an array of strings')
    return tuple(_text(item, field, path) for item in value)


def _startup_scalar(value: Any, property: dict, name: str, path: Path) -> None:
    expected = {'string': (str,), 'boolean': (bool,), 'integer': (int,), 'number': (int, float)}[property['type']]
    if type(value) not in expected:
        raise ModuleManifestError(f'{path}: {name} must have type {property["type"]}')
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if value < property.get('minimum', float('-inf')) or value > property.get('maximum', float('inf')):
            raise ModuleManifestError(f'{path}: {name} is outside its allowed range')


def _load(path: Path) -> list[ModuleProcessor]:
    try:
        data = tomllib.loads(path.read_text(encoding='utf-8'))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ModuleManifestError(f'{path}: {exc}') from exc
    if set(data) - {'schema_version', 'id', 'extras', 'processors'}:
        raise ModuleManifestError(f'{path}: unknown module fields: {sorted(set(data) - {"schema_version", "id", "extras", "processors"})}')
    if type(data.get('schema_version')) is not int or data['schema_version'] != 1:
        raise ModuleManifestError(f'{path}: schema_version must be 1')
    if not (path.parent / "pyproject.toml").is_file():
        raise ModuleManifestError(f"{path}: pyproject.toml is required in the module directory")
    module_id = _text(data.get('id'), 'id', path)
    if not SLUG.fullmatch(module_id):
        raise ModuleManifestError(f'{path}: id must be a lowercase hyphenated identifier')
    extras = _strings(data.get('extras', []), 'extras', path)
    if any(not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', extra) for extra in extras):
        raise ModuleManifestError(f'{path}: extras must be Python extra names')
    records = data.get('processors')
    if not isinstance(records, list) or not records:
        raise ModuleManifestError(f'{path}: processors must contain at least one [[processors]] table')
    allowed = {'id', 'registration_id', 'processor_id', 'kind', 'display_name', 'description', 'command', 'port', 'port_env', 'requires', 'aliases', 'model_access', 'model_requirements', 'capabilities', 'config_schema', 'health_path', 'readiness_path', 'readiness_config', 'startup_schema', 'enabled_by_default'}
    result = []
    for record in records:
        if not isinstance(record, dict) or set(record) - allowed:
            raise ModuleManifestError(f'{path}: unknown processor fields or invalid processor table')
        enabled_by_default = record.get('enabled_by_default', True)
        if not isinstance(enabled_by_default, bool):
            raise ModuleManifestError(f'{path}: enabled_by_default must be a boolean')
        identifier = _text(record.get('id'), 'processors.id', path)
        if not SLUG.fullmatch(identifier):
            raise ModuleManifestError(f'{path}: processors.id must be a lowercase hyphenated identifier')
        kind = record.get('kind')
        if not isinstance(kind, str) or kind not in KINDS:
            raise ModuleManifestError(f'{path}: kind must be one of {sorted(KINDS)}')
        command = _strings(record.get('command'), 'command', path)
        if not command or any(arg.split('=')[0] in {'--host', '--port'} for arg in command):
            raise ModuleManifestError(f'{path}: command must contain Python arguments without --host or --port (supplied by OSII)')
        port = record.get('port')
        if type(port) is not int or not 1 <= port <= 65535:
            raise ModuleManifestError(f'{path}: port must be between 1 and 65535')
        port_env = record.get('port_env', 'OSII_' + identifier.upper().replace('-', '_') + '_PORT')
        if not isinstance(port_env, str) or not ENV_NAME.fullmatch(port_env):
            raise ModuleManifestError(f'{path}: port_env must be an uppercase environment variable name')
        identities = [_text(record.get('registration_id', identifier), 'registration_id', path), _text(record.get('processor_id'), 'processor_id', path)]
        aliases = _strings(record.get('aliases', []), 'aliases', path)
        if any(not IDENTITY.fullmatch(item) for item in [*identities, *aliases]):
            raise ModuleManifestError(f'{path}: invalid registration_id, processor_id, or alias')
        tables = {}
        for key in ['model_requirements', 'capabilities', 'config_schema', 'startup_schema']:
            value = record.get(key, {})
            if not isinstance(value, dict):
                raise ModuleManifestError(f'{path}: {key} must be a table')
            tables[key] = value
        startup = tables['startup_schema']
        if startup:
            properties = startup.get('properties', {})
            if startup.get('type') != 'object' or not isinstance(properties, dict) or startup.get('additionalProperties') is not False:
                raise ModuleManifestError(f'{path}: startup_schema must be a closed object schema')
            for name, prop in properties.items():
                if not ENV_NAME.fullmatch(name) or name in {'DATABASE_URL', 'OSII_STORAGE_BACKEND', 'PYTHONPATH', 'UV_PROJECT_ENVIRONMENT', 'OSII_CONFIG_DIR'}:
                    raise ModuleManifestError(f'{path}: invalid startup setting {name}')
                if not isinstance(prop, dict) or prop.get('type') not in {'string', 'boolean', 'integer', 'number'} or 'default' not in prop:
                    raise ModuleManifestError(f'{path}: startup settings need scalar types and defaults')
                _startup_scalar(prop['default'], prop, name, path)
        if any(key not in {'chat', 'embedding'} or not isinstance(value, str) or value not in {'required', 'optional'} for key, value in tables['model_requirements'].items()):
            raise ModuleManifestError(f'{path}: invalid model_requirements')
        access = record.get('model_access', 'gateway' if tables['model_requirements'] else 'none')
        if not isinstance(access, str) or access not in {'gateway', 'none'} or (access == 'none' and 'required' in tables['model_requirements'].values()):
            raise ModuleManifestError(f'{path}: model_access must satisfy model_requirements')
        health_path = record.get('health_path', '/health')
        readiness_path = record.get('readiness_path', health_path)
        for url_path in [health_path, readiness_path]:
            if not isinstance(url_path, str) or not url_path.startswith('/') or url_path.startswith('//') or any(char in url_path for char in '?#\\'):
                raise ModuleManifestError(f'{path}: health/readiness paths must be relative HTTP paths without a query or fragment')
        result.append(ModuleProcessor(path, module_id, identifier, *identities, kind,
            _text(record.get('display_name'), 'display_name', path), _text(record.get('description'), 'description', path),
            command, port, port_env, extras, _strings(record.get('requires', []), 'requires', path), aliases,
            access, tables['model_requirements'], tables['capabilities'], tables['config_schema'], health_path, readiness_path,
            _strings(record.get('readiness_config', []), 'readiness_config', path), startup, enabled_by_default))
    return result


def discover_processors(directory: Path | None = None) -> list[ModuleProcessor]:
    directory = (directory or modules_directory()).resolve()
    processors = []
    module_ids: set[str] = set()
    seen: dict[tuple[str, str], Path] = {}
    for manifest in sorted(directory.glob('*/' + MANIFEST_NAME)):
        if manifest.parent.name.startswith('.'):
            continue
        if manifest.resolve().parent.parent != directory:
            raise ModuleManifestError(f'{manifest}: module must reside inside the configured modules directory')
        rows = _load(manifest)
        if rows[0].module_id in module_ids:
            raise ModuleManifestError(f'{manifest}: duplicate module id {rows[0].module_id}')
        module_ids.add(rows[0].module_id)
        for row in rows:
            identities = [('service', row.id), ('registration', row.registration_id), *[('processor', name) for name in (row.processor_id, *row.aliases)]]
            for key in identities:
                if key in seen:
                    raise ModuleManifestError(f'{manifest}: duplicate {key[0]} identity {key[1]} (also in {seen[key]})')
                seen[key] = manifest
        processors.extend(rows)
    return processors


def active_processors(directory: Path | None = None, env: Mapping[str, str] | None = None) -> list[ModuleProcessor]:
    env = os.environ if env is None else env
    result = [row for row in discover_processors(directory) if row.is_enabled(env)]
    ports: dict[int, str] = {}
    for row in result:
        port = row.resolved_port(env)
        if port in ports:
            raise ModuleManifestError(f'{row.manifest}: port {port} conflicts with processor {ports[port]}; adjust {row.port_env} or an OSII_ENABLE_ switch')
        ports[port] = row.id
    return result
