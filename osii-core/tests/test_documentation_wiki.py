import json

import pytest
from osii.domain.artifacts.documentation_wiki import (
    DocumentationCitation,
    DocumentationWikiPage,
    documentation_scope,
    get_documentation_wiki,
    read_documentation_evidence,
    save_documentation_wiki,
    search_documentation_wiki,
)
from osii.domain.scopes.collections import (
    add_documents_to_collection,
    create_collection,
)
from osii.processor_sdk.models import WikiMarkdownArtifactData
from pydantic import ValidationError


@pytest.fixture
def wiki_page(sample_osii_object):
    return DocumentationWikiPage(
        title="Thermal calibration",
        markdown="Calibration reduced drift in the reported experiment. Conditions may differ in production.",
        knowledge_kind="experimental_lesson",
        software="LabVIEW",
        software_version="2024",
        tags=["calibration", "drift"],
        citations=[
            DocumentationCitation(
                file_id=sample_osii_object["file_id"], char_start=0, char_end=19
            )
        ],
        change_summary="Record the experimental lesson and its limitations",
    )


def save(root, page, scope=None, revision=0):
    return save_documentation_wiki(
        root, scope, "thermal-calibration", page, expected_revision=revision
    )


def test_page_is_portable_standard_artifact_with_evidence(temp_osii_root, wiki_page):
    saved = save(temp_osii_root, wiki_page)
    data = saved["data"]
    assert WikiMarkdownArtifactData.model_validate(data).title == "Thermal calibration"
    assert saved["freshness"]["status"] == "current"
    assert saved["documentation_wiki"]["review_status"] == "unreviewed"
    assert saved["documentation_wiki"]["revision"] == 1
    assert data["citations"][0]["source_origin"]["representation"] == "canonical"
    assert json.loads((temp_osii_root / saved["relpath"]).read_text()) == data
    evidence = read_documentation_evidence(temp_osii_root, wiki_page.citations[0])
    assert evidence["match_text"] == "Thermal calibration"
    assert evidence["source_origins"][0]["segment_id"] == "seg-000001"


def test_updates_preserve_history_and_reject_lost_updates(temp_osii_root, wiki_page):
    save(temp_osii_root, wiki_page)
    with pytest.raises(ValueError, match="revision conflict"):
        save(temp_osii_root, wiki_page)
    revised = wiki_page.model_copy(
        update={"markdown": "Revised lesson with experimental limitations."}
    )
    result = save(temp_osii_root, revised, revision=1)
    info = result["documentation_wiki"]
    assert info["revision"] == 2
    assert info["history"][0]["page"]["markdown"] == wiki_page.markdown
    with pytest.raises(ValueError, match="revision conflict"):
        save(temp_osii_root, wiki_page, revision=1)
    assert (
        get_documentation_wiki(temp_osii_root, None, "thermal-calibration")["data"][
            "markdown"
        ]
        == revised.markdown
    )


@pytest.mark.parametrize("changed_file", ["text.txt", "manifest.jsonl", "meta.toml"])
def test_changed_evidence_marks_page_stale(temp_osii_root, wiki_page, changed_file):
    save(temp_osii_root, wiki_page)
    path = temp_osii_root / "objects" / wiki_page.citations[0].file_id / changed_file
    content = path.read_text()
    if changed_file == "meta.toml":
        content = content.replace("test123", "new-source-digest")
    else:
        content += "\n"
    path.write_text(content)
    result = get_documentation_wiki(temp_osii_root, None, "thermal-calibration")
    assert result["freshness"]["status"] == "stale"
    assert "Source changed" in result["freshness"]["reasons"][0]


def test_missing_evidence_marks_page_stale(temp_osii_root, wiki_page):
    save(temp_osii_root, wiki_page)
    (temp_osii_root / "objects" / wiki_page.citations[0].file_id / "text.txt").unlink()
    assert (
        get_documentation_wiki(temp_osii_root, None, "thermal-calibration")[
            "freshness"
        ]["status"]
        == "stale"
    )


