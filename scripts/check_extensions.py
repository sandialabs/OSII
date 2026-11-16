"""Check extension layout/naming and run each module's declared offline tests."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'osii-core'))
from osii.processor_modules import discover_processors


def module_test_command(directory: Path, extras: tuple[str, ...]) -> list[str]:
    config = tomllib.loads((directory / 'pyproject.toml').read_text())
    ci = config.get('tool', {}).get('osii', {}).get('ci', {})
    paths, arguments, test_extras = ci.get('paths'), ci.get('args', []), ci.get('extras', [])
    if not isinstance(paths, list) or not paths:
        raise ValueError(f'{directory}/pyproject.toml: declare [tool.osii.ci] paths for offline contract tests')
    for values in (paths, arguments, test_extras):
        if not isinstance(values, list) or any(not isinstance(value, str) or not value for value in values):
            raise ValueError(f'{directory}/pyproject.toml: CI paths, args, and extras must be string arrays')
    declared_extras = config.get('project', {}).get('optional-dependencies', {})
    missing = set([*extras, *test_extras]) - set(declared_extras)
    if missing:
        raise ValueError(f'{directory}/pyproject.toml: undeclared test/runtime extras: {sorted(missing)}')
    resolved = [(directory / path).resolve() for path in paths]
    if any(not path.is_relative_to(directory.resolve()) or not path.exists() for path in resolved):
        raise ValueError(f'{directory}/pyproject.toml: CI test paths must exist inside this module')
    return ['uv', 'run', '--python', '3.12', '--project', str(directory),
        *[arg for extra in dict.fromkeys([*extras, *test_extras]) for arg in ('--extra', extra)],
        'python', '-m', 'pytest', *map(str, resolved), '-q', *arguments]


def check(root: Path) -> list[tuple[Path, list[str]]]:
    obsolete = 'osii-' + 'toolbox'
    tracked = subprocess.check_output(['git', 'ls-files', '-z'], cwd=root).decode().split('\0')
    problems = []
    for name in filter(None, tracked):
        path = root / name
        if obsolete in Path(name).parts:
            problems.append(f'{name}: obsolete backend directory')
        if path.suffix == '.ipynb' or not path.is_file():
            continue
        if path.suffix not in {'.md', '.py', '.toml', '.yml', '.yaml', '.ts', '.tsx', '.ps1', '.txt'} and path.name not in {'Makefile', '.env.example', '.gitignore'}:
            continue
        if obsolete in path.read_text(encoding='utf-8'):
            problems.append(f'{name}: obsolete backend directory reference')
    modules = root / 'osii-processor-modules'
    if not modules.is_dir():
        raise ValueError(f'{modules}: missing processor module directory')
    processors = discover_processors(modules)
    declared = {row.directory: row.extras for row in processors}
    for project in modules.glob('*/pyproject.toml'):
        if not project.parent.name.startswith('.') and project.parent.resolve() not in declared:
            problems.append(f'{project.parent}: missing processor-module.toml')
    commands = [(directory, module_test_command(directory, extras)) for directory, extras in declared.items()]
    if not declared and not problems:
        problems.append(f'{modules}: no processor modules discovered')
    if problems:
        raise ValueError('\n'.join(problems))
    return commands


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--test', action='store_true', help='Run all declared module contract tests in isolated environments')
    args = parser.parse_args()
    try:
        commands = check(ROOT)
        print(f'Validated naming, manifests, and test declarations for {len(commands)} processor modules.', flush=True)
        if args.test:
            for directory, command in commands:
                print(f'Testing processor module: {directory.name}', flush=True)
                subprocess.run(command, cwd=ROOT, env={**os.environ, 'UV_PROJECT_ENVIRONMENT':str(directory/'osii-env')}, check=True)
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
