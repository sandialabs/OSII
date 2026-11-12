"""Display adapters for derived document metadata, shared across applications."""

from pathlib import Path

from osii.processor_sdk.document_metadata import DocumentMetadata


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


METADATA_FIELDS = (
    "descriptive_title",
    "title",
    "author",
    "date",
    "agency",
    "document_type",
)


def metadata_product_path(root: Path, file_id: str) -> Path:
    from osii.domain.artifacts.products import product_path

    return product_path(
        root,
        {"scope_type": "object", "file_id": file_id},
        "document_metadata--manual.json",
    )


def read_manual_metadata(root: Path, file_id: str) -> tuple[str | None, dict | None]:
    from osii.domain.artifacts.products import read_product

    history = read_product(metadata_product_path(root, file_id))
    data = history["data"]
    return history["current"], data.get("document_metadata") if isinstance(
        data, dict
    ) else None


def save_manual_metadata(
    root: Path, file_id: str, values: dict, expected: str | None
) -> tuple[str | None, dict | None]:
    from osii.domain.artifacts.products import publish_product
    from osii.domain.read.docs import get_doc_meta

    if get_doc_meta(root, file_id) is None:
        raise LookupError("Unknown file_id")
    if not isinstance(values, dict) or set(values) - set(METADATA_FIELDS):
        raise ValueError("Provide document metadata fields only")
    record = DocumentMetadata.model_validate(
        {
            "method": "human",
            "model": None,
            **{name: {"value": values.get(name)} for name in METADATA_FIELDS},
        }
    )
    publish_product(
        root,
        metadata_product_path(root, file_id),
        {
            "artifact_type": "document_metadata",
            "title": "Document metadata",
            "document_metadata": record.model_dump(mode="json"),
        },
        origin="human",
        expected=expected,
        check_expected=True,
    )
    from osii.domain.catalog_db import upsert_document

    upsert_document(root, file_id)
    return read_manual_metadata(root, file_id)
