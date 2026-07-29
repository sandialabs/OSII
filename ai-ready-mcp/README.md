# osii-mcp

`osii-mcp` is an HTTP MCP server that provides smart traversal of an OSII store using the installed `osii` Python package.

It is intended for:
- scope discovery
- object inspection
- preferred text access
- grounded text span inspection
- collection traversal
- search over scopes

It is not intended to replace the OSII backend itself. Instead, it exposes a traversal-oriented tool surface for MCP clients.

## What this MCP does

This MCP server exposes tools that let an LLM or client:

- inspect the root scope
- list folder scopes
- list collection scopes
- describe a scope
- retrieve scope summaries
- retrieve scope artifact summaries
- inspect objects
- inspect preferred text
- inspect grounded text context
- search within a scope

## Install

```powershell
pip install uv
uv sync --extra dev
```

## Run

```powershell
$env:OSII_ROOT="C:\path\to\.osii"
$env:MCP_HOST="127.0.0.1"
$env:MCP_PORT="8021"
$env:ATLAS_MCP_TOKEN="replace-me"
uv run osii-mcp
```

Default HTTP MCP endpoint:
```text
http://127.0.0.1:8021/mcp
```

## Notes

This repo expects the `osii` package to be importable in the active environment.

## Screenshot

Replace the image below with a real screenshot from your MCP client.

![Screenshot of the MCP server working](docs/screenshot.png)