def test_bounds_and_unknown_sources_are_rejected(temp_osii_root, wiki_page):
    too_long = wiki_page.model_copy(
        update={
            "citations": [
                DocumentationCitation(
                    file_id=wiki_page.citations[0].file_id, char_start=0, char_end=999
                )
            ]
        }
    )
    with pytest.raises(ValueError, match="outside canonical"):
        save(temp_osii_root, too_long)
    unknown = wiki_page.model_copy(
        update={
            "citations": [
                DocumentationCitation(file_id="unknown", char_start=0, char_end=10)
            ]
        }
    )
    with pytest.raises(ValueError, match="outside scope"):
        save(temp_osii_root, unknown)
    assert not list((temp_osii_root / "enrichments").glob("*.json"))
    assert not list((temp_osii_root / "enrichments").glob("*.lock"))


@pytest.mark.parametrize("page_id", ["../escape", "..", "/absolute", "a/b", "a\\b"])
def test_page_paths_are_bounded(temp_osii_root, wiki_page, page_id):
    with pytest.raises(ValueError, match="safe name"):
        save_documentation_wiki(
            temp_osii_root, None, page_id, wiki_page, expected_revision=0
        )


@pytest.mark.parametrize(
    "kind,key",
    [("object", "file_id"), ("folder", "folder_id"), ("collection", "collection_id")],
)
def test_scope_paths_are_bounded(temp_osii_root, kind, key):
    with pytest.raises(ValueError, match="safe name"):
        documentation_scope(temp_osii_root, {"scope_type": kind, key: "../../escape"})
    with pytest.raises(ValueError, match="Unknown"):
        documentation_scope(temp_osii_root, {"scope_type": kind, key: "missing"})


def test_collection_membership_limits_reuse(temp_osii_root, wiki_page):
    save(temp_osii_root, wiki_page)
    collection = create_collection(
        temp_osii_root,
        name="Selected documentation",
        description="",
        kind="manual",
        color=None,
    )
    scope = {"scope_type": "collection", "collection_id": collection["id"]}
    assert search_documentation_wiki(temp_osii_root, scope, query="calibration") == []
    with pytest.raises(ValueError, match="outside scope"):
        save(temp_osii_root, wiki_page, scope=scope)
    add_documents_to_collection(
        temp_osii_root, collection["id"], [wiki_page.citations[0].file_id]
    )
    assert search_documentation_wiki(temp_osii_root, scope, query="calibration")[0][
        "scope"
    ] == {"scope_type": "root"}
    save(temp_osii_root, wiki_page, scope=scope)
    assert any(
        item["scope"] == scope
        for item in search_documentation_wiki(temp_osii_root, None, query="calibration")
    )


@pytest.mark.parametrize(
    "scope",
    [
        {"scope_type": "object", "file_id": "sha256-test123"},
        {"scope_type": "folder", "folder_id": "folder-root"},
    ],
)
def test_object_and_folder_pages_are_discoverable(temp_osii_root, wiki_page, scope):
    save(temp_osii_root, wiki_page, scope=scope)
    assert (
        search_documentation_wiki(temp_osii_root, None, query="calibration")[0]["scope"]
        == scope
    )


def test_software_version_filters_and_token_coverage(temp_osii_root, wiki_page):
    save(temp_osii_root, wiki_page)
    assert (
        search_documentation_wiki(
            temp_osii_root, None, query="calibration", software_version="2023"
        )
        == []
    )
    assert (
        search_documentation_wiki(
            temp_osii_root, None, query="calibration", software="other"
        )
        == []
    )
    matches = search_documentation_wiki(
        temp_osii_root,
        None,
        query="how do I reduce calibration drift",
        software="labview",
        software_version="2024",
    )
    assert 0 < matches[0]["match_coverage"] < 1
    assert (
        search_documentation_wiki(temp_osii_root, None, query="calibration drift")[0][
            "match_coverage"
        ]
        == 1
    )


