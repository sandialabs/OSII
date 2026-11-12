import argparse
import os
import sys
from pathlib import Path

from fastmcp import FastMCP
from fastmcp.server.auth.providers.jwt import StaticTokenVerifier
from osii.domain.artifacts.documentation_wiki import DocumentationWikiPage

from osii_mcp import core

ABOUT_PATH = Path(__file__).resolve().parent / "About.md"

DEBUG = os.getenv("DEBUG", "false").lower() == "true"


def _build_auth() -> StaticTokenVerifier | None:
    if DEBUG or "--stdio" in sys.argv:
        return None

    token = os.getenv("ATLAS_MCP_TOKEN")
    if not token:
        raise ValueError(
            "ATLAS_MCP_TOKEN environment variable is not set. "
            "Set it to a non-empty token before starting the server."
        )

    return StaticTokenVerifier(
        tokens={
            token: {
                "user_id": "atlas-ui",
                "client_id": "atlas-ui-backend",
                "scopes": ["read", "write"],
            }
        }
    )


def _load_about() -> str:
    try:
        return ABOUT_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        return "About.md was not found."


mcp = FastMCP("osii-mcp", instructions=_load_about(), auth=_build_auth())


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": False})
def search_documentation(
    query: str,
    scope: dict | None = None,
    mode: str = "hybrid",
    top_k: int = 5,
    prefer_wiki: bool = True,
    software: str = "",
    software_version: str = "",
) -> dict:
    """Find coding guidance in current cited wiki pages, then OSII source passages.

    Scope defaults to the library root. Set prefer_wiki=False to retrieve source
    passages even when a current wiki matches. Wiki matching is heuristic; check
    software/version applicability and read full pages before relying on excerpts.
    """
    return core.search_documentation(
        query,
        scope,
        mode=mode,
        top_k=top_k,
        prefer_wiki=prefer_wiki,
        software=software,
        software_version=software_version,
    )


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": False})
def get_documentation_evidence(
    file_id: str, char_start: int, char_end: int, context_chars: int = 200
) -> dict:
    """Read a canonical source passage, PDF page/segment origins, and source identity.

    Use search result offsets; edited/preferred text has different coordinates.
    This evidence supports citations when saving API guidance or research lessons.
    """
    return core.get_documentation_evidence(file_id, char_start, char_end, context_chars)


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": False})
def list_wiki_pages(
    scope: dict | None = None,
    query: str = "",
    top_k: int = 10,
    software: str = "",
    software_version: str = "",
) -> dict:
    """Discover reusable wiki pages, their revision, source freshness and excerpts."""
    return core.list_wiki_pages(scope, query, top_k, software, software_version)


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": False})
def get_wiki_page(
    page_id: str, scope: dict | None = None, include_history: bool = False
) -> dict:
    """Read a harness-authored wiki page, citations, freshness and revision history.

    Revision history is omitted unless include_history=True to save context.
    Pass the page's scope from search/list results. For other processors' wiki
    artifacts use get_enrichment_artifact with the listed filename and scope.
    """
    return core.get_wiki_page(page_id, scope, include_history)


@mcp.tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "openWorldHint": False,
    }
)
def save_wiki_page(
    page_id: str,
    page: DocumentationWikiPage,
    expected_revision: int,
    scope: dict | None = None,
) -> dict:
    """Persist or improve cited coding knowledge as a standard OSII wiki artifact.

    The harness authors the page. Cite canonical source spans and state software,
    version, experimental conditions, limitations and unresolved contradictions.
    expected_revision=0 creates a page; updates require the last read revision.
    Source existence/bounds are checked; semantic support is not verified.
    """
    return core.save_wiki_page(page_id, page, expected_revision, scope)


@mcp.tool
def get_root_scope() -> dict:
    return core.get_root_scope()


@mcp.tool
def list_folder_scopes() -> dict:
    return core.list_folder_scopes()


@mcp.tool
def list_collection_scopes() -> dict:
    return core.list_collection_scopes()


@mcp.tool
def describe_scope(scope: dict) -> dict:
    return core.describe_scope_core(scope)


@mcp.tool
def get_scope_summaries(scope: dict) -> dict:
    return core.get_scope_summaries(scope)


@mcp.tool
def get_scope_artifacts(scope: dict) -> dict:
    return core.get_scope_artifacts(scope)


@mcp.tool
def list_enrichment_artifacts(scope: dict) -> dict:
    """List standard or custom enrichment artifacts attached to a scope."""
    return core.list_enrichment_artifacts(scope)


@mcp.tool
def get_enrichment_artifact(scope: dict, filename: str) -> dict:
    """Read one enrichment JSON artifact for table/graph/entity/wiki interaction."""
    return core.get_enrichment_artifact(scope, filename)


@mcp.tool
def get_collection(collection_id: str) -> dict:
    return core.get_collection_core(collection_id)


@mcp.tool
def get_object(file_id: str) -> dict:
    return core.get_object_core(file_id)


@mcp.tool
def get_object_preferred_text(file_id: str) -> dict:
    return core.get_object_preferred_text(file_id)


@mcp.tool
def get_object_text_span_context(
    file_id: str, char_start: int, char_end: int, context_chars: int = 200
) -> dict:
    return core.get_object_text_span_context(
        file_id, char_start, char_end, context_chars
    )


@mcp.tool
def search_scope(
    query: str,
    scope: dict,
    mode: str = "hybrid",
    top_k: int = 10,
    group_by: str | None = "file",
) -> dict:
    return core.search_scope(query, scope, mode=mode, top_k=top_k, group_by=group_by)


@mcp.prompt
def about() -> str:
    return _load_about()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Start the OSII coding documentation assistant"
    )
    transport = parser.add_mutually_exclusive_group()
    transport.add_argument(
        "--stdio",
        action="store_true",
        help="Use STDIO transport for a local coding harness",
    )
    transport.add_argument("--sse", action="store_true", help="Use SSE transport")
    args = parser.parse_args()

    host = os.getenv("MCP_HOST", "127.0.0.1")
    port = int(os.getenv("MCP_PORT", "8021"))

    if args.stdio:
        mcp.run(transport="stdio", show_banner=False)
    elif args.sse:
        print(f"\nStarting SSE server on http://{host}:{port}/sse")
        mcp.run(transport="sse", host=host, port=port)
    else:
        print(f"\nStarting HTTP server on http://{host}:{port}/mcp")
        mcp.run(transport="http", host=host, port=port)


if __name__ == "__main__":
    main()
