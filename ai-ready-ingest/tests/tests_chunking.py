from osii.indexing.chunking import generate_chunk_records


def test_generate_paragraph_chunks(temp_osii_root, sample_osii_object):
    rows = generate_chunk_records(
        temp_osii_root,
        method="paragraph",
    )
    assert len(rows) >= 1
    assert rows[0]["file_id"] == sample_osii_object["file_id"]
    assert rows[0]["chunk_method"] == "paragraph"
    assert rows[0]["char_end"] > rows[0]["char_start"]


def test_generate_window_chunks(temp_osii_root, sample_osii_object):
    rows = generate_chunk_records(
        temp_osii_root,
        method="window",
        chunk_size=10,
        overlap=2,
    )
    assert len(rows) >= 1
    assert rows[0]["file_id"] == sample_osii_object["file_id"]
    assert rows[0]["chunk_method"] == "window"