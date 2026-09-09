# About this MCP server

This MCP server provides smart traversal of an OSII store through the installed `osii` Python package.

## What this server does

This server exposes tools that let a client or LLM:

- inspect the root of an OSII store
- list folder and collection scopes
- describe scope membership
- retrieve lightweight object summaries
- inspect full object aggregates
- retrieve preferred text
- inspect grounded text span context
- list enrichments
- search within a scope

## When to use it

Use this MCP when you want to explore an OSII store programmatically and navigate its scopes, objects, text, and search results without going through the browser dashboard.

## Notes for the LLM

- Prefer scope-level traversal before drilling into individual objects.
- Use search when you need evidence for a specific topic.
- Use preferred text and grounded text span context for detailed inspection.
- Object, scope, and search tools are grounded in the installed `osii` package, not in guessed filesystem traversal.