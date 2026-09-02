"""Portable subject-matter guidance, separate from extracted source evidence.

Processors receive the resolved text explicitly; they never read these files.
Context belongs to one exact scope, with no implicit hierarchy inheritance.
"""

from pathlib import Path

from osii.domain.storage.atomic import atomic_write_text


def expert_context_path(osii_root: Path, scope: dict) -> Path:
    """Return the canonical Markdown sidecar for a root/object/folder/collection."""
    root = Path(osii_root).resolve()
    kind = scope.get("scope_type") or scope.get("type")
    if kind == "root":
        path = root / "expert-context.md"
    else:
        keys = {"object": "file_id", "folder": "folder_id", "collection": "collection_id"}
        if kind not in keys:
            raise ValueError("Expert context scope must be root, object, folder, or collection.")
        identifier = scope.get(keys[kind])
        if not isinstance(identifier, str) or not identifier or identifier in {".", ".."} or any(
            char in identifier for char in "/\\:\x00"
        ):
            raise ValueError(f"A valid {keys[kind]} is required for expert context.")
        if kind == "folder":
            path = root / "folders" / f"folder-{identifier}.expert-context.md"
        else:
            directory = "objects" if kind == "object" else "collections"
            path = root / directory / identifier / "expert-context.md"
    if not path.resolve().is_relative_to(root):
        raise ValueError("Expert context must remain inside the OSII store.")
    return path


def save_expert_context(osii_root: Path, scope: dict, text: str) -> Path:
    """Save guidance atomically; an empty string explicitly clears saved guidance."""
    if not isinstance(text, str):
        raise ValueError("Expert context must be text.")
    text = text.strip()
    if len(text) > 20_000:
        raise ValueError("Expert context must not exceed 20,000 characters.")
    return atomic_write_text(expert_context_path(osii_root, scope), text + "\n" if text else "")


def load_expert_context(osii_root: Path, scope: dict) -> str | None:
    """Read saved guidance without changing the store; absent/empty means none."""
    path = expert_context_path(osii_root, scope)
    try:
        return path.read_text(encoding="utf-8").strip() or None
    except FileNotFoundError:
        return None


def resolve_expert_context(osii_root: Path, scope: dict, supplied: str | None) -> str | None:
    """Save new nonblank guidance, otherwise reuse guidance for this exact scope.

    Omitting context during OCR must not erase guidance needed by a later VLM.
    Use save_expert_context(..., "") to deliberately clear it instead.
    """
    if supplied is not None and not isinstance(supplied, str):
        raise ValueError("Expert context must be text or null.")
    if supplied and supplied.strip():
        save_expert_context(osii_root, scope, supplied)
        return supplied.strip()
    return load_expert_context(osii_root, scope)
