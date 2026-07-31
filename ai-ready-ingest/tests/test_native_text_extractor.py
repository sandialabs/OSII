from pathlib import Path

import fitz
import pytest

from osii.domain.storage.store import ensure_osii_store_layout
from osii.domain.processing.extractor_selection import (
    choose_extractor_for_path,
    load_extractor_routes,
)
from osii.extraction.dispatcher import dispatch_extract


def _extract(source: Path, source_root: Path, osii_root: Path) -> str:
    result = dispatch_extract(
        extractor_name="native_text",
        source_path=source,
        data_volume_root=source_root.parent,
        osii_store=osii_root,
    )
    return (osii_root / "objects" / result["file_id"] / "text.txt").read_text(
        encoding="utf-8"
    )


def test_native_text_extractor_handles_plain_text(tmp_path: Path):
    source_root = tmp_path / "source"
    source_root.mkdir()
    osii_root = tmp_path / ".osii"
    ensure_osii_store_layout(osii_root)
    source = source_root / "notes.md"
    source.write_text("Container-free extraction works.", encoding="utf-8")

    text = _extract(source, source_root, osii_root)

    assert "Container-free extraction works." in text


def test_native_text_extractor_preserves_pdf_page_text(tmp_path: Path):
    source_root = tmp_path / "source"
    source_root.mkdir()
    osii_root = tmp_path / ".osii"
    ensure_osii_store_layout(osii_root)
    source = source_root / "report.pdf"
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "Host-native PDF text")
    document.save(source)
    document.close()

    text = _extract(source, source_root, osii_root)

    assert "Host-native PDF text" in text


def test_native_routes_leave_unsupported_binaries_for_explicit_handling(
    monkeypatch,
):
    config = Path(__file__).resolve().parents[1] / "config" / "extractor_routes_native.toml"
    monkeypatch.setenv("OSII_EXTRACTOR_ROUTES_PATH", str(config))
    routes = load_extractor_routes()

    assert choose_extractor_for_path(Path("report.pdf"), routes) == "native_text"
    assert choose_extractor_for_path(Path("archive.bin"), routes) == "tika"


def test_native_text_extractor_rejects_scanned_pdf(tmp_path: Path):
    source_root = tmp_path / "source"
    source_root.mkdir()
    osii_root = tmp_path / ".osii"
    ensure_osii_store_layout(osii_root)
    source = source_root / "scan.pdf"
    document = fitz.open()
    document.new_page()
    document.save(source)
    document.close()

    with pytest.raises(RuntimeError, match="requires an OCR extractor"):
        _extract(source, source_root, osii_root)
