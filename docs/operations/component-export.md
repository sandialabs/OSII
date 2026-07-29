# Export components for separate repositories

Use the cross-platform export script when transferring OSII to an environment
where its components will become separate repositories. It copies source and
the relevant interface documentation into new directory trees; it does not
change the monorepo, initialize Git repositories, or copy generated data.

Preview the default export:

```bash
python scripts/export_components.py --output ../osii-component-export --dry-run
```

Create all exports:

```bash
python scripts/export_components.py --output ../osii-component-export
```

Export only selected components:

```bash
python scripts/export_components.py --output ../osii-component-export --components backend,frontend,mcp
```

The output contains `backend`, `frontend`, `mcp`, `chat`, `tools`, and
`notebooks` directories plus `EXPORT_MANIFEST.json`. The backend Dockerfile is
adapted to use its exported directory as its build context. The MCP export is
prepared to install `osii` from the receiving environment's package registry.

The manifest records the important handoff dependency: publish the OSII backend
package internally before packaging the MCP server, and publish the processor
SDK before packaging custom processor services. Configure the frontend with the
URL of the deployed backend before releasing it.