def test_existing_processor_wiki_is_available_but_untracked(temp_osii_root):
    directory = temp_osii_root / "enrichments"
    directory.mkdir(exist_ok=True)
    (directory / "other-processor.json").write_text(
        json.dumps(
            {
                "artifact_type": "wiki_markdown",
                "title": "Calibration",
                "markdown": "Calibration drift",
                "citations": [],
            }
        )
    )
    matches = search_documentation_wiki(temp_osii_root, None, query="calibration")
    assert matches[0]["page_id"] is None
    assert matches[0]["freshness"]["status"] == "untracked"


def test_locked_page_rejects_concurrent_writes(temp_osii_root, wiki_page):
    result = save(temp_osii_root, wiki_page)
    path = temp_osii_root / result["relpath"]
    lock = path.with_name(f".{path.name}.lock")
    lock.mkdir()
    with pytest.raises(ValueError, match="being updated"):
        save(temp_osii_root, wiki_page, revision=1)
    assert (
        get_documentation_wiki(temp_osii_root, None, "thermal-calibration")[
            "documentation_wiki"
        ]["revision"]
        == 1
    )


def test_interrupted_publication_preserves_readable_previous_revision(
    temp_osii_root, wiki_page, monkeypatch
):
    from osii.domain.artifacts import documentation_wiki

    saved = save(temp_osii_root, wiki_page)
    from osii.domain.artifacts import products
    write = products.atomic_write_text

    def interrupted_write(path, content):
        if path.name == "manifest.json":
            raise OSError("simulated interruption after metadata publication")
        return write(path, content)

    revised = wiki_page.model_copy(update={"markdown": "Updated calibration lesson."})
    with monkeypatch.context() as patch:
        patch.setattr(products, "atomic_write_text", interrupted_write)
        with pytest.raises(OSError, match="simulated interruption"):
            save(temp_osii_root, revised, revision=1)
    recovered = get_documentation_wiki(temp_osii_root, None, "thermal-calibration")
    assert recovered["data"]["markdown"] == wiki_page.markdown
    assert recovered["documentation_wiki"]["revision"] == 1
    assert recovered["freshness"]["status"] == "current"
    assert (
        save(temp_osii_root, revised, revision=1)["documentation_wiki"]["revision"] == 2
    )


def test_manual_edit_requires_evidence_revalidation(temp_osii_root, wiki_page):
    result = save(temp_osii_root, wiki_page)
    path = temp_osii_root / result["relpath"]
    payload = json.loads(path.read_text())
    payload["markdown"] = "A manually changed conclusion without revalidated citations."
    path.write_text(json.dumps(payload))
    assert (
        get_documentation_wiki(temp_osii_root, None, "thermal-calibration")[
            "freshness"
        ]["status"]
        == "untracked"
    )
    with pytest.raises(ValueError, match="revision conflict"):
        save(temp_osii_root, wiki_page, revision=1)


def test_symlinks_cannot_read_or_overwrite_external_pages(
    temp_osii_root, wiki_page, tmp_path
):
    result = save(temp_osii_root, wiki_page)
    path = temp_osii_root / result["relpath"]
    outside = tmp_path / "outside.json"
    path.rename(outside)
    path.symlink_to(outside)
    with pytest.raises(ValueError, match="symlink"):
        get_documentation_wiki(temp_osii_root, None, "thermal-calibration")
    with pytest.raises(ValueError, match="symlink"):
        save(temp_osii_root, wiki_page, revision=1)
    assert search_documentation_wiki(temp_osii_root, None, query="calibration") == []
    assert json.loads(outside.read_text())["markdown"] == wiki_page.markdown


@pytest.mark.parametrize(
    "field,value",
    [("title", "  "), ("markdown", "  "), ("change_summary", " "), ("citations", [])],
)
def test_pages_require_meaningful_cited_content(wiki_page, field, value):
    with pytest.raises(ValidationError):
        DocumentationWikiPage.model_validate({**wiki_page.model_dump(), field: value})
