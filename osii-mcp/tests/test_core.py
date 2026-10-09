import asyncio
import os
import sys
from pathlib import Path

import pytest
from osii.domain.artifacts.documentation_wiki import DocumentationWikiPage
from osii.domain.storage.folders import write_folder_manifest
from osii.domain.storage.objects import (
    append_manifest_record,
    write_meta_toml,
    write_text_file,
)
from osii_mcp import core


@pytest.fixture
def fake_osii_root(tmp_path: Path, monkeypatch):
    root = tmp_path / ".osii"
    root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("OSII_ROOT", str(root))
    return root


def test_osii_root_env_required(monkeypatch):
    monkeypatch.delenv("OSII_ROOT", raising=False)
    with pytest.raises(RuntimeError):
        core._osii_root()


@pytest.fixture
def documentation_library(fake_osii_root):
    file_id = "manual-123"
    text = "LabVIEW queues transfer data between producer and consumer loops."
    write_meta_toml(
        fake_osii_root,
        file_id=file_id,
        source_relpath="manuals/labview.pdf",
        filename="labview.pdf",
        mime="application/pdf",
        size_bytes=123,
        mtime_utc="2026-01-01T00:00:00Z",
        sha256_hex="123",
    )
    write_text_file(fake_osii_root, file_id, text)
    append_manifest_record(
        fake_osii_root,
        file_id,
        {
            "kind": "text",
            "id": "seg-000001",
            "path": "text.txt",
            "type": "page",
            "span": {"char_start": 0, "char_end": len(text)},
            "source_origin": {"source_type": "pdf", "page": 1},
            "related_ids": [],
        },
    )
    write_folder_manifest(
        fake_osii_root,
        folder_id="manuals",
        path_hint="manuals",
        docs=[{"file_id": file_id, "source_relpath": "manuals/labview.pdf"}],
        subfolders=[],
        stats={},
    )
    page = DocumentationWikiPage(
        title="LabVIEW queues",
        markdown=text,
        software="LabVIEW",
        software_version="2024",
        citations=[{"file_id": file_id, "char_start": 0, "char_end": len(text)}],
        change_summary="Capture producer/consumer guidance",
    )
    return {"root": fake_osii_root, "file_id": file_id, "text": text, "page": page}


@pytest.mark.parametrize("query", ["LabVIEW queues", "LabVIEW queues."])
def test_current_wiki_reuses_knowledge_without_source_search(
    documentation_library, monkeypatch, query
):
    core.save_wiki_page("queues", documentation_library["page"], 0)

    def unexpected_search(*args, **kwargs):
        pytest.fail("Current matching wiki should avoid source retrieval")

    monkeypatch.setattr(core, "dashboard_search", unexpected_search)
    result = core.search_documentation(query)
    assert result["retrieval_mode_used"] == "wiki"
    assert result["source_search_performed"] is False
    assert result["wiki_matches"][0]["page_id"] == "queues"
    assert result["source_results"] == []


@pytest.mark.parametrize("reason", ["missing", "stale", "partial", "force", "version"])
def test_source_retrieval_fallback_is_explicit(
    documentation_library, monkeypatch, reason
):
    if reason != "missing":
        core.save_wiki_page("queues", documentation_library["page"], 0)
    if reason == "stale":
        write_text_file(
            documentation_library["root"],
            documentation_library["file_id"],
            "Updated source text",
        )
    calls = []

    def search(root, **kwargs):
        calls.append(kwargs)
        return "lexical", [
            {
                "file_id": documentation_library["file_id"],
                "char_start": 0,
                "char_end": 7,
                "page": 1,
            }
        ]

    monkeypatch.setattr(core, "dashboard_search", search)
    query = "LabVIEW queues memory" if reason == "partial" else "LabVIEW queues"
    result = core.search_documentation(
        query,
        prefer_wiki=reason != "force",
        software_version="2023" if reason == "version" else "",
    )
    assert result["source_search_performed"] is True
    assert result["retrieval_mode_used"] == "lexical"
    assert result["source_results"][0]["page"] == 1
    assert calls[0]["group_by"] is None


