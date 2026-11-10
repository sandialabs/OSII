"""Versioned text products. Canonical evidence remains in text representations.

The manifest is the commit point. JSON artifact paths remain compatibility views;
all Core readers use the manifest once it exists. Revisions travel with sidecars.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import uuid

from osii.domain.storage.atomic import atomic_write_text

_PROVENANCE = ContextVar("product_provenance", default={})


@contextmanager
def product_provenance(value: dict):
    token = _PROVENANCE.set(value)
    try:
        yield
    finally:
        _PROVENANCE.reset(token)


def current_product_provenance() -> dict:
    """Core orchestration metadata, without introducing a global job context."""
    return dict(_PROVENANCE.get())


def artifact_metadata(metadata: dict | None) -> dict:
    provenance = _PROVENANCE.get()
    return {**(metadata or {}), **({"provenance": provenance} if provenance else {})}


@contextmanager
def _lock(root: Path):
    path = root / "state" / "products.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            if not handle.read(1):
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            if os.name == "nt":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


def validate_scope(scope: dict) -> dict:
    if not isinstance(scope, dict):
        raise ValueError("Scope must be an object")
    kind = scope.get("scope_type") or scope.get("type")
    if not isinstance(kind, str):
        raise ValueError("Choose a document, folder, collection, or library.")
    key = {
        "object": "file_id",
        "folder": "folder_id",
        "collection": "collection_id",
        "root": None,
    }.get(kind)
    if kind not in {"object", "folder", "collection", "root"}:
        raise ValueError("Choose a document, folder, collection, or library.")
    if key:
        value = scope.get(key)
        if (
            not isinstance(value, str)
            or not value
            or value in {".", ".."}
            or any(c in value for c in "/\\\0")
        ):
            raise ValueError(f"Invalid {key}")
    return {"scope_type": kind, **({key: scope[key]} if key else {})}


def product_path(
    root: Path, scope: dict, filename: str, family: str = "enrichment"
) -> Path:
    from .enrichment_artifacts import _scope_enrichment_dir

    scope = validate_scope(scope)
    if family == "synthesis":
        from osii.domain.storage import store

        kind = scope["scope_type"]
        identity = (
            scope.get("file_id") or scope.get("folder_id") or scope.get("collection_id")
        )
        if filename == "current" and kind != "collection":
            function = getattr(store, f"{kind}_synth_text_path")
            path = function(root) if kind == "root" else function(root, identity)
        else:
            if (
                not filename.endswith(".txt")
                or Path(filename).name != filename
                or "\\" in filename
            ):
                raise ValueError("Choose one synthesis text product")
            function = getattr(store, f"{kind}_syntheses_dir")
            directory = function(root) if kind == "root" else function(root, identity)
            path = directory / filename
        if not path.resolve().is_relative_to(root.resolve()) or path.is_symlink():
            raise ValueError("Product must remain inside the local store")
        return path
    if family != "enrichment":
        raise ValueError("Unknown product family")
    relative = Path(filename)
    if (
        not filename
        or relative.is_absolute()
        or "\\" in filename
        or any(part.startswith(".") for part in relative.parts)
        or relative.suffix not in {".json", ".txt", ".md"}
        or filename.endswith(".meta.json")
    ):
        raise ValueError("Choose one JSON, text, or Markdown product inside this scope")
    base = _scope_enrichment_dir(root, scope)[1]
    path = base / relative
    if (
        not path.resolve().is_relative_to(base.resolve())
        or not path.resolve().is_relative_to(root.resolve())
        or path.is_symlink()
    ):
        raise ValueError("Product must remain inside this scope's local store")
    return path


def _directory(path: Path) -> Path:
    return path.parent / ".history" / hashlib.sha256(path.name.encode()).hexdigest()


def _read(path: Path):
    if not path.is_file():
        return None
    if path.suffix == ".txt":
        return {
            "artifact_type": "text",
            "title": "Summary",
            "text": path.read_text(encoding="utf-8"),
        }
    if path.suffix == ".md":
        return {
            "artifact_type": "wiki_markdown",
            "title": path.stem,
            "markdown": path.read_text(encoding="utf-8"),
            "citations": [],
        }
    return json.loads(path.read_text(encoding="utf-8"))


def _legacy(path: Path) -> dict:
    data = _read(path)
    if data is None:
        return {"current": None, "revisions": []}
    revision = (
        "legacy-"
        + hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
    )
    return {
        "current": revision,
        "revisions": [
            {
                "id": revision,
                "origin": "imported",
                "created_at": None,
                "data": data,
                "provenance": {},
            }
        ],
    }


def _load(path: Path) -> dict:
    manifest = _read(_directory(path) / "manifest.json")
    if manifest is None:
        return _legacy(path)
    raw = _read(path)
    # Portable sidecars may be edited by an external harness. A payload absent
    # from history is an untracked human revision, never silently discarded.
    # An older known payload is a lagging compatibility view after interruption;
    # the committed manifest remains authoritative in that case.
    if (
        raw is not None
        and manifest["current"]
        and not any(
            (
                r["data"].get("text") == raw.get("text")
                if path.suffix == ".txt"
                else r["data"].get("markdown") == raw.get("markdown")
                if path.suffix == ".md"
                else r["data"] == raw
            )
            for r in manifest["revisions"]
        )
    ):
        identity = (
            "external-"
            + hashlib.sha256(json.dumps(raw, sort_keys=True).encode()).hexdigest()
        )
        manifest["revisions"].append(
            {
                "id": identity,
                "origin": "human",
                "created_at": None,
                "data": raw,
                "provenance": {},
                "parent": manifest["current"],
                "grounding_needs_review": True,
            }
        )
        manifest["current"] = identity
    return manifest


def read_product(path: Path) -> dict:
    manifest = _load(path)
    active = next(
        (r for r in manifest["revisions"] if r["id"] == manifest["current"]), None
    )
    return {
        "current": manifest["current"],
        "data": active["data"] if active else None,
        "revisions": manifest["revisions"],
    }


def _commit(path: Path, manifest: dict):
    manifest["filename"] = path.name
    # A single atomic manifest contains complete immutable revisions, including
    # legacy imports. A crash cannot publish a pointer to a missing revision.
    atomic_write_text(
        _directory(path) / "manifest.json", json.dumps(manifest, ensure_ascii=False)
    )
    current = next(
        (r for r in manifest["revisions"] if r["id"] == manifest["current"]), None
    )
    if current:
        data = current["data"]
        content = (
            data["text"]
            if path.suffix == ".txt"
            else data["markdown"]
            if path.suffix == ".md"
            else json.dumps(data, indent=2, ensure_ascii=False)
        )
        atomic_write_text(path, content)
    else:
        path.unlink(missing_ok=True)


def publish_product(
    root: Path,
    path: Path,
    data: dict,
    *,
    origin: str = "generated",
    expected: str | None = None,
    check_expected: bool = False,
    generation_parents: dict[str, str | None] | None = None,
) -> dict:
    with _lock(root):
        manifest = _load(path)
        current = next(
            (r for r in manifest["revisions"] if r["id"] == manifest["current"]), None
        )
        if check_expected and manifest["current"] != expected:
            raise FileExistsError(
                "This product changed. Your draft is preserved; compare the latest revision before saving."
            )
        provenance = (
            current.get("provenance", {})
            if origin == "human" and current
            else _PROVENANCE.get()
        )
        # Publishing after a worker restart is idempotent for a completed output.
        previous = next(
            (
                r
                for r in manifest["revisions"]
                if origin == "generated"
                and (provenance.get("commit_id") or provenance.get("run_id"))
                and (
                    r.get("provenance", {}).get("commit_id") == provenance["commit_id"]
                    if provenance.get("commit_id") else
                    r.get("provenance", {}).get("run_id") == provenance["run_id"]
                )
                and r["origin"] == origin
            ),
            None,
        )
        if previous:
            if provenance.get("commit_id") and (previous["data"] != data or
                previous.get("provenance", {}).get("commit_fingerprint") != provenance.get("commit_fingerprint")):
                from osii.domain.storage.commits import CommitConflict
                raise CommitConflict("Processing commit already saved different product data")
            _commit(path, manifest)  # Repair a lagging/missing compatibility view.
            return previous
        revision = {
            "id": uuid.uuid4().hex,
            "origin": origin,
            "created_at": datetime.now(UTC).isoformat(),
            "data": data,
            "provenance": provenance,
            "parent": manifest["current"] if generation_parents is None else generation_parents.get(path.name),
            "grounding_needs_review": origin == "human",
        }
        manifest["revisions"].append(revision)
        # Human edits stay visible. Regeneration creates a candidate for review.
        if origin != "generated" or not current or (
            current["origin"] != "human" and
            (generation_parents is None or generation_parents.get(path.name) == manifest["current"])
        ):
            manifest["current"] = revision["id"]
        _commit(path, manifest)
        return revision


def write_artifact(root: Path, path: Path, data):
    publish_product(root, path, data)


def edit_product(
    root: Path, scope: dict, filename: str, markdown: str, expected: str
) -> dict:
    path = product_path(root, scope, filename)
    current = read_product(path)
    if (
        not isinstance(current["data"], dict)
        or current["data"].get("artifact_type") != "wiki_markdown"
    ):
        raise ValueError("This product is not an editable wiki.")
    data = {**current["data"], "markdown": markdown}
    # Keep citations as provenance; a changed human passage is not automatically grounded.
    publish_product(
        root, path, data, origin="human", expected=expected, check_expected=True
    )
    return read_product(path)


def activate_product(
    root: Path,
    scope: dict,
    filename: str,
    revision: str,
    expected: str,
    family: str = "enrichment",
) -> dict:
    path = product_path(root, scope, filename, family)
    with _lock(root):
        manifest = _load(path)
        if manifest["current"] != expected:
            raise FileExistsError(
                "This product changed. Reload its history before restoring a revision."
            )
        if not any(r["id"] == revision for r in manifest["revisions"]):
            raise ValueError("Revision not found")
        # A restore is a human decision: subsequent generation must not replace it.
        original = next(r for r in manifest["revisions"] if r["id"] == revision)
        restored = {
            **original,
            "id": uuid.uuid4().hex,
            "origin": "human",
            "restored_from": revision,
            "parent": expected,
            "created_at": datetime.now(UTC).isoformat(),
        }
        manifest["revisions"].append(restored)
        manifest["current"] = restored["id"]
        _commit(path, manifest)
    return read_product(path)


def delete_product(root: Path, path: Path):
    with _lock(root):
        manifest = _load(path)
        manifest["current"] = None
        _commit(path, manifest)


def product_input_state(root: Path, scope: dict, history: dict) -> str:
    from osii.domain.artifacts.text_representations import (
        get_preferred_text_representation,
    )
    from osii.domain.scopes.membership import list_scope_file_ids

    current = next(
        (r for r in history["revisions"] if r["id"] == history["current"]), None
    )
    if not current:
        return "unknown"
    provenance = current.get("provenance") or {}
    inputs = provenance.get("inputs")
    if not inputs:
        return "unknown"
    try:
        if set(provenance.get("member_ids", [])) != set(
            list_scope_file_ids(root, validate_scope(scope))
        ):
            return "stale"
        for item in inputs:
            preferred = get_preferred_text_representation(root, item["file_id"])
            if not preferred or hashlib.sha256(
                preferred["text"].encode()
            ).hexdigest() != item.get("source_sha256"):
                return "stale"
    except OSError:
        return "unavailable"
    return "current"


def write_text_product(root: Path, path: Path, text: str):
    publish_product(
        root, path, {"artifact_type": "text", "title": "Summary", "text": text}
    )


def edit_product_data(
    root: Path,
    scope: dict,
    filename: str,
    data,
    expected: str,
    family: str = "enrichment",
) -> dict:
    from pydantic import TypeAdapter
    from osii.processor_sdk.models import StandardArtifactData

    path = product_path(root, scope, filename, family)
    history = read_product(path)
    if history["data"] is None:
        raise ValueError("Product not found")
    serialized = json.dumps(data, allow_nan=False)
    if len(serialized) > 5_000_000:
        raise ValueError("An edited product must contain at most 5,000,000 characters")
    if (
        isinstance(history["data"], dict)
        and history["data"].get("artifact_type") == "document_metadata"
    ):
        from osii.processor_sdk.document_metadata import DocumentMetadata

        if (
            not isinstance(data, dict)
            or data.get("artifact_type") != "document_metadata"
        ):
            raise ValueError("Preserve the document metadata format")
        record = DocumentMetadata.model_validate(data.get("document_metadata"))
        data = {
            **data,
            "document_metadata": record.model_copy(
                update={"method": "human", "model": None}
            ).model_dump(mode="json"),
        }
    if path.suffix == ".txt":
        if not isinstance(data, dict) or not isinstance(data.get("text"), str):
            raise ValueError("A summary requires text")
        data = {**history["data"], "text": data["text"]}
    elif isinstance(history["data"], dict) and history["data"].get("artifact_type") in {
        "wiki_markdown",
        "table",
        "entity_list",
        "knowledge_graph",
    }:
        if (
            not isinstance(data, dict)
            or data.get("artifact_type") != history["data"]["artifact_type"]
        ):
            raise ValueError("Preserve the product format when editing")
        data = (
            TypeAdapter(StandardArtifactData)
            .validate_python(data)
            .model_dump(mode="json")
        )
    publish_product(
        root, path, data, origin="human", expected=expected, check_expected=True
    )
    return read_product(path)


def list_editable_products(root: Path, scope: dict) -> list[dict]:
    from osii.domain.storage import store

    scope = validate_scope(scope)
    products = []
    from .read_enrichments import list_scope_enrichments

    names = []
    for item in list_scope_enrichments(root, scope):
        if item["kind"] == "file":
            names.append(item["name"])
        elif item["kind"] == "bundle":
            names.extend(
                f"{item['name']}/{entry['name']}"
                for entry in item["files"]
                if not entry["is_dir"]
            )
    for name in names:
        if (
            Path(name).suffix not in {".json", ".txt", ".md"}
            or name.endswith(".meta.json")
            or any(part.startswith(".") for part in Path(name).parts)
        ):
            continue
        path = product_path(root, scope, name)
        data = read_product(path)["data"]
        if data is not None:
            products.append(
                {
                    "family": "enrichment",
                    "filename": name,
                    "title": data.get("title", name)
                    if isinstance(data, dict)
                    else name,
                    "artifact_type": data.get("artifact_type")
                    if isinstance(data, dict)
                    else None,
                }
            )
    kind = scope["scope_type"]
    identity = (
        scope.get("file_id") or scope.get("folder_id") or scope.get("collection_id")
    )
    directory_fn = getattr(store, f"{kind}_syntheses_dir")
    directory = directory_fn(root) if kind == "root" else directory_fn(root, identity)
    names = {path.name for path in directory.glob("*.txt")}
    for manifest_path in (directory / ".history").glob("*/manifest.json"):
        manifest = _read(manifest_path)
        name = manifest.get("filename") if isinstance(manifest, dict) else None
        if (
            isinstance(name, str)
            and name.endswith(".txt")
            and Path(name).name == name
            and manifest.get("current")
        ):
            names.add(name)
    names = sorted(
        name
        for name in names
        if read_product(product_path(root, scope, name, "synthesis"))["data"]
        is not None
    )
    if kind != "collection":
        path = product_path(root, scope, "current", "synthesis")
        if read_product(path)["data"] is not None:
            names.insert(0, "current")
    products.extend(
        {
            "family": "synthesis",
            "filename": name,
            "title": "Current summary"
            if name == "current"
            else name.removesuffix(".txt"),
            "artifact_type": "text",
        }
        for name in names
    )
    return products
