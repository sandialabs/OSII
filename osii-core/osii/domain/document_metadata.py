"""Display adapters for derived document metadata, shared across applications."""

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
