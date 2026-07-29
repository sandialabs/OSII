from pathlib import Path

from osii.processors import remote


def test_configured_processor_urls(monkeypatch):
    monkeypatch.setenv(
        "OSII_PROCESSORS",
        "http://processor-a:8000/, http://processor-b:8000",
    )
    assert remote.configured_processor_urls() == [
        "http://processor-a:8000",
        "http://processor-b:8000",
    ]


def test_configured_processor_urls_includes_enabled_admin_registry(tmp_path, monkeypatch):
    monkeypatch.setenv("OSII_PROCESSORS", "http://processor-a:8000")
    monkeypatch.setenv("OSII_ROOT", str(tmp_path))
    state = tmp_path / "state"
    state.mkdir()
    (state / "processor_endpoints.json").write_text(
        '[{"id":"custom", "base_url":"http://custom:8000/", "enabled":true}, '
        '{"id":"disabled", "base_url":"http://disabled:8000", "enabled":false}]',
        encoding="utf-8",
    )

    assert remote.configured_processor_urls() == [
        "http://processor-a:8000",
        "http://custom:8000",
    ]


def test_discovery_ignores_unavailable_processors(monkeypatch):
    monkeypatch.setenv("OSII_PROCESSORS", "http://unavailable")

    def fail(*args, **kwargs):
        raise RuntimeError("unavailable")

    monkeypatch.setattr(remote, "_request_json", fail)
    assert remote.discover_remote_processors() == []
    assert remote.discover_remote_processors(include_errors=True)[0]["error"]
