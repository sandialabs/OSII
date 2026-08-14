from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest


LAUNCHER_PATH = Path(__file__).resolve().parents[1] / "run.py"
SPEC = importlib.util.spec_from_file_location("osii_baseline_launcher", LAUNCHER_PATH)
assert SPEC and SPEC.loader
launcher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(launcher)


@pytest.mark.parametrize(
    ("service", "directory", "port"),
    [
        ("extractor", "local-extractor", 8092),
        ("synthesizer", "local-synthesizer", 8093),
        ("embedder", "local-embedder", 8085),
        ("enricher", "local-enricher", 8094),
        ("model-bridge", "model-provider-bridge", 8095),
    ],
)
def test_selects_one_service_app_directory(monkeypatch, service, directory, port):
    service_root = Path(__file__).resolve().parents[2]
    call = {}
    monkeypatch.setenv("OSII_SERVICE_ROOT", str(service_root))
    monkeypatch.delenv("PORT", raising=False)
    monkeypatch.setattr(sys, "argv", ["run.py", service])
    monkeypatch.setattr(
        launcher.uvicorn,
        "run",
        lambda app, **kwargs: call.update({"app": app, **kwargs}),
    )

    launcher.main()

    assert call["app"] == "app.main:app"
    assert Path(call["app_dir"]).name == directory
    assert call["host"] == "0.0.0.0"
    assert call["port"] == port


def test_port_environment_can_override_default(monkeypatch):
    service_root = Path(__file__).resolve().parents[2]
    call = {}
    monkeypatch.setenv("OSII_SERVICE_ROOT", str(service_root))
    monkeypatch.setenv("PORT", "18085")
    monkeypatch.setattr(sys, "argv", ["run.py", "embedder"])
    monkeypatch.setattr(
        launcher.uvicorn,
        "run",
        lambda app, **kwargs: call.update({"app": app, **kwargs}),
    )

    launcher.main()

    assert call["port"] == 18085
