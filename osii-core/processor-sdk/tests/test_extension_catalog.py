"""Keep the extension gate independent of local/hosted persistence and app fixtures."""
import importlib.util
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('extension_check', ROOT/'scripts/check_extensions.py')
checks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checks)


def fixture_repo(tmp_path):
    subprocess.run(['git','init','-q',str(tmp_path)],check=True)
    module = tmp_path/'osii-processor-modules'/'data-card'
    module.mkdir(parents=True)
    (module/'processor-module.toml').write_text('''schema_version=1
id="data-card"
[[processors]]
id="data-card"
processor_id="example.data-card"
kind="enricher"
display_name="Data card"
description="Fixture"
command=["run.py"]
port=18112
''')
    (module/'tests').mkdir()
    (module/'pyproject.toml').write_text('''[project]
name="fixture-data-card"
version="0.1"
[project.optional-dependencies]
dev=["pytest"]
[tool.osii.ci]
paths=["tests"]
extras=["dev"]
''')
    return module


def test_new_module_gets_offline_ci_without_workflow_list_edit(tmp_path):
    module = fixture_repo(tmp_path)
    commands = checks.check(tmp_path)
    assert len(commands)==1 and commands[0][0]==module
    assert '--extra' in commands[0][1] and 'dev' in commands[0][1]
    assert str(module/'tests') in commands[0][1]


def test_legacy_processor_ids_are_allowed_but_obsolete_folder_is_not(tmp_path):
    fixture_repo(tmp_path)
    source = tmp_path/'source.py'
    source.write_text('processor_id="toolbox.readable-wiki"\n')
    subprocess.run(['git','add','source.py'],cwd=tmp_path,check=True)
    assert checks.check(tmp_path)
    source.write_text('folder="osii-'+'toolbox"\n')
    with pytest.raises(ValueError,match='obsolete backend directory reference'):
        checks.check(tmp_path)


def test_module_cannot_silently_miss_manifest_or_tests(tmp_path):
    module = fixture_repo(tmp_path)
    (module/'processor-module.toml').unlink()
    with pytest.raises(ValueError,match='missing processor-module.toml'):
        checks.check(tmp_path)
    (module/'pyproject.toml').write_text('[project]\nname="fixture"\nversion="0.1"\n')
    with pytest.raises(ValueError,match='declare .* paths'):
        checks.module_test_command(module, ())


def test_module_test_paths_cannot_escape_project(tmp_path):
    module = fixture_repo(tmp_path)
    project=module/'pyproject.toml'
    project.write_text(project.read_text().replace('paths=["tests"]','paths=["../.."]'))
    with pytest.raises(ValueError,match='inside this module'):
        checks.check(tmp_path)


def test_absent_or_empty_catalog_cannot_pass_ci(tmp_path):
    subprocess.run(['git','init','-q',str(tmp_path)],check=True)
    with pytest.raises(ValueError,match='missing processor module directory'):
        checks.check(tmp_path)
    (tmp_path/'osii-processor-modules').mkdir()
    with pytest.raises(ValueError,match='no processor modules discovered'):
        checks.check(tmp_path)


def test_undeclared_test_extras_fail_before_install(tmp_path):
    module = fixture_repo(tmp_path)
    project=module/'pyproject.toml'
    project.write_text(project.read_text().replace('extras=["dev"]','extras=["typo"]'))
    with pytest.raises(ValueError,match='undeclared test/runtime extras'):
        checks.check(tmp_path)
