"""Display adapters for derived document metadata, shared across applications."""

from pathlib import Path

from osii.processor_sdk.document_metadata import DocumentMetadata

METADATA_ENRICHER = "core.document-metadata"
_AI_METHODS = {"text_llm", "vision_llm", "model_generated"}


def document_labels(document: dict) -> dict:
    return {
        key: document[key]
        for key in (
            "file_id",
            "filename",
            "source_relpath",
            "media_type",
            "document_title",
            "title_method",
            "document_metadata",
        )
        if key in document
    }


def synthesis_labels(metadata: dict) -> dict:
    labels = {
        key: metadata[key]
        for key in ("document_title", "title_method")
        if metadata.get(key)
    }
    if metadata.get("document_metadata"):
        try:
            record = DocumentMetadata.model_validate(metadata["document_metadata"])
            labels.update(
                document_metadata=record.model_dump(mode="json"),
                document_title=record.descriptive_title.value or record.title.value,
                title_method=record.method,
            )
        except ValueError:
            pass
    return labels


def saved_descriptive_title(labels: dict) -> str | None:
    """Use reviewed or inferred titles and older model headings for display."""
    if not (labels.get("document_metadata") or labels.get("title_method") in {"model_generated", "text_llm"}):
        return None
    title = labels.get("document_title")
    return " ".join(title.split())[:240] or None if isinstance(title, str) else None


METADATA_FIELDS = (
    "descriptive_title",
    "title",
    "author",
    "date",
    "agency",
    "document_type",
)


def metadata_source(labels: dict, field: str) -> tuple[str, str | None]:
    metadata = labels.get("document_metadata") or {}
    sources = labels.get("metadata_sources")
    saved = sources.get(field) if isinstance(sources, dict) else None
    if isinstance(saved, dict) and saved.get("kind") in ("ai", "unknown"):
        kind = saved["kind"]
        processor = saved.get("processor")
    else:
        method = metadata.get("method")
        if method == "human":
            return "edited", None
        kind = "ai" if method in _AI_METHODS or metadata.get("model") else "unknown"
        processor = labels.get("metadata_processor")
    return kind, processor if isinstance(processor, str) else None


def manual_metadata_product(values: dict, current: dict) -> dict:
    if not isinstance(values, dict) or set(values) - set(METADATA_FIELDS):
        raise ValueError("Provide document metadata fields only")
    record = DocumentMetadata.model_validate({
        "method": "human",
        "model": None,
        **{name: {"value": values.get(name)} for name in METADATA_FIELDS},
    }).model_dump(mode="json")
    data = {
        "artifact_type": "document_metadata",
        "title": "Document metadata",
        "document_metadata": record,
    }
    # The editor prefills saved suggestions. Saving another field must not
    # relabel an unchanged suggestion as human-authored.
    previous = current.get("document_metadata") or {}
    sources = {}
    for field in METADATA_FIELDS:
        value = record[field]["value"]
        old_value = (previous.get(field) or {}).get("value")
        if field == "document_type" and value and old_value:
            value, old_value = value.casefold(), old_value.casefold()
        if value and value == old_value:
            kind, processor = metadata_source(current, field)
            if kind != "edited":
                sources[field] = {"kind": kind, "processor": processor}
    if sources:
        data["metadata_sources"] = sources
    return data


def metadata_product_path(root: Path, file_id: str) -> Path:
    from osii.domain.read.sidecar import SidecarLibraryReader

    path = SidecarLibraryReader(root)._object(file_id) / "enrichments" / "document_metadata--manual.json"
    if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("Metadata must remain inside the local store")
    return path


def read_manual_metadata_product(root: Path, file_id: str) -> tuple[str | None, dict | None]:
    from osii.domain.artifacts.products import read_product

    history = read_product(metadata_product_path(root, file_id))
    data = history["data"]
    return history["current"], data if isinstance(data, dict) else None


def read_manual_metadata(root: Path, file_id: str) -> tuple[str | None, dict | None]:
    revision, data = read_manual_metadata_product(root, file_id)
    return revision, data.get("document_metadata") if data else None


def save_manual_metadata(
    root: Path, file_id: str, values: dict, expected: str | None
) -> tuple[str | None, dict | None]:
    from osii.domain.artifacts.products import publish_product
    from osii.domain.read.docs import get_doc_meta
    from osii.domain.read.synthesis import get_suggested_metadata

    if get_doc_meta(root, file_id) is None:
        raise LookupError("Unknown file_id")
    publish_product(
        root,
        metadata_product_path(root, file_id),
        manual_metadata_product(values, get_suggested_metadata(root, file_id)),
        origin="human",
        expected=expected,
        check_expected=True,
    )
    from osii.domain.catalog_db import upsert_document

    upsert_document(root, file_id)
    return read_manual_metadata(root, file_id)
