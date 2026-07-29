from osii.domain.storage.objects import write_meta_toml, append_manifest_record, write_text_file
from osii.domain.read.segments import get_segment_text


def test_segment_text_from_shared_text_file(temp_osii_root):
    file_id = "sha256-span-test"

    write_meta_toml(
        temp_osii_root,
        file_id=file_id,
        source_relpath="example_data/purcell.pdf",
        filename="example_data/purcell.pdf",
        mime="application/pdf",
        size_bytes=1000,
        mtime_utc="2026-05-21T00:00:00Z",
        sha256_hex="abc123",
        extra_meta=None,
    )

    full_text = "First segment text.\n\nSecond segment text.\n\nThird segment text."
    write_text_file(temp_osii_root, file_id, full_text)

    append_manifest_record(
        temp_osii_root,
        file_id,
        {
            "kind": "text",
            "id": "seg-000001",
            "path": "text.txt",
            "type": "chunk",
            "span": {
                "char_start": 0,
                "char_end": 19,
            },
            "source_origin": {
                "source_type": "generic_text",
                "unit_type": "chunk",
                "chunk_index": 1,
            },
        },
    )

    text = get_segment_text(temp_osii_root, file_id, 1)
    assert text == "First segment text."