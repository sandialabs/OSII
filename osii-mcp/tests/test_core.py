from pathlib import Path
import os

import pytest

from osii_mcp import core


@pytest.fixture
def fake_osii_root(tmp_path: Path, monkeypatch):
    root = tmp_path / ".osii"
    root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("OSII_ROOT", str(root))
    return root


def test_osii_root_env_required(monkeypatch):
    monkeypatch.delenv("OSII_ROOT", raising=False)
    with pytest.raises(RuntimeError):
        core._osii_root()