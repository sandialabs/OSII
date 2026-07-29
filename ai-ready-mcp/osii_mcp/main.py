import argparse
import os
from pathlib import Path

from fastmcp import FastMCP
from fastmcp.server.auth.providers.jwt import StaticTokenVerifier

from osii_mcp import core

ABOUT_PATH = Path(__file__).resolve().parent / "About.md"

DEBUG = os.getenv("DEBUG", "false").lower() == "true"


def _build_auth() -> StaticTokenVerifier | None:
    if DEBUG:
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


mcp = FastMCP("osii-mcp", auth=_build_auth())


def _load_about() -> str:
    try:
        return ABOUT_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        return "About.md was not found."


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
def get_object_text_span_context(file_id: str, char_start: int, char_end: int, context_chars: int = 200) -> dict:
    return core.get_object_text_span_context(file_id, char_start, char_end, context_chars)


@mcp.tool
def search_scope(query: str, scope: dict, mode: str = "hybrid", top_k: int = 10, group_by: str | None = "file") -> dict:
    return core.search_scope(query, scope, mode=mode, top_k=top_k, group_by=group_by)


@mcp.prompt
def about() -> str:
    return _load_about()


def main() -> None:
    parser = argparse.ArgumentParser(description="Start OSII MCP Server")
    parser.add_argument("--stdio", action="store_true", help="Use STDIO transport")
    parser.add_argument("--sse", action="store_true", help="Use SSE transport")
    args = parser.parse_args()

    host = os.getenv("MCP_HOST", "127.0.0.1")
    port = int(os.getenv("MCP_PORT", "8021"))

    if args.stdio:
        print("\nStarting STDIO server...")
        mcp.run()
    elif args.sse:
        print(f"\nStarting SSE server on http://{host}:{port}/sse")
        mcp.run(transport="sse", host=host, port=port)
    else:
        print(f"\nStarting HTTP server on http://{host}:{port}/mcp")
        mcp.run(transport="http", host=host, port=port)


if __name__ == "__main__":
    main()
