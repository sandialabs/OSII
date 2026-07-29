from pathlib import Path

from osii.domain.storage.root_descriptor import write_collection_synthesis
from osii.domain.storage.store import ensure_osii_store_layout, folder_synth_path, root_synth_text_path
from osii.domain.storage.synth import write_folder_synth_text


def test_folder_baseline_synthesis_is_available_without_an_llm(tmp_path: Path):
    osii_root = tmp_path / ".osii"
    ensure_osii_store_layout(osii_root)

    result = write_folder_synth_text(
        osii_store=osii_root,
        folder_id="folder-root",
        folder_label="my_data",
        direct_doc_count=2,
        direct_subfolder_count=1,
    )

    assert result == folder_synth_path(osii_root, "folder-root")
    assert result.read_text(encoding="utf-8") == "my_data contains 2 direct documents and 1 direct subfolder."


def test_root_baseline_synthesis_uses_current_storage_writer(tmp_path: Path):
    osii_root = tmp_path / ".osii"
    ensure_osii_store_layout(osii_root)

    result = write_collection_synthesis(
        osii_store=osii_root,
        collection_name="ignored-compatibility-name",
        root_folder_label="my_data",
        total_files=3,
        top_level_doc_count=2,
        top_level_subfolder_count=1,
    )

    assert result == root_synth_text_path(osii_root)
    assert "my_data contains 3 documents" in result.read_text(encoding="utf-8")
