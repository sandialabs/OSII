"""Derived, agent-authored documentation knowledge; original evidence stays in OSII.

Wiki persistence belongs to Core. The calling harness supplies synthesis, rather
than requiring a second model provider inside the MCP transport.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from osii.domain.artifacts.read_enrichments import (
    get_scope_enrichment_payload,
    list_scope_enrichments,
)
from osii.domain.artifacts.text_spans import get_text_context_by_span
from osii.domain.read.catalog import load_folders_catalog
from osii.domain.read.docs import get_doc_meta
from osii.domain.read.segments import list_segments
from osii.domain.scopes.collections import get_collection, list_collections
from osii.domain.scopes.membership import list_scope_file_ids
from osii.domain.scopes.scopes import normalize_scope_type
from osii.domain.storage.atomic import atomic_write_text
from osii.domain.artifacts.products import write_artifact
from osii.domain.storage.store import (
    collection_enrichments_dir,
    folder_enrichments_dir,
    object_enrichments_dir,
    object_text_path,
    root_enrichments_dir,
)
from pydantic import BaseModel, ConfigDict, Field, model_validator


class DocumentationCitation(BaseModel):
    """Offsets refer to canonical extracted text, never edited/preferred text."""

    model_config = ConfigDict(extra="forbid")
    file_id: str = Field(min_length=1)
    char_start: int = Field(ge=0, strict=True)
    char_end: int = Field(gt=0, strict=True)

    @model_validator(mode="after")
    def ordered_span(self) -> DocumentationCitation:
        if self.char_end <= self.char_start:
            raise ValueError("citation must contain a non-empty text span")
        return self


class DocumentationWikiPage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=200)
    markdown: str = Field(min_length=1, max_length=60000)
    knowledge_kind: Literal[
        "software_documentation", "experimental_lesson", "research_finding", "other"
    ] = "software_documentation"
    software: str = Field(default="", max_length=200)
    software_version: str = Field(default="", max_length=200)
    tags: list[str] = Field(default_factory=list, max_length=30)
    citations: list[DocumentationCitation] = Field(min_length=1, max_length=50)
    change_summary: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def meaningful_content(self) -> DocumentationWikiPage:
        if not all(s.strip() for s in (self.title, self.markdown, self.change_summary)):
            raise ValueError("title, markdown and change_summary must contain text")
        if any(not tag.strip() or len(tag) > 100 for tag in self.tags):
            raise ValueError("tags must contain 1–100 characters")
        return self


def _identifier(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9_.-]{0,199}", value
    ):
        raise ValueError("identifier must be a single safe name")
    return value


def documentation_scope(osii_root: Path, scope: dict | None) -> dict:
    scope = scope if scope is not None else {"scope_type": "root"}
    kind = normalize_scope_type(scope.get("scope_type") or scope.get("type"))
    if kind == "root":
        return {"scope_type": "root"}
    key = {"object": "file_id", "folder": "folder_id", "collection": "collection_id"}[
        kind
    ]
    value = _identifier(scope.get(key) or scope.get("scope_id"))
    if kind == "object":
        exists = get_doc_meta(osii_root, value) is not None
    elif kind == "folder":
        exists = any(
            item.get("folder_id") == value for item in load_folders_catalog(osii_root)
        )
    else:
        exists = get_collection(osii_root, value) is not None
    if not exists:
        raise ValueError(f"Unknown {key}: {value}")
    return {"scope_type": kind, key: value}


def _enrichment_dir(osii_root: Path, scope: dict) -> Path:
    kind = scope["scope_type"]
    if kind == "object":
        path = object_enrichments_dir(osii_root, scope["file_id"])
    elif kind == "folder":
        path = folder_enrichments_dir(osii_root, scope["folder_id"])
    elif kind == "collection":
        path = collection_enrichments_dir(osii_root, scope["collection_id"])
    else:
        path = root_enrichments_dir(osii_root)
    if not path.resolve().is_relative_to(osii_root.resolve()):
        raise ValueError("Enrichment directory escapes OSII_ROOT")
    return path


def _fingerprint(osii_root: Path, file_id: str) -> dict:
    _identifier(file_id)
    path = object_text_path(osii_root, file_id)
    if not path.resolve().is_relative_to(osii_root.resolve()):
        raise ValueError("Source text escapes OSII_ROOT")
    meta = get_doc_meta(osii_root, file_id)
    if meta is None or not path.is_file():
        raise ValueError(f"Missing source text or metadata: {file_id}")
    return {
        "file_id": file_id,
        "text_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "source_relpath": meta.get("file", {}).get("source_relpath", ""),
        "source_sha256": meta.get("hash", {}).get("sha256", ""),
        "manifest_sha256": hashlib.sha256(
            path.with_name("manifest.jsonl").read_bytes()
        ).hexdigest()
        if path.with_name("manifest.jsonl").is_file()
        else "",
    }


def read_documentation_evidence(
    osii_root: Path, citation: DocumentationCitation, *, context_chars: int = 200
) -> dict:
    if (
        not 0 <= context_chars <= 2000
        or citation.char_end - citation.char_start > 12000
    ):
        raise ValueError(
            "Evidence is limited to 12000 characters and 0–2000 context characters"
        )
    fingerprint = _fingerprint(osii_root, citation.file_id)
    result = get_text_context_by_span(
        osii_root, **citation.model_dump(), context_chars=context_chars
    )
    if result is None or result["char_end"] != citation.char_end:
        raise ValueError("Citation span is outside canonical extracted text")
    origins = []
    for segment in list_segments(osii_root, citation.file_id):
        span = segment.get("span") or {}
        start, end = span.get("char_start"), span.get("char_end")
        if (
            isinstance(start, int)
            and isinstance(end, int)
            and start < citation.char_end
            and end > citation.char_start
        ):
            origins.append(
                {
                    "segment_id": segment.get("id"),
                    **(segment.get("source_origin") or {}),
                }
            )
    return {
        **result,
        "source": fingerprint,
        "representation": "canonical",
        "source_origins": origins,
    }


def _payload_hash(data: dict) -> str:
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _wiki_metadata(path: Path, data: dict) -> dict:
    metadata_path = path.with_name(f"{path.stem}.meta.json")
    if metadata_path.is_symlink() or not metadata_path.is_file():
        return {}
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}
    if not isinstance(metadata, dict):
        return {}
    digest = _payload_hash(data)
    if metadata.get("artifact_sha256") == digest:
        return metadata.get("documentation_wiki") or {}
    if metadata.get("previous_artifact_sha256") == digest:
        return metadata.get("previous_documentation_wiki") or {}
    return {}


def _freshness(
    osii_root: Path,
    data: dict,
    info: dict,
    members: set[str],
    fingerprints: dict[str, dict | None] | None = None,
) -> dict:
    citations = data.get("citations") or []
    sources = info.get("sources") or []
    if not citations or not sources:
        return {
            "status": "untracked",
            "reasons": ["No source fingerprints; inspect original evidence"],
        }
    reasons = []
    fingerprints = fingerprints if fingerprints is not None else {}
    cited_ids = {item.get("file_id") for item in citations}
    if cited_ids != {item.get("file_id") for item in sources}:
        reasons.append("Citation fingerprints are incomplete")
    for source in sources:
        file_id = source.get("file_id")
        if file_id not in members:
            reasons.append(f"Source outside current scope: {file_id}")
            continue
        if file_id not in fingerprints:
            try:
                fingerprints[file_id] = _fingerprint(osii_root, file_id)
            except (ValueError, OSError):
                fingerprints[file_id] = None
        if fingerprints[file_id] is None:
            reasons.append(f"Source unavailable: {file_id}")
        elif fingerprints[file_id] != source:
            reasons.append(f"Source changed: {file_id}")
    return {"status": "stale" if reasons else "current", "reasons": reasons}


def _filename(page_id: str) -> str:
    return f"wiki_markdown--coding-assistant-{_identifier(page_id)}.json"


def get_documentation_wiki(osii_root: Path, scope: dict | None, page_id: str) -> dict:
    scope = documentation_scope(osii_root, scope)
    if (_enrichment_dir(osii_root, scope) / _filename(page_id)).is_symlink():
        raise ValueError("Wiki page must not be a symlink")
    result = get_scope_enrichment_payload(osii_root, scope, _filename(page_id))
    if result is None:
        raise ValueError(f"Unknown wiki page: {page_id}")
    result["scope"] = scope
    info = _wiki_metadata(osii_root / result["relpath"], result["data"])
    result["documentation_wiki"] = info
    result["freshness"] = _freshness(
        osii_root, result["data"], info, set(list_scope_file_ids(osii_root, scope))
    )
    return result


def save_documentation_wiki(
    osii_root: Path,
    scope: dict | None,
    page_id: str,
    page: DocumentationWikiPage,
    *,
    expected_revision: int,
) -> dict:
    scope = documentation_scope(osii_root, scope)
    if (
        isinstance(expected_revision, bool)
        or not isinstance(expected_revision, int)
        or expected_revision < 0
    ):
        raise ValueError(
            "expected_revision must be a non-negative integer (0 creates a page)"
        )
    directory = _enrichment_dir(osii_root, scope)
    path = directory / _filename(page_id)
    lock = directory / f".{path.name}.lock"
    try:
        lock.mkdir()
    except FileExistsError as exc:
        raise ValueError("Wiki page is being updated; reread and retry") from exc
    try:
        if path.is_symlink() or path.with_name(f"{path.stem}.meta.json").is_symlink():
            raise ValueError("Wiki page must not be a symlink")
        previous = (
            json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
        )
        previous_info = _wiki_metadata(path, previous) if previous is not None else {}
        revision = previous_info.get("revision", 0)
        if revision != expected_revision or (previous is not None and revision == 0):
            raise ValueError(
                f"Wiki revision conflict: expected {expected_revision}, current {revision}"
            )
        members = set(list_scope_file_ids(osii_root, scope))
        sources = {}
        citations = []
        for citation in page.citations:
            if citation.file_id not in members:
                raise ValueError(f"Citation is outside scope: {citation.file_id}")
            evidence = read_documentation_evidence(osii_root, citation, context_chars=0)
            sources[citation.file_id] = evidence["source"]
            citations.append(
                {
                    **citation.model_dump(),
                    **(
                        {"segment_id": evidence["source_origins"][0]["segment_id"]}
                        if evidence["source_origins"]
                        else {}
                    ),
                    **(
                        {"page": evidence["source_origins"][0]["page"]}
                        if evidence["source_origins"]
                        and isinstance(evidence["source_origins"][0].get("page"), int)
                        and evidence["source_origins"][0]["page"] >= 1
                        else {}
                    ),
                    "source_origin": {
                        "representation": "canonical",
                        "origins": evidence["source_origins"],
                    },
                }
            )
        history = list(previous_info.get("history") or [])
        if previous:
            history.append(
                {
                    "revision": revision,
                    "updated_utc": previous_info.get("updated_utc"),
                    "page": previous,
                    "context": {
                        key: previous_info.get(key)
                        for key in (
                            "knowledge_kind",
                            "software",
                            "software_version",
                            "tags",
                            "change_summary",
                        )
                    },
                    "sources": previous_info.get("sources", []),
                }
            )
        payload = {
            "artifact_type": "wiki_markdown",
            "title": page.title,
            "markdown": page.markdown,
            "citations": citations,
        }
        info = {
            **page.model_dump(exclude={"title", "markdown", "citations"}),
            "schema_version": 1,
            "page_id": page_id,
            "revision": revision + 1,
            "authorship": "coding_harness",
            "review_status": "unreviewed",
            "updated_utc": datetime.now(UTC).isoformat(),
            "sources": list(sources.values()),
            "history": history[-20:],
        }
        if any(
            _fingerprint(osii_root, file_id) != source
            for file_id, source in sources.items()
        ):
            raise ValueError("Source changed while saving; reread evidence and retry")
        # Prepare metadata for both generations before atomically publishing the
        # standard artifact. Readers of the old payload still find matching
        # metadata, including if publication fails or the process is interrupted.
        metadata = {
            "artifact_sha256": _payload_hash(payload),
            "documentation_wiki": info,
            "previous_artifact_sha256": _payload_hash(previous) if previous else None,
            "previous_documentation_wiki": previous_info,
        }
        atomic_write_text(
            path.with_name(f"{path.stem}.meta.json"),
            json.dumps(metadata, indent=2, ensure_ascii=False),
        )
        write_artifact(osii_root, path, payload)
    finally:
        lock.rmdir()
    return get_documentation_wiki(osii_root, scope, page_id)


_STOP_WORDS = {
    "a",
    "an",
    "the",
    "to",
    "of",
    "in",
    "on",
    "for",
    "and",
    "or",
    "is",
    "are",
    "how",
    "do",
    "does",
    "i",
    "with",
    "what",
}


def _terms(text: str) -> set[str]:
    # Preserve dotted symbols and versions while ignoring sentence punctuation.
    return (
        {token.strip(".-") for token in re.findall(r"[\w.+#-]+", text.casefold())}
        - _STOP_WORDS
        - {""}
    )


def search_documentation_wiki(
    osii_root: Path,
    scope: dict | None,
    *,
    query: str = "",
    top_k: int = 10,
    software: str = "",
    software_version: str = "",
) -> list[dict]:
    """Heuristic token matching, not semantic retrieval or claim verification."""
    scope = documentation_scope(osii_root, scope)
    if not 1 <= top_k <= 50:
        raise ValueError("top_k must be between 1 and 50")
    members = set(list_scope_file_ids(osii_root, scope))
    scopes = [scope]
    if scope["scope_type"] != "root":
        scopes.append({"scope_type": "root"})
    else:
        scopes.extend(
            {"scope_type": "folder", "folder_id": _identifier(item["folder_id"])}
            for item in load_folders_catalog(osii_root)
        )
        scopes.extend(
            {"scope_type": "collection", "collection_id": _identifier(item["id"])}
            for item in list_collections(osii_root)
        )
    scopes.extend(
        {"scope_type": "object", "file_id": _identifier(file_id)}
        for file_id in sorted(members)
    )
    query_terms = _terms(query)
    matches = []
    seen = set()
    fingerprints: dict[str, dict | None] = {}
    for candidate_scope in scopes:
        key = tuple(sorted(candidate_scope.items()))
        if key in seen:
            continue
        seen.add(key)
        directory = _enrichment_dir(osii_root, candidate_scope)
        for artifact in list_scope_enrichments(osii_root, candidate_scope):
            if artifact.get("artifact_type") != "wiki_markdown":
                continue
            if (directory / artifact["name"]).is_symlink():
                continue
            result = get_scope_enrichment_payload(
                osii_root, candidate_scope, artifact["name"]
            )
            if result is None:
                continue
            data = result["data"]
            info = _wiki_metadata(directory / artifact["name"], data)
            # Shared root pages may only be reused when all evidence is in scope.
            cited_ids = {item.get("file_id") for item in data.get("citations", [])}
            if candidate_scope != scope and (not cited_ids or not cited_ids <= members):
                continue
            if software and info.get("software", "").casefold() != software.casefold():
                continue
            if (
                software_version
                and info.get("software_version", "").casefold()
                != software_version.casefold()
            ):
                continue
            terms = _terms(
                " ".join(
                    [
                        data.get("title", ""),
                        data.get("markdown", ""),
                        *info.get("tags", []),
                        info.get("software", ""),
                        info.get("software_version", ""),
                    ]
                )
            )
            matched = query_terms & terms
            if query_terms and not matched:
                continue
            matches.append(
                {
                    "scope": candidate_scope,
                    "filename": artifact["name"],
                    "page_id": info.get("page_id"),
                    "revision": info.get("revision"),
                    "title": data.get("title"),
                    "excerpt": data.get("markdown", "")[:2000],
                    "excerpt_truncated": len(data.get("markdown", "")) > 2000,
                    "knowledge_kind": info.get("knowledge_kind", "other"),
                    "software": info.get("software", ""),
                    "software_version": info.get("software_version", ""),
                    "citations": data.get("citations", []),
                    "review_status": info.get("review_status", "unreviewed"),
                    "freshness": _freshness(
                        osii_root, data, info, members, fingerprints
                    ),
                    "match_coverage": len(matched) / len(query_terms)
                    if query_terms
                    else 0.0,
                }
            )
    matches.sort(
        key=lambda item: (
            item["freshness"]["status"] != "current",
            -item["match_coverage"],
            item["title"] or "",
        )
    )
    return matches[:top_k]
