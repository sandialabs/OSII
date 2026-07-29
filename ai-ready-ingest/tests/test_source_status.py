from osii.domain.processing.source_status import (
    get_source_status_value,
    write_source_status,
)


def test_default_source_status_is_active(temp_osii_root, sample_osii_object):
    file_id = sample_osii_object["file_id"]
    assert get_source_status_value(temp_osii_root, file_id) == "active"


def test_write_missing_source_status(temp_osii_root, sample_osii_object):
    file_id = sample_osii_object["file_id"]

    write_source_status(
        temp_osii_root,
        file_id,
        status="missing_source",
        source_relpath="reports/example.pdf",
    )

    assert get_source_status_value(temp_osii_root, file_id) == "missing_source"