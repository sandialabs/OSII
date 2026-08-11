import json
from pathlib import Path

from osii.extraction.osii_tesseract_extractor import OsiiTesseractExtractor


def test_tesseract_extractor_preserves_normalized_regions(monkeypatch, tmp_path: Path):
    source_root = tmp_path / "source"
    source_root.mkdir()
    source = source_root / "scan.pdf"
    source.write_bytes(b"test-pdf-placeholder")
    osii_root = tmp_path / ".osii"

    extractor = OsiiTesseractExtractor()
    monkeypatch.setattr(
        extractor,
        "_ocr_document",
        lambda *_args, **_kwargs: {
            "pages": [{
                "page": 1,
                "width": 1000,
                "height": 1400,
                "results": [{
                    "text": "Grounded OCR text",
                    "bbox": [0.1, 0.2, 0.7, 0.3],
                    "confidence": 0.96,
                    "polygon": [[0.1, 0.2], [0.7, 0.2], [0.7, 0.3], [0.1, 0.3]],
                }],
            }],
        },
    )

    result = extractor.extract(
        source_path=source,
        data_volume_root=source_root,
        osii_store=osii_root,
    )

    manifest_path = osii_root / "objects" / result["file_id"] / "manifest.jsonl"
    record = json.loads(manifest_path.read_text(encoding="utf-8").splitlines()[0])
    assert record["coordinate_space"] == "normalized"
    assert record["regions"][0]["bbox"] == [0.1, 0.2, 0.7, 0.3]
    assert record["source_origin"]["page_width"] == 1000
    assert record["source_origin"]["page_height"] == 1400
