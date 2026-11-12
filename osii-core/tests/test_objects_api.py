def test_get_object_endpoint(client, sample_osii_object):
    file_id = sample_osii_object["file_id"]
    response = client.get(f"/api/objects/{file_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["file_id"] == file_id
    assert "meta" in data
    assert "overview" in data
    assert "collections" in data
    assert "processing" in data
    assert "capabilities" in data["processing"]
    assert "supports_markdown_render" in data["processing"]["capabilities"]


def test_get_object_preferred_text_canonical(client, sample_osii_object):
    file_id = sample_osii_object["file_id"]
    response = client.get(f"/api/objects/{file_id}/texts/preferred")
    assert response.status_code == 200
    data = response.json()
    assert data["file_id"] == file_id
    assert data["representation"] == "canonical"
    assert data["kind"] == "canonical_extracted_text"
    assert "thermal calibration drift" in data["text"].lower()


def test_get_object_preferred_text_edited(client, temp_osii_root, sample_osii_object):
    from osii.domain.artifacts.edited_text import put_edited_text_segments

    file_id = sample_osii_object["file_id"]
    put_edited_text_segments(
        temp_osii_root,
        file_id,
        [
            {
                "id": "seg-000001",
                "text": "Corrected OCR text.",
            }
        ],
    )

    response = client.get(f"/api/objects/{file_id}/texts/preferred")
    assert response.status_code == 200
    data = response.json()
    assert data["file_id"] == file_id
    assert data["representation"] == "edited"
    assert data["kind"] == "edited_text"
    assert "Corrected OCR text." in data["text"]


def test_get_object_text_representations(client, sample_osii_object):
    file_id = sample_osii_object["file_id"]
    response = client.get(f"/api/objects/{file_id}/texts")
    assert response.status_code == 200
    data = response.json()
    assert data["file_id"] == file_id
    assert "representations" in data
    assert "segments" in data
    assert any(item["name"] == "canonical" for item in data["representations"])


def test_get_object_syntheses(client, sample_osii_object):
    file_id = sample_osii_object["file_id"]
    response = client.get(f"/api/objects/{file_id}/syntheses")
    assert response.status_code == 200
    data = response.json()
    assert data["file_id"] == file_id
    assert "syntheses" in data


def test_creation_time_is_saved_when_available_without_unix_ctime_fallback(temp_osii_root, monkeypatch):
    from datetime import UTC, datetime
    from pathlib import Path
    from types import SimpleNamespace
    from osii.domain.read.docs import get_doc_meta
    from osii.domain.storage.objects import iso_birthtime_utc, write_meta_toml

    with monkeypatch.context() as patch:
        patch.setattr(Path, "stat", lambda _: SimpleNamespace(st_ctime=100))
        assert iso_birthtime_utc(Path("source.pdf")) is None
        patch.setattr(Path, "stat", lambda _: SimpleNamespace(st_birthtime=200, st_ctime=100))
        birthtime = iso_birthtime_utc(Path("source.pdf"))
        assert birthtime == datetime.fromtimestamp(200, UTC).isoformat()
    write_meta_toml(temp_osii_root, "sha256-creation", "source.pdf", "source.pdf",
                    "application/pdf", 100, "2026-05-21T00:00:00Z", "creation",
                    birthtime_utc=birthtime)
    assert get_doc_meta(temp_osii_root, "sha256-creation")["file"]["birthtime_utc"] == birthtime