@pytest.mark.parametrize(
    "kwargs",
    [{"query": " "}, {"query": "x", "top_k": 0}, {"query": "x", "mode": "invalid"}],
)
def test_search_rejects_invalid_requests(fake_osii_root, kwargs):
    with pytest.raises(ValueError):
        core.search_documentation(**kwargs)


def test_canonical_evidence_remains_separate_from_edited_text(
    documentation_library, monkeypatch
):
    monkeypatch.setattr(
        core,
        "get_preferred_text_representation",
        lambda *args: {
            "name": "edited",
            "kind": "edited_text",
            "text": "different coordinates",
            "path": "edited_text.json",
        },
    )
    evidence = core.get_documentation_evidence(documentation_library["file_id"], 0, 7)
    assert evidence["representation"] == "canonical"
    assert evidence["match_text"] == "LabVIEW"
    assert (
        core.get_object_preferred_text(documentation_library["file_id"])[
            "representation"
        ]
        == "edited"
    )


def test_stdio_harness_can_learn_and_reuse_documentation(
    documentation_library, monkeypatch
):
    """Exercise actual MCP JSON-RPC, tool schemas and persistence in another process."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from osii.indexing.chunking import write_chunk_manifest

    manifest, _ = write_chunk_manifest(documentation_library["root"])
    with manifest.open("a") as stream:
        stream.write("malformed row to exercise protocol-safe diagnostics\n")

    monkeypatch.delenv("ATLAS_MCP_TOKEN", raising=False)
    monkeypatch.delenv("DEBUG", raising=False)

    async def workflow():
        parameters = StdioServerParameters(
            command=sys.executable,
            args=["-m", "osii_mcp.main", "--stdio"],
            env=dict(os.environ),
        )
        async with (
            stdio_client(parameters) as (read, write),
            ClientSession(read, write) as session,
        ):
            initialized = await session.initialize()
            assert "documentation" in initialized.instructions.lower()
            tools = await session.list_tools()
            names = {tool.name for tool in tools.tools}
            assert {
                "search_documentation",
                "get_documentation_evidence",
                "list_wiki_pages",
                "get_wiki_page",
                "save_wiki_page",
                "search_scope",
            } <= names
            searched = await session.call_tool(
                "search_documentation", {"query": "LabVIEW queues"}
            )
            assert not searched.isError
            assert searched.structuredContent["retrieval_mode_used"] == "lexical"
            assert searched.structuredContent["source_results"][0]["page"] == 1
            evidence = await session.call_tool(
                "get_documentation_evidence",
                {
                    "file_id": documentation_library["file_id"],
                    "char_start": 0,
                    "char_end": 7,
                },
            )
            assert not evidence.isError
            assert evidence.structuredContent["match_text"] == "LabVIEW"
            saved = await session.call_tool(
                "save_wiki_page",
                {
                    "page_id": "queues",
                    "page": documentation_library["page"].model_dump(),
                    "expected_revision": 0,
                },
            )
            assert not saved.isError
            assert saved.structuredContent["documentation_wiki"]["revision"] == 1
            found = await session.call_tool(
                "search_documentation", {"query": "LabVIEW queues"}
            )
            assert found.structuredContent["retrieval_mode_used"] == "wiki"
            read_page = await session.call_tool("get_wiki_page", {"page_id": "queues"})
            assert (
                read_page.structuredContent["data"]["markdown"]
                == documentation_library["text"]
            )
            assert "history" not in read_page.structuredContent["documentation_wiki"]
            conflict = await session.call_tool(
                "save_wiki_page",
                {
                    "page_id": "queues",
                    "page": documentation_library["page"].model_dump(),
                    "expected_revision": 0,
                },
            )
            assert conflict.isError

    asyncio.run(workflow())
    assert core.get_wiki_page("queues")["documentation_wiki"]["revision"] == 1


def test_search_diagnostics_do_not_pollute_stdout(
    documentation_library, capsys, caplog
):
    from osii.indexing.chunking import write_chunk_manifest
    from osii.search.lexical import load_chunk_manifest

    manifest, _ = write_chunk_manifest(documentation_library["root"])
    with manifest.open("a") as stream:
        stream.write("malformed row\n")
    assert load_chunk_manifest(documentation_library["root"])
    assert capsys.readouterr().out == ""
    assert "Malformed chunk manifest" in caplog.text
