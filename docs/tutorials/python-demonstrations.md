# Python demo notebooks

The optional `osii-demo-notebooks` branch contains the Python/Jupyter walkthrough.
It is a separate download with its own environment; the OSII application is not
included in that branch.

```bash
git clone --single-branch --branch osii-demo-notebooks git@github.com:heidikmkv/osii-private.git osii-demo-notebooks
```

Follow that download's README to install its dependencies, choose a Jupyter
kernel, and run the numbered lessons. They cover sidecars, extraction,
collections, search, embeddings, and custom processors.

For an agent connection, download the `osii-mcp` branch instead. Its README
explains how to connect the tool to a processed local sidecar library.

The [single-file tutorial](single-file.md) uses the CLI included in the normal
OSII application download.
