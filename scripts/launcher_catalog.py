"""Create and validate the reviewed, digest-pinned OSII launcher catalog."""

from __future__ import annotations

import copy
import re
from collections.abc import Callable, Iterable, Mapping
from typing import Any


CATALOG_VERSION = 1
NAMESPACE = "ai-ready-everything"
STACK_IMAGES = {
    "core": "core",
    "dashboard": "dashboard",
    "baseline-processors": "baselineProcessors",
}
TOOL_IMAGES = {
    "tesseract-opencv": {
        "id": "tesseract-opencv",
        "displayName": "Tesseract OCR with OpenCV regions",
        "description": "Processor API-compatible OCR with bounding boxes.",
    },
    "llm-wikis": {
        "id": "llm-wikis",
        "displayName": "LLM Wiki enrichers",
        "description": "Optional Processor API enrichers backed by an approved model endpoint.",
    },
}
GENERIC_IMAGES = {
    "tabular": {
        "id": "tabular-dataset-processors",
        "displayName": "Tabular dataset processors",
        "description": "Optional Processor API image; register and run it explicitly.",
    },
}
RELEASE = re.compile(r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\Z")
REGISTRY = re.compile(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?(?::[0-9]{1,5})?\Z")
DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
IMAGE_NAME = re.compile(r"osii-[a-z0-9]+(?:-[a-z0-9]+)*\Z")


class CatalogError(ValueError):
    """The catalog is unsafe, incomplete, or cannot be updated immutably."""


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CatalogError(f"{label} must be an object.")
    return value


def _list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise CatalogError(f"{label} must be an array.")
    return value


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CatalogError(f"{label} must be a non-empty string.")
    return value.strip()


def catalog_reference(registry: str, image: str, digest: str) -> str:
    """Return the one permitted immutable form of an OSII image reference."""
    validate_registry(registry)
    if not IMAGE_NAME.fullmatch(f"osii-{image}"):
        raise CatalogError(f"Unsupported OSII image name {image!r}.")
    if not DIGEST.fullmatch(digest):
        raise CatalogError(f"Image {image} must have a lowercase SHA-256 digest.")
    return f"{registry}/{NAMESPACE}/osii-{image}@{digest}"


def validate_registry(registry: str) -> None:
    if not REGISTRY.fullmatch(registry) or registry in {"localhost", "quay.io"}:
        raise CatalogError("Catalog registry must be a corporate Quay hostname without a URL scheme.")


def validate_reference(reference: Any, registry: str) -> str:
    value = _text(reference, "Catalog image reference")
    prefix = f"{registry}/{NAMESPACE}/"
    if not value.startswith(prefix):
        raise CatalogError(f"Catalog image must be below {prefix}.")
    image, separator, digest = value[len(prefix):].partition("@")
    if separator != "@" or not IMAGE_NAME.fullmatch(image) or not DIGEST.fullmatch(digest):
        raise CatalogError(
            "Catalog image references must use ai-ready-everything/osii-* and a lowercase @sha256 digest."
        )
    return value


def _validate_versions(
    entries: Iterable[Any], registry: str, label: str,
    verify_digest: Callable[[str], None] | None,
) -> None:
    labels: set[str] = set()
    for index, entry in enumerate(entries):
        version = _mapping(entry, f"{label}[{index}]")
        version_label = _text(version.get("label"), f"{label}[{index}].label")
        if version_label in labels:
            raise CatalogError(f"{label} has duplicate version label {version_label!r}.")
        labels.add(version_label)
        reference = validate_reference(version.get("reference"), registry)
        if verify_digest:
            verify_digest(reference)


def validate_catalog(
    catalog: Any, *, registry: str, verify_digest: Callable[[str], None] | None = None,
    allow_empty_stacks: bool = False,
) -> dict[str, Any]:
    """Validate the public contract plus every digest supplied by a caller."""
    validate_registry(registry)
    document = _mapping(catalog, "catalog.json")
    if document.get("version") != CATALOG_VERSION:
        raise CatalogError("catalog.json must keep version 1.")
    if document.get("registry") != registry:
        raise CatalogError("catalog.json registry must match the configured corporate Quay hostname.")
    if document.get("namespace") != NAMESPACE:
        raise CatalogError(f"catalog.json namespace must be {NAMESPACE!r}.")

    stacks = _list(document.get("stacks"), "catalog.json.stacks")
    if not stacks and not allow_empty_stacks:
        raise CatalogError("catalog.json needs at least one complete Stack release.")
    stack_ids: set[str] = set()
    for index, value in enumerate(stacks):
        stack = _mapping(value, f"stacks[{index}]")
        stack_id = _text(stack.get("id"), f"stacks[{index}].id")
        if stack_id in stack_ids:
            raise CatalogError(f"catalog.json has duplicate Stack id {stack_id!r}.")
        stack_ids.add(stack_id)
        _text(stack.get("displayName"), f"stacks[{index}].displayName")
        images = _mapping(stack.get("images"), f"stacks[{index}].images")
        if set(images) != {"release", *STACK_IMAGES.values()}:
            raise CatalogError("Every Stack must contain exactly release, core, dashboard, and baselineProcessors.")
        if _text(images.get("release"), f"stacks[{index}].images.release") != stack_id:
            raise CatalogError("A Stack id and its images.release must be identical.")
        for name, field in STACK_IMAGES.items():
            reference = validate_reference(images.get(field), registry)
            if verify_digest:
                verify_digest(reference)

    for section in ("tools", "images"):
        entries = _list(document.get(section), f"catalog.json.{section}")
        ids: set[str] = set()
        for index, value in enumerate(entries):
            entry = _mapping(value, f"{section}[{index}]")
            identifier = _text(entry.get("id"), f"{section}[{index}].id")
            if identifier in ids:
                raise CatalogError(f"catalog.json has duplicate {section} id {identifier!r}.")
            ids.add(identifier)
            _text(entry.get("displayName"), f"{section}[{index}].displayName")
            _text(entry.get("description"), f"{section}[{index}].description")
            if section == "tools" and entry.get("processorApi") is not True:
                raise CatalogError("Catalog tools must declare processorApi: true.")
            _validate_versions(entry.get("versions"), registry, f"{section}[{index}].versions", verify_digest)
    return dict(document)


def _upsert_stack(catalog: dict[str, Any], release: str, digests: Mapping[str, str]) -> None:
    images = {
        "release": release,
        **{
            field: catalog_reference(catalog["registry"], name, digests[name])
            for name, field in STACK_IMAGES.items()
        },
    }
    value = {"id": release, "displayName": f"OSII {release}", "images": images}
    stacks = catalog["stacks"]
    for index, stack in enumerate(stacks):
        if stack["id"] == release:
            stacks[index] = value
            return
    stacks.append(value)


def _upsert_version(
    entries: list[dict[str, Any]], metadata: Mapping[str, str], release: str, reference: str,
    *, tool: bool,
) -> None:
    entry = next((item for item in entries if item["id"] == metadata["id"]), None)
    if entry is None:
        entry = {
            "id": metadata["id"], "displayName": metadata["displayName"],
            "description": metadata["description"], "versions": [],
        }
        if tool:
            entry["processorApi"] = True
        entries.append(entry)
    existing = next((item for item in entry["versions"] if item["label"] == release), None)
    if existing is None:
        entry["versions"].append({"label": release, "reference": reference})
    elif existing["reference"] != reference:
        raise CatalogError(
            f"Catalog version {metadata['id']} {release} already has a different digest; publish a new version."
        )


def update_catalog(
    catalog: Any, *, release: str, image_digests: Mapping[str, str], published_images: Iterable[str],
) -> dict[str, Any]:
    """Add one compatible Stack and independent optional-image versions."""
    if not RELEASE.fullmatch(release):
        raise CatalogError("Catalog Stack release must be an immutable X.Y.Z identifier.")
    original = _mapping(catalog, "catalog.json")
    registry = _text(original.get("registry"), "catalog.json.registry")
    updated = copy.deepcopy(validate_catalog(catalog, registry=registry, allow_empty_stacks=True))
    for name in STACK_IMAGES:
        if name not in image_digests:
            raise CatalogError(f"Cannot publish a Stack until osii-{name} has an immutable digest.")
    _upsert_stack(updated, release, image_digests)
    published = set(published_images)
    for image, metadata in TOOL_IMAGES.items():
        if image in published:
            _upsert_version(
                updated["tools"], metadata, release,
                catalog_reference(updated["registry"], image, image_digests[image]), tool=True,
            )
    for image, metadata in GENERIC_IMAGES.items():
        if image in published:
            _upsert_version(
                updated["images"], metadata, release,
                catalog_reference(updated["registry"], image, image_digests[image]), tool=False,
            )
    return validate_catalog(updated, registry=updated["registry"])
