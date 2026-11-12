"""Metadata-only, standalone home adapter. Never opens source text or vectors."""

from __future__ import annotations
import json
from pathlib import Path
import struct
import tomllib

from osii.domain.workbench import home_state
from osii.domain.read.sidecar import SidecarLibraryReader
from osii.domain.model_provider_config import selected_model, selected_processor
from osii.domain.storage.embedding_snapshot import active_snapshot
from osii.domain.artifacts.artifact_staleness import get_artifact_staleness
from osii.indexing.common import embedding_namespace
from osii.rag.config import get_chat_settings


def setup_dismissed(root: Path) -> bool:
    try:
        return (
            json.loads((root / "state" / "home.json").read_text()).get(
                "setup_dismissed"
            )
            is True
        )
    except FileNotFoundError:
        return False


def semantic_members(root: Path) -> set[str]:
    provider, model = (
        selected_processor("embedder", osii_root=root),
        selected_model("embedder", osii_root=root),
    )
    if not model or provider == "local.hashing":
        return set()
    namespace = root / "embeddings" / "providers"
    provider_dir, model_dir = embedding_namespace(model=model, provider=provider)
    try:
        directory = active_snapshot(namespace / provider_dir / model_dir)
        meta = tomllib.loads((directory / "segments.meta.toml").read_text())[
            "embeddings"
        ]
        count, dimension = meta["count"], meta["dimension"]
        if (
            meta.get("semantic") is not True
            or meta.get("model") != model
            or meta.get("provider") != provider
        ):
            return set()
        if (
            type(count) is not int
            or not 1 <= count <= 1_000_000
            or type(dimension) is not int
            or not 1 <= dimension <= 8192
        ):
            return set()
        index_path = directory / "segments.faiss"
        # IndexFlatIP's fixed identity/shape header is bounded; vector payloads
        # are validated by the destination tool, never materialized by Home.
        with index_path.open("rb") as handle:
            header = handle.read(16)
        if (
            len(header) != 16
            or header[:4] != b"IxFI"
            or struct.unpack("<iq", header[4:]) != (dimension, count)
        ):
            return set()
        if not count * dimension * 4 + 16 <= index_path.stat().st_size <= 1024 * 1024 * 1024:
            return set()
        members = set()
        total = 0
        mapping = directory / "segments.mapping.jsonl"
        if mapping.stat().st_size > 512 * 1024 * 1024:
            return set()
        with mapping.open() as handle:
            for line in handle:
                row = json.loads(line)
                if row.get("faiss_id") != total or not isinstance(
                    row.get("file_id"), str
                ):
                    return set()
                members.add(row["file_id"])
                total += 1
        return members if total == count else set()
    except (OSError, ValueError, KeyError, TypeError, struct.error):
        return set()


def local_home(root: Path) -> dict:
    reader = SidecarLibraryReader(root)
    members = semantic_members(root)
    documents = text_documents = indexed_documents = 0
    cursor = None
    while True:
        page = reader.list_documents(limit=500, cursor=cursor)
        for doc in page.items:
            documents += 1
            path = reader.representation_path(doc.file_id)
            has_text = path.is_file() and path.stat().st_size > 0
            text_documents += int(has_text)
            stale = (get_artifact_staleness(root, doc.file_id) or {}).get("stale", {})
            indexed_documents += int(
                has_text
                and doc.file_id in members
                and not stale.get("embeddings")
                and not stale.get("search_chunks")
            )
        if not page.next_cursor:
            break
        cursor = page.next_cursor
    chat = get_chat_settings(root)
    primary = chat.chat_provider_chain[0]
    configured = (primary == "ollama" and bool(chat.ollama_chat_model)) or (
        primary == "openai" and bool(chat.openai_chat_model)
    )
    return home_state(
        documents=documents,
        text_documents=text_documents,
        indexed_documents=indexed_documents,
        index_ready=bool(members),
        chat_configured=configured,
        setup_dismissed=setup_dismissed(root),
    )
