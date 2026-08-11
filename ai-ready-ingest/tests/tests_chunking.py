from osii.indexing.chunking import generate_chunk_records
from osii.domain.storage.objects import write_text_file


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


def test_generate_sentence_windows_overlap_without_losing_offsets(
    temp_osii_root,
    sample_osii_object,
):
    file_id = sample_osii_object["file_id"]
    text = " ".join(
        f"Sentence {index} contains grounded technical context."
        for index in range(1, 15)
    )
    write_text_file(temp_osii_root, file_id, text)

    rows = generate_chunk_records(
        temp_osii_root,
        method="sentence_window",
        chunk_size=160,
        overlap=40,
    )

    assert len(rows) > 2
    assert all(row["text"] == text[row["char_start"]:row["char_end"]] for row in rows)
    assert all(len(row["text"]) <= 160 for row in rows)
    assert rows[0]["previous_chunk_id"] is None
    assert rows[-1]["next_chunk_id"] is None
    assert all(row["overlap_with_previous"] >= 40 for row in rows[1:])
    assert rows[1]["previous_chunk_id"] == rows[0]["chunk_id"]


def test_window_overlap_must_be_smaller_than_chunk_size(
    temp_osii_root,
    sample_osii_object,
):
    try:
        generate_chunk_records(
            temp_osii_root,
            method="sentence_window",
            chunk_size=100,
            overlap=100,
        )
        assert False, "Expected invalid overlap to fail"
    except ValueError as exc:
        assert "smaller than chunk_size" in str(exc)
