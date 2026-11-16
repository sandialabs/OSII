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
    # creation of the fake opsii root 
    root = tmp_path / ".osii"
    root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("OSII_ROOT", str(root))
    return root


@pytest.fixture
def documentation_library(fake_osii_root):
    # fake file created with basic text.
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
        docs=[
            {
                "file_id": file_id,
                "source_relpath": "manuals/labview.pdf",
            }
        ],
        subfolders=[],
        stats={},
    )

    # changing summary
    page = DocumentationWikiPage(
        title="LabVIEW queues",
        markdown=text,
        software="LabVIEW",
        software_version="2024",
        citations=[
            {
                "file_id": file_id,
                "char_start": 0,
                "char_end": len(text),
            }
        ],
        change_summary="Capture producer/consumer guidance",
    )

    return {
        "root": fake_osii_root,
        "file_id": file_id,
        "text": text,
        "page": page,
    }


def test_stdio_stale_page_is_refreshed_and_history_is_preserved(
    documentation_library, monkeypatch
):
    #Refreshing old (stale) documentation through the real MCP STDIO protocol.
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from osii.indexing.chunking import write_chunk_manifest

    root = documentation_library["root"]
    file_id = documentation_library["file_id"]
    original_text = documentation_library["text"]

    # Keeping the replacement the same length so the existing page segment remains valid while its canonical contents and source fingerprint change.
    revised_text = ("LabVIEW queues dispatch data between producer and consumer loops.")
    assert len(revised_text) == len(original_text)

    write_chunk_manifest(root)

    # STDIO transport intentionally does not require HTTP authentication. 
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
            await session.initialize()

            created = await session.call_tool(
                "save_wiki_page",
                {
                    "page_id": "queues",
                    "page": documentation_library["page"].model_dump(),
                    "expected_revision": 0,
                },
            )
            assert not created.isError
            assert created.structuredContent["freshness"]["status"] == "current"
            assert created.structuredContent["documentation_wiki"]["revision"] == 1

            current_search = await session.call_tool(
                "search_documentation",
                {"query": "LabVIEW queues"},
            )
            assert not current_search.isError
            assert current_search.structuredContent["retrieval_mode_used"] == "wiki"
            assert current_search.structuredContent["source_search_performed"] is False
            assert (
                current_search.structuredContent["wiki_matches"][0]["freshness"][
                    "status"
                ]
                == "current"
            )

            # Simulate changed and re-ingested canonical evidence. The test and
            # MCP subprocess share this temporary OSII store.
            write_text_file(root, file_id, revised_text)
            write_chunk_manifest(root)

            stale_page = await session.call_tool(
                "get_wiki_page",
                {"page_id": "queues"},
            )
            assert not stale_page.isError
            assert stale_page.structuredContent["freshness"]["status"] == "stale"
            assert stale_page.structuredContent["documentation_wiki"]["revision"] == 1

            # A stale page may remain visible, but it must not suppress source and force retrieval of the current evidence.
            stale_search = await session.call_tool(
                "search_documentation",
                {"query": "LabVIEW queues"},
            )
            assert not stale_search.isError
            assert stale_search.structuredContent["source_search_performed"] is True
            assert stale_search.structuredContent["retrieval_mode_used"] != "wiki"
            assert stale_search.structuredContent["source_results"]

            stale_matches = [
                item
                for item in stale_search.structuredContent["wiki_matches"]
                if item["page_id"] == "queues"
            ]
            assert stale_matches
            assert all(
                item["freshness"]["status"] == "stale"
                for item in stale_matches
            )

            evidence = await session.call_tool(
                "get_documentation_evidence",
                {
                    "file_id": file_id,
                    "char_start": 0,
                    "char_end": len(revised_text),
                },
            )
            assert not evidence.isError
            assert evidence.structuredContent["representation"] == "canonical"
            assert evidence.structuredContent["match_text"] == revised_text

            revised_page = documentation_library["page"].model_copy(
                update={
                    "markdown": revised_text,
                    "change_summary": (
                        "Refresh queue guidance after canonical evidence changed"
                    ),
                }
            )

            refreshed = await session.call_tool(
                "save_wiki_page",
                {
                    "page_id": "queues",
                    "page": revised_page.model_dump(),
                    "expected_revision": 1,
                },
            )
            assert not refreshed.isError
            assert refreshed.structuredContent["freshness"]["status"] == "current"
            assert refreshed.structuredContent["documentation_wiki"]["revision"] == 2

            refreshed_search = await session.call_tool(
                "search_documentation",
                {"query": "LabVIEW queues"},
            )
            assert not refreshed_search.isError
            assert refreshed_search.structuredContent["retrieval_mode_used"] == "wiki"
            assert (
                refreshed_search.structuredContent["source_search_performed"]
                is False
            )
            assert (
                refreshed_search.structuredContent["wiki_matches"][0]["freshness"][
                    "status"
                ]
                == "current"
            )

            page_with_history = await session.call_tool(
                "get_wiki_page",
                {
                    "page_id": "queues",
                    "include_history": True,
                },
            )
            assert not page_with_history.isError

            payload = page_with_history.structuredContent
            info = payload["documentation_wiki"]
            history = info["history"]

            assert payload["freshness"]["status"] == "current"
            assert payload["data"]["markdown"] == revised_text
            assert info["revision"] == 2
            assert info["retained_revision_count"] == 1
            assert len(history) == 1
            assert history[0]["page"]["markdown"] == original_text

    asyncio.run(workflow())

    # Confirm via core API outside MCP session boundary that the core API can read the updated page and that subprocess writes persist across process boundaries.
    final_page = core.get_wiki_page("queues", include_history=True)
    assert final_page["freshness"]["status"] == "current"
    assert final_page["data"]["markdown"] == revised_text
    assert final_page["documentation_wiki"]["revision"] == 2
    assert (
        final_page["documentation_wiki"]["history"][0]["page"]["markdown"]
        == original_text
    )
