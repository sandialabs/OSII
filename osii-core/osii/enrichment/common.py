from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
import hashlib
from pathlib import Path

from osii.domain.scopes.membership import list_scope_file_ids
from osii.domain.artifacts.text_representations import get_preferred_text_representation


def collect_scope_texts(osii_root: Path, scope: dict) -> tuple[list[dict], int]:
    frozen = _SCOPE_INPUTS.get()
    if frozen and frozen[:2] == (str(osii_root.resolve()), scope):
        documents = [dict(item) for item in frozen[2]]
        return documents, sum(len(item["text"]) for item in documents)
    file_ids = list_scope_file_ids(osii_root, scope)
    items = []
    total_chars = 0

    for file_id in file_ids:
        preferred = get_preferred_text_representation(osii_root, file_id)
        if preferred is None:
            continue

        text = preferred.get("text") or ""
        total_chars += len(text)

        items.append(
            {
                "file_id": file_id,
                "representation": preferred.get("name"),
                "kind": preferred.get("kind"),
                "path": preferred.get("path"),
                "text": text,
            }
        )

    return items, total_chars

# A worker request sees the exact bounded text that was approved at submission.
# Context-local storage leaves legacy/native enrichers compatible without a new
# filesystem access API or process-wide mutable input cache.
_SCOPE_INPUTS = ContextVar("osii_scope_inputs", default=None)


@contextmanager
def frozen_scope_inputs(osii_root: Path, scope: dict, documents: list[dict]):
    token = _SCOPE_INPUTS.set((str(osii_root.resolve()), scope, documents))
    try:
        yield
    finally:
        _SCOPE_INPUTS.reset(token)


def snapshot_scope(osii_root: Path, scope: dict, *, max_documents: int = 1000, max_chars: int = 200000) -> dict:
    """Freeze membership and bounded, disclosed excerpts from canonical sidecars."""
    file_ids = sorted(set(list_scope_file_ids(osii_root, scope)))
    if not file_ids:
        raise ValueError("No documents are in this scope.")
    if len(file_ids) > max_documents:
        raise ValueError(f"Choose a scope with at most {max_documents} documents for this tool.")
    allowance = max_chars // len(file_ids)
    documents = []
    for file_id in file_ids:
        preferred = get_preferred_text_representation(osii_root, file_id)
        if preferred is None or not (preferred.get("text") or "").strip():
            continue
        text = preferred["text"]
        path = osii_root / preferred["path"]
        info = path.stat()
        count = min(len(text), allowance)
        excerpt = text[:count]
        documents.append({"file_id": file_id, "representation": preferred["name"],
                          "kind": preferred["kind"], "path": preferred["path"], "text": excerpt,
                          "source_sha256": hashlib.sha256(text.encode()).hexdigest(),
                          "extraction_id": preferred.get("extraction_id"),
                          "size": info.st_size, "mtime_ns": info.st_mtime_ns,
                          "full_chars": len(text), "retained_spans": [{"start": 0, "end": count}],
                          "truncated": count < len(text)})
    if not documents:
        raise ValueError("Read document text before running this tool.")
    return {"documents": documents, "member_ids": file_ids,
            "text_chars": sum(len(d["text"]) for d in documents),
            "truncated_documents": sum(d["truncated"] for d in documents)}


def frozen_object_text(osii_root: Path, file_id: str) -> dict | None:
    frozen = _SCOPE_INPUTS.get()
    if not frozen or frozen[0] != str(osii_root.resolve()):
        return None
    for item in frozen[2]:
        if item["file_id"] == file_id:
            return dict(item)
    raise ValueError("Document is outside the saved scope inputs")


def has_frozen_scope_inputs(osii_root: Path, scope: dict) -> bool:
    value = _SCOPE_INPUTS.get()
    return bool(value and value[:2] == (str(osii_root.resolve()), scope))
