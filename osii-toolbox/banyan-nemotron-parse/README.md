# Banyan Nemotron Parse

An optional model-backed OSII extractor for PDFs and images. Banyan renders
document pages, sends them to a configured Nemotron Parse deployment, and
returns text with page and element bounding-box provenance through Processor
API v1. Its processor ID is `banyan.nemotron-parse`.

Banyan source and its API adapter live in the adjacent
[`banyan-ingest`](../banyan-ingest/README.md) Git subtree. This directory owns
the isolated OSII host environment; its dependencies stay outside the root
workspace and lock.

## Configure and start

Banyan source is included in a normal OSII clone.

Copy [`banyan-ingest/.env.example`](../banyan-ingest/.env.example) to
`banyan-ingest/.env` in that same directory. Set `NEMOPARSE_ENDPOINT` to your
corporate deployment's OpenAI-compatible base URL, `NEMOPARSE_MODEL` to its
served model identifier, and `NEMOPARSE_API_KEY` if required. The example has
no endpoint or credentials. Environment variables override the file.

`make dev` (Windows: `.\scripts\osii.ps1 dev`) prepares this environment and
starts the service on port 8101. `OSII_BANYAN_PORT` changes the port;
`OSII_START_TOOLBOX=false` leaves Toolbox services stopped with manual controls
available in Setup. Health and descriptor discovery work before endpoint access
is available. Starting the service does not invoke a model.

In Setup, explicitly choose **Banyan Nemotron Parse Extractor** for the desired
PDF/image extraction route, then test one document after endpoint access is
ready. The baseline native extractor stays selected until you change the route.
Nemotron credentials stay in Banyan's environment, separate from OSII's chat
connection. Extraction sends document page images to the configured endpoint.

For an independent service, from this directory on macOS, Linux, or Windows:

```sh
uv run --python 3.12 python -m uvicorn banyan_extract.integrations.osii_extractor:app --host 127.0.0.1 --port 8101
```

See [API, provenance, configuration, and offline tests](../banyan-ingest/docs/osii-compatibility.md).
The current adapter accepts PDF, PNG, JPEG, and TIFF; Banyan's standalone PPTX
and LibreOffice workflows are not exposed through this API yet.

The Banyan subtree retains its upstream revision in Git history. OSII-local
checkouts need no separate repository credentials to use this tool.
